"""Fetching candidate reference records from BOLD Systems (Barcode of Life
Data System, boldsystems.org) -- the automatable half of the "leverage
BOLD" decision (see claude/bold-reference-fetch.md). This module only
ever produces a *draft*: a reformatted candidate FASTA plus a review
summary, never something a Run's Stage 9 can search against directly.
Going live is a separate, deliberate action (see app.reference.drafts) --
CLAUDE.md is explicit that the reference set is a domain-expert judgment
call, not something engineering auto-activates, and this module's own
automated filtering below is deliberately only the mechanical slice of
that judgment (a machine-checkable proxy for it), not a replacement.

The real, current BOLD Portal API (verified live against
portal.boldsystems.org while building this -- the older "API_Public"
REST API widely cited in older literature and even in earlier drafts of
our own guidance no longer exists; boldsystems.org's own /data/api/ page
documents this one instead):

    GET /api/query/preprocessor?query=<query>   -- validates the query
    GET /api/query?query=<query>&extent=full    -- returns a query_id token
    GET /api/summary?query=<query>&fields=...   -- optional aggregate counts
    GET /api/documents/<query_id>/download?format=json
        -- the actual records, streamed as newline-delimited JSON (NOT a
           JSON array), following BOLD's own BCDM (Barcode Core Data
           Model) field names.

Query syntax: "<scope>:<value>" or "<scope>:<field>:<value>", e.g.
"tax:Panthera" or "tax:genus:Panthera" -- the unscoped form is used here
deliberately (see fetch_bold_taxon's own docstring) so a caller doesn't
need to already know what taxonomic rank their input is.
"""
import json
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

import httpx

BOLD_API_BASE = "https://portal.boldsystems.org/api"
DEFAULT_MARKER = "COI-5P"
DEFAULT_MAX_RECORDS_PER_SPECIES = 5
DEFAULT_MIN_SEQUENCE_LENGTH = 200
DEFAULT_MAX_N_PROPORTION = 0.05
DEFAULT_TIMEOUT_SECONDS = 60.0
# "required" (default) drops anything not confirmed to species level, per
# CLAUDE.md's own insistence that the reference set's trustworthiness is
# the one thing that shouldn't be silently automated away.
# "allow_lower_rank" is a deliberate, visible risk trade: a record only
# identified to genus/family still gets included (grouped and FASTA-
# labeled under whatever rank BOLD's own `identification` field gives),
# because a lower-rank name isn't a trustworthy species-level answer-key
# entry -- every such record is counted separately in the fetch result
# and must show as a clearly distinct warning in review, never blended
# into the same rows as real species-level entries.
DEFAULT_REQUIRE_SPECIES_LEVEL = "required"
# Both count as a trustworthy species-level identification -- "subspecies"
# is strictly *more* precise than "species", not less, discovered live
# while building this: a real subspecies-ranked BOLD record (e.g.
# "Manis pentadactyla pentadactyla") already carries a clean species
# binomial in its own `species` field ("Manis pentadactyla"); only its
# `identification` field (used as the *fallback* name for a genuinely
# lower rank, see fetch_bold_taxon) carries the extra subspecies epithet.
# Treating "subspecies" as untrustworthy would have wrongly forced every
# subspecies-confirmed record through require_species_level's stricter
# gate for no real reason.
TRUSTWORTHY_RANKS = {"species", "subspecies"}


class BoldApiError(RuntimeError):
    """An operational failure talking to BOLD -- network/HTTP error, or a
    taxon BOLD's own preprocessor rejects as unrecognized. Not raised for
    "zero matching records" (see BoldFetchResult.kept -- an empty result
    is a normal, reportable outcome, not an error)."""


@dataclass
class BoldSpeciesSummary:
    species: str
    kept_count: int
    dropped_count: int
    bins: List[str] = field(default_factory=list)
    # "species" for a real species-level entry; "genus"/"family"/etc. only
    # when require_species_level="allow_lower_rank" let a lower-confidence
    # identification through -- the reviewer must be able to tell these
    # apart from a glance at this same table, not just from the summary's
    # separate warning count.
    identification_rank: str = "species"

    @property
    def bin_consistent(self) -> bool:
        """True if every kept record for this species shares the same
        BIN (BOLD's own DNA-cluster-based proxy for a species boundary)
        -- a split across multiple BINs is exactly the kind of thing the
        domain-expert reviewer should look at before approving, not
        something this module decides on its own."""
        return len(set(self.bins)) <= 1


@dataclass
class BoldFetchResult:
    taxon: str
    marker: str
    fasta_content: str  # already in app.reference.publish's expected >ACCESSION Species | taxonomy shape
    species: List[BoldSpeciesSummary]
    total_fetched: int
    total_kept: int
    drop_reasons: Dict[str, int]  # reason -> count, e.g. "not identified to species level": 12
    species_sharing_a_bin: List[List[str]]  # groups of >1 species name sharing one BIN -- a stronger flag
    # Count of kept records whose identification_rank isn't "species" --
    # only ever nonzero when require_species_level="allow_lower_rank" was
    # explicitly chosen. Tracked separately (not just derivable from
    # `species`) so a reviewer/UI can raise a loud, dedicated warning
    # rather than one that's easy to miss among per-species rows.
    total_kept_at_lower_rank: int = 0


def _preprocess_query(client: httpx.Client, query: str) -> str:
    """Validates `query` against BOLD's own controlled taxonomic
    vocabulary AND resolves it into the fully-qualified "scope:field:value"
    triplet form /api/query actually requires -- verified live against
    the real API while building this: an unscoped "tax:Panthera" is
    accepted *here* and resolved to "tax:genus:Panthera", but passing the
    original unscoped string straight to /api/query fails with a plain
    HTTP 400 ("Invalid triplet token"). The resolved form is what must be
    carried forward, never the caller's original input.
    """
    resp = client.get(f"{BOLD_API_BASE}/query/preprocessor", params={"query": query})
    if resp.status_code != 200:
        raise BoldApiError(f"BOLD rejected the query {query!r}: HTTP {resp.status_code}.")
    data = resp.json()
    successful_terms = data.get("successful_terms")
    if not successful_terms:
        raise BoldApiError(
            f"BOLD didn't recognize {query!r} as a valid taxonomic term -- check the spelling "
            f"(this checks against BOLD's own controlled taxonomy vocabulary)."
        )
    return ";".join(term["matched"] for term in successful_terms)


def _submit_query(client: httpx.Client, query: str) -> str:
    resp = client.get(f"{BOLD_API_BASE}/query", params={"query": query, "extent": "full"})
    if resp.status_code != 200:
        raise BoldApiError(f"BOLD's query endpoint failed: HTTP {resp.status_code}.")
    query_id = resp.json().get("query_id")
    if not query_id:
        raise BoldApiError("BOLD's query endpoint didn't return a query_id.")
    return query_id


def _iter_documents(client: httpx.Client, query_id: str) -> Iterator[dict]:
    """BOLD streams matching records as newline-delimited JSON (one
    document per line), not a JSON array -- parsed here line by line so
    this works the same whether BOLD sends a handful of records or the
    documented maximum of a million."""
    url = f"{BOLD_API_BASE}/documents/{query_id}/download"
    with client.stream("GET", url, params={"format": "json"}) as resp:
        if resp.status_code != 200:
            raise BoldApiError(f"BOLD's document download failed: HTTP {resp.status_code}.")
        for line in resp.iter_lines():
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _taxonomy_string(record: dict) -> str:
    ranks = ("kingdom", "phylum", "class", "order", "family", "genus", "species")
    return ";".join(str(record[r]) for r in ranks if record.get(r))


def _looks_like_valid_sequence(
    nuc: Optional[str], *, min_length: int, max_n_proportion: float
) -> bool:
    if not nuc:
        return False
    nuc = nuc.strip()
    if len(nuc) < min_length:
        return False
    n_count = nuc.upper().count("N")
    return (n_count / len(nuc)) <= max_n_proportion


def fetch_bold_taxon(
    taxon: str,
    *,
    marker: str = DEFAULT_MARKER,
    max_records_per_species: int = DEFAULT_MAX_RECORDS_PER_SPECIES,
    min_sequence_length: int = DEFAULT_MIN_SEQUENCE_LENGTH,
    max_n_proportion: float = DEFAULT_MAX_N_PROPORTION,
    require_species_level: str = DEFAULT_REQUIRE_SPECIES_LEVEL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    http_client: Optional[httpx.Client] = None,
) -> BoldFetchResult:
    """Fetches candidate reference records from BOLD for `taxon` and
    applies the *automatable* slice of the curation judgment CLAUDE.md
    otherwise asks a domain expert for by hand (see
    claude/bold-reference-fetch.md and the BOLD Reference Data Guide
    written for that manual process): drops a too-short/too-ambiguous
    sequence, caps how many records survive per species, and flags (never
    auto-resolves) BIN inconsistency -- both within one species' own
    records and across different species sharing a BIN. All three of
    these, plus the species-level identification requirement itself, are
    exposed as overridable settings (app.configuration.catalog's
    "bold_fetch" entries) rather than fixed constants -- an analyst who
    knows their taxon needs a different bar can set one, per fetch,
    without touching code. require_species_level="allow_lower_rank" is
    the one that trades away real safety (see its own module-level
    constant comment) rather than just tuning a threshold.

    `taxon` is passed to BOLD's query API unscoped ("tax:<taxon>", not
    "tax:genus:<taxon>") deliberately -- CLAUDE.md's own ask was "no
    limitation as long as it's something we could pull," and the unscoped
    form matches a family, genus, or species name alike without the
    caller needing to already know which rank they're typing.

    Returns a BoldFetchResult -- a draft, not anything published or
    active. Raises BoldApiError for a genuine operational failure
    (network error, or BOLD's own preprocessor rejecting the taxon as
    unrecognized); a recognized taxon with zero usable records after
    filtering is a normal, reportable BoldFetchResult (total_kept == 0),
    not an error.
    """
    query = f"tax:{taxon}"
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)
    try:
        resolved_query = _preprocess_query(client, query)
        query_id = _submit_query(client, resolved_query)

        species_by_name: Dict[str, BoldSpeciesSummary] = {}
        bin_to_species: Dict[str, set] = {}
        drop_reasons: Dict[str, int] = {}
        fasta_lines: List[str] = []
        total_fetched = 0
        total_kept = 0

        total_kept_at_lower_rank = 0

        for record in _iter_documents(client, query_id):
            total_fetched += 1
            species = (record.get("species") or "").strip()
            rank = record.get("identification_rank") or ""
            process_id = record.get("processid") or ""

            name = species
            if rank not in TRUSTWORTHY_RANKS or not species:
                if require_species_level == "required":
                    drop_reasons["not identified to species level"] = (
                        drop_reasons.get("not identified to species level", 0) + 1
                    )
                    continue
                # allow_lower_rank: fall back to whatever identification
                # BOLD does have (its own overall `identification` field,
                # which is populated even for a genus/family-only call) --
                # still dropped if BOLD has literally nothing to go on.
                name = (record.get("identification") or "").strip()
                if not name:
                    drop_reasons["no identification available at any rank"] = (
                        drop_reasons.get("no identification available at any rank", 0) + 1
                    )
                    continue
                rank = rank or "unknown"

            if not _looks_like_valid_sequence(
                record.get("nuc"), min_length=min_sequence_length, max_n_proportion=max_n_proportion
            ):
                drop_reasons["sequence too short or too ambiguous"] = (
                    drop_reasons.get("sequence too short or too ambiguous", 0) + 1
                )
                continue

            summary = species_by_name.setdefault(
                name,
                BoldSpeciesSummary(
                    species=name, kept_count=0, dropped_count=0, identification_rank=rank
                ),
            )
            if summary.kept_count >= max_records_per_species:
                drop_reasons["over the per-species cap"] = (
                    drop_reasons.get("over the per-species cap", 0) + 1
                )
                summary.dropped_count += 1
                continue

            bin_uri = record.get("bin_uri") or ""
            if bin_uri:
                summary.bins.append(bin_uri)
                bin_to_species.setdefault(bin_uri, set()).add(name)
            summary.kept_count += 1
            total_kept += 1
            if rank not in TRUSTWORTHY_RANKS:
                total_kept_at_lower_rank += 1

            taxonomy = _taxonomy_string(record)
            header = f">{process_id} {name}" + (f" | {taxonomy}" if taxonomy else "")
            fasta_lines.append(header)
            fasta_lines.append(record["nuc"].strip())

        species_sharing_a_bin = [
            sorted(names) for names in bin_to_species.values() if len(names) > 1
        ]

        return BoldFetchResult(
            taxon=taxon,
            marker=marker,
            fasta_content="\n".join(fasta_lines) + ("\n" if fasta_lines else ""),
            species=sorted(species_by_name.values(), key=lambda s: s.species),
            total_fetched=total_fetched,
            total_kept=total_kept,
            drop_reasons=drop_reasons,
            species_sharing_a_bin=species_sharing_a_bin,
            total_kept_at_lower_rank=total_kept_at_lower_rank,
        )
    finally:
        if owns_client:
            client.close()
