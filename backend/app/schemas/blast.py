from typing import List

from pydantic import BaseModel


class BlastHit(BaseModel):
    rank: int
    species: str
    identity: float  # percent identity, e.g. 99.71
    coverage: float  # percent of the query length aligned
    evalue: float
    bit_score: float
    accession: str


class BlastSearchResult(BaseModel):
    hits: List[BlastHit]
    database_version: str
    query_length: int
