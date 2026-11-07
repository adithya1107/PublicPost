"""Config validation, error format, logging and production settings."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.logging_config import JSONFormatter
from app.main import create_app

SECRET = "x" * 32


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("sqlite:///./local.db", "sqlite:///./local.db"),
    ],
)
def test_database_url_gets_the_psycopg_driver(given: str, expected: str) -> None:
    settings = Settings(_env_file=None, jwt_secret=SECRET, database_url=given)
    assert settings.database_url == expected


def test_missing_jwt_secret_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_short_jwt_secret_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret="too-short")


def test_validation_errors_have_a_string_detail() -> None:
    class Body(BaseModel):
        password: str

    app = create_app()

    @app.post("/echo")
    def echo(body: Body) -> None: ...

    response = TestClient(app).post("/echo", json={})
    assert response.status_code == 422
    assert response.json() == {"detail": "password: Field required"}


def test_unexpected_errors_are_json_and_hide_internals() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert list(response.json()) == ["detail"]
    assert "hunter2" not in response.text


def test_unknown_route_has_a_string_detail(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_no_cors_headers(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_docs_are_off_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").status_code == 200
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_requests_are_logged_as_json_without_query_strings(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="publicpost.request"):
        client.get("/health?token=secret-value")

    record = next(r for r in caplog.records if r.name == "publicpost.request")
    entry = json.loads(JSONFormatter().format(record))
    assert entry["method"] == "GET"
    assert entry["path"] == "/health"
    assert entry["status"] == 200
    assert entry["timestamp"].endswith("Z")
    assert "secret-value" not in json.dumps(entry)
