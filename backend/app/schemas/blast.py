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
    # "local" (the only mode actually implemented today) or "remote" --
    # the report/audit-trail differentiator the remote-vs-local BLAST
    # decision requires (see claude/remote-blast-search.md). Defaults to
    # "local" so every pre-existing caller/fixture that builds a
    # BlastSearchResult without naming a mode keeps meaning what it
    # always meant.
    search_mode: str = "local"
