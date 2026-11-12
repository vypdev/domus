"""The private and HTTPS boundaries for scoped Home Assistant installation reads."""

import hashlib
import hmac
import re
from dataclasses import dataclass, field

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from domus.domain.errors import InvalidInput
from domus.domain.storage import Installation

PROJECTION_PORT = 8100
NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
_DIGEST = re.compile(r"[0-9a-f]{64}")
_SECRET = re.compile(rb"[0-9a-f]{64}")


def validate_digest(value: str, code: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise InvalidInput(code)
    return value


def projection_error(status: int, code: str, _correlation: str = "") -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers=NO_STORE)


@dataclass(frozen=True, slots=True)
class ProjectionGrant:
    installation: Installation
    digest: str = field(repr=False)
    scope_prefix: str

    def accepts(self, scope: Scope) -> bool:
        values = [value for key, value in scope["headers"] if key == b"authorization"]
        if len(values) != 1:
            return False
        prefix = (
            f"Bearer {self.installation.instance_id}.{self.installation.channel}."
            f"{self.scope_prefix}"
        ).encode("ascii")
        value = values[0]
        if not value.startswith(prefix) or not _SECRET.fullmatch(value[len(prefix) :]):
            return False
        return hmac.compare_digest(hashlib.sha256(value[7:]).hexdigest(), self.digest)


@dataclass(frozen=True, slots=True)
class ProjectionRoute:
    api: ASGIApp
    grant: ProjectionGrant
    denied: str


class HAProjectionBoundary:
    def __init__(
        self,
        app: ASGIApp,
        routes: dict[str, ProjectionRoute],
        standalone_host: bytes | None,
    ) -> None:
        self.app, self.routes = app, routes
        self.standalone_host = standalone_host

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        standalone = self.standalone_host is not None
        server = scope.get("server")
        path = scope["path"]
        technical = (
            path in self.routes
            if standalone
            else (server is not None and server[1] == PROJECTION_PORT)
        )
        if not technical:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        route = self.routes.get(path)
        if route is None:
            await projection_error(404, "not_found")(scope, receive, send)
            return
        if standalone and not self._standalone_transport(scope):
            await projection_error(403, "request_forbidden")(scope, receive, send)
            return
        if not route.grant.accepts(scope):
            await projection_error(401, route.denied)(scope, receive, send)
            return
        await route.api(scope, receive, send)

    def _standalone_transport(self, scope: Scope) -> bool:
        hosts = [value for key, value in scope["headers"] if key == b"host"]
        peer = scope.get("client")
        return hosts == [self.standalone_host] and (
            scope["scheme"] == "https" or (peer is not None and peer[0] in ("127.0.0.1", "::1"))
        )
