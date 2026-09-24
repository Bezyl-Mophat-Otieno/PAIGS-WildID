"""
Stage 0 (Import) API tests -- updated for the 2026-09-23 CLAUDE.md rewrite:
upload goes into two labeled, independently-optional slots (forward_read /
reverse_read), and a single file is a fully-supported first-class path, not
a degraded fallback. Written against the new contract before touching the
implementation (strict TDD, confirmed red against the old "files" list API).
"""
import io
from pathlib import Path


def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


class TestCreateRun:
    def test_create_run_with_forward_and_reverse_files(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body and body["id"]
        assert body["current_stage"] == "import"
        assert body["status"] == "in_progress"
        assert body["original_filenames"] == ["3100.ab1", "3730.ab1"]
        assert "3100" in body["sample_id"]
        assert "3730" in body["sample_id"]

    def test_create_run_with_forward_read_only(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["original_filenames"] == ["3100.ab1"]
        assert body["current_stage"] == "import"
        assert body["status"] == "in_progress"
        assert "3100" in body["sample_id"]

    def test_create_run_with_reverse_read_only(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"reverse_read": _file_field(fixtures_dir, "3730.ab1")},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["original_filenames"] == ["3730.ab1"]
        assert "3730" in body["sample_id"]

    def test_create_run_with_explicit_label(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            data={"sample_id": "WILD_042"},
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        )

        assert resp.status_code == 201
        assert resp.json()["sample_id"] == "WILD_042"

    def test_create_run_accepts_labels_regardless_of_true_orientation(self, client, fixtures_dir):
        """Stage 0 doesn't validate forward/reverse correctness -- that's Stage 5's job."""
        resp = client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3730.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3100.ab1"),
            },
        )

        assert resp.status_code == 201
        assert resp.json()["original_filenames"] == ["3730.ab1", "3100.ab1"]

    def test_import_stage_output_records_slots_used_for_two_files(self, client, fixtures_dir):
        """
        Orchestration (POST /runs/{id}/execute) needs to know which upload
        slot a stored file actually came from -- "stored_filenames" alone
        is ambiguous for a single-file run (a lone forward_read and a lone
        reverse_read both produce a one-element list). "slots" records
        this explicitly, in the same order as stored_filenames.
        """
        resp = client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        )
        run_id = resp.json()["id"]

        stage_resp = client.get(f"/runs/{run_id}/stages/import")

        assert stage_resp.json()["output"]["slots"] == ["forward", "reverse"]

    def test_import_stage_output_records_slot_for_forward_only(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
        )
        run_id = resp.json()["id"]

        stage_resp = client.get(f"/runs/{run_id}/stages/import")

        assert stage_resp.json()["output"]["slots"] == ["forward"]

    def test_import_stage_output_records_slot_for_reverse_only(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"reverse_read": _file_field(fixtures_dir, "3730.ab1")},
        )
        run_id = resp.json()["id"]

        stage_resp = client.get(f"/runs/{run_id}/stages/import")

        assert stage_resp.json()["output"]["slots"] == ["reverse"]

    def test_create_run_rejects_when_no_files_provided(self, client):
        resp = client.post("/runs", data={"sample_id": "WILD_EMPTY"})

        assert resp.status_code == 422

    def test_create_run_rejects_non_ab1_extension(self, client, fixtures_dir):
        payload = {
            "forward_read": _file_field(fixtures_dir, "3100.ab1"),
            "reverse_read": ("notes.txt", io.BytesIO(b"not a sequence file"), "text/plain"),
        }

        resp = client.post("/runs", files=payload)

        assert resp.status_code == 422

    def test_create_run_rejects_non_ab1_extension_single_file(self, client):
        payload = {"forward_read": ("notes.txt", io.BytesIO(b"not a sequence file"), "text/plain")}

        resp = client.post("/runs", files=payload)

        assert resp.status_code == 422

    def test_uploaded_files_are_stored_byte_for_byte(self, client, fixtures_dir, temp_storage_root):
        resp = client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        )
        run_id = resp.json()["id"]

        run_dir = temp_storage_root / "runs" / run_id
        stored_files = sorted(run_dir.iterdir())

        assert len(stored_files) == 2
        for stored in stored_files:
            original = fixtures_dir / stored.name
            assert stored.read_bytes() == original.read_bytes()

    def test_uploaded_single_file_is_stored_byte_for_byte(self, client, fixtures_dir, temp_storage_root):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
        )
        run_id = resp.json()["id"]

        run_dir = temp_storage_root / "runs" / run_id
        stored_files = list(run_dir.iterdir())

        assert len(stored_files) == 1
        assert stored_files[0].read_bytes() == (fixtures_dir / "3100.ab1").read_bytes()


class TestListAndGetRun:
    def _create_two_file_run(self, client, fixtures_dir):
        return client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        ).json()

    def test_list_runs_includes_created_run(self, client, fixtures_dir):
        created = self._create_two_file_run(client, fixtures_dir)

        resp = client.get("/runs")

        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert created["id"] in ids

    def test_get_run_returns_summary_with_stage_statuses(self, client, fixtures_dir):
        created = self._create_two_file_run(client, fixtures_dir)

        resp = client.get(f"/runs/{created['id']}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == created["id"]
        stage_statuses = {s["stage_type"]: s["status"] for s in body["stages"]}
        assert stage_statuses.get("import") == "completed"

    def test_get_unknown_run_returns_404(self, client):
        resp = client.get("/runs/does-not-exist")

        assert resp.status_code == 404

    def test_get_import_stage_output(self, client, fixtures_dir):
        created = self._create_two_file_run(client, fixtures_dir)

        resp = client.get(f"/runs/{created['id']}/stages/import")

        assert resp.status_code == 200
        body = resp.json()
        assert body["stage_type"] == "import"
        assert body["status"] == "completed"
        assert body["output"]["original_filenames"] == ["3100.ab1", "3730.ab1"]

    def test_get_stage_output_for_unknown_run_returns_404(self, client):
        resp = client.get("/runs/does-not-exist/stages/import")

        assert resp.status_code == 404


class TestPatchRun:
    def _create_two_file_run(self, client, fixtures_dir):
        return client.post(
            "/runs",
            files={
                "forward_read": _file_field(fixtures_dir, "3100.ab1"),
                "reverse_read": _file_field(fixtures_dir, "3730.ab1"),
            },
        ).json()

    def test_patch_run_updates_label(self, client, fixtures_dir):
        created = self._create_two_file_run(client, fixtures_dir)

        resp = client.patch(f"/runs/{created['id']}", json={"sample_id": "WILD_099"})

        assert resp.status_code == 200
        assert resp.json()["sample_id"] == "WILD_099"

        refetched = client.get(f"/runs/{created['id']}").json()
        assert refetched["sample_id"] == "WILD_099"

    def test_patch_unknown_run_returns_404(self, client):
        resp = client.patch("/runs/does-not-exist", json={"sample_id": "X"})

        assert resp.status_code == 404

    def test_patch_run_rejects_empty_label(self, client, fixtures_dir):
        created = self._create_two_file_run(client, fixtures_dir)

        resp = client.patch(f"/runs/{created['id']}", json={"sample_id": ""})

        assert resp.status_code == 422


class TestCreateRunWithConfigOverrides:
    """POST /runs' 'optional config overrides' (CLAUDE.md's API shape) --
    a JSON object of {catalog key: value}, sent as a form-data text field
    alongside the file upload(s) since the request is already
    multipart/form-data. Execution-time effect (does an override actually
    change the pipeline's outcome) is covered in test_api_execute.py;
    these tests are about create_run's own validation and storage of it.
    """

    def test_accepts_and_stores_valid_config_overrides(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"config_overrides": '{"usability_check.min_length": 300}'},
        )

        assert resp.status_code == 201
        assert resp.json()["config_overrides"] == {"usability_check.min_length": 300}

    def test_omitting_config_overrides_leaves_it_null(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
        )

        assert resp.status_code == 201
        assert resp.json()["config_overrides"] is None

    def test_rejects_invalid_json(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"config_overrides": "{not valid json"},
        )

        assert resp.status_code == 422

    def test_rejects_a_json_value_that_is_not_an_object(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"config_overrides": "[1, 2, 3]"},
        )

        assert resp.status_code == 422

    def test_rejects_an_unknown_config_key(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"config_overrides": '{"not_a_real.key": 1}'},
        )

        assert resp.status_code == 422

    def test_rejects_an_out_of_bounds_value(self, client, fixtures_dir):
        resp = client.post(
            "/runs",
            files={"forward_read": _file_field(fixtures_dir, "3100.ab1")},
            data={"config_overrides": '{"orientation.min_identity": 2.0}'},
        )

        assert resp.status_code == 422
