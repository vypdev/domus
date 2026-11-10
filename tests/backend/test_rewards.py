"""Reward domain checks freeze prices and validate durable lifecycle facts."""

from dataclasses import replace

import pytest

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.identity import Role
from domus.domain.rewards import (
    FundingChange,
    FundingSource,
    Redemption,
    RedemptionStage,
    RewardBalance,
    RewardDecision,
    RewardOffer,
    RewardSetting,
)

OFFER = RewardOffer("offer", "Movie", 800, True, (Role.ADULT,), 1)
REQUEST = Redemption.request("request", "member", OFFER, 10)
REVIEW = RewardDecision("reviewer", 20)
AVAILABLE = RewardBalance(1000, 800)
HELD = RewardBalance(0, 800)


def test_requested_and_approved_transitions_preserve_frozen_cost_and_review():
    assert OFFER.permits(Role.ADULT) and not OFFER.permits(Role.RESTRICTED)
    assert not replace(OFFER, enabled=False).permits(Role.ADULT)
    assert REQUEST.cost_minor == 800 and REQUEST.offer_revision == 1
    assert AVAILABLE.available_minor == 200 and HELD.shortfall_minor == 800
    AVAILABLE.reserve(200)
    with pytest.raises(Conflict, match="insufficient_reward_points"):
        HELD.reserve(1)
    with pytest.raises(InvalidInput, match="invalid_reward_price"):
        AVAILABLE.reserve(0)
    assert REQUEST.reconcile_funding(HELD) is REQUEST
    approved = REQUEST.approve(REVIEW, AVAILABLE)
    assert approved.stage is RedemptionStage.APPROVED and approved.approval == REVIEW
    assert approved.reconcile_funding(AVAILABLE) is approved
    held = approved.reconcile_funding(HELD)
    assert held.approval == REVIEW and held.stage is RedemptionStage.FUNDING_HOLD
    assert REQUEST.approve(REVIEW, HELD).stage is RedemptionStage.FUNDING_HOLD
    with pytest.raises(Conflict, match="redemption_not_requested"):
        held.approve(REVIEW, AVAILABLE)
    with pytest.raises(Conflict, match="reward_funding_hold"):
        held.deliver(REVIEW, AVAILABLE)
    with pytest.raises(Conflict, match="reward_funding_hold"):
        approved.deliver(REVIEW, HELD)
    with pytest.raises(Conflict, match="redemption_not_approved"):
        REQUEST.deliver(REVIEW, AVAILABLE)
    recovered = held.reconcile_funding(AVAILABLE)
    assert recovered.stage is RedemptionStage.APPROVED and recovered.approval == REVIEW
    delivered = recovered.deliver(RewardDecision("reviewer", 30), AVAILABLE)
    assert delivered.stage is RedemptionStage.DELIVERED and delivered.closed.at == 30
    with pytest.raises(Conflict, match="redemption_closed"):
        delivered.cancel(REVIEW, "Later")
    cancelled = held.cancel(REVIEW, "Later")
    assert cancelled.approval == REVIEW and cancelled.cancellation_reason == "Later"


@pytest.mark.parametrize("cost", [True, 0, -1, 1_000_001])
def test_reward_offer_has_a_positive_exact_bounded_cost(cost):
    with pytest.raises(InvalidInput, match="invalid_reward_price"):
        replace(OFFER, cost_minor=cost)


@pytest.mark.parametrize(
    "values",
    [
        {"enabled": "true"},
        {"eligible_roles": [Role.ADULT]},
        {"eligible_roles": ()},
        {"eligible_roles": ("adult",)},
        {"eligible_roles": (Role.ADULT, Role.ADULT)},
    ],
)
def test_reward_offer_requires_unambiguous_eligibility(values):
    with pytest.raises(InvalidInput, match="invalid_reward_offer"):
        replace(OFFER, **values)


@pytest.mark.parametrize(
    "values",
    [
        {"stage": "requested"},
        {"approval": "actor"},
        {"closed": "actor"},
        {"approval": REVIEW},
        {"stage": RedemptionStage.APPROVED},
        {"closed": REVIEW},
        {"cancellation_reason": "Changed"},
        {"stage": RedemptionStage.CANCELLED, "closed": REVIEW},
        {"stage": RedemptionStage.CANCELLED, "closed": REVIEW, "cancellation_reason": " "},
        {"stage": RedemptionStage.APPROVED, "approval": RewardDecision("reviewer", 9)},
        {
            "stage": RedemptionStage.DELIVERED,
            "approval": REVIEW,
            "closed": RewardDecision("reviewer", 19),
        },
    ],
)
def test_invalid_redemption_evidence_cannot_be_loaded(values):
    with pytest.raises(InvalidInput):
        replace(REQUEST, **values)


def test_reward_settings_and_funding_history_use_closed_types():
    with pytest.raises(InvalidInput, match="invalid_reward_setting"):
        RewardSetting("true", 1)
    assert RewardSetting(True, 1).enabled
    event = FundingChange(
        "request", 3, FundingSource.POINTS, "source", RedemptionStage.APPROVED, 20
    )
    for values in (
        {"source": "points"},
        {"stage": "approved"},
        {"stage": RedemptionStage.CANCELLED},
    ):
        with pytest.raises(InvalidInput, match="invalid_reward_funding"):
            replace(event, **values)
