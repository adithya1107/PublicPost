"""Reporting comments, blocking users and deleting accounts (App Store guideline 1.2 and 5.1.1)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db, utcnow
from app.enums import VoteValue
from app.lookups import find_article, find_comment, find_user
from app.models import Article, ArticleVote, Block, Comment, CommentReport, CommentUpvote, User
from app.schemas import DELETED_AUTHOR_NAME, ReportIn

logger = logging.getLogger(__name__)
router = APIRouter()

REPORTS_TO_HIDE = 3


@router.post("/comments/{comment_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def report_comment(
    comment_id: str,
    body: ReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # The lock makes reports on one comment take turns, so it can only be hidden once.
    comment = find_comment(db, comment_id, lock=True)
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")

    # Reporting your own comment or reporting twice succeeds, but adds nothing to the count.
    if comment.author_id == user.id or db.get(CommentReport, (comment.id, user.id)):
        return

    db.add(CommentReport(comment_id=comment.id, reporter_id=user.id, reason=body.reason.value))
    db.flush()

    report_count = db.scalar(
        select(func.count()).select_from(CommentReport).where(CommentReport.comment_id == comment.id)
    )
    if report_count >= REPORTS_TO_HIDE and not comment.is_hidden:
        comment.is_hidden = True
        comment.hidden_at = utcnow()
        find_article(db, comment.article_id, lock=True).comment_count -= 1
        logger.info(
            "Comment auto-hidden",
            extra={"fields": {"comment_id": comment.id, "report_count": report_count}},
        )
    db.commit()


@router.post("/users/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def block_user(
    user_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't block yourself.")
    if find_user(db, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if db.get(Block, (user.id, user_id)) is None:
        db.add(Block(blocker_id=user.id, blocked_id=user_id))
        try:
            db.commit()
        except IntegrityError:  # the same block was sent twice at once, which is fine
            db.rollback()


@router.delete("/users/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def unblock_user(
    user_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # Unblocking someone who isn't blocked, or doesn't exist, leaves the same end result.
    block = None if "\x00" in user_id else db.get(Block, (user.id, user_id))
    if block is not None:
        db.delete(block)
        db.commit()


def _remove_votes(db: Session, user_id: str) -> None:
    votes = db.execute(
        select(ArticleVote.article_id, ArticleVote.value)
        .where(ArticleVote.user_id == user_id)
        .order_by(ArticleVote.article_id)
    ).all()
    for article_id, value in votes:
        column = "upvotes" if value == VoteValue.UP else "downvotes"
        db.execute(
            update(Article)
            .where(Article.id == article_id)
            .values({column: getattr(Article, column) - 1})
        )
    db.execute(delete(ArticleVote).where(ArticleVote.user_id == user_id))


def _remove_comment_upvotes(db: Session, user_id: str) -> None:
    comment_ids = db.scalars(
        select(CommentUpvote.comment_id)
        .where(CommentUpvote.user_id == user_id)
        .order_by(CommentUpvote.comment_id)
    ).all()
    for comment_id in comment_ids:
        db.execute(update(Comment).where(Comment.id == comment_id).values(upvotes=Comment.upvotes - 1))
    db.execute(delete(CommentUpvote).where(CommentUpvote.user_id == user_id))


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Erases the account's personal details, votes and upvotes. Comment text stays, shown under
    "[deleted]". The anonymised row stays too, so comments keep a stable author_id.

    Kept on purpose: reports the user filed, so hidden comments stay hidden, and blocks others
    placed on this user, so a blocked person can't reappear by deleting their account.
    """
    # Taken first, so two simultaneous deletes can't both subtract the same votes. Comment rows
    # are changed before article rows, the same order reporting uses, to avoid deadlocks.
    account = db.get(User, user.id, with_for_update=True, populate_existing=True)
    _remove_comment_upvotes(db, account.id)
    _remove_votes(db, account.id)
    db.execute(delete(Block).where(Block.blocker_id == account.id))

    account.email = None
    account.password_hash = None
    account.display_name = DELETED_AUTHOR_NAME
    account.deleted_at = account.deleted_at or utcnow()
    db.commit()
    logger.info("Account deleted", extra={"fields": {"user_id": account.id}})
