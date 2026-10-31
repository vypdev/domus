"""Shared native input bounds and actual Supervisor peer/base-path policy."""

import re

from starlette.types import Scope

from domus.domain.errors import Forbidden, InvalidInput


def require_ingress_source(scope: Scope) -> None:
    headers = scope["headers"]
    if (
        len(headers) > 100
        or sum(len(key) + len(value) for key, value in headers) > 16_384
        or scope.get("query_string", b"")
    ):
        raise InvalidInput("invalid_request")
    peer = scope.get("client")
    if (
        scope["path"] == "/health"
        and scope["method"] in ("GET", "HEAD")
        and peer
        and peer[0] in ("127.0.0.1", "::1", "172.30.32.2")
    ):
        return
    if peer is None or peer[0] != "172.30.32.2":
        raise Forbidden("ingress_access_required")
    prefixes = [value for key, value in headers if key.lower() == b"x-ingress-path"]
    if len(prefixes) != 1 or not re.fullmatch(
        rb"/api/hassio_ingress/[A-Za-z0-9_-]{16,256}", prefixes[0]
    ):
        raise Forbidden("ingress_access_required")
