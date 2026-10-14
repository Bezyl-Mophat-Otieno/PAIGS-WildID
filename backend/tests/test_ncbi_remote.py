"""app.pipeline.ncbi_remote -- the direct-HTTP NCBI client that is Stage
9's primary remote-search transport (see that module's own docstring for
why this exists alongside the older, unchanged blastn -remote subprocess
path in app.pipeline.blast, now used only as a fallback).

Golden fixtures, not hand-written approximations: every *.html/*.xml file
under tests/fixtures/ncbi_* here is a real response genuinely captured
live from https://blast.ncbi.nlm.nih.gov/Blast.cgi while building this
module (2026-10-14) -- a real CMD=Put submission, a real CMD=Get status
check, and a real CMD=Get&FORMAT_TYPE=XML2_S result (once against a
throwaway query with no real hits, once against a real 200bp fragment of
NC_001422.1 fetched live from NCBI's own eutils, specifically to get a
real multi-hit result to parse). The one exception is
ncbi_status_waiting.html, which is the real ready-status fixture with its
Status line edited from READY to WAITING -- the tiny test query finished
before a genuine WAITING capture was possible; clearly a derived fixture,
not a captured one, same spirit as test_blast.py's own "obviously
synthetic" reference FASTA note.

No real network call in any of these -- httpx.MockTransport replays the
captured bytes.
"""
import httpx
import pytest

from app.pipeline.ncbi_remote import (
    NcbiSearchFailedError,
    NcbiSubmissionFailedError,
    UnrecognizedNcbiResponseError,
    _extract_error_message,
    _extract_rid,
    _extract_rtoe,
    _extract_status,
    _is_html_response,
    check_status,
    fetch_result,
    submit_search,
)
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
QUERY_FASTA = FIXTURES_DIR / "synthetic_blast_query_exact_match.fasta"


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


def _client_returning(body: str, *, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestExtractRid:
    def test_extracts_rid_from_the_real_qblastinfo_block(self):
        assert _extract_rid(_fixture("ncbi_put_response.html")) == "CY4BSCS4016"

    def test_rejects_a_uuid_shaped_value(self):
        text = "QBlastInfoBegin\n RID = 12345678-1234-1234-1234-123456789012\nQBlastInfoEnd"
        assert _extract_rid(text) is None

    def test_returns_none_when_no_rid_present(self):
        assert _extract_rid("<html>nothing useful here</html>") is None


class TestExtractRtoe:
    def test_extracts_rtoe_from_the_real_qblastinfo_block(self):
        assert _extract_rtoe(_fixture("ncbi_put_response.html")) == 30

    def test_returns_none_when_absent(self):
        assert _extract_rtoe("QBlastInfoBegin\nRID = ABC123\nQBlastInfoEnd") is None


class TestExtractStatus:
    def test_reads_ready_from_the_real_status_fixture(self):
        assert _extract_status(_fixture("ncbi_status_ready.html")) == "READY"

    def test_reads_waiting_from_the_derived_waiting_fixture(self):
        assert _extract_status(_fixture("ncbi_status_waiting.html")) == "WAITING"

    def test_reads_unknown_from_the_real_bad_rid_fixture(self):
        assert _extract_status(_fixture("ncbi_status_unknown_bad_rid.html")) == "UNKNOWN"


class TestExtractErrorMessage:
    def test_extracts_the_real_bad_rid_error_message(self):
        message = _extract_error_message(_fixture("ncbi_status_unknown_bad_rid.html"))
        assert message is not None
        assert "Problems retrieving results" in message


class TestIsHtmlResponse:
    def test_recognizes_the_real_html_pages_as_html(self):
        assert _is_html_response(_fixture("ncbi_put_response.html")) is True
        assert _is_html_response(_fixture("ncbi_status_ready.html")) is True

    def test_recognizes_real_xml_as_not_html(self):
        assert _is_html_response(_fixture("ncbi_result_no_hits.xml")) is False


class TestSubmitSearch:
    def test_returns_the_real_rid_and_rtoe(self):
        client = _client_returning(_fixture("ncbi_put_response.html"))

        submission = submit_search(
            QUERY_FASTA, database="core_nt", max_hits=10, http_client=client
        )

        assert submission.rid == "CY4BSCS4016"
        assert submission.rtoe == 30

    def test_raises_submission_failed_when_no_rid_extractable(self):
        client = _client_returning("<html><body>nothing here</body></html>")

        with pytest.raises(NcbiSubmissionFailedError):
            submit_search(QUERY_FASTA, database="core_nt", max_hits=10, http_client=client)

    def test_raises_submission_failed_with_ncbis_own_error_text_when_present(self):
        client = _client_returning(_fixture("ncbi_status_unknown_bad_rid.html"))

        with pytest.raises(NcbiSubmissionFailedError, match="Problems retrieving results"):
            submit_search(QUERY_FASTA, database="core_nt", max_hits=10, http_client=client)


class TestCheckStatus:
    def test_returns_ready_for_the_real_ready_fixture(self):
        client = _client_returning(_fixture("ncbi_status_ready.html"))

        assert check_status("CY4BSCS4016", http_client=client) == "READY"

    def test_returns_waiting_for_the_waiting_fixture(self):
        client = _client_returning(_fixture("ncbi_status_waiting.html"))

        assert check_status("CY4BSCS4016", http_client=client) == "WAITING"

    def test_raises_search_failed_for_an_explicit_failed_status(self):
        client = _client_returning("QBlastInfoBegin\nStatus=FAILED\nQBlastInfoEnd")

        with pytest.raises(NcbiSearchFailedError, match="failed"):
            check_status("CY4BSCS4016", http_client=client)

    def test_raises_search_failed_with_real_message_for_an_unknown_rid(self):
        client = _client_returning(_fixture("ncbi_status_unknown_bad_rid.html"))

        with pytest.raises(NcbiSearchFailedError, match="Problems retrieving results"):
            check_status("NOTAREALRID000", http_client=client)

    def test_raises_unrecognized_when_nothing_matches_at_all(self):
        client = _client_returning("<html><body>a completely new NCBI page shape</body></html>")

        with pytest.raises(UnrecognizedNcbiResponseError):
            check_status("CY4BSCS4016", http_client=client)


class TestFetchResult:
    def test_parses_the_real_no_hits_result(self):
        client = _client_returning(_fixture("ncbi_result_no_hits.xml"))

        result = fetch_result("CY4BSCS4016", max_hits=10, http_client=client)

        assert result.query_length == 56
        assert result.hits == []

    def test_parses_the_real_multi_hit_result(self):
        client = _client_returning(_fixture("ncbi_result_with_hits.xml"))

        result = fetch_result("CY4E8T4S014", max_hits=10, http_client=client)

        assert result.query_length == 200
        assert len(result.hits) == 5
        assert result.hits[0].accession == "PZ509166"
        assert result.hits[0].species == "synthetic construct"
        assert result.hits[0].identity == pytest.approx(100.0)
        assert result.hits[0].rank == 1

    def test_respects_max_hits_against_a_real_multi_hit_result(self):
        client = _client_returning(_fixture("ncbi_result_with_hits.xml"))

        result = fetch_result("CY4E8T4S014", max_hits=2, http_client=client)

        assert len(result.hits) == 2

    def test_raises_unrecognized_for_an_html_page_with_no_error_text(self):
        client = _client_returning("<html><body>a completely new NCBI page shape</body></html>")

        with pytest.raises(UnrecognizedNcbiResponseError):
            fetch_result("CY4BSCS4016", max_hits=10, http_client=client)

    def test_raises_search_failed_for_an_html_error_page(self):
        client = _client_returning(_fixture("ncbi_status_unknown_bad_rid.html"))

        with pytest.raises(NcbiSearchFailedError, match="Problems retrieving results"):
            fetch_result("NOTAREALRID000", max_hits=10, http_client=client)

    def test_raises_unrecognized_for_malformed_xml(self):
        client = _client_returning("<BlastOutput2><not-closed>")

        with pytest.raises(UnrecognizedNcbiResponseError):
            fetch_result("CY4BSCS4016", max_hits=10, http_client=client)

    def test_raises_search_failed_for_a_real_err_block(self):
        xml = (
            '<?xml version="1.0"?><BlastXML2 xmlns="http://www.ncbi.nlm.nih.gov">'
            "<BlastOutput2><report><Report><results><Results><search><Search>"
            "<errors><Err><code>1</code><message>CPU usage limit exceeded</message></Err></errors>"
            "</Search></search></Results></results></Report></report></BlastOutput2></BlastXML2>"
        )
        client = _client_returning(xml)

        with pytest.raises(NcbiSearchFailedError, match="CPU usage limit exceeded"):
            fetch_result("CY4BSCS4016", max_hits=10, http_client=client)
