"""Checks every endpoint against the spec the iOS app depends on, in one place."""

import re
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import utcnow
from app.main import create_app
from app.security import create_token
from tests.factories import auth_headers, make_article, make_comment, make_user

ENDPOINTS = {
    ("GET", "/health"),
    ("GET", "/articles"),
    ("GET", "/articles/{article_id}"),
    ("POST", "/articles/{article_id}/vote"),
    ("GET", "/articles/{article_id}/comments"),
    ("POST", "/articles/{article_id}/comments"),
    ("POST", "/comments/{comment_id}/upvote"),
    ("GET", "/users/me/comments"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/comments/{comment_id}/report"),
    ("POST", "/users/{user_id}/block"),
    ("DELETE", "/users/{user_id}/block"),
    ("DELETE", "/users/me"),
}

PROTECTED = [
    ("POST", "/articles/a1/vote", {"vote": "up"}),
    ("POST", "/articles/a1/comments", {"text": "Hi"}),
    ("POST", "/comments/c1/upvote", {"upvoted": True}),
    ("GET", "/users/me/comments", None),
    ("POST", "/comments/c1/report", {"reason": "spam"}),
    ("POST", "/users/u1/block", None),
    ("DELETE", "/users/u1/block", None),
    ("DELETE", "/users/me", None),
]
PUBLIC = [
    ("GET", "/health"),
    ("GET", "/articles"),
    ("GET", "/articles/a1"),
    ("GET", "/articles/a1/comments"),
]
UNAUTHORIZED = {"detail": "Please log in to do that."}
SECRET = "test-only-secret-" + "x" * 64


def send(client: TestClient, method: str, path: str, body=None, headers: dict | None = None):
    return client.request(method, path, json=body, headers=headers or {})


def test_the_api_has_exactly_the_endpoints_in_the_spec() -> None:
    routes = {
        (method.upper(), path)
        for path, operations in create_app().openapi()["paths"].items()
        for method in operations
    }
    assert routes == ENDPOINTS


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED, ids=lambda v: v if isinstance(v, str) else "")
class TestEveryProtectedRoute:
    def test_no_token_is_401(self, client: TestClient, method, path, body) -> None:
        response = send(client, method, path, body)
        assert response.status_code == 401
        assert response.json() == UNAUTHORIZED

    def test_invalid_token_is_401(self, client: TestClient, method, path, body) -> None:
        response = send(client, method, path, body, {"Authorization": "Bearer garbage"})
        assert response.status_code == 401
        assert response.json() == UNAUTHORIZED

    def test_expired_token_is_401(self, client: TestClient, db: Session, method, path, body) -> None:
        user = make_user(db)
        now = utcnow()
        token = jwt.encode(
            {"sub": user.id, "iat": now - timedelta(days=31), "exp": now - timedelta(days=1)},
            SECRET,
            algorithm="HS256",
        )
        response = send(client, method, path, body, {"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json() == UNAUTHORIZED


@pytest.mark.parametrize(("method", "path"), PUBLIC)
def test_public_routes_work_for_guests_valid_and_invalid_tokens(
    client: TestClient, db: Session, method: str, path: str
) -> None:
    user = make_user(db)
    make_article(db, "a1")
    for headers in ({}, auth_headers(user), {"Authorization": "Bearer garbage"}):
        assert send(client, method, path, headers=headers).status_code == 200


def test_every_error_is_a_string_detail(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    headers = auth_headers(user)
    responses = {
        400: send(client, "POST", f"/users/{user.id}/block", headers=headers),
        401: send(client, "GET", "/users/me/comments"),
        404: send(client, "GET", "/articles/missing"),
        405: send(client, "PUT", "/articles"),
        409: None,
        422: send(client, "GET", "/articles", headers=headers) and client.get("/articles?page=0"),
    }
    register = {"display_name": "Asha", "email": "dup@example.com", "password": "password123"}
    client.post("/auth/register", json=register)
    responses[409] = client.post("/auth/register", json=register)

    for status_code, response in responses.items():
        assert response.status_code == status_code
        assert list(response.json()) == ["detail"]
        assert isinstance(response.json()["detail"], str)


def test_all_ids_are_strings_and_dates_are_utc_with_z(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    top = make_comment(db, user)
    make_comment(db, user, parent_id=top.id)
    utc = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

    article = client.get("/articles/a1").json()
    assert isinstance(article["id"], str)
    assert utc.fullmatch(article["published_at"])

    for comment in client.get("/articles/a1/comments").json():
        for key in ("id", "article_id", "author_id"):
            assert isinstance(comment[key], str)
        assert comment["parent_id"] is None or isinstance(comment["parent_id"], str)
        assert utc.fullmatch(comment["created_at"])


def test_all_keys_are_snake_case(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    make_comment(db, user)
    register = client.post(
        "/auth/register",
        json={"display_name": "Asha", "email": "s@example.com", "password": "password123"},
    ).json()
    headers = auth_headers(user)
    bodies = [
        client.get("/articles/a1").json(),
        client.get("/articles/a1/comments").json()[0],
        client.post("/articles/a1/vote", json={"vote": "up"}, headers=headers).json(),
        register,
        register["user"],
    ]
    for body in bodies:
        assert all(re.fullmatch(r"[a-z_]+", key) for key in body)


def test_token_from_create_token_is_accepted_by_a_protected_route(client: TestClient, db: Session) -> None:
    user = make_user(db)
    response = client.get("/users/me/comments", headers={"Authorization": f"Bearer {create_token(user.id)}"})
    assert response.status_code == 200


def test_no_cors_headers_on_preflight(client: TestClient) -> None:
    response = client.options(
        "/articles", headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in response.headers
