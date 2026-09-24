"""Pydantic contracts for the authentication subsystem (POST /auth/login,
GET /auth/me, POST /admin/invite, GET /admin/users)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    invited_by_id: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class InviteRequest(BaseModel):
    email: str
    role: str = "analyst"

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, value: str) -> str:
        # Deliberately not full RFC validation (and not pydantic's
        # EmailStr, which would pull in the email-validator dependency
        # just for this one field) -- good enough to reject obviously
        # malformed input for a prototype; app.auth.service still checks
        # for a duplicate email regardless of format.
        if not value or "@" not in value or value != value.strip() or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must look like a real email address (e.g. name@example.com).")
        return value


class EmailDeliveryInfo(BaseModel):
    to: str
    subject: str
    delivered: bool
    note: str


class InviteResponse(BaseModel):
    user: UserRead
    temporary_password: str
    email: EmailDeliveryInfo
