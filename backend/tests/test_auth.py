from datetime import timedelta
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.database import utcnow
from app.models import User
from app.security import create_token, hash_password, read_token, verify_password
from tests.factories import auth_headers, make_article, make_user

SECRET = "test-only-secret-" + "x" * 64
VALID = {"display_name": "Asha Rao", "email": "asha@example.com", "password": "correct-horse"}
LOGIN = {"email": VALID["email"], "password": VALID["password"]}


def register(client: TestClient, **overrides):
    return client.post("/auth/register", json=VALID | overrides)


def forged_token(**claims) -> str:
    now = utcnow()
    values = {"sub": "u_1", "iat": now, "exp": now + timedelta(days=1)} | claims
    values = {key: value for key, value in values.items() if value is not None}
    return jwt.encode(values, SECRET, algorithm="HS256")


# --- Register -----------------------------------------------------------------------------


def test_register_returns_the_contract_shape(client: TestClient) -> None:
    response = register(client)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"token", "user"}
    assert set(body["user"]) == {"id", "display_name"}
    assert isinstance(body["user"]["id"], str)
    assert body["user"]["display_name"] == "Asha Rao"
    assert read_token(body["token"]) == body["user"]["id"]


def test_password_is_stored_hashed_with_argon2(client: TestClient, db: Session) -> None:
    register(client)
    user = db.scalar(select(User))
    assert VALID["password"] not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")


def test_duplicate_email_is_409(client: TestClient) -> None:
    register(client)
    response = register(client, display_name="Other")
    assert response.status_code == 409
    assert response.json() == {"detail": "An account with that email already exists."}


def test_email_uniqueness_ignores_case_and_spaces(client: TestClient) -> None:
    register(client)
    assert register(client, email="  ASHA@Example.COM ").status_code == 409


def test_simultaneous_registration_race_is_409_not_500(client: TestClient, db: Session) -> None:
    make_user(db, VALID["email"])
    # Simulates losing the race: the pre-check saw nothing, but the insert then conflicts.
    with patch("app.routers.auth.select") as select_mock:
        select_mock.return_value.where.return_value = select(User.id).where(User.id == "nobody")
        assert register(client).status_code == 409


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"email": "not-an-email"}, "Please enter a valid email address."),
        ({"email": ""}, "Please enter a valid email address."),
        ({"email": "a@b"}, "Please enter a valid email address."),
        ({"password": "short"}, "Password must be at least 8 characters."),
        ({"password": "1234567"}, "Password must be at least 8 characters."),
        ({"password": "x" * 129}, "Password must be at most 128 characters."),
        ({"display_name": "A"}, "Display name must be 2 to 30 characters."),
        ({"display_name": "   A   "}, "Display name must be 2 to 30 characters."),
        ({"display_name": "   "}, "Display name must be 2 to 30 characters."),
        ({"display_name": "x" * 31}, "Display name must be 2 to 30 characters."),
        ({"display_name": "[deleted]"}, "That display name isn't available."),
        ({"display_name": "[DELETED]"}, "That display name isn't available."),
    ],
)
def test_invalid_registration_is_422_with_a_friendly_message(
    client: TestClient, overrides: dict, message: str
) -> None:
    response = register(client, **overrides)
    assert response.status_code == 422
    assert response.json() == {"detail": message}


@pytest.mark.parametrize("field", ["display_name", "email", "password"])
def test_missing_or_wrong_type_fields_are_422_with_string_detail(client: TestClient, field: str) -> None:
    missing = {key: value for key, value in VALID.items() if key != field}
    for body in (missing, VALID | {field: 123}):
        response = client.post("/auth/register", json=body)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("length", [8, 128])
def test_password_length_limits_are_inclusive(client: TestClient, length: int) -> None:
    assert register(client, password="x" * length).status_code == 200


@pytest.mark.parametrize("name", ["Jo", "x" * 30, "अदिति", "  Spaced   Out  "])
def test_valid_display_names(client: TestClient, name: str) -> None:
    assert register(client, display_name=name).status_code == 200


def test_display_name_is_trimmed_and_collapsed(client: TestClient) -> None:
    response = register(client, display_name="  Spaced   Out  ")
    assert response.json()["user"]["display_name"] == "Spaced Out"


def test_passwords_are_never_echoed_in_errors(client: TestClient) -> None:
    response = register(client, password="abc", email="bad")
    assert "abc" not in response.text
    response = client.post("/auth/register", json=VALID | {"email": "bad"})
    assert VALID["password"] not in response.text


# --- Login --------------------------------------------------------------------------------


def test_login_returns_the_same_user_as_register(client: TestClient) -> None:
    user_id = register(client).json()["user"]["id"]
    response = client.post("/auth/login", json=LOGIN)

    assert response.status_code == 200
    assert response.json()["user"] == {"id": user_id, "display_name": "Asha Rao"}
    assert read_token(response.json()["token"]) == user_id


def test_login_email_ignores_case(client: TestClient) -> None:
    register(client)
    assert client.post("/auth/login", json=LOGIN | {"email": "ASHA@EXAMPLE.COM"}).status_code == 200


def test_password_is_case_sensitive_and_not_trimmed(client: TestClient) -> None:
    register(client)
    for password in ("CORRECT-HORSE", " correct-horse", "correct-horse "):
        assert client.post("/auth/login", json=LOGIN | {"password": password}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        LOGIN | {"password": "wrong-password"},
        LOGIN | {"email": "nobody@example.com"},
        LOGIN | {"email": "not-an-email"},
        LOGIN | {"email": ""},
        LOGIN | {"password": ""},
    ],
)
def test_bad_credentials_are_401_with_one_identical_message(client: TestClient, body: dict) -> None:
    register(client)
    response = client.post("/auth/login", json=body)
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password."}


def test_unknown_email_still_spends_time_on_a_password_check(client: TestClient) -> None:
    with patch("app.routers.auth.burn_password_check") as burn:
        client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever1"})
    burn.assert_called_once_with("whatever1")


def test_deleted_account_cannot_log_in(client: TestClient, db: Session) -> None:
    db.add(User(email=None, password_hash=None, display_name="[deleted]", deleted_at=utcnow()))
    db.commit()
    assert client.post("/auth/login", json={"email": "", "password": ""}).status_code == 401


def test_login_upgrades_an_outdated_hash(client: TestClient, db: Session) -> None:
    register(client)
    old_hash = db.scalar(select(User)).password_hash

    with patch("app.routers.auth.needs_rehash", return_value=True):
        assert client.post("/auth/login", json=LOGIN).status_code == 200

    db.expire_all()
    new_hash = db.scalar(select(User)).password_hash
    assert new_hash != old_hash
    assert verify_password(VALID["password"], new_hash)


@pytest.mark.parametrize("field", ["email", "password"])
def test_login_missing_field_is_422(client: TestClient, field: str) -> None:
    body = {key: value for key, value in LOGIN.items() if key != field}
    response = client.post("/auth/login", json=body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


# --- Passwords and tokens -----------------------------------------------------------------


def test_verify_password_rejects_a_corrupt_hash() -> None:
    assert verify_password("anything", "not-a-hash") is False


def test_hashes_are_salted() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_token_expires_after_30_days() -> None:
    claims = jwt.decode(create_token("u_1"), SECRET, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 30 * 24 * 60 * 60
    assert claims["sub"] == "u_1"


def test_token_lifetime_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_EXPIRE_DAYS", "1")
    get_settings.cache_clear()
    try:
        claims = jwt.decode(create_token("u_1"), SECRET, algorithms=["HS256"])
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    assert claims["exp"] - claims["iat"] == 24 * 60 * 60


def test_token_contains_nothing_private() -> None:
    claims = jwt.decode(create_token("u_1"), SECRET, algorithms=["HS256"])
    assert set(claims) == {"sub", "iat", "exp"}


@pytest.mark.parametrize(
    "token",
    [
        "",
        "garbage",
        "a.b.c",
        forged_token(exp=utcnow() - timedelta(seconds=5)),
        forged_token(exp=None),
        forged_token(iat=None),
        forged_token(sub=None),
        jwt.encode({"sub": "u_1", "iat": utcnow(), "exp": utcnow() + timedelta(days=1)}, "x" * 40, algorithm="HS256"),
        jwt.encode({"sub": "u_1", "iat": utcnow(), "exp": utcnow() + timedelta(days=1)}, "", algorithm="none"),
        jwt.encode({"sub": "u_1", "iat": utcnow(), "exp": utcnow() + timedelta(days=1)}, SECRET, algorithm="HS512"),
    ],
    ids=["empty", "garbage", "three-parts", "expired", "no-exp", "no-iat", "no-sub", "wrong-key", "alg-none", "wrong-alg"],
)
def test_bad_tokens_are_rejected(token: str) -> None:
    assert security.read_token(token) is None


def test_a_tampered_token_is_rejected() -> None:
    header, payload, signature = create_token("u_1").split(".")
    forged_payload = jwt.utils.base64url_encode(b'{"sub":"u_admin","iat":1,"exp":99999999999}').decode()
    assert read_token(f"{header}.{forged_payload}.{signature}") is None


# --- Protected and public routes ----------------------------------------------------------


VOTE = {"vote": "up"}


def expect_401(response) -> None:
    assert response.status_code == 401
    assert response.json() == {"detail": "Please log in to do that."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_token_on_a_protected_route_is_401_not_403(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    expect_401(client.post("/articles/a1/vote", json=VOTE))


@pytest.mark.parametrize(
    "header",
    ["Bearer", "Bearer ", "Bearer garbage", "Basic dXNlcjpwYXNz", "garbage"],
)
def test_malformed_authorization_is_401(client: TestClient, db: Session, header: str) -> None:
    make_article(db, "a1")
    expect_401(client.post("/articles/a1/vote", json=VOTE, headers={"Authorization": header}))


def test_expired_token_is_401(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    token = forged_token(sub=user.id, exp=utcnow() - timedelta(seconds=5))
    expect_401(client.post("/articles/a1/vote", json=VOTE, headers={"Authorization": f"Bearer {token}"}))


def test_token_for_an_unknown_user_is_401(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    expect_401(client.post("/articles/a1/vote", json=VOTE, headers=auth_headers("u_gone")))


def test_token_for_a_deleted_account_is_401(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    user.deleted_at = utcnow()
    db.commit()
    expect_401(client.post("/articles/a1/vote", json=VOTE, headers=auth_headers(user)))


def test_bearer_scheme_is_case_insensitive(client: TestClient, db: Session) -> None:
    user = make_user(db)
    make_article(db, "a1")
    token = create_token(user.id)
    response = client.post("/articles/a1/vote", json=VOTE, headers={"Authorization": f"bearer {token}"})
    assert response.status_code == 200


def test_auth_is_checked_before_the_article_and_the_body(client: TestClient) -> None:
    expect_401(client.post("/articles/missing/vote", json={"vote": "sideways"}))


@pytest.mark.parametrize("header", ["Bearer garbage", "Basic abc", "Bearer"])
def test_bad_token_on_public_routes_means_guest_not_an_error(
    client: TestClient, db: Session, header: str
) -> None:
    make_article(db, "a1")
    headers = {"Authorization": header}

    listing = client.get("/articles", headers=headers)
    assert listing.status_code == 200
    assert listing.json()[0]["user_vote"] == "none"

    detail = client.get("/articles/a1", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["user_vote"] == "none"


def test_expired_token_on_public_routes_means_guest(client: TestClient, db: Session) -> None:
    make_article(db, "a1")
    token = forged_token(exp=utcnow() - timedelta(seconds=5))
    response = client.get("/articles", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
