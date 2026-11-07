"""Rate limits and request size limits."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Comment, User
from app.rate_limit import limiter
from app.request_size import MAX_REQUEST_BYTES
from tests.factories import auth_headers, make_article, make_comment, make_user

TOO_OFTEN = {"detail": "You're doing that too often. Please wait a minute and try again."}
TOO_LARGE = {"detail": "That request is too large."}


@pytest.fixture
def limits_on() -> Iterator[None]:
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


def client_from(ip: str) -> TestClient:
    return TestClient(create_app(), client=(ip, 50000))


def expect_limited(response) -> None:
    assert response.status_code == 429
    assert response.json() == TOO_OFTEN
    assert response.headers["retry-after"] == "60"


# --- Login: 10 per minute per IP ----------------------------------------------------------


LOGIN = {"email": "nobody@example.com", "password": "wrong-password"}


def test_eleventh_login_in_a_minute_is_429(limits_on, client: TestClient) -> None:
    for _ in range(10):
        assert client.post("/auth/login", json=LOGIN).status_code == 401
    expect_limited(client.post("/auth/login", json=LOGIN))


def test_correct_password_is_also_blocked_once_limited(limits_on, client: TestClient) -> None:
    good = {"display_name": "Asha", "email": "a@example.com", "password": "password123"}
    client.post("/auth/register", json=good)
    for _ in range(10):
        client.post("/auth/login", json=LOGIN)
    expect_limited(client.post("/auth/login", json={"email": good["email"], "password": good["password"]}))


def test_login_limit_is_per_ip(limits_on) -> None:
    first, second = client_from("203.0.113.1"), client_from("203.0.113.2")
    for _ in range(10):
        first.post("/auth/login", json=LOGIN)
    expect_limited(first.post("/auth/login", json=LOGIN))
    assert second.post("/auth/login", json=LOGIN).status_code == 401


def test_changing_email_does_not_escape_the_login_limit(limits_on, client: TestClient) -> None:
    for index in range(10):
        client.post("/auth/login", json={"email": f"u{index}@example.com", "password": "password123"})
    expect_limited(client.post("/auth/login", json={"email": "new@example.com", "password": "password123"}))


# --- Register: 5 per minute per IP --------------------------------------------------------


def registration(index: int) -> dict:
    return {"display_name": "Asha", "email": f"u{index}@example.com", "password": "password123"}


def test_sixth_registration_in_a_minute_is_429(limits_on, client: TestClient, db: Session) -> None:
    for index in range(5):
        assert client.post("/auth/register", json=registration(index)).status_code == 200
    expect_limited(client.post("/auth/register", json=registration(5)))
    assert db.scalar(select(func.count()).select_from(User)) == 5


def test_register_limit_is_per_ip(limits_on) -> None:
    first, second = client_from("203.0.113.1"), client_from("203.0.113.2")
    for index in range(5):
        first.post("/auth/register", json=registration(index))
    expect_limited(first.post("/auth/register", json=registration(5)))
    assert second.post("/auth/register", json=registration(6)).status_code == 200


def test_login_and_register_are_counted_separately(limits_on, client: TestClient) -> None:
    for index in range(5):
        client.post("/auth/register", json=registration(index))
    assert client.post("/auth/login", json=LOGIN).status_code == 401


# --- Comments: 10 per minute per user -----------------------------------------------------


def post_comment(client: TestClient, user, article_id: str = "a1"):
    return client.post(f"/articles/{article_id}/comments", json={"text": "Hi"}, headers=auth_headers(user))


def test_eleventh_comment_in_a_minute_is_429(limits_on, client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    for _ in range(10):
        assert post_comment(client, user).status_code == 200
    expect_limited(post_comment(client, user))
    assert db.scalar(select(func.count()).select_from(Comment)) == 10


def test_comment_limit_is_per_user_not_per_ip(limits_on, client: TestClient, db: Session) -> None:
    first = make_user(db, "first@example.com")
    second = make_user(db, "second@example.com")
    make_article(db, "a1")
    for _ in range(10):
        post_comment(client, first)
    expect_limited(post_comment(client, first))
    assert post_comment(client, second).status_code == 200


def test_comment_limit_follows_the_user_across_ips(limits_on, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    for _ in range(10):
        client_from("203.0.113.1").post("/articles/a1/comments", json={"text": "Hi"}, headers=auth_headers(user))
    expect_limited(
        client_from("203.0.113.2").post("/articles/a1/comments", json={"text": "Hi"}, headers=auth_headers(user))
    )


def test_comment_limit_covers_all_articles(limits_on, client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    make_article(db, "a2")
    for _ in range(10):
        post_comment(client, user, "a1")
    expect_limited(post_comment(client, user, "a2"))


def test_reading_comments_is_not_limited(limits_on, client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    for _ in range(10):
        post_comment(client, user)
    expect_limited(post_comment(client, user))
    assert client.get("/articles/a1/comments").status_code == 200


def test_guests_get_401_rather_than_using_up_a_limit(limits_on, client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    for _ in range(15):
        assert client.post("/articles/a1/comments", json={"text": "Hi"}).status_code == 401


# --- Votes: 60 per minute per user --------------------------------------------------------


def vote(client: TestClient, user, article_id: str = "a1"):
    return client.post(f"/articles/{article_id}/vote", json={"vote": "up"}, headers=auth_headers(user))


def test_sixty_first_vote_in_a_minute_is_429(limits_on, client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    for _ in range(60):
        assert vote(client, user).status_code == 200
    expect_limited(vote(client, user))


def test_vote_limit_is_per_user_and_covers_all_articles(limits_on, client: TestClient, db: Session) -> None:
    first = make_user(db, "first@example.com")
    second = make_user(db, "second@example.com")
    make_article(db, "a1")
    make_article(db, "a2")
    for _ in range(60):
        vote(client, first, "a1")
    expect_limited(vote(client, first, "a2"))
    assert vote(client, second, "a1").status_code == 200


def test_comment_upvotes_have_their_own_vote_limit(limits_on, client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    comment = make_comment(db, user)

    def upvote():
        return client.post(f"/comments/{comment.id}/upvote", json={"upvoted": True}, headers=auth_headers(user))

    for _ in range(60):
        assert upvote().status_code == 200
    expect_limited(upvote())
    assert vote(client, user).status_code == 200


# --- Switching limits off -----------------------------------------------------------------


def test_limits_can_be_switched_off(client: TestClient) -> None:
    assert limiter.enabled is False
    for _ in range(15):
        assert client.post("/auth/login", json=LOGIN).status_code == 401


# --- Request size -------------------------------------------------------------------------


def test_oversized_request_is_413_with_string_detail(client: TestClient) -> None:
    body = {"email": "a" * MAX_REQUEST_BYTES, "password": "x"}
    response = client.post("/auth/login", json=body)
    assert response.status_code == 413
    assert response.json() == TOO_LARGE


def test_oversized_request_without_a_declared_length_is_413(client: TestClient) -> None:
    def chunks():
        yield b'{"email": "'
        yield b"a" * (MAX_REQUEST_BYTES + 1)
        yield b'", "password": "x"}'

    response = client.post("/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.json() == TOO_LARGE


def test_oversized_request_is_refused_before_login_is_checked(client: TestClient) -> None:
    response = client.post("/auth/login", content=b"x" * (MAX_REQUEST_BYTES + 1))
    assert response.status_code == 413


def test_request_at_the_limit_is_accepted(client: TestClient) -> None:
    padding = MAX_REQUEST_BYTES - len('{"email":"a@example.com","password":"wrong-password","pad":""}')
    content = f'{{"email":"a@example.com","password":"wrong-password","pad":"{"x" * padding}"}}'
    assert len(content) == MAX_REQUEST_BYTES
    response = client.post("/auth/login", content=content, headers={"Content-Type": "application/json"})
    assert response.status_code == 401


def test_longest_real_comment_fits_even_fully_escaped(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    # Each emoji is one Python character here, and two \uXXXX escapes (12 bytes) in the JSON.
    escaped = "\\ud83d\\ude00" * 1000
    response = client.post(
        "/articles/a1/comments",
        content=f'{{"text":"{escaped}"}}',
        headers=auth_headers(user) | {"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "\U0001F600" * 1000
