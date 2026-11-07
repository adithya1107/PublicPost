"""Runs the migrations on SQLite always, and on PostgreSQL when TEST_POSTGRES_URL is set.

That database must be empty, because the test drops everything it creates.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.config import Settings
from app.database import Base, make_engine
from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "users", "articles", "votes", "comments", "comment_upvotes", "comment_reports", "blocks",
}
BACKENDS = ["sqlite"] + (["postgresql"] if os.environ.get("TEST_POSTGRES_URL") else [])


@pytest.mark.parametrize("backend", BACKENDS)
def test_upgrade_matches_models_then_downgrades_cleanly(backend: str, tmp_path: Path) -> None:
    if backend == "sqlite":
        url = f"sqlite:///{tmp_path}/migrations.db"
    else:
        url = Settings(_env_file=None, database_url=os.environ["TEST_POSTGRES_URL"]).database_url
    engine = make_engine(url)

    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "head")
            inspector = inspect(connection)
            assert EXPECTED_TABLES <= set(inspector.get_table_names())

            # An empty diff means the models and migrations describe the same schema.
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            assert compare_metadata(context, Base.metadata) == []

            required_indexes = {
                "articles": {"ix_articles_published_at_id", "ix_articles_category_published_at_id"},
                "comments": {"ix_comments_article_id_created_at"},
            }
            for table, names in required_indexes.items():
                assert names <= {index["name"] for index in inspector.get_indexes(table)}
            assert inspector.get_pk_constraint("votes")["constrained_columns"] == [
                "user_id", "article_id",
            ]

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "base")
            remaining = set(inspect(connection).get_table_names())
            assert not (EXPECTED_TABLES & remaining)
    finally:
        engine.dispose()
