"""Refuses oversized request bodies before they reach the app or use up memory."""

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The largest real request is a comment of 1000 characters, about 12 KB fully JSON-escaped.
MAX_REQUEST_BYTES = 64 * 1024
_TOO_LARGE = "That request is too large."


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            response = JSONResponse(
                {"detail": _TOO_LARGE}, status_code=status.HTTP_413_CONTENT_TOO_LARGE
            )
            await response(scope, receive, send)
            return

        # A chunked request declares no length, so the bytes are counted as they arrive.
        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, _TOO_LARGE)
            return message

        await self.app(scope, counting_receive, send)
