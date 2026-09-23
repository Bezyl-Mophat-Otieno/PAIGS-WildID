from typing import Dict

from pydantic import BaseModel


class TrimResult(BaseModel):
    trimmed_sequence: str
    trimmed_length: int
    trim_start: int  # 0-indexed, inclusive, into the raw sequence
    trim_end: int  # 0-indexed, exclusive
    trim_params: Dict[str, int]
