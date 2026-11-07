"""API request and response shapes. The iOS app decodes these, so names and formats must not drift."""

from datetime import UTC, datetime
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, PlainSerializer, StrictBool, field_validator

from app.enums import NewsCategory, ReportReason, VoteValue

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128  # hashing is deliberately slow, so very long inputs are refused
MIN_DISPLAY_NAME_LENGTH = 2
MAX_DISPLAY_NAME_LENGTH = 30
DELETED_AUTHOR_NAME = "[deleted]"
MAX_COMMENT_LENGTH = 1000


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


UTCTimestamp = Annotated[datetime, PlainSerializer(_format_utc, return_type=str)]


def normalise_email(value: str) -> str:
    """Lowercased, so accounts can't differ only by capitalisation. Raises ValueError if invalid."""
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError("Please enter a valid email address.") from None


def _without_nulls(value: str) -> str:
    """PostgreSQL can't store a null character in text."""
    return value.replace("\x00", "")


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    summary: str
    source_name: str
    article_url: str
    image_url: str | None
    category: NewsCategory
    published_at: UTCTimestamp
    upvotes: int
    downvotes: int
    comment_count: int
    user_vote: VoteValue = VoteValue.NONE


class VoteIn(BaseModel):
    vote: VoteValue


class VoteOut(BaseModel):
    upvotes: int
    downvotes: int
    user_vote: VoteValue


class CommentIn(BaseModel):
    text: str
    parent_id: str | None = None

    @field_validator("text")
    @classmethod
    def check_text(cls, value: str) -> str:
        text = _without_nulls(value).strip()
        if not text:
            raise ValueError("Please write something before posting.")
        if len(text) > MAX_COMMENT_LENGTH:
            raise ValueError(f"Comments can be at most {MAX_COMMENT_LENGTH} characters.")
        return text


class CommentOut(BaseModel):
    id: str
    article_id: str
    author_id: str
    author_name: str
    text: str
    created_at: UTCTimestamp
    upvotes: int
    parent_id: str | None
    user_upvoted: bool


class UpvoteIn(BaseModel):
    upvoted: StrictBool


class UpvoteOut(BaseModel):
    upvotes: int


class ReportIn(BaseModel):
    reason: ReportReason


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str


class AuthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token: str
    user: UserOut


class RegisterIn(BaseModel):
    display_name: str
    email: str
    password: str

    @field_validator("display_name")
    @classmethod
    def check_display_name(cls, value: str) -> str:
        name = " ".join(_without_nulls(value).split())
        if not MIN_DISPLAY_NAME_LENGTH <= len(name) <= MAX_DISPLAY_NAME_LENGTH:
            raise ValueError(
                f"Display name must be {MIN_DISPLAY_NAME_LENGTH} to "
                f"{MAX_DISPLAY_NAME_LENGTH} characters."
            )
        if name.casefold() == DELETED_AUTHOR_NAME:
            raise ValueError("That display name isn't available.")
        return name

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return normalise_email(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        if len(value) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if len(value) > MAX_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
        return value


class LoginIn(BaseModel):
    # Not validated as an email: a malformed one is just wrong credentials, so it gets a 401.
    email: str
    password: str
