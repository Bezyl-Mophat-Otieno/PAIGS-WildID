"""GET/PUT /config -- HTTP-level tests.

GET is open to any authenticated user (an analyst needs to see current
thresholds when creating a run); PUT is admin-only -- a global threshold
change affects every future Run for every user, not just the caller's
own, the same reasoning that makes POST /reference-database/publish
admin-only (see tests/test_api_reference.py).
"""
from app.configuration.catalog import CATALOG


class TestListConfig:
    def test_returns_all_catalog_entries_seeded_with_defaults(self, client):
        resp = client.get("/config")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == len(CATALOG)
        by_key = {row["key"]: row for row in body}
        for definition in CATALOG:
            row = by_key[definition.key]
            assert row["value"] == definition.default
            assert row["default"] == definition.default
            assert row["stage_type"] == definition.stage_type
            assert row["param_name"] == definition.param_name
            assert row["value_type"] == definition.value_type
            assert row["label"]
            assert row["description"]


class TestUpdateConfig:
    def test_updates_the_value(self, client):
        rows = client.get("/config").json()
        row = next(r for r in rows if r["key"] == "usability_check.min_length")

        resp = client.put(f"/config/{row['id']}", json={"value": 400})

        assert resp.status_code == 200
        assert resp.json()["value"] == 400

    def test_a_later_get_reflects_the_update(self, client):
        rows = client.get("/config").json()
        row = next(r for r in rows if r["key"] == "blast.max_hits")
        client.put(f"/config/{row['id']}", json={"value": 20})

        rows_after = client.get("/config").json()
        row_after = next(r for r in rows_after if r["key"] == "blast.max_hits")
        assert row_after["value"] == 20

    def test_returns_404_for_unknown_id(self, client):
        resp = client.put("/config/does-not-exist", json={"value": 1})
        assert resp.status_code == 404

    def test_returns_422_for_a_value_outside_bounds(self, client):
        rows = client.get("/config").json()
        row = next(r for r in rows if r["key"] == "sanity_check.max_n_proportion")

        resp = client.put(f"/config/{row['id']}", json={"value": 5.0})

        assert resp.status_code == 422


class TestConfigRequiresAuthentication:
    def test_list_config_requires_a_token(self, anon_client):
        resp = anon_client.get("/config")

        assert resp.status_code == 401

    def test_update_config_requires_a_token(self, anon_client):
        resp = anon_client.put("/config/some-id", json={"value": 1})

        assert resp.status_code == 401

    def test_an_analyst_can_read_config(self, analyst_client):
        resp = analyst_client.get("/config")

        assert resp.status_code == 200

    def test_an_analyst_cannot_update_config(self, client, analyst_client):
        rows = client.get("/config").json()
        row = rows[0]

        resp = analyst_client.put(f"/config/{row['id']}", json={"value": row["value"]})

        assert resp.status_code == 403
