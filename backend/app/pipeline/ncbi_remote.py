"""Direct HTTP client for NCBI's Common URL API (Blast.cgi) -- Stage 9's
primary remote-search transport, used instead of shelling out to
`blastn -remote` and blocking a thread for the whole search.

Why this exists: `blastn -remote` hands all communication with NCBI to
BLAST+'s own bundled client, which this app cannot see inside -- a single
subprocess call that either returns within `blast.remote_timeout_seconds`
or gets killed, discarding whatever NCBI was still computing (see
app.pipeline.blast.search_blast_remote, kept unchanged as the fallback
transport -- see app.orchestration.execute._fallback_to_subprocess_search).
This module instead submits the search itself, gets back a Request ID
(RID) immediately, and lets the caller (app.orchestration.execute's
background-poller-driven state machine) check on it across many cheap,
non-blocking ticks instead of one long blocking one -- never losing a
slow-but-legitimate search to an artificial timeout.

Submission uses GET, not POST, for CMD=Put. This isn't cosmetic: verified
live against the real endpoint while building this (2026-10-14), NCBI's
CMD=Put response is a plain HTML page with the RID embedded in an
`<!--QBlastInfoBegin ... QBlastInfoEnd-->` comment block either way, but
POST submissions have been observed (by a colleague building a parallel
implementation) to sometimes come back with no RID in that block at all,
while GET still reliably includes it. There is no documented JSON/XML
submission response from NCBI's URL API -- parsing this HTML comment
block is the only submission mechanism NCBI offers, not a workaround of
our own invention (see https://blast.ncbi.nlm.nih.gov/doc/blast-help/urlapi.html).

Three distinct failure modes, deliberately not collapsed into one:

- NcbiSubmissionFailedError: CMD=Put didn't yield a RID. The one trigger
  for falling back to the blastn -remote subprocess path -- submission
  hasn't committed us to anything on NCBI's side yet, so falling back
  here is free, unlike mid-flight.
- NcbiSearchFailedError: NCBI *did* answer clearly, and the answer is "no"
  (Status=FAILED, a real <Err> block, or a recognizable error message) --
  a correctly-understood, genuine failure.
- UnrecognizedNcbiResponseError: the response doesn't match any
  documented shape at all -- NCBI changed something. Always fails loud,
  with a snippet of the actual raw response attached, rather than
  guessing past it and risking a silently wrong result. See
  claude/remote-blast-search.md for the operational playbook this maps
  to (when this fires, what an operator should do).
"""
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import httpx
from Bio import SeqIO

from app.schemas.blast import BlastHit

NCBI_BLAST_URL = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"
NCBI_TOOL = "PAIGSWildID"
NCBI_PROGRAM = "blastn"

# NCBI's own URL API guidance: don't poll a single RID more than once a
# minute. The initial wait (before the *first* status check) instead uses
# NCBI's own RTOE estimate from the Put response, clamped to this range --
# waiting exactly as long as NCBI told us to expect, rather than either
# hammering a search we were just told isn't ready, or guessing a longer
# fixed delay than necessary.
DEFAULT_POLL_INTERVAL_SECONDS = 60
MIN_INITIAL_WAIT_SECONDS = 5
MAX_INITIAL_WAIT_SECONDS = 60

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class NcbiSubmissionFailedError(RuntimeError):
    """CMD=Put didn't yield a usable RID -- see module docstring."""


class NcbiSearchFailedError(RuntimeError):
    """NCBI reported a genuine, understood failure -- see module docstring."""


class UnrecognizedNcbiResponseError(RuntimeError):
    """NCBI's response didn't match any known/documented shape -- see
    module docstring. Carries a snippet of the raw response in its
    message so the failure is debuggable without re-fetching anything."""


@dataclass
class NcbiSubmission:
    rid: str
    rtoe: Optional[int]
    raw_response: str


@dataclass
class NcbiFetchedResult:
    query_length: int
    hits: List[BlastHit]
    raw_response: str


def _request(params: dict, *, http_client: httpx.Client) -> str:
    query = dict(params)
    query["TOOL"] = NCBI_TOOL
    email = os.environ.get("PAIGS_NCBI_EMAIL", "").strip()
    if email:
        query["EMAIL"] = email

    try:
        response = http_client.get(NCBI_BLAST_URL, params=query)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise NcbiSearchFailedError(f"Could not communicate with NCBI BLAST: {exc}") from exc
    return response.text


def _is_html_response(text: str) -> bool:
    sample = (text or "").lstrip().lower()
    return (
        sample.startswith("<!doctype html")
        or sample.startswith("<html")
        or "<html" in sample[:500]
    )


def _qblast_block(text: str) -> str:
    match = re.search(r"QBlastInfoBegin(.*?)QBlastInfoEnd", text or "", re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else (text or "")


def _extract_rid(text: str) -> Optional[str]:
    region = _qblast_block(text)
    for pattern in (
        r"(?im)^\s*RID\s*=\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*$",
        r"(?im)\bRID\s*=\s*([A-Za-z0-9][A-Za-z0-9._-]*)\b",
    ):
        match = re.search(pattern, region)
        if match:
            rid = match.group(1).strip()
            if _UUID_RE.fullmatch(rid):
                # A UUID-shaped value here is never a real NCBI RID --
                # reject it rather than treat it as one.
                continue
            return rid
    return None


def _extract_rtoe(text: str) -> Optional[int]:
    match = re.search(r"(?im)^\s*RTOE\s*=\s*(\d+)\s*$", _qblast_block(text))
    return int(match.group(1)) if match else None


def _extract_status(text: str) -> Optional[str]:
    region = _qblast_block(text)
    match = re.search(r"(?im)^\s*Status\s*=\s*([A-Za-z]+)\s*$", region)
    if match:
        return match.group(1).upper()
    match = re.search(r"(?im)^\s*Status\s*=\s*([A-Za-z]+)\s*$", text or "")
    return match.group(1).upper() if match else None


def _extract_error_message(text: str) -> Optional[str]:
    if not text:
        return None
    for pattern in (
        r'(?im)<p[^>]*class="error"[^>]*>\s*(.*?)\s*</p>',
        r"(?im)^\s*ERROR\s*=\s*(.+?)\s*$",
        r"(?im)^\s*Message\s*=\s*(.+?)\s*$",
        r"(?im)<message[^>]*>\s*(.*?)\s*</message>",
    ):
        match = re.search(pattern, text)
        if match:
            value = re.sub(r"<[^>]+>", " ", match.group(1))
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                return value
    return None


def _new_client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


def submit_search(
    query_fasta: Path,
    *,
    database: str,
    entrez_query: str = "",
    max_hits: int,
    http_client: Optional[httpx.Client] = None,
) -> NcbiSubmission:
    """Submits `query_fasta` (expected to hold exactly one sequence, same
    as every other Stage 9 entry point) to NCBI via CMD=Put and returns
    the RID/RTOE NCBI hands back. Raises NcbiSubmissionFailedError when no
    RID can be extracted at all -- the orchestration layer's one trigger
    to fall back to the blastn -remote subprocess path instead of failing
    the run outright.
    """
    records = list(SeqIO.parse(str(query_fasta), "fasta"))
    if not records:
        raise ValueError(f"No sequences found in query FASTA: {query_fasta}")
    record = records[0]
    fasta_query = f">{record.id}\n{str(record.seq)}"

    params = {
        "CMD": "Put",
        "PROGRAM": NCBI_PROGRAM,
        "DATABASE": database,
        "QUERY": fasta_query,
        "MEGABLAST": "on",
        "HITLIST_SIZE": str(max_hits),
    }
    if entrez_query:
        params["ENTREZ_QUERY"] = entrez_query

    owns_client = http_client is None
    client = http_client or _new_client()
    try:
        response_text = _request(params, http_client=client)
    finally:
        if owns_client:
            client.close()

    rid = _extract_rid(response_text)
    if not rid:
        detail = _extract_error_message(response_text) or (
            "NCBI did not return a Request ID (RID) for this submission."
        )
        raise NcbiSubmissionFailedError(detail)

    return NcbiSubmission(rid=rid, rtoe=_extract_rtoe(response_text), raw_response=response_text)


def check_status(rid: str, *, http_client: Optional[httpx.Client] = None) -> str:
    """Returns "WAITING" or "READY". Raises NcbiSearchFailedError for a
    genuine NCBI-reported failure (Status=FAILED, or Status=UNKNOWN paired
    with a recognizable error message) and UnrecognizedNcbiResponseError
    when the response doesn't match any known shape at all.
    """
    params = {"CMD": "Get", "RID": rid, "FORMAT_OBJECT": "SearchInfo"}
    owns_client = http_client is None
    client = http_client or _new_client()
    try:
        response_text = _request(params, http_client=client)
    finally:
        if owns_client:
            client.close()

    status = _extract_status(response_text)

    if status == "READY":
        return "READY"
    if status == "WAITING":
        return "WAITING"
    if status == "FAILED":
        raise NcbiSearchFailedError(f"NCBI reported the BLAST search (RID {rid}) failed.")

    error_message = _extract_error_message(response_text)
    if error_message:
        raise NcbiSearchFailedError(f"NCBI reported a problem with RID {rid}: {error_message}")
    raise UnrecognizedNcbiResponseError(
        f"Could not determine a search status for RID {rid} -- no recognizable "
        f"Status= field in NCBI's response. Response started with: "
        f"{response_text[:300]!r}"
    )


def _species_from_hit(descr: Optional[ET.Element]) -> str:
    if descr is None:
        return "unknown"
    sciname = (descr.findtext("sciname") or "").strip()
    if sciname:
        return sciname
    title = (descr.findtext("title") or "").strip()
    match = re.search(r"\b([A-Z][a-z]{2,})\s+([a-z][a-z-]{2,})\b", title)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return title or "unknown"


def fetch_result(
    rid: str, *, max_hits: int, http_client: Optional[httpx.Client] = None
) -> NcbiFetchedResult:
    """Fetches and parses a completed search's XML2 result -- only
    meaningful once check_status() has returned "READY". Raises
    NcbiSearchFailedError for a real NCBI-reported <Err> block, and
    UnrecognizedNcbiResponseError if the XML doesn't parse, or doesn't
    contain the documented BlastOutput2 structure at all (NCBI changed
    the schema, or returned an HTML page where XML was expected).
    """
    params = {"CMD": "Get", "RID": rid, "FORMAT_TYPE": "XML2_S"}
    owns_client = http_client is None
    client = http_client or _new_client()
    try:
        response_text = _request(params, http_client=client)
    finally:
        if owns_client:
            client.close()

    if not response_text.strip():
        raise UnrecognizedNcbiResponseError(f"NCBI returned an empty result for RID {rid}.")

    if _is_html_response(response_text):
        error_message = _extract_error_message(response_text)
        if error_message:
            raise NcbiSearchFailedError(
                f"NCBI reported a problem fetching RID {rid}: {error_message}"
            )
        raise UnrecognizedNcbiResponseError(
            f"Expected an XML result for RID {rid} but got an HTML page instead. "
            f"Response started with: {response_text[:300]!r}"
        )

    try:
        root = ET.fromstring(response_text)
    except ET.ParseError as exc:
        raise UnrecognizedNcbiResponseError(
            f"Could not parse NCBI's XML result for RID {rid}: {exc}"
        ) from exc

    # XML2 is namespaced (xmlns="http://www.ncbi.nlm.nih.gov"); strip
    # namespaces so plain tag lookups below work regardless.
    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]

    errors = [msg for e in root.findall(".//Err") if (msg := e.findtext("message"))]
    if errors:
        raise NcbiSearchFailedError(
            f"NCBI BLAST reported an error for RID {rid}: {'; '.join(errors)}"
        )

    search_nodes = root.findall(".//Search")
    if not search_nodes:
        raise UnrecognizedNcbiResponseError(
            f"NCBI's XML result for RID {rid} had no <Search> element -- unexpected "
            f"shape. Response started with: {response_text[:300]!r}"
        )

    search = search_nodes[0]
    query_length = int(search.findtext("query-len") or 0)

    hits: List[BlastHit] = []
    for rank, hit in enumerate(search.findall("./hits/Hit"), start=1):
        if rank > max_hits:
            break
        descr = hit.find("./description/HitDescr")
        accession = None
        if descr is not None:
            accession = descr.findtext("accession") or descr.findtext("id")
        hsp_nodes = hit.findall("./hsps/Hsp")
        if not hsp_nodes:
            continue
        best = max(hsp_nodes, key=lambda h: float(h.findtext("bit-score") or 0.0))

        align_length = int(best.findtext("align-len") or 0)
        identities = int(best.findtext("identity") or 0)
        identity_pct = (identities / align_length * 100.0) if align_length else 0.0

        query_from = int(best.findtext("query-from") or 0)
        query_to = int(best.findtext("query-to") or 0)
        coverage = (
            (abs(query_to - query_from) + 1) / query_length * 100.0 if query_length else 0.0
        )

        hits.append(
            BlastHit(
                rank=rank,
                species=_species_from_hit(descr),
                identity=round(identity_pct, 2),
                coverage=round(coverage, 2),
                evalue=float(best.findtext("evalue") or 0.0),
                bit_score=float(best.findtext("bit-score") or 0.0),
                accession=accession or "unknown",
            )
        )

    return NcbiFetchedResult(query_length=query_length, hits=hits, raw_response=response_text)
