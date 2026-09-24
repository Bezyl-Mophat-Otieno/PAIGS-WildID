"""Password hashing + JWT helpers (app.auth.security) -- unit tests, no
DB or HTTP involved."""
import datetime as dt

import jwt
import pytest

from app.auth.security import (
    JWT_ALGORITHM,
    JWT_SECRET,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_the_plaintext(self):
        assert hash_password("correct horse battery staple") != "correct horse battery staple"

    def test_verify_succeeds_for_the_correct_password(self):
        hashed = hash_password("correct horse battery staple")

        assert verify_password("correct horse battery staple", hashed) is True

    def test_verify_fails_for_the_wrong_password(self):
        hashed = hash_password("correct horse battery staple")

        assert verify_password("wrong password", hashed) is False

    def test_hashing_the_same_password_twice_gives_different_hashes(self):
        # bcrypt salts each hash -- this is what makes a stolen
        # hashed_password column useless against rainbow tables.
        assert hash_password("same password") != hash_password("same password")


class TestAccessTokens:
    def test_decode_round_trips_the_user_id_and_role(self):
        token = create_access_token("user-123", "admin")

        payload = decode_access_token(token)

        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"

    def test_decode_rejects_a_tampered_token(self):
        token = create_access_token("user-123", "admin")
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        with pytest.raises(jwt.PyJWTError):
            decode_access_token(tampered)

    def test_decode_rejects_a_token_signed_with_a_different_secret(self):
        forged = jwt.encode(
            {"sub": "user-123", "role": "admin"}, "not-the-real-secret", algorithm=JWT_ALGORITHM
        )

        with pytest.raises(jwt.PyJWTError):
            decode_access_token(forged)

    def test_decode_rejects_an_expired_token(self):
        now = dt.datetime.now(dt.timezone.utc)
        expired_payload = {
            "sub": "user-123",
            "role": "admin",
            "iat": now - dt.timedelta(hours=2),
            "exp": now - dt.timedelta(hours=1),
        }
        expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        with pytest.raises(jwt.PyJWTError):
            decode_access_token(expired_token)
