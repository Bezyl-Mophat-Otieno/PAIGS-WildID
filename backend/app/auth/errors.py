"""Exceptions for the authentication subsystem. Kept separate from
service.py so app.api.auth / app.api.admin can import just the error
types, same convention as app.configuration.errors."""


class InvalidCredentialsError(Exception):
    """Wrong email/password, or the account doesn't exist / is inactive
    -- deliberately the same error either way, so a login attempt can't
    be used to enumerate which emails have accounts."""


class EmailAlreadyExistsError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"A user with email '{email}' already exists.")


class InvalidRoleError(Exception):
    def __init__(self, role: str):
        self.role = role
        super().__init__(f"'{role}' is not a valid role.")
