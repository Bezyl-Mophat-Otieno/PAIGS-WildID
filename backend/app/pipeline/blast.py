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
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import List

from Bio import SeqIO

from app.schemas.blast import BlastHit, BlastSearchResult

DEFAULT_MAX_HITS = 10


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


def search_blast(
    query_fasta: Path,
    db_prefix: Path,
    *,
    database_version: str,
    max_hits: int = DEFAULT_MAX_HITS,
) -> BlastSearchResult:
    """Search `query_fasta` (Stage 8's output, expected to hold exactly one
    sequence) against an already-built BLAST database, returning a ranked
    hit list. `database_version` is caller-supplied metadata -- CLAUDE.md
    requires the reference DB version used to be recorded per run, and
    that's tracked alongside the curated FASTA itself, not something
    blastn reports.
    """
    query_records = list(SeqIO.parse(str(query_fasta), "fasta"))
    if not query_records:
        raise ValueError(f"No sequences found in query FASTA: {query_fasta}")
    query_length = len(query_records[0].seq)

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

    hits: List[BlastHit] = []
    for rank, line in enumerate(
        (ln for ln in result.stdout.splitlines() if ln.strip()), start=1
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

    return BlastSearchResult(
        hits=hits,
        database_version=database_version,
        query_length=query_length,
    )
