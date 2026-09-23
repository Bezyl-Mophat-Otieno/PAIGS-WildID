"""
Stage 1 -- Format Validity Check.

A hard stop, deliberately the very first check -- before anything about
read quality is considered. Is each uploaded file a structurally valid AB1
file at all: can it be opened and parsed, is it not corrupted. This is a
yes/no question about file integrity, unrelated to how good the DNA read
itself is (that judgment starts at Stage 3, Coarse Sanity Check).

Per CLAUDE.md: "attempting the parse itself is the check; a parse failure
is the fail condition."
"""
from pathlib import Path
from typing import Dict, Union

from Bio import SeqIO

from app.schemas.format_check import FileFormatCheck

PathLike = Union[str, Path]


def check_format(file_path: PathLike) -> FileFormatCheck:
    """Attempt to parse a single file as an AB1 file. The parse attempt is the check."""
    path = Path(file_path)
    filename = path.name

    try:
        with open(path, "rb") as fh:
            SeqIO.read(fh, "abi")
    except Exception as exc:  # noqa: BLE001 -- intentionally broad: any parse failure is a fail
        return FileFormatCheck(filename=filename, valid=False, reason=_plain_language_reason(exc))

    return FileFormatCheck(filename=filename, valid=True)


def check_format_for_files(paths: Dict[str, PathLike]) -> Dict[str, FileFormatCheck]:
    """
    Stage-level entry point: run check_format for whichever slots
    ("forward", "reverse", or both -- matching Stage 0's upload slots) were
    provided for this run.
    """
    return {slot: check_format(path) for slot, path in paths.items()}


def _plain_language_reason(exc: Exception) -> str:
    """Translate a low-level parse exception into a specific, plain-language message."""
    message = str(exc)

    if isinstance(exc, FileNotFoundError) or "No such file" in message:
        return "The file could not be found or read."
    if "Empty file" in message:
        return "The file is empty."
    if "should start with ABIF" in message:
        return "This doesn't look like an AB1 file -- it's missing the AB1 file header."
    # Anything else (e.g. a truncated/corrupted file failing partway through
    # the binary structure) is a genuine structural problem, just not one
    # with a friendlier message available from the parser itself.
    return "This file could not be read as a valid AB1 file -- its structure appears corrupted or incomplete."
