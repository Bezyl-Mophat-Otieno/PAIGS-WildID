"""GET /runs/{id}/report -- the actual PDF download endpoint.

GET /runs/{id}/stages/report already existed (it returns the Report
Stage's audit-trail output, {"report_path": "..."}), but that's a
server-side filesystem path, not something a caller can fetch. This
endpoint is the missing download counterpart -- streams Stage 11's real
PDF bytes back with the right media type and a human-meaningful filename.

Reuses the same real-data/real-reference-DB setup as
test_api_execute.py's test_single_file_runs_the_full_pipeline_to_a_completed_report,
since a completed report is a precondition for anything meaningful to
download.
"""
import io
from pathlib import Path


def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


def _publish_reference_db_for_3100(client):
    # Same trimmed_3100 sequence test_api_execute.py uses -- guarantees a
    # clean, unambiguous 100%-identity/coverage BLAST hit so the run
    # actually reaches Stage 11.
    trimmed_3100 = (
        "AGCGATTCCAGCTTCATATAGTCGAGTTGCAGACTACAATCCGAACTGAGAACAACTTTATGGGATTTGCT"
        "TGACCTCGCGGTTTCGCTGCCCTTTGTATTGTCCATTGTAGCACGTGTGTAGCCCAAATCATAAGGGGCAT"
        "GATGATTTGACGTCATCCCCACCTTCCTCCGGTTTGTCACCGGCAGTCAACTTAGAGTGCCCAACTTAAT"
        "GATGGCAACTAAGCTTAAGGGTTGCGCTCGTTGCGGGACTTAACCCAACATCTCACGACACGAGCTGAC"
        "GACAACCATGCACCACCTGTCACTCTGTCCCCCGAAGGGGAAAACTCTATCTCTAGAGGAGTCAGAGGA"
        "TGTCAAGATTTGGTAAGGTTCTTCGCGTTGCTTCGAATTAAACCACATGCTCCACCGCTTGTGCGGGTC"
        "CCCGTCAATTCCTTTGAGTTTCAACCTTGCGGTCGTACTCCCCAGGCGGAGTGCTTAATGCGTTAGCTG"
        "CAGCACTAAGGGGCGGAAACCCCCTAACACTTAGCACTCATCGTTTACGGCGTGGACTACCAGGGTATC"
        "TAATCCTGTTTGATCCCCACGCTTTCGCACATCAGCGTCAGTTACAGACCAGAAAGTCGCCTTCGCCAC"
        "TGGTGTTCCTCCATATCTCTGCGCATTTCACCGCTACACAT"
    )
    fasta_bytes = f">REF3100 Testus fixturensis\n{trimmed_3100}\n".encode()
    resp = client.post(
        "/reference-database/publish",
        files={"fasta": ("reference.fasta", io.BytesIO(fasta_bytes), "text/plain")},
        data={"version": "v1"},
    )
    assert resp.status_code == 201, resp.text


class TestDownloadReport:
    def test_downloads_the_real_pdf_for_a_completed_run(
        self, client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)

        create_resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"sample_id": "WILD_report_test"},
        )
        run_id = create_resp.json()["id"]

        exec_resp = client.post(f"/runs/{run_id}/execute")
        assert exec_resp.json()["status"] == "completed"

        resp = client.get(f"/runs/{run_id}/report")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "WILD_report_test_report.pdf" in resp.headers["content-disposition"]
        assert resp.content.startswith(b"%PDF")

    def test_returns_404_for_unknown_run(self, client):
        resp = client.get("/runs/does-not-exist/report")

        assert resp.status_code == 404

    def test_returns_404_when_run_has_not_reached_reporting(self, client, fixtures_dir):
        # No reference DB published -- run will stop at Stage 1
        # (format_check fails) long before Stage 11 ever runs.
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "not_ab1_format.ab1")}
        )
        run_id = create_resp.json()["id"]
        client.post(f"/runs/{run_id}/execute")

        resp = client.get(f"/runs/{run_id}/report")

        assert resp.status_code == 404
        assert "no completed report" in resp.json()["detail"].lower()

    def test_returns_404_for_a_run_that_was_never_executed(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        run_id = create_resp.json()["id"]

        resp = client.get(f"/runs/{run_id}/report")

        assert resp.status_code == 404
