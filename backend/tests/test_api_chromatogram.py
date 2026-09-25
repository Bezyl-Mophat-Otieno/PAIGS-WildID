"""GET /runs/{run_id}/chromatogram/{slot} -- HTTP-level tests.

Written first, against the not-yet-existing endpoint, to confirm red
before implementing. Function-level extraction correctness lives in
test_chromatogram.py; this covers routing, auth, and the
ownership/visibility rules the rest of /runs already follows.
"""
import io
from pathlib import Path


def _file_field(fixtures_dir: Path, name: str):
    data = (fixtures_dir / name).read_bytes()
    return (name, io.BytesIO(data), "application/octet-stream")


def _create_run(caller, fixtures_dir, **file_slots):
    files = {slot: _file_field(fixtures_dir, filename) for slot, filename in file_slots.items()}
    resp = caller.post("/runs", files=files)
    assert resp.status_code == 201
    return resp.json()


class TestRequiresAuthentication:
    def test_requires_a_token(self, anon_client):
        resp = anon_client.get("/runs/some-id/chromatogram/forward")

        assert resp.status_code == 401


class TestGetChromatogram:
    def test_returns_the_forward_reads_chromatogram(self, client, fixtures_dir):
        run = _create_run(client, fixtures_dir, forward_read="3100.ab1")

        resp = client.get(f"/runs/{run['id']}/chromatogram/forward")

        assert resp.status_code == 200
        body = resp.json()
        assert body["channel_order"] == ["G", "A", "T", "C"]
        assert set(body["trace"].keys()) == {"G", "A", "T", "C"}
        assert body["num_samples"] > 0
        assert len(body["peak_locations"]) == len(body["base_calls"]) == 795

    def test_404_for_a_slot_that_was_never_uploaded(self, client, fixtures_dir):
        run = _create_run(client, fixtures_dir, forward_read="3100.ab1")

        resp = client.get(f"/runs/{run['id']}/chromatogram/reverse")

        assert resp.status_code == 404

    def test_both_slots_available_on_a_two_file_run(self, client, fixtures_dir):
        run = _create_run(
            client, fixtures_dir, forward_read="3100.ab1", reverse_read="3730.ab1"
        )

        forward_resp = client.get(f"/runs/{run['id']}/chromatogram/forward")
        reverse_resp = client.get(f"/runs/{run['id']}/chromatogram/reverse")

        assert forward_resp.status_code == 200
        assert reverse_resp.status_code == 200
        assert forward_resp.json()["base_calls"] != reverse_resp.json()["base_calls"]

    def test_422_for_an_invalid_slot_name(self, client, fixtures_dir):
        run = _create_run(client, fixtures_dir, forward_read="3100.ab1")

        resp = client.get(f"/runs/{run['id']}/chromatogram/sideways")

        assert resp.status_code == 422

    def test_404_for_an_unknown_run(self, client):
        resp = client.get("/runs/does-not-exist/chromatogram/forward")

        assert resp.status_code == 404


class TestOwnershipAndVisibility:
    def test_an_analyst_cannot_view_someone_elses_chromatogram(
        self, client, analyst_client, fixtures_dir
    ):
        admin_run = _create_run(client, fixtures_dir, forward_read="3100.ab1")

        resp = analyst_client.get(f"/runs/{admin_run['id']}/chromatogram/forward")

        assert resp.status_code == 404

    def test_an_admin_can_view_an_analysts_chromatogram(
        self, client, analyst_client, fixtures_dir
    ):
        analyst_run = _create_run(analyst_client, fixtures_dir, forward_read="3100.ab1")

        resp = client.get(f"/runs/{analyst_run['id']}/chromatogram/forward")

        assert resp.status_code == 200
