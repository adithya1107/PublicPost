from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BeforeValidator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_optional_user
from app.database import get_db
from app.enums import NewsCategory, VoteValue
from app.lookups import find_article
from app.models import Article, ArticleVote, User
from app.rate_limit import VOTE_LIMIT, limiter, user_or_ip
from app.schemas import ArticleOut, VoteIn, VoteOut

PAGE_SIZE = 10
MAX_PAGE = 100_000  # keeps the database offset inside a safe integer range

router = APIRouter()


def _blank_as_none(value: object) -> object:
    return value or None


def _with_user_votes(db: Session, articles: list[Article], user: User | None) -> list[ArticleOut]:
    votes: dict[str, str] = {}
    if user is not None and articles:
        rows = db.execute(
            select(ArticleVote.article_id, ArticleVote.value).where(
                ArticleVote.user_id == user.id,
                ArticleVote.article_id.in_([article.id for article in articles]),
            )
        )
        votes = {article_id: value for article_id, value in rows}
    return [
        ArticleOut.model_validate(article).model_copy(
            update={"user_vote": VoteValue(votes.get(article.id, VoteValue.NONE))}
        )
        for article in articles
    ]


@router.get("/articles", response_model=list[ArticleOut])
def list_articles(
    category: Annotated[NewsCategory | None, BeforeValidator(_blank_as_none), Query()] = None,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[ArticleOut]:
    statement = select(Article).order_by(Article.published_at.desc(), Article.id.desc())
    if category:
        statement = statement.where(Article.category == category.value)
    articles = list(db.scalars(statement.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)))
    return _with_user_votes(db, articles, user)


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(
    article_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> ArticleOut:
    article = find_article(db, article_id)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    return _with_user_votes(db, [article], user)[0]


@router.post("/articles/{article_id}/vote", response_model=VoteOut)
@limiter.shared_limit(VOTE_LIMIT, scope="votes", key_func=user_or_ip)
def vote_on_article(
    request: Request,
    article_id: str,
    body: VoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoteOut:
    # Locking the article makes votes on it take turns, so counters can't drift. SQLite has no
    # row locks and ignores this, which is fine for local development.
    article = find_article(db, article_id, lock=True)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")

    existing = db.get(ArticleVote, (user.id, article.id))
    previous = VoteValue(existing.value) if existing else VoteValue.NONE

    if body.vote != previous:
        article.upvotes += (body.vote == VoteValue.UP) - (previous == VoteValue.UP)
        article.downvotes += (body.vote == VoteValue.DOWN) - (previous == VoteValue.DOWN)
        if body.vote == VoteValue.NONE:
            db.delete(existing)
        elif existing:
            existing.value = body.vote.value
        else:
            db.add(ArticleVote(user_id=user.id, article_id=article.id, value=body.vote.value))
        db.commit()

    return VoteOut(upvotes=article.upvotes, downvotes=article.downvotes, user_vote=body.vote)
