"""Finding rows from IDs in URLs.

IDs come straight from the client. PostgreSQL raises an error for a null character in a query,
so an ID containing one is treated as simply not found rather than crashing with a 500.
"""

from sqlalchemy.orm import Session

from app.models import Article, Comment, User


def find_article(db: Session, article_id: str, *, lock: bool = False) -> Article | None:
    if "\x00" in article_id:
        return None
    return db.get(Article, article_id, with_for_update=lock or None)


def find_user(db: Session, user_id: str) -> User | None:
    if "\x00" in user_id:
        return None
    return db.get(User, user_id)


def find_comment(db: Session, comment_id: str, *, lock: bool = False) -> Comment | None:
    if "\x00" in comment_id:
        return None
    return db.get(Comment, comment_id, with_for_update=lock or None)
