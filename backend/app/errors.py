"""Every error leaves the API as {"detail": "message"}, with detail always a string.

The iOS client decodes `detail` as a String. FastAPI's default validation response has a list
there, which the app could only show as a generic server error.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


def validation_message(exc: RequestValidationError) -> str:
    """Describes the first problem, e.g. "password: String should have at least 8 characters"."""
    errors = exc.errors()
    if not errors:
        return "Invalid request."
    first = errors[0]
    # Our own validators write full sentences for users, and the app shows them as they are.
    if first["type"] == "value_error":
        return first["msg"].removeprefix("Value error, ")
    # loc starts with where the value came from ("body", "query", ...); the field name follows.
    field = ".".join(str(part) for part in first["loc"][1:])
    return f"{field}: {first['msg']}" if field else first["msg"]


async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": validation_message(exc)},
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong on our side. Please try again."},
    )


async def _handle_rate_limit(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "You're doing that too often. Please wait a minute and try again."},
        headers={"Retry-After": str(exc.limit.limit.get_expiry())},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RateLimitExceeded, _handle_rate_limit)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
