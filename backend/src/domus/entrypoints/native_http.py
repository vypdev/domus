"""Native HTTP binds HA Ingress to local sessions and the common household API."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, cast

from fastapi import Depends, FastAPI, Header, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import APIKeyCookie
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Scope

from domus.application.identity_ports import LeaseClock
from domus.application.sessions import SessionStatus
from domus.domain.errors import DomusError, Forbidden
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.entry_context import CONTEXT_HEADER, EntryHTTPContext
from domus.entrypoints.household_http import HouseholdHTTPContext, create_household_router
from domus.entrypoints.http import CSRFResponse, SessionResponse
from domus.entrypoints.http_contract import ErrorResponse, StrictModel
from domus.entrypoints.http_errors import classify
from domus.entrypoints.ingress_boundary import require_ingress_source

_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
    ),
}


@dataclass(frozen=True, slots=True)
class NativeHTTPContext:
    household: HouseholdHTTPContext
    status: Callable[[], SessionStatus]
    csrf: Callable[[], str]
    verify_csrf: Callable[[str], None]


class NativeSessionResponse(SessionResponse):
    source: Literal["home_assistant_ingress"] = "home_assistant_ingress"


class _Empty(StrictModel):
    pass


def _error(status: int, code: str, correlation: str) -> Response:
    uncertain = status == 500
    return JSONResponse(
        {
            "state": "blocked",
            "code": code,
            "message": (
                "Domus could not confirm the request result."
                if uncertain
                else "The request was not accepted. No household change was made."
            ),
            "action_required": (
                "Retry the same payload and Idempotency-Key or inspect the operation ID. "
                "Do not start a replacement command."
                if uncertain
                else "Open or refresh Domus through Home Assistant and review current access. "
                "No separate Domus login is required. Existing household records are retained."
            ),
            "correlation_id": correlation,
        },
        status_code=status,
        headers={**_HEADERS, **({"Retry-After": "1"} if code == "storage_busy" else {})},
    )


class _NativeBoundary(BoundedHTTP):
    def __init__(
        self, app: ASGIApp, origins: tuple[str, ...], correlation: Callable[[], str]
    ) -> None:
        self.origins = origins
        super().__init__(app, self._allowed, correlation, _error, _HEADERS)

    def _allowed(self, scope: Scope) -> None:
        require_ingress_source(scope)
        if scope["method"] not in ("GET", "HEAD", "POST", "PUT"):
            raise Forbidden("request_forbidden")
        if scope["method"] in ("POST", "PUT"):
            origins = [value for name, value in scope["headers"] if name.lower() == b"origin"]
            if len(origins) != 1 or origins[0].decode("latin1") not in self.origins:
                raise Forbidden("request_forbidden")
            if scope["path"] == "/health":
                raise Forbidden("request_forbidden")


def create_native_app(
    context: Callable[[Request], NativeHTTPContext],
    origins: tuple[str, ...],
    channel: str,
    clock: LeaseClock,
    *,
    correlation: Callable[[], str],
    entry: EntryHTTPContext | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Domus native Home Assistant application",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 403, 404, 405, 408, 409, 413, 422, 500, 503)
        },
    )
    app.add_middleware(_NativeBoundary, origins=origins, correlation=correlation)

    async def domain_error(request: Request, error: Exception) -> Response:
        status, code = classify(cast(DomusError, error))
        return _error(status, code, request.state.correlation_id)

    async def invalid(request: Request, error: Exception) -> Response:
        return _error(422, "invalid_request", request.state.correlation_id)

    async def missing(request: Request, error: Exception) -> Response:
        return _error(
            cast(HTTPException, error).status_code,
            "resource_unavailable",
            request.state.correlation_id,
        )

    async def unexpected(request: Request, error: Exception) -> Response:
        return _error(500, "internal_error", request.state.correlation_id)

    app.add_exception_handler(DomusError, domain_error)
    app.add_exception_handler(RequestValidationError, invalid)
    app.add_exception_handler(HTTPException, missing)
    app.add_exception_handler(Exception, unexpected)

    cookie_scheme = APIKeyCookie(
        name="ingress_session", scheme_name="HomeAssistantIngress", auto_error=False
    )

    def security(
        request: Request,
        _cookie: Annotated[str | None, Security(cookie_scheme)],
        _context: Annotated[str | None, Header(alias=CONTEXT_HEADER)] = None,
    ) -> None:
        access = context(request)
        if request.headers.getlist(CONTEXT_HEADER):
            if entry is None:
                raise Forbidden("request_forbidden")
            entry.require(request, access.status().human)
        if request.method in ("POST", "PUT"):
            tokens = request.headers.getlist("x-csrf-token")
            if len(tokens) != 1:
                raise Forbidden("request_forbidden")
            access.verify_csrf(tokens[0])

    @app.get(
        "/api/v1/session", response_model=NativeSessionResponse, dependencies=[Depends(security)]
    )
    def session(request: Request, query: Annotated[_Empty, Query()]) -> NativeSessionResponse:
        status = context(request).status()
        metadata = entry.describe(request, status) if entry is not None else None
        return NativeSessionResponse(
            ha_user_id=status.human.ha_user_id,
            ha_administrator=status.human.is_administrator,
            access="full" if status.fresh else "read_only",
            expires_in=max(0, (status.expires_at - clock.now()) // 1000)
            if metadata is None
            else max(0, (metadata.expires_at - metadata.server_time) // 1000),
            context=metadata,
            message="Your existing Home Assistant session is verified."
            if status.fresh
            else "Home Assistant is unavailable. Your existing session has read-only access.",
            action_required="No additional login is required."
            if status.fresh
            else "Reconnect to Home Assistant before making changes.",
        )

    @app.get("/api/v1/auth/csrf", response_model=CSRFResponse, dependencies=[Depends(security)])
    def csrf(request: Request, query: Annotated[_Empty, Query()]) -> CSRFResponse:
        return CSRFResponse(csrf_token=context(request).csrf())

    @app.get("/api/v1/openapi.json", dependencies=[Depends(security)])
    def schema(request: Request, query: Annotated[_Empty, Query()]) -> dict[str, object]:
        context(request).status()
        return app.openapi()

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(security)])
    def home(request: Request) -> Response:
        context(request).status()
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Domus {channel.title()}</title></head><body><main>"
            f"<h1>Domus {channel.title()}</h1><p>Development preview</p>"
            "<h2>Connected to Home Assistant</h2>"
            "<p>Your existing Home Assistant sign-in is being used. "
            "No additional login is required.</p><p>The household interface is being prepared.</p>"
            '<p><a href="./">Refresh connection</a></p></main></body></html>'
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ready", "scope": "process"}

    app.include_router(
        create_household_router(
            lambda request: context(request).household, security=Depends(security)
        )
    )
    return app
