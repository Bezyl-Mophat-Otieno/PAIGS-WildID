from typing import Optional

from pydantic import BaseModel


class FileFormatCheck(BaseModel):
    """Stage 1 output for a single file: is it a structurally valid AB1 file."""

    filename: str
    valid: bool
    reason: Optional[str] = None
