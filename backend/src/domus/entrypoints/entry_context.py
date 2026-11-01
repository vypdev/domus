"""Nonsecret deployment facts and opt-in context assertions never select an actor."""

import hmac
from dataclasses import dataclass, field
from typing import Literal, cast

from fastapi import Request
from pydantic import Field

from domus.application.identity_ports import LeaseClock
from domus.application.ports import Clock
from domus.application.sessions import SessionStatus
from domus.domain.errors import Forbidden, InvalidInput, StorageFailure
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.entrypoints.http_contract import StrictModel
from domus.entrypoints.ingress_boundary import require_ingress_source

CONTEXT_HEADER = "X-Domus-Context"
_MAX_TIME = 2**53 - 1


class EntryContextResponse(StrictModel):
    installation_id: str
    channel: Literal["stable", "edge"]
    deployment: Literal["native", "standalone"]
    application_base: str
    household_api_available: bool
    server_time: int = Field(ge=0, le=_MAX_TIME)
    expires_at: int = Field(ge=0, le=_MAX_TIME)


def _time(value: int) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_TIME:
        raise StorageFailure("invalid_entry_clock")
    return value


@dataclass(frozen=True, slots=True)
class EntryHTTPContext:
    installation: Installation
    deployment: Literal["native", "standalone"]
    lease_clock: LeaseClock
    utc_clock: Clock
    household_api_available: bool
    _lease_origin: int = field(init=False, repr=False)
    _epoch_offset: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            self.deployment not in ("native", "standalone")
            or type(self.household_api_available) is not bool
        ):
            raise InvalidInput("invalid_request")
        origin = _time(self.lease_clock.now())
        object.__setattr__(self, "_lease_origin", origin)
        object.__setattr__(self, "_epoch_offset", _time(self.utc_clock.now()) - origin)

    def asserted(self, request: Request) -> bool:
        return bool(request.headers.getlist(CONTEXT_HEADER))

    def require(self, request: Request, human: HumanIdentity) -> None:
        values = request.headers.getlist(CONTEXT_HEADER)
        expected = (
            f"v1:{self.installation.instance_id}:{self.installation.channel}:{human.ha_user_id}"
        ).encode("ascii")
        try:
            if (
                len(values) != 1
                or len(values[0]) > 256
                or not hmac.compare_digest(values[0].encode("ascii"), expected)
            ):
                raise Forbidden("request_forbidden")
        except UnicodeError:
            raise Forbidden("request_forbidden") from None

    def describe(self, request: Request, status: SessionStatus) -> EntryContextResponse:
        now = _time(self.lease_clock.now())
        if now < self._lease_origin:
            raise StorageFailure("invalid_entry_clock")
        base = "/"
        if self.deployment == "native":
            require_ingress_source(request.scope)
            base = request.headers["X-Ingress-Path"] + "/"
        return EntryContextResponse(
            installation_id=self.installation.instance_id,
            channel=cast(Literal["stable", "edge"], self.installation.channel),
            deployment=self.deployment,
            application_base=base,
            household_api_available=self.household_api_available,
            server_time=_time(self._epoch_offset + now),
            expires_at=_time(self._epoch_offset + _time(status.expires_at)),
        )
