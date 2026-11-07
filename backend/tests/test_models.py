"""Rules enforced by the schema itself."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import Article, ArticleVote, Block, Comment, CommentReport, User
from tests.factories import make_article, make_user


def test_new_rows_get_string_ids_and_zero_counts(db: Session) -> None:
    user = make_user(db)
    article = make_article(db)
    comment = Comment(article_id=article.id, author_id=user.id, text="Hello")
    db.add(comment)
    db.commit()

    assert user.id.startswith("u_")
    assert comment.id.startswith("c_")
    assert (article.upvotes, article.downvotes, article.comment_count) == (0, 0, 0)
    assert comment.upvotes == 0
    assert comment.is_hidden is False


def test_datetimes_come_back_as_aware_utc(db: Session) -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    make_article(db, published_at=datetime(2026, 11, 7, 15, 30, tzinfo=ist))
    db.expire_all()

    published = db.get(Article, "0123456789abcdef").published_at
    assert published == datetime(2026, 11, 7, 10, 0, tzinfo=UTC)
    assert published.utcoffset() == timedelta(0)


def test_naive_datetimes_are_refused(db: Session) -> None:
    with pytest.raises(StatementError):
        make_article(db, published_at=datetime(2026, 11, 7, 10, 0))


def test_unknown_category_is_refused(db: Session) -> None:
    with pytest.raises(IntegrityError):
        make_article(db, category="Politics")


def test_email_must_be_unique_but_deleted_accounts_free_it(db: Session) -> None:
    make_user(db, "taken@example.com")
    db.add(User(email="taken@example.com", password_hash="h", display_name="Other"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Several anonymised accounts can exist at once.
    db.add_all([User(email=None, display_name="[deleted]"), User(email=None, display_name="[deleted]")])
    db.commit()


def test_one_vote_per_user_per_article(db: Session) -> None:
    user = make_user(db)
    article = make_article(db)
    db.add(ArticleVote(user_id=user.id, article_id=article.id, value="up"))
    db.commit()
    db.expunge_all()

    db.add(ArticleVote(user_id=user.id, article_id=article.id, value="down"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_none_is_not_a_stored_vote(db: Session) -> None:
    user = make_user(db)
    article = make_article(db)
    db.add(ArticleVote(user_id=user.id, article_id=article.id, value="none"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_article_with_comments_cannot_be_deleted(db: Session) -> None:
    user = make_user(db)
    article = make_article(db)
    db.add(Comment(article_id=article.id, author_id=user.id, text="Keep me"))
    db.commit()

    db.delete(article)
    with pytest.raises(IntegrityError):
        db.commit()


def test_deleting_an_article_removes_its_votes(db: Session) -> None:
    user = make_user(db)
    article = make_article(db)
    db.add(ArticleVote(user_id=user.id, article_id=article.id, value="up"))
    db.commit()
    db.expunge_all()

    db.delete(db.get(Article, article.id))
    db.commit()
    assert db.get(ArticleVote, (user.id, article.id)) is None


def test_one_report_per_user_per_comment(db: Session) -> None:
    user = make_user(db)
    article = make_article(db)
    comment = Comment(article_id=article.id, author_id=user.id, text="Hello")
    db.add(comment)
    db.commit()
    db.add(CommentReport(comment_id=comment.id, reporter_id=user.id, reason="spam"))
    db.commit()
    db.expunge_all()

    db.add(CommentReport(comment_id=comment.id, reporter_id=user.id, reason="abuse"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_unknown_report_reason_is_refused(db: Session) -> None:
    user = make_user(db)
    article = make_article(db)
    comment = Comment(article_id=article.id, author_id=user.id, text="Hello")
    db.add(comment)
    db.commit()
    db.add(CommentReport(comment_id=comment.id, reporter_id=user.id, reason="boring"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_cannot_block_yourself(db: Session) -> None:
    user = make_user(db)
    db.add(Block(blocker_id=user.id, blocked_id=user.id))
    with pytest.raises(IntegrityError):
        db.commit()
