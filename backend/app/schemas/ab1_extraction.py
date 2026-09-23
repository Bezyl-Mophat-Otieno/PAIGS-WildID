from typing import List

from pydantic import BaseModel


class ReadExtraction(BaseModel):
    """Stage 2 output for a single file: raw sequence + per-base Phred quality."""

    raw_sequence: str
    raw_length: int
    quality_scores: List[int]
