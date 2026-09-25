"""GET /runs/reports/export -- bulk report export (ZIP).

Item 7 of the user's punch list: "Only single-report PDF download
exists today. If we want 'export selected' or 'export all' from the
reports screen, that button needs a real endpoint behind it."

Written first, against the not-yet-existing endpoint, to confirm red
before implementing. Reuses the same real-pipeline/reference-DB-publish
pattern test_api_report.py already established for a single completed
report -- a bulk export only makes sense to test against real, actually-
generated PDFs, not mocked stage output.
"""
import io
import zipfile
from pathlib import Path


def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


TRIMMED_3100 = (
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


def _publish_reference_db_for_3100(client):
    fasta_bytes = f">REF3100 Testus fixturensis\n{TRIMMED_3100}\n".encode()
    resp = client.post(
        "/reference-database/publish",
        files={"fasta": ("reference.fasta", io.BytesIO(fasta_bytes), "text/plain")},
        data={"version": "v1"},
    )
    assert resp.status_code == 201, resp.text


def _create_and_execute_completed_run(caller, fixtures_dir, sample_id):
    create_resp = caller.post(
        "/runs",
        files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
        data={"sample_id": sample_id},
    )
    run_id = create_resp.json()["id"]
    exec_resp = caller.post(f"/runs/{run_id}/execute")
    assert exec_resp.json()["status"] == "completed", exec_resp.text
    return run_id


def _create_and_execute_failed_run(caller, fixtures_dir, sample_id):
    create_resp = caller.post(
        "/runs",
        files={"forward_read": _file_field(fixtures_dir, "empty.ab1")},
        data={"sample_id": sample_id},
    )
    run_id = create_resp.json()["id"]
    exec_resp = caller.post(f"/runs/{run_id}/execute")
    assert exec_resp.json()["status"] == "failed", exec_resp.text
    return run_id


class TestRequiresAuthentication:
    def test_requires_a_token(self, anon_client):
        resp = anon_client.get("/runs/reports/export")

        assert resp.status_code == 401


class TestBulkExport:
    def test_404_when_the_caller_has_no_completed_reports_at_all(self, client):
        resp = client.get("/runs/reports/export")

        assert resp.status_code == 404

    def test_exports_all_of_the_callers_completed_reports_as_a_zip(
        self, client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)
        run_a = _create_and_execute_completed_run(client, fixtures_dir, "EXPORT_A")
        run_b = _create_and_execute_completed_run(client, fixtures_dir, "EXPORT_B")

        resp = client.get("/runs/reports/export")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert ".zip" in resp.headers["content-disposition"]
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 2
        assert any(run_a in name for name in names)
        assert any(run_b in name for name in names)
        for name in names:
            assert zf.read(name).startswith(b"%PDF")

    def test_run_ids_filters_to_just_the_requested_runs(
        self, client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)
        run_a = _create_and_execute_completed_run(client, fixtures_dir, "EXPORT_A")
        run_b = _create_and_execute_completed_run(client, fixtures_dir, "EXPORT_B")
        _create_and_execute_completed_run(client, fixtures_dir, "EXPORT_C")

        resp = client.get("/runs/reports/export", params={"run_ids": [run_a, run_b]})

        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 2
        assert any(run_a in name for name in names)
        assert any(run_b in name for name in names)

    def test_skips_runs_that_never_reached_a_completed_report(
        self, client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)
        completed_run = _create_and_execute_completed_run(client, fixtures_dir, "EXPORT_OK")
        _create_and_execute_failed_run(client, fixtures_dir, "EXPORT_FAILED")

        resp = client.get("/runs/reports/export")

        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 1
        assert completed_run in names[0]

    def test_404_when_every_requested_run_id_is_unexportable(
        self, client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)
        failed_run = _create_and_execute_failed_run(client, fixtures_dir, "EXPORT_FAILED")

        resp = client.get("/runs/reports/export", params={"run_ids": [failed_run]})

        assert resp.status_code == 404


class TestScoping:
    def test_an_analyst_only_exports_their_own_reports(
        self, client, analyst_client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)
        admin_run = _create_and_execute_completed_run(client, fixtures_dir, "ADMIN_RUN")
        analyst_run = _create_and_execute_completed_run(analyst_client, fixtures_dir, "ANALYST_RUN")

        resp = analyst_client.get("/runs/reports/export")

        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 1
        assert analyst_run in names[0]
        assert admin_run not in names[0]

    def test_an_analyst_cannot_export_an_admins_report_by_id(
        self, client, analyst_client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)
        admin_run = _create_and_execute_completed_run(client, fixtures_dir, "ADMIN_RUN")

        resp = analyst_client.get("/runs/reports/export", params={"run_ids": [admin_run]})

        assert resp.status_code == 404

    def test_an_admin_exports_reports_across_every_user(
        self, client, analyst_client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)
        admin_run = _create_and_execute_completed_run(client, fixtures_dir, "ADMIN_RUN")
        analyst_run = _create_and_execute_completed_run(analyst_client, fixtures_dir, "ANALYST_RUN")

        resp = client.get("/runs/reports/export")

        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 2
        assert any(admin_run in name for name in names)
        assert any(analyst_run in name for name in names)
