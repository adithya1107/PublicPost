"""Alembic environment. Uses the app's engine unless a test passes its own connection."""

from alembic import context
from sqlalchemy.engine import Connection

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.config import get_settings
from app.database import Base, UTCDateTime, engine
from app.logging_config import configure_logging


def render_item(type_, obj, autogen_context):
    """Migrations stay self-contained: they record the plain column type, not our app class."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        render_item=render_item,
        # SQLite can't alter most things in place, so changes rebuild the table.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


configure_logging(get_settings().log_level)

if context.is_offline_mode():
    raise SystemExit("Offline migrations aren't supported; run against a database.")

provided = context.config.attributes.get("connection")
if provided is not None:
    run(provided)
else:
    with engine.connect() as connection:
        run(connection)
