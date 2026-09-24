"""app.auth.service -- unit tests against a raw DB session (db_session
fixture), no HTTP involved. Mirrors app.configuration's own
test_configuration_service.py in shape."""
import pytest

from app.auth import service as auth_service
from app.auth.errors import EmailAlreadyExistsError, InvalidCredentialsError, InvalidRoleError
from app.auth.security import verify_password
from app.models.user import User


class TestEnsureDefaultAdmin:
    def test_creates_exactly_one_admin_seeded_from_env_defaults(self, db_session):
        auth_service.ensure_default_admin(db_session)

        admins = db_session.query(User).filter(User.role == "admin").all()
        assert len(admins) == 1
        assert admins[0].email == auth_service.ADMIN_EMAIL
        assert verify_password(auth_service.ADMIN_PASSWORD, admins[0].hashed_password)
        assert admins[0].invited_by_id is None
        assert admins[0].is_active is True

    def test_is_idempotent_and_never_touches_an_existing_row(self, db_session):
        auth_service.ensure_default_admin(db_session)
        seeded = db_session.query(User).filter(User.role == "admin").one()
        seeded.hashed_password = "manually-changed-hash"
        db_session.commit()

        auth_service.ensure_default_admin(db_session)

        admins = db_session.query(User).filter(User.role == "admin").all()
        assert len(admins) == 1
        assert admins[0].hashed_password == "manually-changed-hash"


class TestAuthenticate:
    def test_seeds_and_authenticates_the_default_admin_on_first_call(self, db_session):
        user = auth_service.authenticate(
            db_session, auth_service.ADMIN_EMAIL, auth_service.ADMIN_PASSWORD
        )

        assert user.role == "admin"

    def test_raises_for_an_unknown_email(self, db_session):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate(db_session, "nobody@example.com", "whatever")

    def test_raises_for_the_wrong_password(self, db_session):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate(db_session, auth_service.ADMIN_EMAIL, "definitely-wrong")

    def test_raises_for_an_inactive_user(self, db_session):
        user, _ = auth_service.create_invited_user(
            db_session, "inactive@example.com", "analyst", invited_by_id=None
        )
        user.is_active = False
        db_session.commit()

        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate(db_session, "inactive@example.com", "whatever")


class TestCreateInvitedUser:
    def test_creates_a_user_with_the_requested_role(self, db_session):
        user, temporary_password = auth_service.create_invited_user(
            db_session, "analyst1@example.com", "analyst", invited_by_id="admin-id-123"
        )

        assert user.email == "analyst1@example.com"
        assert user.role == "analyst"
        assert user.invited_by_id == "admin-id-123"
        assert user.is_active is True
        assert verify_password(temporary_password, user.hashed_password)

    def test_generates_a_different_temporary_password_each_time(self, db_session):
        _, password_a = auth_service.create_invited_user(
            db_session, "a@example.com", "analyst", invited_by_id=None
        )
        _, password_b = auth_service.create_invited_user(
            db_session, "b@example.com", "analyst", invited_by_id=None
        )

        assert password_a != password_b

    def test_raises_for_a_duplicate_email(self, db_session):
        auth_service.create_invited_user(db_session, "dup@example.com", "analyst", invited_by_id=None)

        with pytest.raises(EmailAlreadyExistsError):
            auth_service.create_invited_user(db_session, "dup@example.com", "analyst", invited_by_id=None)

    def test_raises_for_an_invalid_role(self, db_session):
        with pytest.raises(InvalidRoleError):
            auth_service.create_invited_user(db_session, "x@example.com", "superuser", invited_by_id=None)


class TestListUsers:
    def test_lists_every_user_oldest_first(self, db_session):
        auth_service.ensure_default_admin(db_session)
        auth_service.create_invited_user(db_session, "later@example.com", "analyst", invited_by_id=None)

        users = auth_service.list_users(db_session)

        assert [u.email for u in users] == [auth_service.ADMIN_EMAIL, "later@example.com"]
