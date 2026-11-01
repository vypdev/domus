"""Serve nonpersonal fixed-base UI resources behind the existing HTTP boundaries."""

import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from domus.domain.errors import InvalidInput, StorageFailure
from domus.entrypoints.ingress_boundary import require_ingress_source
from domus.entrypoints.ui_bundle import BOOTSTRAP_SLOT, UIBundle

Deployment = Literal["native", "standalone"]
_POLICY = "domus_ui_response"


@dataclass(frozen=True, slots=True)
class _ShellPolicy:
    nonce: str


class _UIHeaders:
    def __init__(self, app: ASGIApp, deployment: Deployment) -> None:
        self.app, self.deployment = app, deployment

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        state.pop(_POLICY, None)
        ancestors = "'self'" if self.deployment == "native" else "'none'"
        base = (
            f"default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors {ancestors}"
        )

        async def secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                policy = state.get(_POLICY)
                csp = base
                if isinstance(policy, _ShellPolicy) and message["status"] == 200:
                    csp = (
                        "default-src 'none'; script-src 'self'; "
                        f"style-src 'self' 'nonce-{policy.nonce}'; "
                        "connect-src 'self'; img-src 'self'; font-src 'self'; object-src 'none'; "
                        f"base-uri 'none'; form-action 'none'; frame-ancestors {ancestors}"
                    )
                message = {
                    **message,
                    "headers": [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() != b"content-security-policy"
                    ]
                    + [(b"content-security-policy", csp.encode("ascii"))],
                }
            await send(message)

        await self.app(scope, receive, secured)


def _clean(request: Request) -> None:
    if request.scope.get("query_string") or any(
        value in request.scope.get("raw_path", b"") for value in (b"%", b"\\")
    ):
        raise InvalidInput("invalid_request")


def _response(request: Request, content: bytes, mime: str, status: int = 200) -> Response:
    return Response(
        b"" if request.method == "HEAD" else content,
        status_code=status,
        media_type=mime,
        headers={"Content-Length": str(len(content))},
    )


def attach_ui(
    app: FastAPI,
    bundle: UIBundle | None,
    deployment: Deployment,
    bind: Callable[[Request], None],
    *,
    nonce: Callable[[], str] = lambda: secrets.token_urlsafe(24),
) -> None:
    if deployment not in ("native", "standalone"):
        raise InvalidInput("invalid_request")
    app.add_middleware(_UIHeaders, deployment=deployment)

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def home(request: Request) -> Response:
        _clean(request)
        bind(request)
        if bundle is None:
            return _response(
                request,
                b"<!doctype html><html lang=en><meta charset=utf-8><title>Domus</title>"
                b"<h1>UI assets are unavailable</h1><p>Build or install the verified "
                b"Domus interface. "
                b"Existing household records and server history are retained.</p></html>",
                "text/html",
                503,
            )
        base = "/"
        if deployment == "native":
            require_ingress_source(request.scope)
            base = request.headers["X-Ingress-Path"] + "/"
        style_nonce = nonce()
        if not isinstance(style_nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32}", style_nonce):
            raise StorageFailure("ui_bundle_unavailable")
        bootstrap = json.dumps(
            {
                "version": 1,
                "deployment": deployment,
                "application_base": base,
                "style_nonce": style_nonce,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
        template = bundle.template.replace(BOOTSTRAP_SLOT, bootstrap)
        template = template.replace('"./assets/', '"' + base + "assets/")
        request.scope["state"][_POLICY] = _ShellPolicy(style_nonce)
        return _response(request, template.encode("utf-8"), "text/html")

    @app.api_route("/assets/{filename}", methods=["GET", "HEAD"], include_in_schema=False)
    def asset(request: Request, filename: str) -> Response:
        _clean(request)
        bind(request)
        item = bundle.assets.get("assets/" + filename) if bundle is not None else None
        if item is None:
            return _response(request, b"Resource unavailable.", "text/plain", 404)
        return _response(request, item[0], item[1])
