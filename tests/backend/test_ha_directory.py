"""One bounded real protocol lookup distinguishes negative human facts from source failure."""

import pytest
from test_ha_websocket import USER, provider, scenario

from domus.domain.errors import Forbidden, IdentityRejected, InvalidInput
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_directory import HomeAssistantDirectory
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket

OTHER, INACTIVE, SYSTEM, MISSING = (value * 32 for value in ("b", "c", "d", "e"))


def person(user_id: str, *, active: bool = True, system: bool = False, owner: bool = False) -> dict:
    return {
        "id": user_id,
        "is_owner": owner,
        "is_active": active,
        "system_generated": system,
        "group_ids": ["system-users"],
    }


def test_one_lookup_returns_only_exact_eligible_humans_in_requested_order() -> None:
    records = [
        person(USER, owner=True),
        person(OTHER),
        person(INACTIVE, active=False),
        person(SYSTEM, system=True),
    ]
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        adapter = HomeAssistantDirectory(HomeAssistantWebSocket(endpoint), "fixture-access")
        humans = adapter.eligible((OTHER, MISSING, USER, INACTIVE, SYSTEM))
        assert tuple(human.ha_user_id for human in humans) == (OTHER, USER)
        assert not humans[0].is_administrator and humans[1].is_administrator
        assert "fixture-access" not in repr(adapter)


def test_single_human_port_uses_the_same_proven_directory_contract() -> None:
    with provider(scenario([person(USER)], operation="config/auth/list")) as endpoint:
        adapter = HomeAssistantDirectory(HomeAssistantWebSocket(endpoint), "fixture-access")
        assert adapter.get(USER).ha_user_id == USER
    with pytest.raises(InvalidInput):
        HomeAssistantDirectory(HomeAssistantWebSocket(endpoint), "invalid token")


@pytest.mark.parametrize(
    "requested", [[USER], ("invalid",), (USER, USER), tuple("a" * 32 for _ in range(257))]
)
def test_unbounded_malformed_or_duplicate_requests_fail_before_contacting_ha(
    requested: tuple,
) -> None:
    with pytest.raises(InvalidInput):
        HomeAssistantWebSocket(HAEndpoint("http://unreachable.invalid")).directory_users(
            "fixture-access", requested
        )


def test_empty_candidate_set_requires_no_source_request() -> None:
    assert (
        HomeAssistantWebSocket(HAEndpoint("http://unreachable.invalid")).directory_users(
            "fixture-access", ()
        )
        == ()
    )


@pytest.mark.parametrize(
    "broken",
    [{"is_active": 1}, {"system_generated": "false"}, {"is_owner": 1}, {"group_ids": [None]}],
)
def test_malformed_candidate_never_becomes_a_silent_partial_success(broken: dict) -> None:
    records = [person(USER, owner=True), {**person(OTHER), **broken}]
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        with pytest.raises(IdentityRejected):
            HomeAssistantDirectory(HomeAssistantWebSocket(endpoint), "fixture-access").eligible(
                (USER, OTHER)
            )


def test_directory_permission_denial_is_not_an_empty_eligible_set() -> None:
    with provider(scenario(None, operation="config/auth/list", success=False)) as endpoint:
        with pytest.raises(Forbidden, match="ha_directory_forbidden"):
            HomeAssistantDirectory(HomeAssistantWebSocket(endpoint), "fixture-access").eligible(
                (USER,)
            )


def test_unrequested_human_cannot_influence_a_requested_identity() -> None:
    records = [person(OTHER, owner=True), person(USER)]
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        humans = HomeAssistantDirectory(
            HomeAssistantWebSocket(endpoint), "fixture-access"
        ).eligible((USER,))
        assert len(humans) == 1
        assert humans[0].ha_user_id == USER
        assert not humans[0].is_administrator


@pytest.mark.parametrize("duplicate", [USER, OTHER])
def test_ambiguous_directory_rejects_duplicate_ids_even_outside_candidates(duplicate: str) -> None:
    records = [person(USER), person(OTHER), person(duplicate, owner=True)]
    with provider(scenario(records, operation="config/auth/list")) as endpoint:
        with pytest.raises(IdentityRejected, match="ha_subject_rejected"):
            HomeAssistantDirectory(HomeAssistantWebSocket(endpoint), "fixture-access").eligible(
                (USER,)
            )
