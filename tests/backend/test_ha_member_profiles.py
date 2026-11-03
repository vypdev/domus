"""Real bounded HA protocol fixtures establish source facts independently of role authority."""

import json

import pytest
from test_ha_websocket import CURRENT, GRANT, USER, provider

from domus.domain.errors import Forbidden, IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.member_sources import SourceState
from domus.infrastructure.ha_member_profiles import (
    HomeAssistantMemberProfiles,
    NativeMemberProfiles,
)
from domus.infrastructure.ha_websocket import HomeAssistantWebSocket

OTHER = "b" * 32
ROW = {"id": USER, "name": "<b>Literal</b>", "is_active": True, "system_generated": False}


def protocol(responses, calls):
    def handle(connection):
        connection.send(json.dumps({"type": "auth_required", "ha_version": "fixture"}))
        assert json.loads(connection.recv()) == {"type": "auth", "access_token": "fixture-access"}
        connection.send(json.dumps({"type": "auth_ok", "ha_version": "fixture"}))
        command = json.loads(connection.recv())
        assert command["id"] == 1
        calls.append(command["type"])
        success, result = responses[command["type"]]
        connection.send(
            json.dumps({"id": 1, "type": "result", "success": success, "result": result})
        )

    return handle


@pytest.mark.parametrize("standalone", [False, True])
def test_complete_directory_uses_one_fixed_read_and_preserves_exact_subject_and_ineligible_accounts(
    standalone,
):
    calls = []
    rows = [
        ROW,
        {**ROW, "id": OTHER, "is_active": False, "picture": "https://external.invalid/image"},
    ]
    with provider(protocol({"config/auth/list": (True, rows)}, calls)) as endpoint:
        source = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER, GRANT if standalone else None
        )
        value = source.read()
    assert calls == ["config/auth/list"]
    assert value.directory.state is SourceState.AVAILABLE
    assert value.profile(USER).profile.name == "<b>Literal</b>"
    assert value.profile(OTHER).profile.name == "<b>Literal</b>"
    assert value.profile(OTHER).profile.eligible is False
    assert not hasattr(value.profile(OTHER).profile, "avatar")
    assert not hasattr(value.profile(USER).profile, "is_administrator")
    assert "fixture-access" not in repr(source) and "fixture-refresh" not in repr(source)


@pytest.mark.parametrize("standalone", [False, True])
def test_exactly_256_distinct_accounts_form_a_complete_directory_in_provider_order(standalone):
    rows = [
        {
            **ROW,
            "id": f"{index:032x}",
            "name": f"Account {index}",
            "is_active": index % 2 == 0,
            "system_generated": index % 3 == 0,
        }
        for index in range(255)
    ] + [ROW]
    calls = []
    with provider(protocol({"config/auth/list": (True, rows)}, calls)) as endpoint:
        value = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER, GRANT if standalone else None
        ).read()
    assert calls == ["config/auth/list"]
    assert value.directory.state is SourceState.AVAILABLE
    profiles = value.directory.profiles
    assert len(profiles) == 256
    assert tuple(profile.ha_user_id for profile in profiles) == tuple(row["id"] for row in rows)
    assert tuple(profile.name for profile in profiles) == tuple(row["name"] for row in rows)
    assert [profile.eligible for profile in profiles[:5]] == [False, False, True, False, True]
    assert value.subject == USER and value.own.state is SourceState.AVAILABLE
    assert value.own.profile == profiles[-1]
    assert value.own.profile.ha_user_id == USER
    assert value.own.profile.name == "<b>Literal</b>" and value.own.profile.eligible is True


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("failure", ["distinct-overflow", "malformed-final-account"])
def test_invalid_boundary_directory_never_certifies_its_valid_prefix(standalone, failure):
    rows = [{**ROW, "id": f"{index:032x}"} for index in range(255)] + [ROW]
    if failure == "distinct-overflow":
        rows.append({**ROW, "id": f"{255:032x}"})
        assert len({row["id"] for row in rows}) == 257
    else:
        rows[-1] = {**ROW, "name": False}
        assert len({row["id"] for row in rows}) == 256
    calls = []
    with provider(
        protocol(
            {
                "config/auth/list": (True, rows),
                "auth/current_user": (True, {**CURRENT, "name": "Separately verified own name"}),
            },
            calls,
        )
    ) as endpoint:
        value = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER, GRANT if standalone else None
        ).read()
    assert value.directory.state is SourceState.UNAVAILABLE and value.directory.profiles == ()
    assert value.profile(f"{0:032x}").state is SourceState.UNAVAILABLE
    if standalone:
        assert calls == ["config/auth/list", "auth/current_user"]
        assert value.own.state is SourceState.AVAILABLE
        assert value.own.profile.ha_user_id == USER
        assert value.own.profile.name == "Separately verified own name"
    else:
        assert calls == ["config/auth/list"]
        assert value.own.state is SourceState.UNAVAILABLE and value.own.profile is None


def test_native_directory_denial_never_uses_the_technical_tokens_current_user_as_the_actor():
    calls = []
    with provider(protocol({"config/auth/list": (False, None)}, calls)) as endpoint:
        value = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER
        ).read()
    assert calls == ["config/auth/list"]
    assert value.directory.state is SourceState.DENIED and value.own.state is SourceState.DENIED


def test_standalone_directory_denial_keeps_only_exact_own_oauth_verified_metadata():
    calls = []
    with provider(
        protocol(
            {
                "config/auth/list": (False, None),
                "auth/current_user": (True, {**CURRENT, "name": "Own name"}),
            },
            calls,
        )
    ) as endpoint:
        value = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER, GRANT
        ).read()
    assert calls == ["config/auth/list", "auth/current_user"]
    assert value.directory.state is SourceState.DENIED and value.directory.profiles == ()
    assert value.own.state is SourceState.AVAILABLE and value.own.profile.name == "Own name"
    assert value.profile(OTHER).state is SourceState.DENIED


@pytest.mark.parametrize("rows", [[], [{**ROW, "id": OTHER}]])
def test_verified_omission_is_absence_and_never_an_unavailable_or_fabricated_own_profile(rows):
    calls = []
    with provider(protocol({"config/auth/list": (True, rows)}, calls)) as endpoint:
        value = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER, GRANT
        ).read()
    assert value.directory.state is SourceState.AVAILABLE and value.own.state is SourceState.ABSENT
    assert calls == ["config/auth/list"]


@pytest.mark.parametrize(
    "rows",
    [
        None,
        {},
        [None],
        [ROW, ROW],
        [ROW] * 257,
        [{**ROW, "id": "person.alias"}],
        [{**ROW, "is_active": 1}],
        [{**ROW, "system_generated": "false"}],
        [{"id": USER}],
        [{**ROW, "name": "\tInvalid"}],
        [{**ROW, "name": "\ud800"}],
        [{**ROW, "name": "A" * 257}],
        [{**ROW, "name": False}],
    ],
)
def test_malformed_or_overflow_directory_never_certifies_a_partial_or_empty_result(rows):
    calls = []
    with provider(protocol({"config/auth/list": (True, rows)}, calls)) as endpoint:
        value = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER
        ).read()
    assert value.directory.state is SourceState.UNAVAILABLE and value.directory.profiles == ()
    assert value.own.state is SourceState.UNAVAILABLE
    assert calls == ["config/auth/list"]


@pytest.mark.parametrize(
    "patch", [{"id": OTHER}, {"credentials": []}, {"name": "\tInvalid"}, {"is_admin": 1}]
)
def test_invalid_own_metadata_cannot_replace_proof_or_select_another_subject(patch):
    calls = []
    with provider(
        protocol(
            {
                "config/auth/list": (False, None),
                "auth/current_user": (True, {**CURRENT, "name": "Own", **patch}),
            },
            calls,
        )
    ) as endpoint:
        value = HomeAssistantMemberProfiles(
            HomeAssistantWebSocket(endpoint), "fixture-access", USER, GRANT
        ).read()
    assert value.own.state is SourceState.UNAVAILABLE and value.own.profile is None
    assert value.directory.state is SourceState.DENIED


@pytest.mark.parametrize(
    "error",
    [
        IdentityUnavailable("ha_unavailable"),
        IdentityRejected("invalid_ha_protocol"),
        InvalidInput("invalid_request"),
    ],
)
def test_unavailable_directory_can_keep_a_separately_verified_own_profile(error):
    class Lookup:
        def _request(self, token, operation):
            assert token == "fixture-access"
            if operation == "config/auth/list":
                raise error
            return {**CURRENT, "name": None}

    value = HomeAssistantMemberProfiles(Lookup(), "fixture-access", USER, GRANT).read()
    assert value.directory.state is SourceState.UNAVAILABLE
    assert value.own.state is SourceState.AVAILABLE and value.own.profile.name is None


@pytest.mark.parametrize(
    "error,state",
    [
        (Forbidden("ha_directory_forbidden"), SourceState.DENIED),
        (IdentityUnavailable("ha_unavailable"), SourceState.UNAVAILABLE),
    ],
)
def test_own_lookup_failure_is_honest_and_contains_no_raw_provider_data(error, state):
    class Lookup:
        def _request(self, token, operation):
            raise error

    value = HomeAssistantMemberProfiles(Lookup(), "fixture-access", USER, GRANT).read()
    assert value.own.state is state and value.own.profile is None


@pytest.mark.parametrize(
    "token,subject,grant",
    [
        ("bad token", USER, None),
        ("fixture-access", "forged", None),
        ("different", USER, GRANT),
        ("fixture-access", USER, "forged"),
    ],
)
def test_source_binding_rejects_unsupported_material_before_any_provider_call(
    token, subject, grant
):
    with pytest.raises(InvalidInput):
        HomeAssistantMemberProfiles(None, token, subject, grant)


def test_native_binding_uses_current_read_proof_without_adopting_transport_identity():
    from types import SimpleNamespace

    from domus.domain.identity import HumanIdentity

    calls = []
    with provider(protocol({"config/auth/list": (True, [ROW])}, calls)) as endpoint:
        source = NativeMemberProfiles(
            HomeAssistantWebSocket(endpoint),
            "fixture-access",
            SimpleNamespace(read=lambda: HumanIdentity(USER, False, True, False)),
        )
        value = source.read()
    assert value.subject == USER and value.own.profile.ha_user_id == USER
    assert "fixture-access" not in repr(source)
