"""Database tables.

Foreign keys record two rules from the spec in the schema itself:
- An article with comments can't be deleted (comments.article_id is RESTRICT).
- A user is never hard-deleted while they have comments. Account deletion anonymises the row
  instead, so comments keep a stable author_id and show the author as "[deleted]".
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, utcnow
from app.enums import NewsCategory, ReportReason, VoteValue


def new_user_id() -> str:
    return f"u_{uuid4().hex}"


def new_comment_id() -> str:
    return f"c_{uuid4().hex}"


def _sql_in(column: str, values: list[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_user_id)
    # Both become NULL when the account is deleted, which frees the email for a new account.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        CheckConstraint(_sql_in("category", [c.value for c in NewsCategory]), name="category"),
        Index("ix_articles_published_at_id", "published_at", "id"),
        Index("ix_articles_category_published_at_id", "category", "published_at", "id"),
    )

    # First 16 hex characters of the SHA-256 of the normalised article URL.
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(200))
    article_url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(16))
    published_at: Mapped[datetime] = mapped_column(UTCDateTime)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    upvotes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    downvotes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    comment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ArticleVote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        CheckConstraint(_sql_in("value", [VoteValue.UP.value, VoteValue.DOWN.value]), name="value"),
        Index("ix_votes_article_id", "article_id"),
    )

    # The composite primary key is the unique index on (user_id, article_id).
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    article_id: Mapped[str] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[str] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_article_id_created_at", "article_id", "created_at"),
        Index("ix_comments_author_id_created_at", "author_id", "created_at"),
        Index("ix_comments_parent_id", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_comment_id)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="RESTRICT"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("comments.id", ondelete="RESTRICT"))
    text: Mapped[str] = mapped_column(String(1000))
    upvotes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    hidden_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    author: Mapped[User] = relationship()


class CommentUpvote(Base):
    __tablename__ = "comment_upvotes"
    __table_args__ = (Index("ix_comment_upvotes_comment_id", "comment_id"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    comment_id: Mapped[str] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CommentReport(Base):
    __tablename__ = "comment_reports"
    __table_args__ = (
        CheckConstraint(_sql_in("reason", [r.value for r in ReportReason]), name="reason"),
        Index("ix_comment_reports_reporter_id", "reporter_id"),
    )

    # One report per user per comment, so the auto-hide threshold counts different users.
    comment_id: Mapped[str] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True
    )
    reporter_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (
        CheckConstraint("blocker_id <> blocked_id", name="not_self"),
        Index("ix_blocks_blocked_id", "blocked_id"),
    )

    blocker_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
