"""Stage 8 -- FASTA generation.

A pure format-conversion step: the sequence that passed Stage 7's
usability check is written out as FASTA, the standard text format
nearly every downstream bioinformatics tool -- including Stage 9's
BLAST search -- expects as input. Per CLAUDE.md's own example, the
FASTA header is the sample ID (e.g. `>WILD_001`), not a database
primary key.

Tool: Biopython's Bio.SeqIO, used here for writing (it's been used for
reading since Stage 1/2's AB1 extraction).
"""
import io
from pathlib import Path

from Bio.Seq import Seq
from Bio.SeqIO import write as seqio_write
from Bio.SeqRecord import SeqRecord

from app.schemas.fasta import FastaResult


def generate_fasta(sample_id: str, sequence: str) -> FastaResult:
    if not sequence:
        raise ValueError("Cannot generate a FASTA record from an empty sequence.")

    record = SeqRecord(Seq(sequence), id=sample_id, description="")
    buffer = io.StringIO()
    seqio_write([record], buffer, "fasta")

    return FastaResult(
        sequence_id=sample_id,
        sequence_length=len(sequence),
        fasta_content=buffer.getvalue(),
    )


def write_fasta_file(fasta_result: FastaResult, dest_path: Path) -> Path:
    """
    Materialize generate_fasta()'s in-memory content to a real file --
    the Stage 8 -> Stage 9 handoff named in
    claude/stage-8-9-status.md's Known follow-ups. Stage 9's
    search_blast() needs a file path, not a Python string (blastn is a
    subprocess, it reads files), so this is what a future orchestration
    layer will call between the two stages.

    Deliberately storage-location-agnostic, matching every other
    pipeline module (none of them import app.storage or know about
    Run ids) -- the caller decides where the file lives. For a real Run,
    that will be alongside its other files, e.g.
    app.storage.run_dir(run_id) / "query.fasta".
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(fasta_result.fasta_content)
    return dest_path
