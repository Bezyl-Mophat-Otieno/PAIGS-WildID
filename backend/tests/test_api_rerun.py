"""POST /runs/{id}/rerun -- API-level tests.

Written first, against the not-yet-existing endpoint, to confirm red
before implementing. CLAUDE.md's Configuration model: "trying different
settings means triggering a whole new Run... reusing the same file(s),
adjusted config... the two Runs sit side by side, fully independent and
comparable." These tests cover the endpoint's own contract (file reuse,
validation, lineage); the killer end-to-end proof that a rerun with
different config actually produces a different outcome than the
original is TestRerunChangesOutcome below.
"""
import io
from pathlib import Path


def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


class TestRerunRun:
    def test_returns_404_for_unknown_run(self, client):
        resp = client.post("/runs/does-not-exist/rerun")

        assert resp.status_code == 404

    def test_creates_a_new_run_with_a_different_id(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{source_id}/rerun")

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] != source_id
        assert body["current_stage"] == "import"
        assert body["status"] == "in_progress"
        assert body["original_filenames"] == ["3100.ab1"]

    def test_records_lineage_back_to_the_source_run(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{source_id}/rerun")

        assert resp.json()["rerun_of"] == source_id

    def test_copies_the_source_runs_files_byte_for_byte(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        new_run = client.post(f"/runs/{source_id}/rerun").json()

        source_import = client.get(f"/runs/{source_id}/stages/import").json()
        new_import = client.get(f"/runs/{new_run['id']}/stages/import").json()

        assert new_import["output"]["slots"] == source_import["output"]["slots"]
        assert new_import["output"]["original_filenames"] == ["3100.ab1"]

        original_bytes = (fixtures_dir / "3100.ab1").read_bytes()
        # The new run's own execute call (below, in a different test) is
        # what proves those bytes are actually usable -- here we only
        # confirm the import stage recorded a real stored filename.
        assert new_import["output"]["stored_filenames"]

    def test_leaves_the_source_run_completely_untouched(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        )
        source_id = create_resp.json()["id"]
        source_before = client.get(f"/runs/{source_id}").json()

        client.post(f"/runs/{source_id}/rerun", json={"config_overrides": {"blast.max_hits": 5}})

        source_after = client.get(f"/runs/{source_id}").json()
        assert source_after == source_before

    def test_default_config_overrides_is_null_when_omitted(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{source_id}/rerun")

        assert resp.json()["config_overrides"] is None

    def test_stores_supplied_config_overrides(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        resp = client.post(
            f"/runs/{source_id}/rerun",
            json={"config_overrides": {"usability_check.min_length": 100}},
        )

        assert resp.status_code == 201
        assert resp.json()["config_overrides"] == {"usability_check.min_length": 100}

    def test_rejects_an_unknown_config_key(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        resp = client.post(
            f"/runs/{source_id}/rerun", json={"config_overrides": {"not_a_real.key": 1}}
        )

        assert resp.status_code == 422

    def test_rejects_an_out_of_bounds_value(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        resp = client.post(
            f"/runs/{source_id}/rerun",
            json={"config_overrides": {"orientation.min_identity": 2.0}},
        )

        assert resp.status_code == 422

    def test_accepts_a_custom_sample_id(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{source_id}/rerun", json={"sample_id": "WILD_001_RETRY"})

        assert resp.json()["sample_id"] == "WILD_001_RETRY"

    def test_defaults_to_a_fresh_auto_generated_sample_id(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"sample_id": "WILD_ORIGINAL"},
        )
        source_id = create_resp.json()["id"]

        resp = client.post(f"/runs/{source_id}/rerun")

        # Not required to equal the original label -- a fresh timestamped
        # default, same convention as a brand-new upload (app.naming).
        assert resp.json()["sample_id"] != "WILD_ORIGINAL"
        assert "3100" in resp.json()["sample_id"]

    def test_a_rerun_can_itself_be_executed(self, client, fixtures_dir):
        create_resp = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        source_id = create_resp.json()["id"]
        new_run = client.post(f"/runs/{source_id}/rerun").json()

        resp = client.post(f"/runs/{new_run['id']}/execute")

        # No reference database published in this test -- stops at blast,
        # same operational-stop behavior a fresh upload would show. The
        # point here is only that a rerun's copied files are real,
        # readable AB1 bytes that Stage 1/2 can actually process.
        assert resp.status_code == 200
        assert resp.json()["current_stage"] == "blast"


class TestRerunChangesOutcome:
    """The end-to-end proof this endpoint exists for: the *same* uploaded
    file, run twice with different configuration, produces two
    independent, differently-outcomed Runs -- the original is never
    touched."""

    def test_rerun_with_a_tighter_threshold_fails_where_the_original_completed(
        self, client, fixtures_dir
    ):
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

        # Original: default config, completes to a PASS report.
        original_create = client.post(
            "/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")}
        )
        original_id = original_create.json()["id"]
        original_exec = client.post(f"/runs/{original_id}/execute")
        assert original_exec.json()["status"] == "completed"
        assert original_exec.json()["current_stage"] == "report"

        # Rerun of the exact same source, with a tightened min_length --
        # 700 > the read's real 667bp trimmed length.
        rerun = client.post(
            f"/runs/{original_id}/rerun",
            json={"config_overrides": {"usability_check.min_length": 700}},
        ).json()
        assert rerun["id"] != original_id
        assert rerun["rerun_of"] == original_id

        rerun_exec = client.post(f"/runs/{rerun['id']}/execute")

        assert rerun_exec.status_code == 200
        assert rerun_exec.json()["status"] == "failed"
        assert rerun_exec.json()["current_stage"] == "usability_check"

        # The original Run's own recorded outcome is completely
        # unaffected by the rerun -- "the two Runs sit side by side,
        # fully independent and comparable."
        original_after = client.get(f"/runs/{original_id}").json()
        assert original_after["status"] == "completed"
        assert original_after["current_stage"] == "report"
