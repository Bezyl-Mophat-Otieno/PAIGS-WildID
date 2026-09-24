"""POST /auth/login, GET /auth/me -- HTTP-level tests."""
from app.auth import service as auth_service


def _login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


class TestLogin:
    def test_default_admin_can_log_in_with_the_seeded_credentials(self, client):
        resp = _login(client, auth_service.ADMIN_EMAIL, auth_service.ADMIN_PASSWORD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["role"] == "admin"
        assert body["email"] == auth_service.ADMIN_EMAIL
        assert body["access_token"]

    def test_wrong_password_is_rejected(self, client):
        resp = _login(client, auth_service.ADMIN_EMAIL, "not-the-real-password")

        assert resp.status_code == 401

    def test_unknown_email_is_rejected(self, client):
        resp = _login(client, "nobody@example.com", "whatever")

        assert resp.status_code == 401


class TestMe:
    def test_requires_a_token(self, anon_client):
        resp = anon_client.get("/auth/me")

        assert resp.status_code == 401

    def test_returns_the_authenticated_users_own_profile(self, client):
        token = _login(client, auth_service.ADMIN_EMAIL, auth_service.ADMIN_PASSWORD).json()[
            "access_token"
        ]

        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == auth_service.ADMIN_EMAIL
        assert body["role"] == "admin"
        assert "hashed_password" not in body

    def test_rejects_a_garbage_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

        assert resp.status_code == 401
