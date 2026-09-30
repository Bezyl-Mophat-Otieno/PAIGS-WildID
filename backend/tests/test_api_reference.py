"""
Reference Database API tests -- the admin HTTP equivalent of running
scripts/publish_reference_db.py by hand, per the user's explicit request
not to require the manual script path.

Written first, against the not-yet-existing app.api.reference module, to
confirm red before implementing. Calls the exact same
app.reference.publish.publish_reference_db() the CLI script and
tests/test_reference_publish.py already exercise directly -- these tests
cover the HTTP layer (upload handling, status codes, response shapes),
not the publish logic itself again.

GET /versions and GET /active are open to any authenticated user (an
analyst needs to see which reference database is active). POST /publish
is admin-only -- publishing a new version changes what every future
Run's Stage 9 search sees for every user, not just the caller's own, the
same reasoning that makes PUT /config/{id} admin-only (see
tests/test_api_config.py).
"""
from pathlib import Path

SYNTHETIC_FASTA = """\
>SYNTH001 Panthera leo | Felidae
ATGGCCAACGTACTAGTAATGATCGGAGGATTTGGAAACTGACTAGTGCCTCTAATAATCGGGGCCCCA
GACATAGCATTTCCACGAATAAATAATATAAGCTTCTGACTTCTCCCTCCTTCTTTCCTATTACTCCTA
>SYNTH002 Panthera pardus
ATGGCCAACGTACTAGTAATGATCGGAGGATTTGGCAACTGACTAGTGCCTCTAATAATCGGGGCCCCT
GACATAGCATTTCCACGAATAAATAATATAAGCTTCTGACTTCTCCCTCCTTCTTTCCTATTACTCCTG
"""


def _publish(client, version, content=SYNTHETIC_FASTA, filename="reference.fasta"):
    return client.post(
        "/reference-database/publish",
        files={"fasta": (filename, content, "text/plain")},
        data={"version": version},
    )


class TestPublishEndpoint:
    def test_publishes_successfully(self, client, temp_reference_data_root):
        response = _publish(client, "v1")

        assert response.status_code == 201
        body = response.json()
        assert body["version"] == "v1"
        assert body["sequence_count"] == 2
        assert Path(body["fasta_path"]).is_file()
        assert Path(body["db_prefix"] + ".nhr").is_file()

    def test_rejects_malformed_fasta(self, client, temp_reference_data_root):
        response = _publish(client, "v1", content="not a fasta file at all\n")

        assert response.status_code == 422

    def test_rejects_empty_version(self, client, temp_reference_data_root):
        response = _publish(client, "   ")

        assert response.status_code == 422

    def test_rejects_non_fasta_filename(self, client, temp_reference_data_root):
        response = _publish(client, "v1", filename="reference.txt")

        assert response.status_code == 422

    def test_published_version_becomes_active(self, client, temp_reference_data_root):
        _publish(client, "v1")

        response = client.get("/reference-database/active")

        assert response.status_code == 200
        assert response.json()["version"] == "v1"
        assert response.json()["is_active"] is True

    def test_republishing_a_new_version_deactivates_the_old_one(self, client, temp_reference_data_root):
        _publish(client, "v1")
        _publish(client, "v2")

        active = client.get("/reference-database/active").json()
        versions = {v["version"]: v["is_active"] for v in client.get("/reference-database/versions").json()}

        assert active["version"] == "v2"
        assert versions == {"v1": False, "v2": True}


class TestListVersionsEndpoint:
    def test_empty_before_anything_published(self, client, temp_reference_data_root):
        response = client.get("/reference-database/versions")

        assert response.status_code == 200
        assert response.json() == []

    def test_lists_published_versions_newest_first(self, client, temp_reference_data_root):
        _publish(client, "v1")
        _publish(client, "v2")

        response = client.get("/reference-database/versions")
        versions = [v["version"] for v in response.json()]

        assert versions == ["v2", "v1"]


class TestActiveVersionEndpoint:
    def test_404_before_anything_published(self, client, temp_reference_data_root):
        response = client.get("/reference-database/active")

        assert response.status_code == 404

    def test_reflects_the_most_recently_published_version(self, client, temp_reference_data_root):
        _publish(client, "v1")
        _publish(client, "v2")

        response = client.get("/reference-database/active")

        assert response.json()["version"] == "v2"


class TestReferenceDatabaseRequiresAuthentication:
    def test_publish_requires_a_token(self, anon_client, temp_reference_data_root):
        response = _publish(anon_client, "v1")
        assert response.status_code == 401

    def test_list_versions_requires_a_token(self, anon_client, temp_reference_data_root):
        response = anon_client.get("/reference-database/versions")
        assert response.status_code == 401

    def test_active_version_requires_a_token(self, anon_client, temp_reference_data_root):
        response = anon_client.get("/reference-database/active")
        assert response.status_code == 401

    def test_an_analyst_can_list_versions(self, analyst_client, temp_reference_data_root):
        response = analyst_client.get("/reference-database/versions")
        assert response.status_code == 200

    def test_an_analyst_can_read_the_active_version(self, client, analyst_client, temp_reference_data_root):
        _publish(client, "v1")
        response = analyst_client.get("/reference-database/active")
        assert response.status_code == 200

    def test_an_analyst_cannot_publish(self, analyst_client, temp_reference_data_root):
        response = _publish(analyst_client, "v1")
        assert response.status_code == 403


def _fake_fetch_result(taxon="Panthera"):
    from app.reference.bold import BoldFetchResult, BoldSpeciesSummary

    return BoldFetchResult(
        taxon=taxon,
        marker="COI-5P",
        fasta_content=">AAA001-01 Panthera leo | Felidae;Panthera;Panthera leo\n" + "ACGT" * 100 + "\n",
        species=[
            BoldSpeciesSummary(species="Panthera leo", kept_count=1, dropped_count=0, bins=["BOLD:AAA0001"])
        ],
        total_fetched=1,
        total_kept=1,
        drop_reasons={},
        species_sharing_a_bin=[],
    )


class TestSuggestedTaxaEndpoint:
    def test_returns_a_non_empty_list_open_to_any_authenticated_user(self, analyst_client):
        response = analyst_client.get("/reference-database/suggested-taxa")

        assert response.status_code == 200
        assert len(response.json()) > 0

    def test_requires_a_token(self, anon_client):
        response = anon_client.get("/reference-database/suggested-taxa")
        assert response.status_code == 401


class TestCreateDraftEndpoint:
    def test_creates_a_pending_review_draft(self, client, temp_reference_data_root, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )

        response = client.post("/reference-database/drafts", json={"taxon": "Panthera"})

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending_review"
        assert body["taxon"] == "Panthera"
        assert body["summary"]["total_kept"] == 1
        assert body["summary"]["species"][0]["species"] == "Panthera leo"

    def test_returns_422_for_an_unrecognized_taxon(self, client, temp_reference_data_root, monkeypatch):
        from app.reference.bold import BoldApiError

        def _raise(taxon, **kw):
            raise BoldApiError(f"BOLD didn't recognize {taxon!r}.")

        monkeypatch.setattr("app.reference.drafts.fetch_bold_taxon", _raise)

        response = client.post("/reference-database/drafts", json={"taxon": "Notarealtaxonxyz"})

        assert response.status_code == 422

    def test_rejects_blank_taxon(self, client, temp_reference_data_root):
        response = client.post("/reference-database/drafts", json={"taxon": ""})
        assert response.status_code == 422

    def test_an_analyst_cannot_create_a_draft(self, analyst_client, temp_reference_data_root):
        response = analyst_client.post("/reference-database/drafts", json={"taxon": "Panthera"})
        assert response.status_code == 403

    def test_requires_a_token(self, anon_client):
        response = anon_client.post("/reference-database/drafts", json={"taxon": "Panthera"})
        assert response.status_code == 401


class TestListAndGetDraftEndpoints:
    def test_list_and_get_round_trip(self, client, temp_reference_data_root, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        create_resp = client.post("/reference-database/drafts", json={"taxon": "Panthera"})
        draft_id = create_resp.json()["id"]

        list_resp = client.get("/reference-database/drafts")
        assert list_resp.status_code == 200
        assert any(d["id"] == draft_id for d in list_resp.json())

        get_resp = client.get(f"/reference-database/drafts/{draft_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == draft_id

    def test_get_returns_404_for_unknown_id(self, client):
        response = client.get("/reference-database/drafts/does-not-exist")
        assert response.status_code == 404

    def test_an_analyst_cannot_list_drafts(self, analyst_client):
        response = analyst_client.get("/reference-database/drafts")
        assert response.status_code == 403


class TestDiscardDraftEndpoint:
    def test_discarding_a_pending_draft(self, client, temp_reference_data_root, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        create_resp = client.post("/reference-database/drafts", json={"taxon": "Panthera"})
        draft_id = create_resp.json()["id"]

        response = client.post(f"/reference-database/drafts/{draft_id}/discard")

        assert response.status_code == 200
        assert response.json()["status"] == "discarded"

    def test_discarding_twice_returns_409(self, client, temp_reference_data_root, monkeypatch):
        monkeypatch.setattr(
            "app.reference.drafts.fetch_bold_taxon", lambda taxon, **kw: _fake_fetch_result(taxon)
        )
        create_resp = client.post("/reference-database/drafts", json={"taxon": "Panthera"})
        draft_id = create_resp.json()["id"]
        client.post(f"/reference-database/drafts/{draft_id}/discard")

        response = client.post(f"/reference-database/drafts/{draft_id}/discard")

        assert response.status_code == 409

    def test_discarding_unknown_draft_returns_404(self, client):
        response = client.post("/reference-database/drafts/does-not-exist/discard")
        assert response.status_code == 404
