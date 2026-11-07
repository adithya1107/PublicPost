"""Test setup. Environment variables are set before any app import, because the engine is
created on import. Tests use a throwaway SQLite file built by the real migrations.

To run the whole suite on PostgreSQL, set TEST_DATABASE_URL. Its tables get emptied.
"""

import os
import tempfile

_tmp = tempfile.TemporaryDirectory(prefix="publicpost-tests-")
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp.name}/test.db"
os.environ["JWT_SECRET"] = "test-only-secret-" + "x" * 64
os.environ["LOG_LEVEL"] = "INFO"
os.environ["INGESTION_ENABLED"] = "false"  # tests must never reach out to real news sites
os.environ["RATE_LIMITS_ENABLED"] = "false"  # turned on only by the rate limit tests

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Comment  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(connection=None) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    if connection is not None:
        config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
def empty_tables_after_test() -> Iterator[None]:
    yield
    with engine.begin() as connection:
        # A parent comment can't be deleted while replies point at it, so replies go first.
        connection.execute(Comment.__table__.delete().where(Comment.parent_id.is_not(None)))
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client
