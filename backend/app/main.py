"""Application entry point: uvicorn app.main:app

No CORS middleware on purpose: the only client is the iOS app, which isn't subject to CORS.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.errors import register_error_handlers
from app.logging_config import RequestLoggingMiddleware, configure_logging
from app.rate_limit import limiter
from app.request_size import RequestSizeLimitMiddleware
from app.routers import articles, auth, comments, health, moderation
from app.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    scheduler = (
        start_scheduler(settings.ingestion_interval_minutes) if settings.ingestion_enabled else None
    )
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="PublicPost API",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.limiter = limiter
    # The last one added runs first, so oversized requests still get logged.
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(articles.router)
    app.include_router(auth.router)
    app.include_router(comments.router)
    app.include_router(moderation.router)
    return app


app = create_app()
