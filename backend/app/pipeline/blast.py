"""Stage 9 -- BLAST comparison.

The FASTA sequence from Stage 8 is searched against a curated reference
database of known species sequences via BLAST+ -- a separate compiled
program, not a Python package, invoked here as a subprocess (per
CLAUDE.md's explicit note that "the server/Docker image needs the
BLAST+ binary baked in, not just listed in requirements.txt").

Reference database: per CLAUDE.md, built ahead of time from a curated
FASTA of known species by domain experts (species/taxonomy, sequence,
accession, source, database version) -- never guessed or fabricated by
engineering. `build_reference_database` just wraps `makeblastdb` to
index whatever curated FASTA the domain experts hand over; the tests
for this module use a small, clearly-synthetic placeholder FASTA
(tests/fixtures/synthetic_blast_reference.fasta -- obviously-fake
"SYNTH"-prefixed accessions, real species names attached to made-up
sequences) purely to prove the plumbing works end-to-end. It is not,
and must never be mistaken for, real curated reference data -- see
claude/stage-8-9-status.md for the full rationale.

Binary discovery (`_find_blast_binary`): checks the `BLAST_BIN_DIR` env
var first (an explicit override for whatever install layout a given
deployment uses), then PATH (`shutil.which`, where a normal `apt-get
install ncbi-blast+` in the Dockerfile puts it), then falls back to
`~/ncbi-blast+/bin` -- the documented local dev install location for
sandboxed environments where BLAST+ was extracted without root access
(see claude/stage-8-9-status.md).

If a `lib/` directory sits next to the resolved binary's own `bin/`
directory, it's prepended to LD_LIBRARY_PATH for the subprocess call --
harmless (and unused) for a normal system install where BLAST's shared
libraries are already registered with the system linker, but required
for the extracted-without-root dev layout, where they aren't on the
default linker search path.

Remote search (`search_blast_remote`): the same `blastn` binary, given
`-remote` instead of a local `-db <prefix>`, submits the query to NCBI's
own hosted databases over the network instead of a locally-built index --
the "remote" half of the remote-vs-local BLAST search decision (see
claude/remote-blast-search.md / CLAUDE.md's Stage 9 section). No
`makeblastdb` step, no local index -- but a real network round trip to
NCBI, so it needs its own timeout (`blast.remote_timeout_seconds`) and its
own error type (`RemoteBlastSearchError`) distinct from a local search's
"binary/database not found" failures. Its result is marked
`search_mode="remote"` and carries the exact raw response text plus the
moment it was queried, since (unlike a local search's pinned reference DB
version) NCBI's own database changes over time and the same query run
again later isn't guaranteed to reproduce -- that raw response is the
audit trail's substitute for reproducibility.
"""
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from Bio import SeqIO

from app.schemas.blast import BlastHit, BlastSearchResult

DEFAULT_MAX_HITS = 10
# A real NCBI remote search against a large database (nt especially --
# blast.remote_database's own broadest, slowest option) commonly takes
# several minutes under normal NCBI server load, not seconds -- 120s
# turned out to be too short in practice (a real search against nt timed
# out at exactly that default). 300s is still a guess pending real
# operational experience, not a number NCBI documents as a guarantee --
# revisit once actual observed remote search times are in hand.
DEFAULT_REMOTE_TIMEOUT_SECONDS = 300


class RemoteBlastSearchError(RuntimeError):
    """An operational failure of a remote BLAST search -- a network/NCBI-side
    error, or the request exceeding blast.remote_timeout_seconds. Distinct
    from a query that legitimately found no hits, which is a normal, empty
    BlastSearchResult, not an error."""


def _find_blast_binary(name: str) -> str:
    env_dir = os.environ.get("BLAST_BIN_DIR")
    if env_dir:
        candidate = Path(env_dir) / name
        if candidate.is_file():
            return str(candidate)
        raise RuntimeError(
            f"BLAST_BIN_DIR is set to {env_dir!r}, but no {name!r} binary was found there."
        )

    on_path = shutil.which(name)
    if on_path:
        return on_path

    fallback = Path.home() / "ncbi-blast+" / "bin" / name
    if fallback.is_file():
        return str(fallback)

    raise RuntimeError(
        f"Could not locate the BLAST+ binary {name!r}. Install BLAST+ (e.g. via "
        f"`apt-get install ncbi-blast+` in the deployment image), make sure it's "
        f"on PATH, or set the BLAST_BIN_DIR environment variable to the directory "
        f"containing its binaries."
    )


def _subprocess_env(binary_path: str) -> dict:
    env = os.environ.copy()
    sibling_lib_dir = Path(binary_path).resolve().parent.parent / "lib"
    if sibling_lib_dir.is_dir():
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = (
            f"{sibling_lib_dir}:{existing}" if existing else str(sibling_lib_dir)
        )
    return env


def build_reference_database(reference_fasta: Path, output_prefix: Path, *, title: str) -> None:
    """Index a curated reference FASTA into a searchable BLAST database via
    `makeblastdb`. Run once (or whenever the curated FASTA changes), not
    per-search.
    """
    binary = _find_blast_binary("makeblastdb")
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            binary,
            "-in", str(reference_fasta),
            "-dbtype", "nucl",
            "-out", str(output_prefix),
            "-title", title,
        ],
        capture_output=True,
        text=True,
        env=_subprocess_env(binary),
    )
    if result.returncode != 0:
        raise RuntimeError(f"makeblastdb failed: {result.stderr.strip()}")


def _query_length(query_fasta: Path) -> int:
    query_records = list(SeqIO.parse(str(query_fasta), "fasta"))
    if not query_records:
        raise ValueError(f"No sequences found in query FASTA: {query_fasta}")
    return len(query_records[0].seq)


def _parse_hits(stdout: str, query_length: int) -> List[BlastHit]:
    """Shared by the local and remote search paths -- blastn's `-outfmt 6`
    tabular output means the exact same line shape either way; only how
    blastn was invoked (and what gets recorded as evidence afterward)
    differs between them."""
    hits: List[BlastHit] = []
    for rank, line in enumerate(
        (ln for ln in stdout.splitlines() if ln.strip()), start=1
    ):
        sseqid, pident, length, evalue, bitscore, stitle = line.split("\t", 5)
        species = (
            stitle[len(sseqid):].strip() if stitle.startswith(sseqid) else stitle.strip()
        )
        hits.append(
            BlastHit(
                rank=rank,
                species=species,
                identity=float(pident),
                coverage=(float(length) / query_length * 100) if query_length else 0.0,
                evalue=float(evalue),
                bit_score=float(bitscore),
                accession=sseqid,
            )
        )
    return hits


def search_blast(
    query_fasta: Path,
    db_prefix: Path,
    *,
    database_version: str,
    max_hits: int = DEFAULT_MAX_HITS,
) -> BlastSearchResult:
    """Search `query_fasta` (Stage 8's output, expected to hold exactly one
    sequence) against an already-built local BLAST database, returning a
    ranked hit list. `database_version` is caller-supplied metadata --
    CLAUDE.md requires the reference DB version used to be recorded per
    run, and that's tracked alongside the curated FASTA itself, not
    something blastn reports.
    """
    query_length = _query_length(query_fasta)

    binary = _find_blast_binary("blastn")
    result = subprocess.run(
        [
            binary,
            "-query", str(query_fasta),
            "-db", str(db_prefix),
            "-outfmt", "6 sseqid pident length evalue bitscore stitle",
            "-max_target_seqs", str(max_hits),
        ],
        capture_output=True,
        text=True,
        env=_subprocess_env(binary),
    )
    if result.returncode != 0:
        raise RuntimeError(f"blastn failed: {result.stderr.strip()}")

    return BlastSearchResult(
        hits=_parse_hits(result.stdout, query_length),
        database_version=database_version,
        query_length=query_length,
        search_mode="local",
    )


def search_blast_remote(
    query_fasta: Path,
    *,
    remote_database: str,
    entrez_query: str = "",
    max_hits: int = DEFAULT_MAX_HITS,
    timeout_seconds: int = DEFAULT_REMOTE_TIMEOUT_SECONDS,
) -> BlastSearchResult:
    """Search `query_fasta` against one of NCBI's own hosted nucleotide
    databases (`nt`, `core_nt`, `refseq_rna`, `refseq_genomic`) via
    `blastn -remote` -- no local index, a real network round trip to NCBI
    instead. `entrez_query`, if given, narrows/widens the search scope at
    NCBI's end (e.g. excluding environmental/uncultured entries, or
    restricting to a taxonomic group) rather than filtering the results
    afterward.

    Raises RemoteBlastSearchError on a network/NCBI-side failure or a
    timeout -- an operational stop, same treatment as
    NoActiveReferenceDatabaseError on the local path (see
    app.orchestration.execute's Stage 9 handling).
    """
    query_length = _query_length(query_fasta)

    binary = _find_blast_binary("blastn")
    command = [
        binary,
        "-query", str(query_fasta),
        "-db", remote_database,
        "-remote",
        "-outfmt", "6 sseqid pident length evalue bitscore stitle",
        "-max_target_seqs", str(max_hits),
    ]
    if entrez_query:
        command.extend(["-entrez_query", entrez_query])

    queried_at = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=_subprocess_env(binary),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RemoteBlastSearchError(
            f"Remote BLAST search against NCBI's {remote_database!r} database "
            f"timed out after {timeout_seconds}s."
        ) from exc

    if result.returncode != 0:
        raise RemoteBlastSearchError(
            f"Remote BLAST search against NCBI's {remote_database!r} database "
            f"failed: {result.stderr.strip()}"
        )

    return BlastSearchResult(
        hits=_parse_hits(result.stdout, query_length),
        database_version=f"NCBI {remote_database} (remote, live -- not version-pinned)",
        query_length=query_length,
        search_mode="remote",
        remote_database=remote_database,
        entrez_query=entrez_query or None,
        queried_at=queried_at,
        raw_response=result.stdout,
    )
