"""Native HA authentication preview; no OAuth, personal business data or mutations."""

import base64
import hashlib
import re
from collections.abc import Callable
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Scope

from domus.domain.errors import (
    DomusError,
    Forbidden,
    IdentityUnavailable,
    InvalidInput,
    Unauthenticated,
)
from domus.domain.identity import HumanIdentity
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.http import ErrorResponse

IdentityProof = Callable[[str, tuple[tuple[str, str], ...]], HumanIdentity]
_STYLE = (
    "body{font:1rem system-ui;margin:3rem auto;padding:1rem;"
    "max-width:44rem;color-scheme:light dark}"
)
_STYLE_HASH = base64.b64encode(hashlib.sha256(_STYLE.encode()).digest()).decode()
_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        f"default-src 'none'; style-src 'sha256-{_STYLE_HASH}'; base-uri 'none'; form-action 'none'"
    ),
}


class IngressIdentityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    state: str = "authenticated"
    source: str = "home_assistant_ingress"
    ha_user_id: str
    ha_administrator: bool
    message: str = "Your existing Home Assistant session is verified."


def _blocked(status: int, code: str, correlation: str) -> Response:
    return JSONResponse(
        {
            "state": "blocked",
            "code": code,
            "message": (
                "Domus could not verify access through Home Assistant. "
                "No household change was made."
            ),
            "action_required": (
                "Open Domus from its Home Assistant app page. If already open there, "
                "check the app's HA connection. No separate Domus login is required."
            ),
            "correlation_id": correlation,
        },
        status_code=status,
        headers=_HEADERS,
    )


class _IngressBoundary(BoundedHTTP):
    def __init__(self, app: ASGIApp, correlation: Callable[[], str]) -> None:
        super().__init__(app, self._allowed, correlation, _blocked, _HEADERS)

    def _allowed(self, scope: Scope) -> None:
        headers = scope["headers"]
        if (
            len(headers) > 100
            or sum(len(key) + len(value) for key, value in headers) > 16_384
            or scope.get("query_string", b"")
        ):
            raise InvalidInput("invalid_request")
        peer = scope.get("client")
        if scope["path"] == "/health" and peer and peer[0] in ("127.0.0.1", "::1", "172.30.32.2"):
            return
        if peer is None or peer[0] != "172.30.32.2":
            raise Forbidden("ingress_access_required")
        prefixes = [value for key, value in headers if key.lower() == b"x-ingress-path"]
        if len(prefixes) != 1 or not re.fullmatch(
            rb"/api/hassio_ingress/[A-Za-z0-9_-]{16,256}", prefixes[0]
        ):
            raise Forbidden("ingress_access_required")
        if scope["method"] not in ("GET", "HEAD"):
            raise Forbidden("request_forbidden")


def create_ingress_app(
    identity: IdentityProof, channel: str, *, correlation: Callable[[], str]
) -> FastAPI:
    if channel not in ("stable", "edge"):
        raise InvalidInput("invalid_channel")
    app = FastAPI(
        title="Domus native HA preview",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 422, 500, 503)},
    )
    app.add_middleware(_IngressBoundary, correlation=correlation)

    async def failure(request: Request, error: Exception) -> Response:
        status, code = 500, "internal_error"
        if isinstance(error, IdentityUnavailable):
            status, code = 503, "ha_unavailable"
        elif isinstance(error, Unauthenticated):
            status, code = 401, "ha_rejected"
        elif isinstance(error, HTTPException):
            status, code = error.status_code, "resource_unavailable"
        return _blocked(status, code, request.state.correlation_id)

    for kind in (DomusError, HTTPException, Exception):
        app.add_exception_handler(kind, failure)

    def prove(request: Request) -> HumanIdentity:
        peer = cast(tuple[str, int], request.scope["client"])
        return identity(
            peer[0],
            tuple(
                (key.decode("latin1"), value.decode("latin1"))
                for key, value in request.scope["headers"]
            ),
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Response:
        prove(request)
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Domus {channel.title()}</title><style>{_STYLE}</style></head><body><main>"
            f"<h1>Domus {channel.title()}</h1><p>Development preview</p>"
            "<h2>Connected to Home Assistant</h2>"
            "<p>Your existing Home Assistant sign-in is being used. "
            "No additional login is required.</p>"
            "<p>Household setup is not available in this build.</p>"
            '<p><a href="./">Refresh connection</a></p></main></body></html>'
        )

    @app.get("/api/v1/identity", response_model=IngressIdentityResponse)
    def own_identity(request: Request) -> IngressIdentityResponse:
        human = prove(request)
        return IngressIdentityResponse(
            ha_user_id=human.ha_user_id, ha_administrator=human.is_administrator
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ready", "scope": "process"}

    return app
