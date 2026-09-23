"""
Stage 2 -- AB1 extraction.

For each file that passed Stage 1 (Format Validity Check), parses the raw
sequence and per-base Phred quality scores out of the binary AB1
structure. Pure extraction, no judgment applied -- that starts at Stage 3
(Coarse Sanity Check).

Not responsible for handling invalid files: orchestration only calls this
on files that already passed Stage 1, so a parse failure here is allowed
to raise rather than being caught and translated (unlike Stage 1, whose
whole job is exactly that translation).
"""
from pathlib import Path
from typing import Dict, Union

from Bio import SeqIO

from app.schemas.ab1_extraction import ReadExtraction

PathLike = Union[str, Path]


def extract_read(file_path: PathLike) -> ReadExtraction:
    """Parse a single AB1 file's raw sequence and per-base Phred quality scores."""
    with open(file_path, "rb") as fh:
        record = SeqIO.read(fh, "abi")

    raw_sequence = str(record.seq)
    quality_scores = list(record.letter_annotations["phred_quality"])

    return ReadExtraction(
        raw_sequence=raw_sequence,
        raw_length=len(raw_sequence),
        quality_scores=quality_scores,
    )


def extract_reads_for_files(paths: Dict[str, PathLike]) -> Dict[str, ReadExtraction]:
    """
    Stage-level entry point: run extract_read for whichever slots
    ("forward", "reverse", or both) were provided for this run.
    """
    return {slot: extract_read(path) for slot, path in paths.items()}
