import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import Article, Block, Comment, CommentUpvote, User
from tests.factories import auth_headers, make_article, make_comment, make_user

needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Needs PostgreSQL row locks; SQLite doesn't handle concurrent writers",
)
BASE = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


def post(client: TestClient, user, text: str = "Hello", article_id: str = "a1", **fields):
    return client.post(
        f"/articles/{article_id}/comments",
        json={"text": text} | fields,
        headers=auth_headers(user),
    )


def upvote(client: TestClient, user, comment_id: str, upvoted: bool = True):
    return client.post(
        f"/comments/{comment_id}/upvote", json={"upvoted": upvoted}, headers=auth_headers(user)
    )


def comment_count(db: Session, article_id: str = "a1") -> int:
    db.expire_all()
    return db.get(Article, article_id).comment_count


def ids(response) -> list[str]:
    return [comment["id"] for comment in response.json()]


@pytest.fixture
def user(db: Session) -> User:
    return make_user(db)


@pytest.fixture
def article(db: Session) -> Article:
    return make_article(db, "a1")


# --- Reading ------------------------------------------------------------------------------


def test_comment_has_exactly_the_contract_shape(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user, text="Nice", upvotes=4)

    assert client.get("/articles/a1/comments").json() == [
        {
            "id": comment.id,
            "article_id": "a1",
            "author_id": user.id,
            "author_name": "Asha",
            "text": "Nice",
            "created_at": "2026-11-07T10:00:00Z",
            "upvotes": 4,
            "parent_id": None,
            "user_upvoted": False,
        }
    ]


def test_no_comments_is_an_empty_list(client: TestClient, article) -> None:
    assert client.get("/articles/a1/comments").json() == []


def test_comments_on_an_unknown_article_are_404(client: TestClient) -> None:
    response = client.get("/articles/missing/comments")
    assert response.status_code == 404
    assert response.json() == {"detail": "Article not found"}


def test_comments_are_oldest_first(client: TestClient, db: Session, user, article) -> None:
    newer = make_comment(db, user, created_at=BASE)
    older = make_comment(db, user, created_at=BASE - timedelta(hours=1))
    assert ids(client.get("/articles/a1/comments")) == [older.id, newer.id]


def test_only_this_articles_comments_are_returned(client: TestClient, db: Session, user, article) -> None:
    make_article(db, "a2")
    mine = make_comment(db, user)
    make_comment(db, user, article_id="a2")
    assert ids(client.get("/articles/a1/comments")) == [mine.id]


def test_hidden_comments_are_excluded_for_everyone(client: TestClient, db: Session, user, article) -> None:
    visible = make_comment(db, user)
    make_comment(db, user, is_hidden=True, hidden_at=utcnow())

    assert ids(client.get("/articles/a1/comments")) == [visible.id]
    assert ids(client.get("/articles/a1/comments", headers=auth_headers(user))) == [visible.id]


def test_blocked_authors_are_excluded_only_for_the_blocker(client: TestClient, db: Session, user, article) -> None:
    troll = make_user(db, "troll@example.com")
    bystander = make_user(db, "other@example.com")
    trolls = make_comment(db, troll)
    mine = make_comment(db, user)
    db.add(Block(blocker_id=user.id, blocked_id=troll.id))
    db.commit()

    assert ids(client.get("/articles/a1/comments", headers=auth_headers(user))) == [mine.id]
    assert set(ids(client.get("/articles/a1/comments", headers=auth_headers(bystander)))) == {mine.id, trolls.id}
    assert set(ids(client.get("/articles/a1/comments"))) == {mine.id, trolls.id}
    # Blocking is one-way: the blocked user still sees the blocker's comments.
    assert set(ids(client.get("/articles/a1/comments", headers=auth_headers(troll)))) == {mine.id, trolls.id}


def test_replies_survive_when_their_parent_is_hidden_or_blocked(client: TestClient, db: Session, user, article) -> None:
    other = make_user(db, "other@example.com")
    hidden_parent = make_comment(db, other, is_hidden=True)
    reply = make_comment(db, user, parent_id=hidden_parent.id)

    # The app shows a reply with no visible parent as a normal comment.
    assert ids(client.get("/articles/a1/comments")) == [reply.id]


def test_deleted_author_is_shown_as_deleted(client: TestClient, db: Session, article) -> None:
    gone = User(email=None, password_hash=None, display_name="[deleted]", deleted_at=utcnow())
    db.add(gone)
    db.commit()
    make_comment(db, gone, text="Still here")

    comment = client.get("/articles/a1/comments").json()[0]
    assert comment["author_name"] == "[deleted]"
    assert comment["author_id"] == gone.id
    assert comment["text"] == "Still here"


def test_bad_token_on_comments_means_guest(client: TestClient, db: Session, user, article) -> None:
    make_comment(db, user)
    response = client.get("/articles/a1/comments", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 200
    assert response.json()[0]["user_upvoted"] is False


# --- Posting ------------------------------------------------------------------------------


def test_post_returns_a_full_comment(client: TestClient, user, article) -> None:
    response = post(client, user, "My take")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id", "article_id", "author_id", "author_name", "text",
        "created_at", "upvotes", "parent_id", "user_upvoted",
    }
    assert isinstance(body["id"], str)
    assert (body["article_id"], body["author_id"], body["author_name"]) == ("a1", user.id, "Asha")
    assert (body["text"], body["upvotes"], body["parent_id"], body["user_upvoted"]) == ("My take", 0, None, False)
    assert body["created_at"].endswith("Z")


def test_posted_comment_shows_up_in_the_thread(client: TestClient, user, article) -> None:
    created = post(client, user).json()
    assert client.get("/articles/a1/comments").json() == [created]


def test_posting_requires_login(client: TestClient, article) -> None:
    response = client.post("/articles/a1/comments", json={"text": "Hi"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Please log in to do that."}


def test_posting_on_an_unknown_article_is_404(client: TestClient, user) -> None:
    assert post(client, user, article_id="missing").status_code == 404


def test_text_is_trimmed(client: TestClient, user, article) -> None:
    assert post(client, user, "  \n Hello there \t\n").json()["text"] == "Hello there"


def test_inner_formatting_and_markup_are_stored_unchanged(client: TestClient, user, article) -> None:
    text = "Line one\n\nLine <b>two</b> & 'three'"
    assert post(client, user, text).json()["text"] == text


@pytest.mark.parametrize("length", [1, 1000])
def test_length_limits_are_inclusive(client: TestClient, user, article, length: int) -> None:
    assert post(client, user, "x" * length).status_code == 200


def test_limit_applies_after_trimming(client: TestClient, user, article) -> None:
    assert post(client, user, "   " + "x" * 1000 + "   ").status_code == 200


def test_limit_counts_characters_not_bytes(client: TestClient, user, article) -> None:
    assert post(client, user, "अ" * 1000).status_code == 200


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "Please write something before posting."),
        ("    ", "Please write something before posting."),
        ("\n\t ", "Please write something before posting."),
        ("\x00", "Please write something before posting."),
        ("x" * 1001, "Comments can be at most 1000 characters."),
    ],
)
def test_invalid_text_is_422_and_stores_nothing(client: TestClient, db: Session, user, article, text: str, message: str) -> None:
    response = post(client, user, text)
    assert response.status_code == 422
    assert response.json() == {"detail": message}
    assert db.scalar(select(func.count()).select_from(Comment)) == 0
    assert comment_count(db) == 0


@pytest.mark.parametrize("body", [{}, {"text": None}, {"text": 5}, {"text": "Hi", "parent_id": 5}, []])
def test_wrong_body_shape_is_422_with_string_detail(client: TestClient, user, article, body) -> None:
    response = client.post("/articles/a1/comments", json=body, headers=auth_headers(user))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_null_characters_are_removed_from_text(client: TestClient, user, article) -> None:
    assert post(client, user, "Hel\x00lo").json()["text"] == "Hello"


def test_posting_increases_the_comment_count(client: TestClient, db: Session, user, article) -> None:
    top = post(client, user).json()
    post(client, user, parent_id=top["id"])
    assert comment_count(db) == 2
    assert client.get("/articles/a1").json()["comment_count"] == 2


# --- Replies ------------------------------------------------------------------------------


def test_reply_attaches_to_its_parent(client: TestClient, user, article) -> None:
    top = post(client, user).json()
    assert post(client, user, "Reply", parent_id=top["id"]).json()["parent_id"] == top["id"]


def test_explicit_null_parent_is_a_top_level_comment(client: TestClient, user, article) -> None:
    assert post(client, user, parent_id=None).json()["parent_id"] is None


def test_reply_to_a_reply_attaches_to_the_top_level_comment(client: TestClient, user, article) -> None:
    top = post(client, user).json()
    first = post(client, user, parent_id=top["id"]).json()
    second = post(client, user, parent_id=first["id"]).json()
    third = post(client, user, parent_id=second["id"]).json()

    assert second["parent_id"] == top["id"]
    assert third["parent_id"] == top["id"]


MISSING_PARENT = {"detail": "The comment you're replying to is no longer available."}


def test_reply_to_an_unknown_comment_is_404(client: TestClient, db: Session, user, article) -> None:
    response = post(client, user, parent_id="c_missing")
    assert response.status_code == 404
    assert response.json() == MISSING_PARENT
    assert comment_count(db) == 0


def test_reply_to_a_comment_on_another_article_is_404(client: TestClient, db: Session, user, article) -> None:
    make_article(db, "a2")
    elsewhere = make_comment(db, user, article_id="a2")
    assert post(client, user, parent_id=elsewhere.id).json() == MISSING_PARENT


def test_reply_to_a_hidden_comment_is_404(client: TestClient, db: Session, user, article) -> None:
    hidden = make_comment(db, user, is_hidden=True)
    assert post(client, user, parent_id=hidden.id).status_code == 404


def test_reply_to_a_hidden_reply_is_404(client: TestClient, db: Session, user, article) -> None:
    top = make_comment(db, user)
    reply = make_comment(db, user, parent_id=top.id, is_hidden=True)
    assert post(client, user, parent_id=reply.id).status_code == 404


def test_reply_to_a_reply_under_a_hidden_comment_is_404(client: TestClient, db: Session, user, article) -> None:
    top = make_comment(db, user, is_hidden=True)
    reply = make_comment(db, user, parent_id=top.id)
    assert post(client, user, parent_id=reply.id).status_code == 404


# --- Upvotes ------------------------------------------------------------------------------


def test_upvote_returns_the_contract_shape(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    response = upvote(client, user, comment.id)
    assert response.status_code == 200
    assert response.json() == {"upvotes": 1}


def test_upvote_is_idempotent(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    assert [upvote(client, user, comment.id).json()["upvotes"] for _ in range(3)] == [1, 1, 1]
    assert db.scalar(select(func.count()).select_from(CommentUpvote)) == 1


def test_removing_an_upvote_is_idempotent_and_never_negative(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    assert upvote(client, user, comment.id, False).json() == {"upvotes": 0}
    upvote(client, user, comment.id)
    assert upvote(client, user, comment.id, False).json() == {"upvotes": 0}
    assert upvote(client, user, comment.id, False).json() == {"upvotes": 0}
    assert db.scalar(select(func.count()).select_from(CommentUpvote)) == 0


def test_upvotes_from_different_users_add_up(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    other = make_user(db, "other@example.com")
    upvote(client, user, comment.id)
    assert upvote(client, other, comment.id).json() == {"upvotes": 2}
    assert upvote(client, user, comment.id, False).json() == {"upvotes": 1}


def test_user_upvoted_is_per_user(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    other = make_user(db, "other@example.com")
    upvote(client, user, comment.id)

    def seen_by(headers: dict) -> bool:
        return client.get("/articles/a1/comments", headers=headers).json()[0]["user_upvoted"]

    assert seen_by(auth_headers(user)) is True
    assert seen_by(auth_headers(other)) is False
    assert seen_by({}) is False


def test_upvoting_requires_login(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    assert client.post(f"/comments/{comment.id}/upvote", json={"upvoted": True}).status_code == 401


def test_upvoting_an_unknown_comment_is_404(client: TestClient, user) -> None:
    response = upvote(client, user, "c_missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Comment not found"}


def test_upvoting_a_hidden_comment_is_404(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user, is_hidden=True)
    assert upvote(client, user, comment.id).status_code == 404


@pytest.mark.parametrize("body", [{}, {"upvoted": "true"}, {"upvoted": 1}, {"upvoted": None}])
def test_invalid_upvote_body_is_422_with_string_detail(client: TestClient, db: Session, user, article, body) -> None:
    comment = make_comment(db, user)
    response = client.post(f"/comments/{comment.id}/upvote", json=body, headers=auth_headers(user))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


# --- My comments --------------------------------------------------------------------------


def test_my_comments_requires_login(client: TestClient) -> None:
    response = client.get("/users/me/comments")
    assert response.status_code == 401
    assert response.json() == {"detail": "Please log in to do that."}


def test_my_comments_is_empty_for_a_new_user(client: TestClient, user) -> None:
    assert client.get("/users/me/comments", headers=auth_headers(user)).json() == []


def test_my_comments_are_only_mine_newest_first_across_articles(client: TestClient, db: Session, user, article) -> None:
    make_article(db, "a2")
    other = make_user(db, "other@example.com")
    older = make_comment(db, user, created_at=BASE - timedelta(hours=2))
    newer = make_comment(db, user, article_id="a2", created_at=BASE)
    make_comment(db, other)

    assert ids(client.get("/users/me/comments", headers=auth_headers(user))) == [newer.id, older.id]


def test_my_comments_include_replies_and_hidden_ones(client: TestClient, db: Session, user, article) -> None:
    top = make_comment(db, user)
    reply = make_comment(db, user, parent_id=top.id, created_at=BASE + timedelta(minutes=1))
    hidden = make_comment(db, user, is_hidden=True, created_at=BASE + timedelta(minutes=2))

    assert ids(client.get("/users/me/comments", headers=auth_headers(user))) == [hidden.id, reply.id, top.id]


def test_my_comments_show_my_upvotes(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    upvote(client, user, comment.id)
    response = client.get("/users/me/comments", headers=auth_headers(user)).json()[0]
    assert (response["user_upvoted"], response["upvotes"]) == (True, 1)


# --- Null characters (PostgreSQL rejects these in queries) ---------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/articles/%00"),
        ("get", "/articles/%00/comments"),
    ],
)
def test_null_character_in_a_public_id_is_404(client: TestClient, method: str, path: str) -> None:
    assert getattr(client, method)(path).status_code == 404


def test_null_character_in_a_protected_id_is_404(client: TestClient, user) -> None:
    headers = auth_headers(user)
    assert client.post("/articles/%00/vote", json={"vote": "up"}, headers=headers).status_code == 404
    assert client.post("/articles/%00/comments", json={"text": "Hi"}, headers=headers).status_code == 404
    assert client.post("/comments/%00/upvote", json={"upvoted": True}, headers=headers).status_code == 404


def test_null_character_in_a_parent_id_is_404(client: TestClient, user, article) -> None:
    assert post(client, user, parent_id="\x00").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"email": "a\x00b@example.com", "password": "password123"},
        {"email": "a@example.com", "password": "pass\x00word123"},
    ],
)
def test_null_characters_in_login_do_not_crash(client: TestClient, body: dict) -> None:
    assert client.post("/auth/login", json=body).status_code == 401


def test_null_characters_in_registration_do_not_crash(client: TestClient) -> None:
    body = {"display_name": "As\x00ha", "email": "n@example.com", "password": "pass\x00word123"}
    response = client.post("/auth/register", json=body)
    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Asha"

    bad_email = body | {"email": "a\x00b@example.com"}
    assert client.post("/auth/register", json=bad_email).status_code == 422


# --- Concurrency --------------------------------------------------------------------------


@needs_postgres
def test_concurrent_comments_keep_the_count_exact(client: TestClient, db: Session, article) -> None:
    users = [make_user(db, f"u{i}@example.com") for i in range(8)]

    def send(index: int) -> int:
        return post(client, users[index % len(users)], f"Comment {index}").status_code

    with ThreadPoolExecutor(8) as pool:
        assert set(pool.map(send, range(40))) == {200}

    assert comment_count(db) == 40


@needs_postgres
def test_concurrent_upvotes_keep_the_count_exact(client: TestClient, db: Session, user, article) -> None:
    comment = make_comment(db, user)
    users = [make_user(db, f"u{i}@example.com") for i in range(10)]
    # Every user sends the same upvote three times at once.
    requests = [users[i % len(users)] for i in range(30)]

    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda voter: upvote(client, voter, comment.id).status_code, requests))

    assert set(codes) == {200}
    db.expire_all()
    assert db.get(Comment, comment.id).upvotes == 10
    assert db.scalar(select(func.count()).select_from(CommentUpvote)) == 10
