"""Password hashing (argon2) and login tokens (JWT)."""

from datetime import timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.database import utcnow

_ALGORITHM = "HS256"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("not-a-real-password")


def burn_password_check(password: str) -> None:
    """Takes as long as a real check, so response time doesn't reveal whether an email exists."""
    verify_password(password, _dummy_hash())


def create_token(user_id: str) -> str:
    settings = get_settings()
    now = utcnow()
    claims = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def read_token(token: str) -> str | None:
    """The user id from a valid token, or None if it's invalid, tampered with or expired."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    return claims["sub"]
