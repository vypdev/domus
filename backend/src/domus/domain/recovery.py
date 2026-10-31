"""Pure, target-bound recovery with bounded request and single-use approval windows."""

from dataclasses import dataclass, replace
from enum import StrEnum

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    MappingMode,
    Member,
    validate_revision,
)
from domus.domain.storage import Installation, JsonDocument, Receipt, validate_identifier

RECOVERY_LIFETIME = 600_000


def closed_recovery(receipt: Receipt) -> str | None:
    """Original terminal facts identify a resource that restoration must never rearm."""
    expected = {"recovery.complete": "recovered", "recovery.cancel": "canceled"}.get(
        receipt.command.action
    )
    if expected is None:
        return None
    result = receipt.result.decode()
    request_id = result.get("request_id")
    if not isinstance(request_id, str) or result.get("state") != expected:
        raise InvalidInput("invalid_recovery_history")
    validate_identifier(request_id)
    return request_id


class RecoveryState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CONSUMED = "consumed"
    CANCELED = "canceled"


def validate_recovery_time(value: int) -> None:
    if type(value) is not int or not 0 <= value <= 2**63 - 1 - RECOVERY_LIFETIME:
        raise InvalidInput("invalid_recovery_time")


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    request_id: str
    household_id: str
    target_ha_user_id: str
    installation: Installation
    mapping: AdministratorMapping
    policy_revision: int
    member_id: str | None
    member_revision: int
    created_at: int
    expires_at: int
    state: RecoveryState = RecoveryState.PENDING
    revision: int = 1
    approved_at: int | None = None
    closed_at: int | None = None

    def __post_init__(self) -> None:
        for value in (self.request_id, self.household_id, self.target_ha_user_id):
            validate_identifier(value)
        validate_revision(self.policy_revision)
        validate_recovery_time(self.created_at)
        if (
            not isinstance(self.installation, Installation)
            or not isinstance(self.mapping, AdministratorMapping)
            or self.mapping.mode not in (MappingMode.SETUP, MappingMode.SELECTED)
            or type(self.expires_at) is not int
            or not isinstance(self.state, RecoveryState)
        ):
            raise InvalidInput("invalid_recovery_request")
        if self.member_id is None:
            if type(self.member_revision) is not int or self.member_revision != 0:
                raise InvalidInput("invalid_recovery_member")
        else:
            validate_identifier(self.member_id)
            validate_revision(self.member_revision)
        if self.approved_at is not None:
            validate_recovery_time(self.approved_at)
            if not self.created_at <= self.approved_at < self.created_at + RECOVERY_LIFETIME:
                raise InvalidInput("invalid_recovery_request")
        origin = self.created_at if self.approved_at is None else self.approved_at
        if self.expires_at != origin + RECOVERY_LIFETIME:
            raise InvalidInput("invalid_recovery_request")
        if self.closed_at is not None:
            validate_recovery_time(self.closed_at)
            earliest = self.created_at if self.approved_at is None else self.approved_at
            if self.closed_at < earliest:
                raise InvalidInput("invalid_recovery_request")
        expected = {
            RecoveryState.PENDING: (1, False, False),
            RecoveryState.APPROVED: (2, True, False),
            RecoveryState.CONSUMED: (3, True, True),
            RecoveryState.CANCELED: (2 if self.approved_at is None else 3, False, True),
        }[self.state]
        if (
            type(self.revision) is not int
            or self.revision != expected[0]
            or (self.state is not RecoveryState.CANCELED)
            and (self.approved_at is not None) != expected[1]
            or (self.closed_at is not None) != expected[2]
            or self.state is RecoveryState.CONSUMED
            and self.closed_at is not None
            and self.closed_at >= self.expires_at
        ):
            raise InvalidInput("invalid_recovery_request")

    def document(self) -> JsonDocument:
        return JsonDocument.from_value(
            {
                "request_id": self.request_id,
                "household_id": self.household_id,
                "target_ha_user_id": self.target_ha_user_id,
                "instance_id": self.installation.instance_id,
                "channel": self.installation.channel,
                "mapping_mode": self.mapping.mode.value,
                "mapping_target": self.mapping.target_ha_user_id,
                "policy_revision": self.policy_revision,
                "member_id": self.member_id,
                "member_revision": self.member_revision,
                "created_at": self.created_at,
                "expires_at": self.expires_at,
                "state": self.state.value,
                "revision": self.revision,
                "approved_at": self.approved_at,
                "closed_at": self.closed_at,
            }
        )

    def require_current(
        self, installation: Installation, policy: HouseholdPolicy | None, member: Member | None
    ) -> None:
        if (
            self.installation != installation
            or policy is None
            or policy.household_id != self.household_id
            or policy.mapping != self.mapping
            or policy.revision != self.policy_revision
            or (None if member is None else member.member_id) != self.member_id
            or (0 if member is None else member.revision) != self.member_revision
            or member is not None
            and (
                member.household_id != self.household_id
                or member.ha_user_id != self.target_ha_user_id
            )
        ):
            raise Conflict("recovery_binding_changed")

    def visible_state(self, now: int) -> str:
        validate_recovery_time(now)
        origin = self.created_at if self.approved_at is None else self.approved_at
        if self.state in (RecoveryState.PENDING, RecoveryState.APPROVED) and not (
            origin <= now < self.expires_at
        ):
            return "expired"
        return self.state.value

    def _live(self, now: int) -> None:
        if self.visible_state(now) == "expired":
            raise Conflict("recovery_expired")

    def approve(self, now: int) -> RecoveryRequest:
        self._live(now)
        if self.state is not RecoveryState.PENDING:
            raise Conflict("recovery_not_pending")
        return replace(
            self,
            state=RecoveryState.APPROVED,
            revision=2,
            approved_at=now,
            expires_at=now + RECOVERY_LIFETIME,
        )

    def consume(self, now: int) -> RecoveryRequest:
        self._live(now)
        if self.state is not RecoveryState.APPROVED:
            raise Conflict("recovery_not_approved")
        return replace(self, state=RecoveryState.CONSUMED, revision=3, closed_at=now)

    def cancel(self, now: int) -> RecoveryRequest:
        validate_recovery_time(now)
        if self.state not in (RecoveryState.PENDING, RecoveryState.APPROVED):
            raise Conflict("recovery_closed")
        if now < self.created_at:
            raise Conflict("recovery_expired")
        return replace(
            self, state=RecoveryState.CANCELED, revision=self.revision + 1, closed_at=now
        )
