"""Observe disposable HTTP requests without retrying or changing the product exchange."""

import faulthandler
import hashlib
import sys
from threading import Timer
from time import monotonic

from starlette.types import ASGIApp, Message, Receive, Scope, Send


def observe_http(app: ASGIApp, mode: str, prefix: str) -> ASGIApp:
    async def observed(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        path = scope["path"].removeprefix(prefix)
        if not path.startswith("/api/v1/"):
            await app(scope, receive, send)
            return
        method, started = scope["method"], monotonic()
        phase, status = "accepted", 0
        setup = method == "POST" and path == "/api/v1/household"
        keys = [v for k, v in scope["headers"] if k.lower() == b"idempotency-key"]
        key_digest = hashlib.sha256(keys[0]).hexdigest()[:12] if len(keys) == 1 else "none"

        def report(event: str) -> None:
            print(
                f"fixture_http {event} mode={mode} method={method} path={path} "
                f"key_digest={key_digest} phase={phase} status={status} "
                f"elapsed_ms={(monotonic() - started) * 1000:.1f}",
                file=sys.stderr,
                flush=True,
            )

        def pending() -> None:
            report("pending")
            # Stack locations only: no request headers, bodies, credentials or frame locals.
            faulthandler.dump_traceback(file=sys.stderr)

        async def received() -> Message:
            nonlocal phase
            message = await receive()
            phase = message["type"]
            return message

        async def sent(message: Message) -> None:
            nonlocal phase, status
            phase = message["type"]
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        watchdog = Timer(5, pending) if setup else None
        if watchdog is not None:
            watchdog.daemon = True
            report("begin")
            watchdog.start()
        try:
            await app(scope, received, sent)
        except BaseException:
            report("raised")
            raise
        finally:
            if watchdog is not None:
                watchdog.cancel()
            if setup or status >= 500 or monotonic() - started >= 5:
                report("end")

    return observed
