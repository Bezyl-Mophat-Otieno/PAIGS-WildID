from typing import Optional

from pydantic import BaseModel


class SanityCheckResult(BaseModel):
    n_proportion: float
    raw_length: int
    status: str  # "PASS" or "FAIL"
    reason: Optional[str] = None
