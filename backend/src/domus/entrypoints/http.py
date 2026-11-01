"""Strict authentication DTOs and HTTP cookie/origin boundaries; no business storage."""

import hashlib
import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal, Self, cast
from urllib.parse import parse_qsl, urlsplit

from fastapi import Depends, FastAPI, Header, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.security import APIKeyCookie
from pydantic import Field, model_validator
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Scope

from domus.application.authentication import Authentication
from domus.application.identity_ports import LoginProvider
from domus.application.sessions import SessionGuard
from domus.domain.errors import (
    DomusError,
    Forbidden,
    IdentityRejected,
    InvalidInput,
    Unauthenticated,
)
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.entry_context import CONTEXT_HEADER, EntryContextResponse, EntryHTTPContext
from domus.entrypoints.household_http import HouseholdHTTPContext, create_household_router
from domus.entrypoints.http_contract import ErrorResponse, StrictModel
from domus.entrypoints.http_errors import classify
from domus.entrypoints.task_http import TaskHTTPContext, create_task_router
from domus.entrypoints.ui_bundle import UIBundle
from domus.entrypoints.ui_http import attach_ui


@dataclass(frozen=True, slots=True)
class HTTPSettings:
    origin: str
    cookie_tag: str
    csrf_secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.cookie_tag)
            or type(self.csrf_secret) is not bytes
            or len(self.csrf_secret) < 32
        ):
            raise InvalidInput("invalid_http_settings")

    @property
    def secure(self) -> bool:
        return self.origin.startswith("https://")

    @property
    def session_cookie(self) -> str:
        return ("__Host-" if self.secure else "") + self.cookie_tag + "-session"

    @property
    def browser_cookie(self) -> str:
        return ("__Host-" if self.secure else "") + self.cookie_tag + "-browser"

    def csrf(self, session_id: str) -> str:
        return hmac.new(self.csrf_secret, session_id.encode("utf-8"), hashlib.sha256).hexdigest()


def _cookie(scope: Scope, name: str, *, required: bool = True) -> str | None:
    candidates: list[str] = []
    for key, value in scope["headers"]:
        if key.lower() == b"cookie":
            for pair in value.decode("latin1").split(";"):
                cookie_name, separator, content = pair.strip().partition("=")
                if cookie_name == name and separator:
                    candidates.append(content)
    if not candidates and not required:
        return None
    if len(candidates) != 1 or not re.fullmatch(r"[A-Za-z0-9._~-]{1,128}", candidates[0]):
        raise Unauthenticated("session_required")
    return candidates[0]


_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def _error(status: int, code: str, correlation: str) -> JSONResponse:
    restart_login = code in ("invalid_login_attempt", "login_attempt_expired")
    return JSONResponse(
        {
            "state": "blocked",
            "code": code,
            "message": (
                "The sign-in attempt is missing, expired or no longer valid."
                if restart_login
                else (
                    "Domus could not confirm the request result."
                    if status == 500
                    else "The request was not accepted. No household change was made."
                )
            ),
            "action_required": (
                "Start a new sign-in at /api/v1/auth/start and complete it within five minutes. "
                "Existing household records are retained."
                if restart_login
                else (
                    "For a household change, retry the same payload and Idempotency-Key or check "
                    "its operation ID. Do not start a replacement command."
                    if status == 500
                    else (
                        "Review the request or sign in again. "
                        "Existing household records are retained."
                    )
                )
            ),
            "correlation_id": correlation,
        },
        status_code=status,
        headers={**_SECURITY_HEADERS, **({"Retry-After": "1"} if code == "storage_busy" else {})},
    )


class _HTTPBoundary(BoundedHTTP):
    def __init__(
        self, app: ASGIApp, settings: HTTPSettings, correlation: Callable[[], str]
    ) -> None:
        self.settings = settings
        super().__init__(app, self._allowed, correlation, _error, _SECURITY_HEADERS)

    def _allowed(self, scope: Scope) -> None:
        headers = scope["headers"]
        if len(headers) > 100 or sum(len(key) + len(value) for key, value in headers) > 16_384:
            raise InvalidInput("invalid_request")

        def values(name: bytes) -> list[bytes]:
            return [value for key, value in headers if key.lower() == name]

        hosts = values(b"host")
        expected = urlsplit(self.settings.origin)
        if len(hosts) != 1 or any(
            key.lower().startswith(b"x-remote-user-") or key.lower() == b"x-ingress-path"
            for key, _ in headers
        ):
            raise Forbidden("request_forbidden")
        try:
            host = hosts[0].decode("ascii")
            if any(character.isspace() or character in "/\\?#%" for character in host):
                raise ValueError("invalid host")
            actual = urlsplit(expected.scheme + "://" + host)
            default = 443 if expected.scheme == "https" else 80
            actual_port = actual.port if actual.port is not None else default
            expected_port = expected.port if expected.port is not None else default
            if (
                actual.hostname != expected.hostname
                or actual.username is not None
                or actual_port != expected_port
            ):
                raise ValueError("invalid host")
        except ValueError, UnicodeError:
            raise Forbidden("request_forbidden") from None
        query = scope.get("query_string", b"")
        if len(query) > 8192:
            raise InvalidInput("invalid_request")
        pairs = parse_qsl(query.decode("latin1"), keep_blank_values=True)
        if len(pairs) != len({key for key, _ in pairs}):
            raise InvalidInput("invalid_request")
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
            origins, csrf = values(b"origin"), values(b"x-csrf-token")
            session_id = _cookie(scope, self.settings.session_cookie)
            if (
                len(origins) != 1
                or origins[0] != self.settings.origin.encode("ascii")
                or len(csrf) != 1
                or not hmac.compare_digest(
                    csrf[0], self.settings.csrf(cast(str, session_id)).encode("ascii")
                )
            ):
                raise Forbidden("request_forbidden")


_Strict = StrictModel


class EmptyRequest(_Strict):
    pass


class CallbackQuery(_Strict):
    state: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")
    code: str | None = Field(
        default=None, min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9._~-]+$"
    )
    error: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z_]+$")

    @model_validator(mode="after")
    def one_result(self) -> Self:
        if (self.code is None) == (self.error is None):
            raise ValueError("provide_one_callback_result")
        return self


class SessionResponse(_Strict):
    state: Literal["authenticated"] = "authenticated"
    ha_user_id: str
    ha_administrator: bool
    access: Literal["full", "read_only"]
    expires_in: int
    context: EntryContextResponse | None = None
    message: str
    action_required: str


class CSRFResponse(_Strict):
    csrf_token: str


class LogoutResponse(_Strict):
    state: Literal["logged_out"] = "logged_out"
    upstream_revoked: bool | None
    message: Literal["You are signed out of Domus."] = "You are signed out of Domus."
    action_required: str


def create_app(
    authentication: Authentication,
    guard: SessionGuard,
    provider: LoginProvider,
    settings: HTTPSettings,
    *,
    correlation: Callable[[], str],
    entry: EntryHTTPContext,
    household_context: Callable[[str], HouseholdHTTPContext] | None = None,
    task_context: Callable[[str], TaskHTTPContext] | None = None,
    ui_bundle: UIBundle | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Domus",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        redirect_slashes=False,
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 403, 404, 405, 408, 409, 413, 422, 500, 503)
        },
    )
    app.add_middleware(_HTTPBoundary, settings=settings, correlation=correlation)
    cookie_security = Security(
        APIKeyCookie(name=settings.session_cookie, scheme_name="DomusSession", auto_error=False)
    )

    def bound_context(
        request: Request,
        _session_cookie: Annotated[str | None, cookie_security],
        _context: Annotated[str | None, Header(alias=CONTEXT_HEADER)] = None,
    ) -> None:
        if entry.asserted(request):
            entry.require(
                request, guard.read(cast(str, _cookie(request.scope, settings.session_cookie)))
            )

    session_security = Depends(bound_context)

    async def domain_error(request: Request, error: Exception) -> Response:
        status, code = classify(cast(DomusError, error))
        return _error(status, code, request.state.correlation_id)

    async def invalid_request(request: Request, error: Exception) -> Response:
        return _error(422, "invalid_request", request.state.correlation_id)

    async def missing_route(request: Request, error: Exception) -> Response:
        return _error(
            cast(HTTPException, error).status_code,
            "resource_unavailable",
            request.state.correlation_id,
        )

    async def unexpected(request: Request, error: Exception) -> Response:
        return _error(500, "internal_error", request.state.correlation_id)

    app.add_exception_handler(DomusError, domain_error)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(HTTPException, missing_route)
    app.add_exception_handler(Exception, unexpected)

    def cookie(response: Response, name: str, value: str, age: int) -> None:
        response.set_cookie(
            name,
            value,
            max_age=age,
            secure=settings.secure,
            httponly=True,
            samesite="lax",
            path="/",
        )

    @app.get("/api/v1/auth/start", status_code=303, response_class=RedirectResponse)
    def start(parameters: Annotated[EmptyRequest, Query()]) -> Response:
        result = authentication.start()
        response = RedirectResponse(result.authorization_url, status_code=303)
        cookie(response, settings.browser_cookie, result.browser_token, 300)
        return response

    @app.get(
        "/api/v1/auth/callback",
        status_code=303,
        response_class=RedirectResponse,
        description=(
            "Exactly one of code or error is required, together with state and the bound browser "
            "cookie. Providing both outcomes or neither returns 422 without consuming the attempt. "
            "A code completes authorization; an error records a declined authorization."
        ),
    )
    def callback(request: Request, parameters: Annotated[CallbackQuery, Query()]) -> Response:
        try:
            browser = cast(str, _cookie(request.scope, settings.browser_cookie))
        except Unauthenticated:
            raise IdentityRejected("invalid_login_attempt") from None
        if parameters.error is not None:
            authentication.cancel(parameters.state, browser)
            response: Response = _error(401, "sign_in_declined", request.state.correlation_id)
        else:
            previous = _cookie(request.scope, settings.session_cookie, required=False)
            lease = authentication.complete(cast(str, parameters.code), parameters.state, browser)
            if previous is not None:
                provider.sign_out(previous)
            response = RedirectResponse("/", status_code=303)
            cookie(
                response,
                settings.session_cookie,
                lease.session_id,
                max(0, (lease.expires_at - authentication.clock.now()) // 1000),
            )
        response.delete_cookie(
            settings.browser_cookie, path="/", secure=settings.secure, httponly=True, samesite="lax"
        )
        return response

    @app.get("/api/v1/session", response_model=SessionResponse, dependencies=[session_security])
    def session(request: Request, parameters: Annotated[EmptyRequest, Query()]) -> SessionResponse:
        status = guard.status(cast(str, _cookie(request.scope, settings.session_cookie)))
        metadata = entry.describe(request, status)
        return SessionResponse(
            ha_user_id=status.human.ha_user_id,
            ha_administrator=status.human.is_administrator,
            access="full" if status.fresh else "read_only",
            expires_in=max(0, (metadata.expires_at - metadata.server_time) // 1000),
            context=metadata,
            message=(
                "Your Home Assistant identity is verified."
                if status.fresh
                else "Home Assistant is unavailable. Your existing session has read-only access."
            ),
            action_required=(
                "No action required."
                if status.fresh
                else "Reconnect to Home Assistant before making changes."
            ),
        )

    @app.get("/api/v1/auth/csrf", response_model=CSRFResponse, dependencies=[session_security])
    def csrf(request: Request, parameters: Annotated[EmptyRequest, Query()]) -> CSRFResponse:
        session_id = cast(str, _cookie(request.scope, settings.session_cookie))
        guard.read(session_id)
        return CSRFResponse(csrf_token=settings.csrf(session_id))

    @app.post(
        "/api/v1/auth/logout",
        response_model=LogoutResponse,
        dependencies=[session_security],
        openapi_extra={
            "parameters": [
                {"name": "Origin", "in": "header", "required": True, "schema": {"type": "string"}},
                {
                    "name": "X-CSRF-Token",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "minLength": 64, "maxLength": 64},
                },
            ]
        },
    )
    def logout(request: Request, response: Response, body: EmptyRequest) -> LogoutResponse:
        session_id = cast(str, _cookie(request.scope, settings.session_cookie))
        revoked = provider.sign_out(session_id)
        response.delete_cookie(
            settings.session_cookie, path="/", secure=settings.secure, httponly=True, samesite="lax"
        )
        return LogoutResponse(
            upstream_revoked=revoked,
            action_required=(
                "No action required."
                if revoked is True
                else (
                    "Review the Domus authorization in your Home Assistant profile; "
                    "revocation was not confirmed."
                )
            ),
        )

    if household_context is not None:
        factory = household_context

        def context(request: Request) -> HouseholdHTTPContext:
            return factory(cast(str, _cookie(request.scope, settings.session_cookie)))

        app.include_router(create_household_router(context, security=session_security))
    if task_context is not None:
        task_factory = task_context

        def tasks(request: Request) -> TaskHTTPContext:
            return task_factory(cast(str, _cookie(request.scope, settings.session_cookie)))

        app.include_router(create_task_router(tasks, security=session_security))
    attach_ui(app, ui_bundle, "standalone", lambda request: None)
    return app
