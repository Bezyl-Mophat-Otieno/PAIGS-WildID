"""CORS -- the frontend (a React SPA on its own dev-server origin, e.g.
http://localhost:5173) cannot call this API at all without it: browsers
block a cross-origin fetch unless the server's response carries the
right Access-Control-Allow-* headers. Nothing else about the API surface
matters to a browser-based frontend until this is in place.

Origins are configurable (PAIGS_CORS_ORIGINS, comma-separated), same
env-var-with-a-documented-fallback convention as every other setting in
this app (see app/db.py's DATABASE_URL, app/auth/service.py's
ADMIN_EMAIL). The fallback is permissive ("*") since this is still a
prototype with no fixed frontend origin yet -- allow_credentials is
deliberately False (this API is authenticated via a Bearer token in the
Authorization header, not cookies, so a wildcard origin is safe; the two
together are otherwise rejected by browsers/Starlette).
"""


class TestCORS:
    def test_preflight_allows_the_requested_origin(self, client):
        resp = client.options(
            "/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] in ("*", "http://localhost:5173")

    def test_actual_response_carries_the_cors_header(self, client):
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})

        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    def test_authorization_header_is_an_allowed_request_header(self, client):
        resp = client.options(
            "/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

        assert resp.status_code == 200
        allowed = resp.headers.get("access-control-allow-headers", "")
        assert allowed == "*" or "authorization" in allowed.lower()
