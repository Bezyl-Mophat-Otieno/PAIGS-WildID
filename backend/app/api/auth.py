"""POST /auth/login, GET /auth/me -- the auth subsystem's HTTP surface.

POST /auth/login accepts OAuth2PasswordRequestForm (the standard
username/password form fields, `username` doubling as email) rather
than a JSON body -- this is what makes Swagger UI's "Authorize" padlock
work out of the box, and needs no new dependency (python-multipart is
already pinned, in use since Stage 0's file uploads).
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.dependencies import get_current_user
from app.auth.errors import InvalidCredentialsError
from app.auth.security import create_access_token
from app.db import get_db
from app.models.user import User
from app.schemas.auth import TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        user = auth_service.authenticate(db, form.username, form.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, role=user.role, email=user.email)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return current_user
