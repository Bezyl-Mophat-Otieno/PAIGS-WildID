"""POST /admin/invite, GET /admin/users -- the admin subsystem's HTTP
surface. Deliberately the only admin-related features for now (per the
product decision): inviting a user, and seeing who's been invited so
far -- without the latter, an admin who lost the one-time
temporary_password from the invite response would have no way to even
confirm the invite happened. Both endpoints require the caller's own
token to carry role="admin" (app.auth.dependencies.require_admin).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.dependencies import require_admin
from app.auth.email_stub import send_invitation_email
from app.auth.errors import EmailAlreadyExistsError, InvalidRoleError
from app.db import get_db
from app.models.user import User
from app.schemas.auth import EmailDeliveryInfo, InviteRequest, InviteResponse, UserRead

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/invite", response_model=InviteResponse, status_code=201)
def invite_user(
    payload: InviteRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        user, temporary_password = auth_service.create_invited_user(
            db, payload.email, payload.role, invited_by_id=admin.id
        )
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except InvalidRoleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    delivery = send_invitation_email(user.email, temporary_password, user.role)
    return InviteResponse(
        user=UserRead.model_validate(user),
        temporary_password=temporary_password,
        email=EmailDeliveryInfo(
            to=delivery.to,
            subject=delivery.subject,
            delivered=delivery.delivered,
            note=delivery.note,
        ),
    )


@router.get("/users", response_model=List[UserRead])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return auth_service.list_users(db)
