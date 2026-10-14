from datetime import datetime
from typing import List, Optional

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
    # "local" or "remote" -- the report/audit-trail differentiator the
    # remote-vs-local BLAST decision requires (see
    # claude/remote-blast-search.md). Defaults to "local" so every
    # pre-existing caller/fixture that builds a BlastSearchResult without
    # naming a mode keeps meaning what it always meant.
    search_mode: str = "local"

    # Remote-mode-only evidence, all None for a local-mode result. Local
    # search's audit trail is its pinned database_version (reproducible by
    # construction); remote search has no equivalent pinned version, so
    # instead it records exactly what NCBI returned and exactly when --
    # the raw response text stands in for reproducibility that isn't
    # otherwise possible once NCBI's own database has since moved on.
    remote_database: Optional[str] = None
    entrez_query: Optional[str] = None
    queried_at: Optional[datetime] = None
    raw_response: Optional[str] = None

    # "http" (the primary transport -- app.pipeline.ncbi_remote talking to
    # NCBI's Blast.cgi directly) or "subprocess_fallback" (the older
    # blastn -remote subprocess path, used only when HTTP submission
    # itself couldn't be completed -- see
    # app.orchestration.execute._fallback_to_subprocess_search). None for
    # local-mode results, and for any remote result recorded before this
    # field existed. Surfaced so a report can show plainly when a run had
    # to degrade to the fallback, rather than burying it in raw_response.
    remote_transport: Optional[str] = None
