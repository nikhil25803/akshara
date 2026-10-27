import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestTooLarge(Exception):
    pass


class ApiKeyMiddleware:
    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in {"/", "/health"}:
            await self.app(scope, receive, send)
            return

        supplied_key = Headers(scope=scope).get("api_key", "")
        if not secrets.compare_digest(supplied_key, self.api_key):
            await JSONResponse(
                {"detail": "Invalid or missing API key"}, status_code=401
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] not in {"/v1/ocr", "/v1/extract"}
        ):
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length:
            try:
                if int(content_length) < 0:
                    raise ValueError
            except ValueError:
                await JSONResponse(
                    {"detail": "Invalid Content-Length"}, status_code=400
                )(scope, receive, send)
                return
            if int(content_length) > self.max_bytes:
                await JSONResponse({"detail": "Upload is too large"}, status_code=413)(
                    scope, receive, send
                )
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await JSONResponse({"detail": "Upload is too large"}, status_code=413)(
                scope, receive, send
            )
