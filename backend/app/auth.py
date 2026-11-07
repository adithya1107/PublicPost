"""FastAPI dependencies that identify the caller from the Authorization header."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import read_token


def bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


def _user_from_request(request: Request, db: Session) -> User | None:
    token = bearer_token(request)
    user_id = read_token(token) if token else None
    if user_id is None:
        return None
    user = db.get(User, user_id)
    # A token outlives account deletion, so the account itself has to be checked too.
    return None if user is None or user.deleted_at is not None else user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """For protected routes: a missing, invalid or expired token is a 401."""
    user = _user_from_request(request, db)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Please log in to do that.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """For public routes: a bad token means guest, not an error.

    A 401 here would make the current app replace the feed with its bundled sample stories,
    because ResilientService falls back on any failure loading page 1.
    """
    return _user_from_request(request, db)
