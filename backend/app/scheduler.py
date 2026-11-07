"""Background news fetching. Assumes one server process: run uvicorn with a single worker."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import utcnow
from app.ingestion import run_ingestion


def start_scheduler(interval_minutes: int) -> BackgroundScheduler:
    """Runs ingestion now, without delaying startup, and then on the given interval."""
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_ingestion,
        "interval",
        minutes=interval_minutes,
        id="ingest_news",
        next_run_time=utcnow(),
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    return scheduler
