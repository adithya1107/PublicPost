from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, get_optional_user
from app.database import get_db
from app.lookups import find_article, find_comment
from app.models import Block, Comment, CommentUpvote, User
from app.rate_limit import COMMENT_LIMIT, VOTE_LIMIT, limiter, user_or_ip
from app.schemas import CommentIn, CommentOut, UpvoteIn, UpvoteOut

router = APIRouter()

_ARTICLE_NOT_FOUND = "Article not found"
_COMMENT_NOT_FOUND = "Comment not found"
_PARENT_NOT_FOUND = "The comment you're replying to is no longer available."


def _to_out(db: Session, comments: list[Comment], user: User | None) -> list[CommentOut]:
    upvoted: set[str] = set()
    if user is not None and comments:
        upvoted = set(
            db.scalars(
                select(CommentUpvote.comment_id).where(
                    CommentUpvote.user_id == user.id,
                    CommentUpvote.comment_id.in_([comment.id for comment in comments]),
                )
            )
        )
    return [
        CommentOut(
            id=comment.id,
            article_id=comment.article_id,
            author_id=comment.author_id,
            author_name=comment.author.display_name,
            text=comment.text,
            created_at=comment.created_at,
            upvotes=comment.upvotes,
            parent_id=comment.parent_id,
            user_upvoted=comment.id in upvoted,
        )
        for comment in comments
    ]


@router.get("/articles/{article_id}/comments", response_model=list[CommentOut])
def list_comments(
    article_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[CommentOut]:
    if find_article(db, article_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _ARTICLE_NOT_FOUND)

    statement = (
        select(Comment)
        .options(joinedload(Comment.author))
        .where(Comment.article_id == article_id, Comment.is_hidden.is_(False))
        .order_by(Comment.created_at, Comment.id)
    )
    if user is not None:
        blocked = select(Block.blocked_id).where(Block.blocker_id == user.id)
        statement = statement.where(Comment.author_id.not_in(blocked))
    return _to_out(db, list(db.scalars(statement)), user)


def _resolve_parent(db: Session, article_id: str, parent_id: str | None) -> str | None:
    """The comment a new reply attaches to. A reply to a reply attaches to the top-level
    comment, so threads stay one level deep."""
    if parent_id is None:
        return None

    parent = find_comment(db, parent_id)
    if parent is None or parent.article_id != article_id or parent.is_hidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _PARENT_NOT_FOUND)
    if parent.parent_id is None:
        return parent.id

    top_level = find_comment(db, parent.parent_id)
    if top_level is None or top_level.is_hidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _PARENT_NOT_FOUND)
    return top_level.id


@router.post("/articles/{article_id}/comments", response_model=CommentOut)
@limiter.shared_limit(COMMENT_LIMIT, scope="comments", key_func=user_or_ip)
def create_comment(
    request: Request,
    article_id: str,
    body: CommentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentOut:
    # The lock makes new comments on one article take turns, so comment_count stays exact.
    article = find_article(db, article_id, lock=True)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _ARTICLE_NOT_FOUND)

    comment = Comment(
        article_id=article.id,
        author=user,
        parent_id=_resolve_parent(db, article.id, body.parent_id),
        text=body.text,
    )
    db.add(comment)
    article.comment_count += 1
    db.commit()
    return _to_out(db, [comment], user)[0]


@router.post("/comments/{comment_id}/upvote", response_model=UpvoteOut)
@limiter.shared_limit(VOTE_LIMIT, scope="comment_upvotes", key_func=user_or_ip)
def set_comment_upvote(
    request: Request,
    comment_id: str,
    body: UpvoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UpvoteOut:
    comment = find_comment(db, comment_id, lock=True)
    if comment is None or comment.is_hidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _COMMENT_NOT_FOUND)

    existing = db.get(CommentUpvote, (user.id, comment.id))
    # Only an actual change touches the count, so repeating a request has no further effect.
    if body.upvoted and existing is None:
        db.add(CommentUpvote(user_id=user.id, comment_id=comment.id))
        comment.upvotes += 1
        db.commit()
    elif not body.upvoted and existing is not None:
        db.delete(existing)
        comment.upvotes -= 1
        db.commit()
    return UpvoteOut(upvotes=comment.upvotes)


@router.get("/users/me/comments", response_model=list[CommentOut])
def list_my_comments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CommentOut]:
    """Newest first. Includes the user's own comments that moderation has hidden."""
    statement = (
        select(Comment)
        .options(joinedload(Comment.author))
        .where(Comment.author_id == user.id)
        .order_by(Comment.created_at.desc(), Comment.id.desc())
    )
    return _to_out(db, list(db.scalars(statement)), user)
