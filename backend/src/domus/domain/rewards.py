"""Exact reward prices, reservations and reviewed redemption transitions."""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import Role, validate_revision
from domus.domain.point_allocation import MAX_POINT_SHARE
from domus.domain.storage import validate_identifier
from domus.domain.task_values import validate_task_text, validate_task_time


class RedemptionStage(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    FUNDING_HOLD = "funding_hold"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


RESERVED_STAGES = frozenset(
    {RedemptionStage.REQUESTED, RedemptionStage.APPROVED, RedemptionStage.FUNDING_HOLD}
)


def _price(cost_minor: int) -> None:
    if type(cost_minor) is not int or not 1 <= cost_minor <= MAX_POINT_SHARE:
        raise InvalidInput("invalid_reward_price")


@dataclass(frozen=True, slots=True)
class RewardSetting:
    enabled: bool
    revision: int

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise InvalidInput("invalid_reward_setting")
        validate_revision(self.revision)


@dataclass(frozen=True, slots=True)
class RewardOffer:
    offer_id: str
    title: str
    cost_minor: int
    enabled: bool
    eligible_roles: tuple[Role, ...]
    revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.offer_id)
        validate_task_text(self.title, maximum=160, required=True)
        _price(self.cost_minor)
        if (
            type(self.enabled) is not bool
            or type(self.eligible_roles) is not tuple
            or not self.eligible_roles
            or not all(isinstance(role, Role) for role in self.eligible_roles)
            or len(set(self.eligible_roles)) != len(self.eligible_roles)
        ):
            raise InvalidInput("invalid_reward_offer")
        validate_revision(self.revision)

    def permits(self, role: Role) -> bool:
        return self.enabled and role in self.eligible_roles


@dataclass(frozen=True, slots=True)
class RewardBalance:
    posted_minor: int
    reserved_minor: int

    @property
    def available_minor(self) -> int:
        return self.posted_minor - self.reserved_minor

    @property
    def shortfall_minor(self) -> int:
        return max(0, -self.available_minor)

    def reserve(self, price: int) -> None:
        _price(price)
        if self.available_minor < price:
            raise Conflict("insufficient_reward_points")


@dataclass(frozen=True, slots=True)
class RewardDecision:
    actor_member_id: str
    at: int

    def __post_init__(self) -> None:
        validate_identifier(self.actor_member_id)
        validate_task_time(self.at)


@dataclass(frozen=True, slots=True)
class Redemption:
    redemption_id: str
    member_id: str
    offer_id: str
    title: str
    offer_revision: int
    cost_minor: int
    requested_at: int
    stage: RedemptionStage = RedemptionStage.REQUESTED
    revision: int = 1
    approval: RewardDecision | None = None
    closed: RewardDecision | None = None
    cancellation_reason: str | None = None

    def __post_init__(self) -> None:
        for value in (self.redemption_id, self.member_id, self.offer_id):
            validate_identifier(value)
        validate_task_text(self.title, maximum=160, required=True)
        validate_revision(self.offer_revision)
        validate_revision(self.revision)
        _price(self.cost_minor)
        validate_task_time(self.requested_at)
        if (
            not isinstance(self.stage, RedemptionStage)
            or self.approval is not None
            and not isinstance(self.approval, RewardDecision)
            or self.closed is not None
            and not isinstance(self.closed, RewardDecision)
        ):
            raise InvalidInput("invalid_redemption")
        if self.stage is RedemptionStage.REQUESTED and self.approval is not None:
            raise InvalidInput("invalid_redemption")
        if (
            self.stage
            in {RedemptionStage.APPROVED, RedemptionStage.FUNDING_HOLD, RedemptionStage.DELIVERED}
            and self.approval is None
        ):
            raise InvalidInput("invalid_redemption")
        terminal = self.stage in {RedemptionStage.DELIVERED, RedemptionStage.CANCELLED}
        if terminal != (self.closed is not None):
            raise InvalidInput("invalid_redemption")
        if (self.stage is RedemptionStage.CANCELLED) != (self.cancellation_reason is not None):
            raise InvalidInput("invalid_redemption")
        if self.cancellation_reason is not None:
            validate_task_text(self.cancellation_reason, maximum=1000, required=True)
        if (
            self.approval is not None
            and self.approval.at < self.requested_at
            or self.closed is not None
            and self.closed.at < (self.requested_at if self.approval is None else self.approval.at)
        ):
            raise InvalidInput("invalid_redemption_time")

    @classmethod
    def request(cls, identity: str, member_id: str, offer: RewardOffer, at: int) -> Self:
        return cls(
            identity, member_id, offer.offer_id, offer.title, offer.revision, offer.cost_minor, at
        )

    def approve(self, decision: RewardDecision, balance: RewardBalance) -> Self:
        if self.stage is not RedemptionStage.REQUESTED:
            raise Conflict("redemption_not_requested")
        stage = (
            RedemptionStage.FUNDING_HOLD if balance.shortfall_minor else RedemptionStage.APPROVED
        )
        return replace(self, stage=stage, approval=decision, revision=self.revision + 1)

    def reconcile_funding(self, balance: RewardBalance) -> Self:
        stage = (
            RedemptionStage.FUNDING_HOLD if balance.shortfall_minor else RedemptionStage.APPROVED
        )
        if (
            self.stage not in {RedemptionStage.APPROVED, RedemptionStage.FUNDING_HOLD}
            or self.stage is stage
        ):
            return self
        return replace(self, stage=stage, revision=self.revision + 1)

    def deliver(self, decision: RewardDecision, balance: RewardBalance) -> Self:
        if self.stage not in {RedemptionStage.APPROVED, RedemptionStage.FUNDING_HOLD}:
            raise Conflict("redemption_not_approved")
        if self.stage is RedemptionStage.FUNDING_HOLD or balance.shortfall_minor:
            raise Conflict("reward_funding_hold")
        return replace(
            self, stage=RedemptionStage.DELIVERED, closed=decision, revision=self.revision + 1
        )

    def cancel(self, decision: RewardDecision, reason: str) -> Self:
        if self.stage not in RESERVED_STAGES:
            raise Conflict("redemption_closed")
        return replace(
            self,
            stage=RedemptionStage.CANCELLED,
            closed=decision,
            cancellation_reason=reason,
            revision=self.revision + 1,
        )


@dataclass(frozen=True, slots=True)
class RewardSpend:
    redemption_id: str
    title: str
    cost_minor: int
    posted_at: int

    def __post_init__(self) -> None:
        validate_identifier(self.redemption_id)
        validate_task_text(self.title, maximum=160, required=True)
        _price(self.cost_minor)
        validate_task_time(self.posted_at)


class FundingSource(StrEnum):
    POINTS = "points"
    CANCELLATION = "cancellation"


@dataclass(frozen=True, slots=True)
class FundingChange:
    redemption_id: str
    revision: int
    source: FundingSource
    source_id: str
    stage: RedemptionStage
    occurred_at: int

    def __post_init__(self) -> None:
        validate_identifier(self.redemption_id)
        validate_identifier(self.source_id)
        validate_revision(self.revision)
        validate_task_time(self.occurred_at)
        if (
            not isinstance(self.source, FundingSource)
            or not isinstance(self.stage, RedemptionStage)
            or self.stage not in {RedemptionStage.APPROVED, RedemptionStage.FUNDING_HOLD}
        ):
            raise InvalidInput("invalid_reward_funding")
