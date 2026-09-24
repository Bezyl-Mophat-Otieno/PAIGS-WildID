from typing import Optional

from pydantic import BaseModel


class UsabilityCheckResult(BaseModel):
    final_length: int
    mean_quality: float
    ambiguous_positions: int
    status: str  # "PASS" or "FAIL"
    reason: Optional[str] = None
