"""Bounded ASGI input and response protections shared by HTTP deployment adapters."""

from asyncio import timeout
from collections.abc import Callable, Mapping

from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from domus.domain.errors import DomusError, InvalidInput


class BoundedHTTP:
    def __init__(
        self,
        app: ASGIApp,
        validate: Callable[[Scope], None],
        correlation: Callable[[], str],
        error: Callable[[int, str, str], Response],
        headers: Mapping[str, str],
    ) -> None:
        self.app, self.validate, self.correlation = app, validate, correlation
        self.error, self.headers = error, headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation = self.correlation()
        scope.setdefault("state", {})["correlation_id"] = correlation
        try:
            self.validate(scope)
        except DomusError as error:
            status = 422 if isinstance(error, InvalidInput) else 403
            await self.error(
                status, "invalid_request" if status == 422 else "request_forbidden", correlation
            )(scope, receive, send)
            return
        body = bytearray()
        try:
            async with timeout(5):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    data = message.get("body", b"")
                    if len(body) + len(data) > 65_536:
                        await self.error(413, "request_too_large", correlation)(
                            scope, receive, send
                        )
                        return
                    body.extend(data)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await self.error(408, "request_timeout", correlation)(scope, receive, send)
            return
        if scope["method"] in ("GET", "HEAD") and body:
            await self.error(422, "invalid_request", correlation)(scope, receive, send)
            return
        first = True

        async def buffered() -> Message:
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                protected = {key.lower().encode("ascii") for key in self.headers}
                message = {
                    **message,
                    "headers": [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() not in protected
                    ]
                    + [
                        (key.lower().encode("ascii"), value.encode("ascii"))
                        for key, value in self.headers.items()
                    ],
                }
            await send(message)

        await self.app(scope, buffered, secured)
