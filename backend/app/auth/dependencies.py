"""FastAPI dependencies enforcing authentication/authorization.

OAuth2PasswordBearer here only extracts the Bearer token from the
Authorization header (and tells Swagger UI's "Authorize" button which
endpoint issues tokens) -- it does not, by itself, check anything.
get_current_user is what actually validates the token and loads the
User; require_admin layers a role check on top, translating failures
into HTTPException the same way app/api/config.py does for
app.configuration.errors.
"""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_access_token(token)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials.")
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Could not validate credentials.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required.")
    return user
