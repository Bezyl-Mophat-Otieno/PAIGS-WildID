from typing import List

from pydantic import BaseModel


class ConsensusResult(BaseModel):
    consensus_sequence: str
    consensus_length: int
    ambiguous_positions: List[int]
    quality_scores: List[int]
