"""Raw AB1 chromatogram/peak data -- backs GET /runs/{id}/chromatogram/{slot}.

Item 6 of the user's punch list: "Add an endpoint to expose the raw AB1
chromatogram/peak data ... Needed so an analyst can visually
double-check a flagged or low-confidence base call instead of just
trusting a number." Already anticipated in docs/PLAN.md's own
"Chromatogram viewer" future-frontend note, which names the exact raw
ABIF tags to read: DATA9-DATA12 (the four fluorescence channels) and
PLOC2 (per-base peak locations), both under Biopython's
`record.annotations["abif_raw"]` -- the same raw-tag escape hatch
app.pipeline.ab1_extraction's own module docstring already mentions is
available but doesn't use, since Stage 2 only needs the base-called
sequence and quality, not the trace itself.

Channel ordering is read from the file's own FWO_1 tag ("field order"),
never hard-coded as G/A/T/C -- ABIF's spec allows it to vary file to
file, and assuming a fixed order would silently mis-label channels on
a file that orders them differently.

Pure extraction, same spirit as app.pipeline.ab1_extraction.extract_read:
no judgment applied, just reshaping what's already in the file into a
JSON-friendly shape. A parse failure here is allowed to raise, same
reasoning as Stage 2 -- the API layer only calls this on a file it
already knows exists and was accepted at Stage 1.
"""
from pathlib import Path
from typing import Union

from Bio import SeqIO

from app.schemas.chromatogram import ChromatogramResult

PathLike = Union[str, Path]

# ABIF's four fluorescence-channel data tags, always in this fixed slot
# order -- FWO_1 says which base each one holds for this particular
# file, not which tag holds which channel.
_CHANNEL_TAGS = ("DATA9", "DATA10", "DATA11", "DATA12")


def extract_chromatogram(file_path: PathLike) -> ChromatogramResult:
    with open(file_path, "rb") as fh:
        record = SeqIO.read(fh, "abi")

    raw = record.annotations["abif_raw"]

    # FWO_1 is raw bytes, e.g. b"GATC" -- decode to the base letters in
    # the same order DATA9/10/11/12 are given.
    channel_order = [chr(b) for b in raw["FWO_1"]]
    trace = {base: list(raw[tag]) for base, tag in zip(channel_order, _CHANNEL_TAGS)}
    num_samples = len(next(iter(trace.values()))) if trace else 0

    return ChromatogramResult(
        channel_order=channel_order,
        trace=trace,
        num_samples=num_samples,
        peak_locations=list(raw["PLOC2"]),
        base_calls=str(record.seq),
    )
