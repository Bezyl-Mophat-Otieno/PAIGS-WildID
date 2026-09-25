"""Admin cross-tenant visibility into Runs -- the deliberate "later step"
flagged (not built) in tests/test_api_runs_ownership.py and
claude/tenant-scoping-status.md: "we will expand the admin to see all
the runs and analysis of everyone."

The visibility this grants is read-only. An admin can *see* any user's
Run (list it, fetch its detail, its stages, its report), but cannot
*act on* a Run they don't own -- execute, rerun, and patch stay strictly
owner-scoped even for an admin. Rationale: "see all the runs and
analysis of everyone" is a request to view everyone's work, not a
request to let an admin execute or edit someone else's data on their
behalf, and this pipeline is headed toward forensic/evidentiary use,
where an admin silently mutating another analyst's Run would undermine
the audit trail. If the product actually wants admin write-access too,
that's a one-line change per endpoint (_get_owned_run -> _get_visible_run)
-- flagging the distinction now rather than silently deciding the
broader version.

An analyst's own view is unchanged -- still scoped to just their own
Runs (see test_api_runs_ownership.py, not repeated in full here).
"""
import io
from pathlib import Path


def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


def _create_run(caller, fixtures_dir, filename="3100.ab1"):
    resp = caller.post("/runs", files={"forward_read": _file_field(fixtures_dir, filename)})
    assert resp.status_code == 201
    return resp.json()


def _publish_reference_db_for_3100(client):
    # Same trimmed_3100 sequence tests/test_api_report.py uses -- a
    # clean, unambiguous 100%-identity/coverage BLAST hit so the run
    # actually reaches Stage 11 and produces a real report.
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


class TestAdminListVisibility:
    def test_admin_list_runs_sees_every_users_runs(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir, "3100.ab1")
        analyst_run = _create_run(analyst_client, fixtures_dir, "3730.ab1")

        admin_view = {r["id"] for r in client.get("/runs").json()}

        assert admin_run["id"] in admin_view
        assert analyst_run["id"] in admin_view

    def test_analyst_list_runs_still_only_sees_their_own(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir, "3100.ab1")
        analyst_run = _create_run(analyst_client, fixtures_dir, "3730.ab1")

        analyst_view = {r["id"] for r in analyst_client.get("/runs").json()}

        assert analyst_run["id"] in analyst_view
        assert admin_run["id"] not in analyst_view


class TestAdminReadAccessToSomeoneElsesRun:
    def test_admin_can_view_an_analysts_run_detail(self, client, analyst_client, fixtures_dir):
        analyst_run = _create_run(analyst_client, fixtures_dir)

        resp = client.get(f"/runs/{analyst_run['id']}")

        assert resp.status_code == 200
        assert resp.json()["id"] == analyst_run["id"]

    def test_admin_can_view_an_analysts_run_stage(self, client, analyst_client, fixtures_dir):
        analyst_run = _create_run(analyst_client, fixtures_dir)

        resp = client.get(f"/runs/{analyst_run['id']}/stages/import")

        assert resp.status_code == 200

    def test_admin_can_download_an_analysts_completed_report(
        self, client, analyst_client, fixtures_dir, temp_reference_data_root
    ):
        _publish_reference_db_for_3100(client)

        create_resp = analyst_client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"sample_id": "ANALYST_owned_report"},
        )
        run_id = create_resp.json()["id"]
        exec_resp = analyst_client.post(f"/runs/{run_id}/execute")
        assert exec_resp.json()["status"] == "completed"

        resp = client.get(f"/runs/{run_id}/report")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")


class TestAdminCannotActOnSomeoneElsesRun:
    """Visibility, not authority -- see the module docstring."""

    def test_admin_cannot_execute_an_analysts_run(self, client, analyst_client, fixtures_dir):
        analyst_run = _create_run(analyst_client, fixtures_dir)

        resp = client.post(f"/runs/{analyst_run['id']}/execute")

        assert resp.status_code == 404

    def test_admin_cannot_rerun_an_analysts_run(self, client, analyst_client, fixtures_dir):
        analyst_run = _create_run(analyst_client, fixtures_dir)

        resp = client.post(f"/runs/{analyst_run['id']}/rerun")

        assert resp.status_code == 404

    def test_admin_cannot_patch_an_analysts_run(self, client, analyst_client, fixtures_dir):
        analyst_run = _create_run(analyst_client, fixtures_dir)

        resp = client.patch(f"/runs/{analyst_run['id']}", json={"sample_id": "HIJACKED_BY_ADMIN"})

        assert resp.status_code == 404
