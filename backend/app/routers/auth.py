from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.rate_limit import LOGIN_LIMIT, REGISTER_LIMIT, limiter
from app.schemas import AuthOut, LoginIn, RegisterIn, normalise_email
from app.security import (
    burn_password_check,
    create_token,
    hash_password,
    needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth")

_EMAIL_TAKEN = "An account with that email already exists."
_BAD_CREDENTIALS = "Incorrect email or password."


@router.post("/register", response_model=AuthOut)
@limiter.limit(REGISTER_LIMIT)
def register(request: Request, body: RegisterIn, db: Session = Depends(get_db)) -> AuthOut:
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, _EMAIL_TAKEN)

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two simultaneous registrations with the same email
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _EMAIL_TAKEN) from None
    return AuthOut(token=create_token(user.id), user=user)


@router.post("/login", response_model=AuthOut)
@limiter.limit(LOGIN_LIMIT)
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)) -> AuthOut:
    try:
        email = normalise_email(body.email)
    except ValueError:
        email = None
    user = db.scalar(select(User).where(User.email == email)) if email else None

    if user is None or user.password_hash is None:
        burn_password_check(body.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    if needs_rehash(user.password_hash):  # hashing settings were strengthened since sign-up
        user.password_hash = hash_password(body.password)
        db.commit()
    return AuthOut(token=create_token(user.id), user=user)
