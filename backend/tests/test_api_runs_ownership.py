"""Runs are scoped per-owner: whoever creates a Run (admin or analyst --
role doesn't matter for this) is the only one who can see or act on it,
for now. CLAUDE.md doesn't mention this -- it's a direct product
decision: "all runs should be scoped to a tenant ... be it an admin or
a mere analyst they should be able to view their work," with a
deliberate note that giving admin cross-tenant visibility is a later
step, not this one -- so today an admin's own view of /runs is scoped
exactly like an analyst's.

Uses the `analyst_client` / `anon_client` fixtures (tests/conftest.py) --
`client` is already authenticated as the seeded default admin.
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


class TestRequiresAuthentication:
    def test_create_run_requires_a_token(self, anon_client, fixtures_dir):
        resp = anon_client.post("/runs", files={"forward_read": _file_field(fixtures_dir, "3100.ab1")})

        assert resp.status_code == 401

    def test_list_runs_requires_a_token(self, anon_client):
        resp = anon_client.get("/runs")

        assert resp.status_code == 401

    def test_get_run_requires_a_token(self, anon_client):
        resp = anon_client.get("/runs/some-id")

        assert resp.status_code == 401


class TestOwnership:
    def test_created_run_is_owned_by_the_creating_user(self, client, fixtures_dir):
        run = _create_run(client, fixtures_dir)

        me = client.get("/auth/me").json()

        assert run["owner_id"] == me["id"]

    def test_list_runs_only_returns_the_callers_own_runs(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir, "3100.ab1")
        analyst_run = _create_run(analyst_client, fixtures_dir, "3730.ab1")

        admin_view = client.get("/runs").json()
        analyst_view = analyst_client.get("/runs").json()

        admin_ids = {r["id"] for r in admin_view}
        analyst_ids = {r["id"] for r in analyst_view}
        assert admin_run["id"] in admin_ids
        assert analyst_run["id"] not in admin_ids
        assert analyst_run["id"] in analyst_ids
        assert admin_run["id"] not in analyst_ids

    def test_get_run_on_someone_elses_run_is_404_not_403(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir)

        resp = analyst_client.get(f"/runs/{admin_run['id']}")

        # 404, not 403 -- an analyst shouldn't be able to confirm another
        # user's run even exists.
        assert resp.status_code == 404

    def test_get_stage_on_someone_elses_run_is_404(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir)

        resp = analyst_client.get(f"/runs/{admin_run['id']}/stages/import")

        assert resp.status_code == 404

    def test_execute_on_someone_elses_run_is_404(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir)

        resp = analyst_client.post(f"/runs/{admin_run['id']}/execute")

        assert resp.status_code == 404

    def test_rerun_on_someone_elses_run_is_404(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir)

        resp = analyst_client.post(f"/runs/{admin_run['id']}/rerun")

        assert resp.status_code == 404

    def test_rerun_is_owned_by_whoever_triggered_it(self, client, fixtures_dir):
        source_run = _create_run(client, fixtures_dir)
        me = client.get("/auth/me").json()

        resp = client.post(f"/runs/{source_run['id']}/rerun")

        assert resp.status_code == 201
        assert resp.json()["owner_id"] == me["id"]

    def test_patch_on_someone_elses_run_is_404(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir)

        resp = analyst_client.patch(f"/runs/{admin_run['id']}", json={"sample_id": "HIJACKED"})

        assert resp.status_code == 404

    def test_report_download_on_someone_elses_run_is_404(self, client, analyst_client, fixtures_dir):
        admin_run = _create_run(client, fixtures_dir)

        resp = analyst_client.get(f"/runs/{admin_run['id']}/report")

        assert resp.status_code == 404

    def test_owner_can_still_do_everything_on_their_own_run(self, client, fixtures_dir):
        run = _create_run(client, fixtures_dir)

        assert client.get(f"/runs/{run['id']}").status_code == 200
        assert client.get(f"/runs/{run['id']}/stages/import").status_code == 200
        assert client.patch(f"/runs/{run['id']}", json={"sample_id": "STILL_MINE"}).status_code == 200
