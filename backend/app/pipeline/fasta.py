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
