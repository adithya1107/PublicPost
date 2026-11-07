import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, ArticleVote
from tests.factories import auth_headers, make_article, make_user


def vote(client: TestClient, user, value: str, article_id: str = "a1"):
    return client.post(f"/articles/{article_id}/vote", json={"vote": value}, headers=auth_headers(user))


def counts(db: Session, article_id: str = "a1") -> tuple[int, int]:
    db.expire_all()
    article = db.get(Article, article_id)
    return article.upvotes, article.downvotes


def test_vote_returns_the_contract_shape(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    response = vote(client, user, "up")

    assert response.status_code == 200
    assert response.json() == {"upvotes": 1, "downvotes": 0, "user_vote": "up"}


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        (["up"], (1, 0, "up")),
        (["down"], (0, 1, "down")),
        (["none"], (0, 0, "none")),
        (["up", "up"], (1, 0, "up")),
        (["down", "down"], (0, 1, "down")),
        (["up", "down"], (0, 1, "down")),
        (["down", "up"], (1, 0, "up")),
        (["up", "none"], (0, 0, "none")),
        (["down", "none"], (0, 0, "none")),
        (["none", "none"], (0, 0, "none")),
        (["up", "none", "up"], (1, 0, "up")),
        (["up", "down", "none", "down", "up", "up"], (1, 0, "up")),
    ],
    ids=lambda value: "-".join(value) if isinstance(value, list) else None,
)
def test_vote_transitions(client: TestClient, db: Session, steps: list[str], expected: tuple) -> None:
    user = make_user(db)
    make_article(db, "a1")

    for step in steps:
        response = vote(client, user, step)

    upvotes, downvotes, user_vote = expected
    assert response.json() == {"upvotes": upvotes, "downvotes": downvotes, "user_vote": user_vote}
    assert counts(db) == (upvotes, downvotes)
    assert client.get("/articles/a1", headers=auth_headers(user)).json()["user_vote"] == user_vote


def test_none_removes_the_stored_vote(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    vote(client, user, "up")
    vote(client, user, "none")
    assert db.scalar(select(func.count()).select_from(ArticleVote)) == 0


def test_one_vote_row_per_user_however_often_they_change_it(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    for value in ("up", "down", "up", "up", "down"):
        vote(client, user, value)
    assert db.scalar(select(func.count()).select_from(ArticleVote)) == 1


def test_votes_from_different_users_add_up(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    users = [make_user(db, f"u{i}@example.com") for i in range(5)]
    for user, value in zip(users, ["up", "up", "up", "down", "down"]):
        response = vote(client, user, value)
    assert response.json() == {"upvotes": 3, "downvotes": 2, "user_vote": "down"}
    assert counts(db) == (3, 2)


def test_one_users_change_keeps_other_users_votes(client: TestClient, db: Session) -> None:
    make_article(db, "a1", upvotes=100, downvotes=50)
    user = make_user(db)
    vote(client, user, "up")
    assert counts(db) == (101, 50)
    vote(client, user, "down")
    assert counts(db) == (100, 51)
    vote(client, user, "none")
    assert counts(db) == (100, 50)


def test_votes_on_one_article_do_not_touch_another(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    make_article(db, "a2")
    vote(client, user, "up", "a1")
    vote(client, user, "down", "a2")

    assert counts(db, "a1") == (1, 0)
    assert counts(db, "a2") == (0, 1)


def test_voting_on_an_unknown_article_is_404(client: TestClient, db: Session) -> None:
    response = vote(client, make_user(db), "up", "missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Article not found"}


@pytest.mark.parametrize(
    "body",
    [{"vote": "sideways"}, {"vote": "UP"}, {"vote": ""}, {"vote": None}, {"vote": 1}, {}, []],
)
def test_invalid_vote_body_is_422_and_changes_nothing(client: TestClient, db: Session, body) -> None:
    user = make_user(db)
    make_article(db, "a1")
    response = client.post("/articles/a1/vote", json=body, headers=auth_headers(user))

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert counts(db) == (0, 0)


def test_malformed_json_is_422_with_string_detail(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    response = client.post(
        "/articles/a1/vote",
        content="{not json",
        headers=auth_headers(user) | {"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


# --- user_vote on the read endpoints ------------------------------------------------------


def test_user_vote_is_per_user(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    voter_up = make_user(db, "up@example.com")
    voter_down = make_user(db, "down@example.com")
    bystander = make_user(db, "none@example.com")
    vote(client, voter_up, "up")
    vote(client, voter_down, "down")

    def seen_by(headers: dict) -> tuple[str, str]:
        detail = client.get("/articles/a1", headers=headers).json()["user_vote"]
        listing = client.get("/articles", headers=headers).json()[0]["user_vote"]
        return detail, listing

    assert seen_by(auth_headers(voter_up)) == ("up", "up")
    assert seen_by(auth_headers(voter_down)) == ("down", "down")
    assert seen_by(auth_headers(bystander)) == ("none", "none")
    assert seen_by({}) == ("none", "none")


def test_listing_returns_each_articles_own_vote(client: TestClient, db: Session) -> None:
    user = make_user(db)
    start = datetime(2026, 11, 7, tzinfo=UTC)
    for index, article_id in enumerate(["up1", "down1", "plain1"]):
        make_article(db, article_id, published_at=start - timedelta(hours=index))
    vote(client, user, "up", "up1")
    vote(client, user, "down", "down1")

    listing = client.get("/articles", headers=auth_headers(user)).json()
    assert {a["id"]: a["user_vote"] for a in listing} == {"up1": "up", "down1": "down", "plain1": "none"}


def test_counts_are_public_but_guests_have_no_vote(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    vote(client, make_user(db), "up")
    body = client.get("/articles/a1").json()
    assert (body["upvotes"], body["user_vote"]) == (1, "none")


# --- Concurrency --------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Needs PostgreSQL row locks; SQLite doesn't handle concurrent writers",
)
def test_concurrent_votes_keep_counters_exact(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    users = [make_user(db, f"u{i}@example.com") for i in range(12)]
    # Each user fires a burst of changing votes, all at once, ending on a known value.
    requests = [
        (user, value)
        for index, user in enumerate(users)
        for value in ("up", "down", "none", "up" if index % 3 else "down")
    ]

    def send(request: tuple) -> int:
        user, value = request
        return vote(client, user, value).status_code

    with ThreadPoolExecutor(8) as pool:
        assert set(pool.map(send, requests)) == {200}

    # Requests from one user may land in any order, so compare counters to the stored votes.
    db.expire_all()
    stored = dict(
        db.execute(select(ArticleVote.value, func.count()).group_by(ArticleVote.value)).all()
    )
    assert counts(db) == (stored.get("up", 0), stored.get("down", 0))


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Needs PostgreSQL row locks; SQLite doesn't handle concurrent writers",
)
def test_same_vote_sent_many_times_at_once_counts_once(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    user = make_user(db)

    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: vote(client, user, "up").status_code, range(24)))

    assert set(codes) == {200}
    assert counts(db) == (1, 0)
