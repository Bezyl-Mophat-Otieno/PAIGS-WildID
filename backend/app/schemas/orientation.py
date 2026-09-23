from typing import Optional

from pydantic import BaseModel


class OrientationResult(BaseModel):
    orientation: str  # "as_is" | "reverse_read_reverse_complemented" | "no_overlap_found"
    alignment_score: Optional[float] = None
    overlap_length: Optional[int] = None
    identity: Optional[float] = None
    label_orientation_mismatch: Optional[bool] = None
