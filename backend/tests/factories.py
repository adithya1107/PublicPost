"""Helpers for creating rows in tests."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Article, Comment, User
from app.security import create_token

BASE_TIME = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


def make_user(db: Session, email: str = "a@example.com") -> User:
    user = User(email=email, password_hash="hash", display_name="Asha")
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User | str) -> dict[str, str]:
    user_id = user if isinstance(user, str) else user.id
    return {"Authorization": f"Bearer {create_token(user_id)}"}


def make_article(db: Session, article_id: str = "0123456789abcdef", **overrides) -> Article:
    values = {
        "id": article_id,
        "title": "Title",
        "summary": "Summary",
        "source_name": "Source",
        "article_url": "https://example.com/a",
        "category": "Tech",
        "published_at": BASE_TIME,
    } | overrides
    article = Article(**values)
    db.add(article)
    db.commit()
    return article


def make_comment(db: Session, author: User, article_id: str = "a1", **overrides) -> Comment:
    values = {"text": "Hello", "created_at": BASE_TIME} | overrides
    comment = Comment(article_id=article_id, author_id=author.id, **values)
    db.add(comment)
    db.commit()
    return comment
