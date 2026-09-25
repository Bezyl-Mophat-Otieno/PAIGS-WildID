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
