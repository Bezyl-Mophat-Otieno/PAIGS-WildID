"""POST /runs/{id}/execute -- API-level orchestration tests.

Written first, against the not-yet-existing endpoint, to confirm red
before implementing.

Covers exactly what needs real file uploads through the real API (Stage
0's storage + Stage 1/2's real AB1 parsing, and the run-not-found /
already-executed guards) using the fixtures already in this repo. The
two-read success path through Orientation + Consensus -- which needs a
genuine matching pair no real AB1 fixture here provides -- is instead
covered at the function level in test_orchestration.py; see that file's
own docstring for why.
"""
import io
from pathlib import Path



def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


class TestExecuteRun:
    def test_returns_404_for_unknown_run(self, client):
        resp = client.post("/runs/does-not-exist/execute")

        assert resp.status_code == 404

    def test_returns_409_if_already_executed(self, client, fixtures_dir, temp_reference_data_root):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        run_id = create_resp.json()["id"]

        first = client.post(f"/runs/{run_id}/execute")
        assert first.status_code == 200

        second = client.post(f"/runs/{run_id}/execute")
        assert second.status_code == 409

    def test_stops_at_format_check_for_an_invalid_file(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "not_ab1_format.ab1")}
        )
        run_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{run_id}/execute")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["current_stage"] == "format_check"

        stage_resp = client.get(f"/runs/{run_id}/stages/format_check")
        assert stage_resp.json()["output"]["forward"]["valid"] is False

    def test_stops_at_sanity_check_for_a_single_low_quality_file(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "empty.ab1")}
        )
        run_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{run_id}/execute")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["current_stage"] == "sanity_check"

    def test_both_reads_failing_sanity_stops_the_run(self, client, fixtures_dir):
        # Same real fixture uploaded to both slots -- still two independent
        # files on disk, both structurally valid, both genuinely bad data
        # (5bp, all-N), so both fail Stage 3 for real.
        create_resp = client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "empty.ab1"),
                "reverse_read": _file_field(fixtures_dir, "empty.ab1"),
            },
        )
        run_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{run_id}/execute")

        assert resp.json()["status"] == "failed"
        assert resp.json()["current_stage"] == "sanity_check"

    def test_two_real_unrelated_reads_stop_at_orientation_no_overlap(
        self, client, fixtures_dir
    ):
        # 3100.ab1 and 3730.ab1 are confirmed-unrelated real fixtures (see
        # claude/stage-5-6-status.md) -- both pass format/sanity/trim, but
        # genuinely share no overlap. A real exercise of Stage 5's "flags
        # for review rather than guessing" path, no synthetic data needed.
        create_resp = client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        )
        run_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{run_id}/execute")

        assert resp.json()["status"] == "failed"
        assert resp.json()["current_stage"] == "orientation"

        orientation_stage = client.get(f"/runs/{run_id}/stages/orientation").json()
        assert orientation_stage["output"]["orientation"] == "no_overlap_found"

        consensus_stage = client.get(f"/runs/{run_id}/stages/consensus").json()
        assert consensus_stage["status"] == "skipped"

    def test_stops_at_blast_when_no_reference_database_is_published(
        self, client, fixtures_dir, temp_reference_data_root
    ):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        run_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{run_id}/execute")

        assert resp.json()["status"] == "failed"
        assert resp.json()["current_stage"] == "blast"

        blast_stage = client.get(f"/runs/{run_id}/stages/blast").json()
        assert blast_stage["status"] == "failed"
        assert "reference database" in blast_stage["output"]["error"].lower()

    def test_single_file_runs_the_full_pipeline_to_a_completed_report(
        self, client, fixtures_dir, temp_reference_data_root
    ):
        # A reference DB whose one entry is 3100.ab1's own real trimmed
        # sequence (empirically extracted once via the actual pipeline --
        # see claude/orchestration-status.md) -- guarantees a clean,
        # unambiguous 100%-identity/coverage BLAST hit, so this test
        # exercises Stage 1 through Stage 11 against real data end to end.
        # Published through the real admin API (not publish_reference_db()
        # directly) so it lands in the exact same database /runs/{id}/execute
        # will read from -- the `client` fixture's own isolated db, separate
        # from the `db_session` fixture's.
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
        publish_resp = client.post(
            "/reference-database/publish",
            files={"fasta": ("reference.fasta", io.BytesIO(fasta_bytes), "text/plain")},
            data={"version": "v1"},
        )
        assert publish_resp.status_code == 201, publish_resp.text

        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        run_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{run_id}/execute")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["current_stage"] == "report"

        identification = client.get(f"/runs/{run_id}/stages/identification").json()
        assert identification["output"]["status"] == "PASS"
        assert identification["output"]["candidate_species"] == "Testus fixturensis"

        report_stage = client.get(f"/runs/{run_id}/stages/report").json()
        report_path = Path(report_stage["output"]["report_path"])
        assert report_path.is_file()
        assert report_path.read_bytes().startswith(b"%PDF")

        run_detail = client.get(f"/runs/{run_id}").json()
        stage_types = {s["stage_type"] for s in run_detail["stages"]}
        assert stage_types == {
            "import",
            "format_check",
            "ab1_extraction",
            "sanity_check",
            "trim",
            "orientation",
            "consensus",
            "usability_check",
            "fasta",
            "blast",
            "identification",
            "report",
        }
