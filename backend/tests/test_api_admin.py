"""POST /admin/invite, GET /admin/users -- HTTP-level tests."""
from app.auth import service as auth_service


def _admin_token(client):
    resp = client.post(
        "/auth/login",
        data={"username": auth_service.ADMIN_EMAIL, "password": auth_service.ADMIN_PASSWORD},
    )
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestInviteUser:
    def test_admin_can_invite_an_analyst(self, client):
        token = _admin_token(client)

        resp = client.post(
            "/admin/invite",
            json={"email": "newanalyst@example.com", "role": "analyst"},
            headers=_auth_headers(token),
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["user"]["email"] == "newanalyst@example.com"
        assert body["user"]["role"] == "analyst"
        assert body["temporary_password"]
        assert "hashed_password" not in body["user"]

    def test_the_returned_credentials_actually_log_in(self, client):
        token = _admin_token(client)
        invite = client.post(
            "/admin/invite",
            json={"email": "loginme@example.com", "role": "analyst"},
            headers=_auth_headers(token),
        ).json()

        resp = client.post(
            "/auth/login",
            data={"username": "loginme@example.com", "password": invite["temporary_password"]},
        )

        assert resp.status_code == 200
        assert resp.json()["role"] == "analyst"

    def test_email_delivery_is_stubbed_not_actually_sent(self, client):
        token = _admin_token(client)

        resp = client.post(
            "/admin/invite",
            json={"email": "stubcheck@example.com", "role": "analyst"},
            headers=_auth_headers(token),
        )

        body = resp.json()
        assert body["email"]["to"] == "stubcheck@example.com"
        assert body["email"]["delivered"] is False

    def test_defaults_to_the_analyst_role_when_omitted(self, client):
        token = _admin_token(client)

        resp = client.post(
            "/admin/invite", json={"email": "defaultrole@example.com"}, headers=_auth_headers(token)
        )

        assert resp.json()["user"]["role"] == "analyst"

    def test_duplicate_email_is_rejected(self, client):
        token = _admin_token(client)
        client.post(
            "/admin/invite",
            json={"email": "dup@example.com", "role": "analyst"},
            headers=_auth_headers(token),
        )

        resp = client.post(
            "/admin/invite",
            json={"email": "dup@example.com", "role": "analyst"},
            headers=_auth_headers(token),
        )

        assert resp.status_code == 409

    def test_non_admin_cannot_invite(self, client):
        admin_token = _admin_token(client)
        invite = client.post(
            "/admin/invite",
            json={"email": "plainanalyst@example.com", "role": "analyst"},
            headers=_auth_headers(admin_token),
        ).json()
        analyst_token = client.post(
            "/auth/login",
            data={"username": "plainanalyst@example.com", "password": invite["temporary_password"]},
        ).json()["access_token"]

        resp = client.post(
            "/admin/invite",
            json={"email": "shouldfail@example.com", "role": "analyst"},
            headers=_auth_headers(analyst_token),
        )

        assert resp.status_code == 403

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/admin/invite", json={"email": "noauth@example.com", "role": "analyst"})

        assert resp.status_code == 401

    def test_malformed_email_is_rejected(self, client):
        token = _admin_token(client)

        resp = client.post(
            "/admin/invite",
            json={"email": "not-an-email", "role": "analyst"},
            headers=_auth_headers(token),
        )

        assert resp.status_code == 422


class TestListUsers:
    def test_admin_sees_the_seeded_admin_and_every_invited_user(self, client):
        token = _admin_token(client)
        client.post(
            "/admin/invite",
            json={"email": "listed@example.com", "role": "analyst"},
            headers=_auth_headers(token),
        )

        resp = client.get("/admin/users", headers=_auth_headers(token))

        assert resp.status_code == 200
        emails = {row["email"] for row in resp.json()}
        assert auth_service.ADMIN_EMAIL in emails
        assert "listed@example.com" in emails

    def test_passwords_are_never_exposed(self, client):
        token = _admin_token(client)

        resp = client.get("/admin/users", headers=_auth_headers(token))

        for row in resp.json():
            assert "hashed_password" not in row
            assert "password" not in row

    def test_non_admin_cannot_list_users(self, client):
        admin_token = _admin_token(client)
        invite = client.post(
            "/admin/invite",
            json={"email": "cantlistusers@example.com", "role": "analyst"},
            headers=_auth_headers(admin_token),
        ).json()
        analyst_token = client.post(
            "/auth/login",
            data={"username": "cantlistusers@example.com", "password": invite["temporary_password"]},
        ).json()["access_token"]

        resp = client.get("/admin/users", headers=_auth_headers(analyst_token))

        assert resp.status_code == 403
