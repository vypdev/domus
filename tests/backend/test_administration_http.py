"""Both actual ASGI deployments protect profile state and mutation-free original recovery."""

from contextlib import contextmanager
from dataclasses import replace

import pytest
from test_auth_http import login
from test_household_http import fixture as standalone_fixture
from test_household_http import setup as standalone_setup
from test_household_http import write_headers as standalone_headers
from test_native_http import fixture as native_fixture
from test_native_http import headers as native_headers
from test_native_http import setup as native_setup
from test_task_runtime import api as api

from domus.domain.errors import IdentityUnavailable
from domus.domain.identity import HumanIdentity, MemberStatus, Permission, PermissionRule
from domus.domain.member_profiles import MemberLocale, MemberPreferences, MemberPresentation

BASE = "/api/v1/administration"


@pytest.mark.parametrize("profile", [False, True])
def test_original_lookup_preserves_the_saved_domain_message(api, profile):
    if profile:
        member_id = api.client.get(BASE + "/preferences").json()["member_id"]
        route = BASE + f"/members/{member_id}/presentation"
        body = {"expected_revision": 1, "alias": "Public alias"}
        action = "member.presentation.update"
    else:
        route = "/api/v1/household"
        body = {"expected_revision": 1, "name": "Updated home", "time_zone": "UTC"}
        action = "household.update"
    saved = api.client.put(route, json=body, headers=api.headers("domain-message"))
    assert saved.status_code == 200, saved.text
    recovered = api.client.get(BASE + f"/requests/{action}/domain-message")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["message"] == saved.json()["message"]
    assert recovered.json()["notification_delivery"] == "unavailable"


def test_actual_compositions_bind_profile_authority_without_a_second_login(api):
    before = api.client.get(BASE + "/preferences")
    assert before.status_code == 200, before.text
    saved = api.client.put(
        BASE + "/preferences",
        json={"expected_revision": 1, "locale": "es", "routine_participation_summaries": False},
        headers=api.headers("preferences"),
    )
    assert saved.status_code == 200, saved.text
    recovered = api.client.get(BASE + "/requests/member.preferences.update/preferences")
    assert recovered.json()["operation_id"] == saved.json()["operation_id"]
    with api.store.read() as unit:
        assert (
            unit.preferences.get("home", before.json()["member_id"]).locale is MemberLocale.SPANISH
        )


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_published_int64_revision_schema_never_rounds_its_maximum(tmp_path, monkeypatch, mode):
    with configured(tmp_path, monkeypatch, mode) as (client, _, _, _, _):
        schemas = client.get("/api/v1/openapi.json").json()["components"]["schemas"]
        checked = []

        def visit(value, location):
            if isinstance(value, dict):
                if value.get("type") == "integer" and value.get("maximum", 0) > 2**53:
                    maximum = value["maximum"]
                    assert type(maximum) is int, location
                    assert maximum in (2**53 - 1, 2**63 - 1), location
                    checked.append(location)
                for key, nested in value.items():
                    visit(nested, location + "." + key)
            elif isinstance(value, list):
                for index, nested in enumerate(value):
                    visit(nested, location + f"[{index}]")

        visit(schemas, "schemas")
        assert any("PreferencesRequest" in name for name in checked)
        assert any("AliasRequest" in name for name in checked)
        assert any("HouseholdUpdateRequest" in name for name in checked)
        assert any("PolicyBody" in name for name in checked)


@contextmanager
def configured(tmp_path, monkeypatch, mode):
    if mode == "native":
        runtime, client, source, clock = native_fixture(tmp_path, monkeypatch)
        try:
            native_setup(client)
            from test_native_http import INSTANCE

            from domus.domain.storage import Installation
            from domus.infrastructure.sqlite import SQLiteDatabase

            store = SQLiteDatabase(tmp_path / "domus.sqlite3", Installation(INSTANCE, "edge"))
            yield client, store, source, clock, lambda key: native_headers(client, key)
        finally:
            client.close()
            runtime.close()
    else:
        client, store, source, _, _, clock = standalone_fixture(tmp_path)
        try:
            login(client)
            standalone_setup(client)
            yield client, store, source, clock, lambda key: standalone_headers(client, key)
        finally:
            client.close()


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_profiles_and_original_key_lookup_are_available_only_in_the_configured_runtime(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        response = client.get(BASE + "/preferences")
        assert response.status_code == 200, response.text
        owner = response.json()["member_id"]
        assert response.json()["locale"] is None
        assert response.json()["routine_participation_summaries"] is True
        alias = client.put(
            BASE + f"/members/{owner}/presentation",
            json={"expected_revision": 1, "alias": "  <b>Literal</b>  "},
            headers=headers("alias"),
        )
        assert alias.status_code == 200 and alias.json()["result"]["alias"] == "<b>Literal</b>"
        payload = {"expected_revision": 1, "locale": "es", "routine_participation_summaries": False}
        saved = client.put(BASE + "/preferences", json=payload, headers=headers("private"))
        assert saved.status_code == 200, saved.text
        assert saved.json()["result"]["notification_delivery"] == "unavailable"
        assert client.get(BASE + "/preferences").json()["locale"] == "es"
        before = store.path.read_bytes()
        recovered = client.get(BASE + "/requests/member.preferences.update/private")
        assert (
            recovered.status_code == 200
            and recovered.json()["operation_id"] == saved.json()["operation_id"]
        )
        assert recovered.json()["notification_delivery"] == "unavailable"
        assert (
            client.get(BASE + "/requests/member.preferences.update/unreceived").status_code == 404
        )
        assert store.path.read_bytes() == before
        public = client.get(BASE + f"/members/{owner}/presentation").json()
        assert public["alias"] == "<b>Literal</b>" and "locale" not in public
        assert (
            client.put(BASE + "/preferences", json=payload, headers=headers("private")).json()
            == saved.json()
        )


@pytest.mark.parametrize("mode", ["native", "standalone"])
@pytest.mark.parametrize("change", ["origin", "csrf", "duplicate_key", "query"])
def test_profile_write_preserves_origin_csrf_unique_key_and_closed_query(
    tmp_path, monkeypatch, mode, change
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        write = headers("private")
        if change == "origin":
            write["Origin"] = "https://foreign.invalid"
        if change == "csrf":
            write["X-CSRF-Token"] = "f" * 64
        final = list(write.items())
        if change == "duplicate_key":
            final.append(("Idempotency-Key", "replacement"))
        path = BASE + "/preferences" + ("?member_id=forged" if change == "query" else "")
        before = store.path.read_bytes()
        response = client.put(
            path,
            json={"expected_revision": 1, "locale": "es", "routine_participation_summaries": False},
            headers=final,
        )
        assert response.status_code in (400, 403, 422) and store.path.read_bytes() == before


@pytest.mark.parametrize("mode", ["native", "standalone"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("member_id", "forged"),
        ("actor_id", "forged"),
        ("locale", "future"),
        ("routine_participation_summaries", 0),
        ("expected_revision", True),
        ("expected_revision", 1.0),
        ("expected_revision", 0),
        ("expected_revision", 2**63),
    ],
)
def test_preferences_dto_is_closed_and_never_selects_an_owner(
    tmp_path, monkeypatch, mode, field, value
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        body = {
            "expected_revision": 1,
            "locale": None,
            "routine_participation_summaries": True,
            field: value,
        }
        before = store.path.read_bytes()
        response = client.put(BASE + "/preferences", json=body, headers=headers("invalid"))
        assert response.status_code == 422 and store.path.read_bytes() == before
        assert "forged" not in response.text


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_original_get_needs_neither_mutation_csrf_nor_revision_and_cannot_widen_entry_recovery(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, _, _, _, headers):
        saved = client.put(
            BASE + "/preferences",
            json={"expected_revision": 1, "locale": None, "routine_participation_summaries": False},
            headers=headers("saved"),
        )
        assert saved.status_code == 200
        assert client.get(BASE + "/requests/member.preferences.update/saved").status_code == 200
        assert client.get(BASE + "/requests/household.setup/setup").status_code == 422
        assert (
            client.get(
                BASE + "/requests/member.preferences.update/saved?expected_revision=1"
            ).status_code
            == 422
        )
        assert client.get(BASE + "/preferences?member_id=other").status_code == 422
        assert client.get(BASE + "/preferences/other").status_code == 404


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_profile_reads_keep_bounded_outage_grace_and_changes_remain_blocked(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, source, _, headers):
        write = headers("blocked")
        source.error = IdentityUnavailable("ha_unavailable")
        before = store.path.read_bytes()
        assert client.get(BASE + "/preferences").status_code == 200
        response = client.put(
            BASE + "/preferences",
            json={"expected_revision": 1, "locale": None, "routine_participation_summaries": False},
            headers=write,
        )
        assert response.status_code == 503 and store.path.read_bytes() == before


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_suspension_and_pending_membership_block_profile_access_without_client_role_trust(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        write = headers("private")
        preferences = client.get(BASE + "/preferences").json()
        with store.write() as unit:
            member = unit.members.get("home", preferences["member_id"])
            unit.members.save(
                replace(member, revision=member.revision + 1, status=MemberStatus.SUSPENDED),
                member.revision,
            )
        assert client.get(BASE + "/preferences").status_code == 403
        response = client.put(
            BASE + "/preferences",
            json={"expected_revision": 1, "locale": "es", "routine_participation_summaries": False},
            headers=write,
        )
        assert response.status_code == 403


def switch_administrator(client, source, mode, headers):
    human = HumanIdentity("b" * 32, True, True, False)
    if mode == "native":
        source.people[human.ha_user_id] = human
        client.headers["X-Remote-User-Id"] = human.ha_user_id
    else:
        assert (
            client.post("/api/v1/auth/logout", json={}, headers=headers("logout")).status_code
            == 200
        )
        source.human = human
        login(client)
    joined = client.post(
        "/api/v1/members/enrollment", json={"expected_revision": 0}, headers=headers("join")
    )
    assert joined.status_code == 200 and joined.json()["result"]["status"] == "active"
    assert client.get("/api/v1/authorization").json()["effective_role"] == "administrator"


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_even_another_current_administrator_cannot_read_private_original_by_id_or_key(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, source, _, headers):
        owner = client.get(BASE + "/preferences").json()["member_id"]
        saved = client.put(
            BASE + "/preferences",
            json={"expected_revision": 1, "locale": "es", "routine_participation_summaries": False},
            headers=headers("private"),
        ).json()
        switch_administrator(client, source, mode, headers)
        before = store.path.read_bytes()
        assert client.get(BASE + "/requests/member.preferences.update/private").status_code == 404
        assert client.get("/api/v1/operations/" + saved["operation_id"]).status_code == 404
        own = client.get(BASE + "/preferences").json()
        assert own["member_id"] != owner and own["locale"] is None
        assert own["routine_participation_summaries"] is True
        roster = client.get("/api/v1/members").json()
        assert all(
            "locale" not in row and "routine_participation_summaries" not in row
            for row in roster["members"]
        )
        assert store.path.read_bytes() == before
        public = client.put(
            BASE + f"/members/{owner}/presentation",
            json={"expected_revision": 1, "alias": "Public alias"},
            headers=headers("public"),
        )
        assert public.status_code == 200
        with store.read() as unit:
            assert unit.preferences.get("home", owner).locale.value == "es"


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_original_recovery_rechecks_permission_and_event_ack_is_not_notification_delivery(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        saved = client.put(
            BASE + "/preferences",
            json={"expected_revision": 1, "locale": "es", "routine_participation_summaries": False},
            headers=headers("original"),
        ).json()
        path = BASE + "/requests/member.preferences.update/original"
        assert client.get(path).json()["event_delivery"] == "pending"
        with store.write() as unit:
            assert unit.outbox.acknowledge(saved["operation_id"])
        recovered = client.get(path).json()
        assert recovered["event_delivery"] == "delivered"
        assert recovered["notification_delivery"] == "unavailable"
        with store.write() as unit:
            current = unit.members.get("home", saved["result"]["member_id"])
            unit.members.save(
                replace(
                    current,
                    revision=current.revision + 1,
                    exceptions=(PermissionRule(Permission.PREFERENCES_WRITE, False),),
                ),
                current.revision,
            )
        before = store.path.read_bytes()
        assert client.get(BASE + "/preferences").status_code == 200
        assert client.get(path).status_code == 403
        assert client.get("/api/v1/operations/" + saved["operation_id"]).status_code == 403
        assert store.path.read_bytes() == before


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_capabilities_describe_only_wired_contract_and_closed_journal_without_changing_state(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, _):
        before = store.path.read_bytes()
        result = client.get(BASE + "/capabilities")
        assert result.status_code == 200
        assert result.json() == {
            "state": "available",
            "contract_version": 1,
            "exact_revisions": "json-integer-int64",
            "actions": [
                "household.update",
                "member.preferences.update",
                "member.presentation.update",
                "member.update",
                "policy.update",
            ],
            "journal": {
                "namespace": "administration",
                "version": 1,
                "maximum_records": 8,
                "maximum_bytes": 65536,
                "lifetime_ms": 3600000,
            },
        }
        assert client.get(BASE + "/capabilities?actor_id=forged").status_code == 422
        assert store.path.read_bytes() == before


def test_unconfigured_transport_does_not_claim_administration_routes_exist(tmp_path):
    client, _, _, _, _, _ = standalone_fixture(tmp_path, administration=False)
    try:
        login(client)
        assert client.get(BASE + "/capabilities").status_code == 404
        assert BASE + "/preferences" not in client.get("/api/v1/openapi.json").json()["paths"]
    finally:
        client.close()


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_revisions_cross_the_wire_as_exact_int64_values_beyond_javascript_safe_integer(
    tmp_path, monkeypatch, mode
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        owner = client.get(BASE + "/preferences").json()["member_id"]
        revision = 2**53 + 1
        # Seed a genuine supported database revision without billions of unrelated writes.
        with store._connection() as connection:
            for table in ("member_preferences", "member_presentations"):
                connection.execute(
                    f"UPDATE {table} SET revision=? WHERE member_id=?", (revision, owner)
                )
        prefs = client.get(BASE + "/preferences")
        assert prefs.json()["revision"] == revision and str(revision) in prefs.text
        saved = client.put(
            BASE + "/preferences",
            content=(
                '{"expected_revision":'
                + str(revision)
                + ',"locale":"es","routine_participation_summaries":false}'
            ),
            headers={**headers("exact"), "Content-Type": "application/json"},
        )
        assert saved.status_code == 200 and saved.json()["result"]["revision"] == revision + 1
        alias = client.put(
            BASE + f"/members/{owner}/presentation",
            json={
                "expected_revision": revision,
                "alias": None,
            },
            headers=headers("exact-alias"),
        )
        assert alias.status_code == 200 and alias.json()["result"]["revision"] == revision + 1
        with store.read() as unit:
            assert unit.preferences.get("home", owner) == MemberPreferences(
                owner, "home", MemberLocale.SPANISH, False, revision + 1
            )
            assert unit.presentations.get("home", owner) == MemberPresentation(
                owner, "home", None, revision + 1
            )


@pytest.mark.parametrize("mode", ["native", "standalone"])
@pytest.mark.parametrize("alias", ["", "   ", "A" * 81, "\tAlias", "Alias\x00", "\ud800"])
def test_alias_rejects_invalid_values_before_any_effect(tmp_path, monkeypatch, mode, alias):
    import json

    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        owner = client.get(BASE + "/preferences").json()["member_id"]
        before = store.path.read_bytes()
        response = client.put(
            BASE + f"/members/{owner}/presentation",
            content=json.dumps({"expected_revision": 1, "alias": alias}),
            headers={**headers("invalid"), "Content-Type": "application/json"},
        )
        assert response.status_code == 422 and store.path.read_bytes() == before


@pytest.mark.parametrize("mode", ["native", "standalone"])
@pytest.mark.parametrize(
    "body", [b'{"expected_revision":1,"alias":"A","alias":"B"}', b"\xff", b"[]"]
)
def test_alias_json_boundary_rejects_ambiguous_or_unsupported_encoding(
    tmp_path, monkeypatch, mode, body
):
    with configured(tmp_path, monkeypatch, mode) as (client, store, _, _, headers):
        owner = client.get(BASE + "/preferences").json()["member_id"]
        before = store.path.read_bytes()
        response = client.put(
            BASE + f"/members/{owner}/presentation",
            content=body,
            headers={**headers("invalid"), "Content-Type": "application/json"},
        )
        assert response.status_code == 422 and store.path.read_bytes() == before


def profile_provider(api, *, denied=False, malformed=False):
    from domus.domain.errors import Forbidden

    calls = []

    def request(token, operation):
        calls.append(operation)
        if operation == "config/auth/list":
            if denied:
                raise Forbidden("ha_directory_forbidden")
            if malformed:
                return [{"id": "forged"}]
            return [
                {"id": user, "name": "<b>Same</b>", "is_active": True, "system_generated": False}
                for user in ("a" * 32, "b" * 32)
            ] + [
                {"id": "c" * 32, "name": "Inactive", "is_active": False, "system_generated": False}
            ]
        assert operation == "auth/current_user"
        return {
            "id": api.source.human.ha_user_id,
            "is_admin": api.source.human.is_administrator,
            "name": "Own name",
            "credentials": [{"auth_provider_type": "homeassistant"}],
        }

    api.source._request = request
    return calls


def test_both_compositions_publish_real_source_states_and_only_permitted_directory_facts(api):
    calls = profile_provider(api)
    before = api.store.path.read_bytes()
    roster = api.client.get(BASE + "/roster")
    assert roster.status_code == 200, roster.text
    assert roster.json()["directory_state"] == "available"
    metadata = roster.json()["members"][0]["metadata"]
    assert metadata == {"state": "available", "name": "<b>Same</b>", "avatar_state": "unavailable"}
    directory = api.client.get(BASE + "/directory")
    assert directory.status_code == 200, directory.text
    assert {row["ha_user_id"] for row in directory.json()["profiles"]} == {"a" * 32, "b" * 32}
    assert calls == ["config/auth/list", "config/auth/list"]
    assert api.store.path.read_bytes() == before


def test_ordinary_wire_roster_omits_other_linkage_from_every_nested_metadata_surface(api):
    from dataclasses import replace

    from domus.domain.identity import MemberStatus, Role

    profile_provider(api)
    api.user("b" * 32)
    enrolled = api.client.post(
        "/api/v1/members/enrollment", json={"expected_revision": 0}, headers=api.headers("join")
    )
    assert enrolled.status_code == 200
    target = enrolled.json()["result"]["member_id"]
    # Existing command acceptance owns activation; this establishes the read-permission fixture.
    with api.store.write() as unit:
        member = unit.members.get("home", target)
        unit.members.save(
            replace(
                member,
                role=Role.RESTRICTED,
                status=MemberStatus.ACTIVE,
                revision=member.revision + 1,
            ),
            member.revision,
        )
    before = api.store.path.read_bytes()
    response = api.client.get(BASE + "/roster")
    assert response.status_code == 200, response.text
    assert len(response.json()["members"]) == 2
    other = next(row for row in response.json()["members"] if row["member"]["member_id"] != target)
    assert other["member"]["ha_user_id"] is None and other["member"]["exceptions"] is None
    assert set(other["metadata"]) == {"state", "name", "avatar_state"}
    assert "a" * 32 not in response.text
    assert api.client.get(BASE + "/directory").status_code == 403
    assert api.store.path.read_bytes() == before


def test_provider_denial_keeps_roster_and_only_standalone_own_oauth_metadata(api):
    profile_provider(api, denied=True)
    response = api.client.get(BASE + "/roster")
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["directory_state"] == "denied" and len(value["members"]) == 1
    metadata = value["members"][0]["metadata"]
    assert metadata["state"] == ("available" if api.mode == "standalone" else "denied")
    assert metadata["name"] == ("Own name" if api.mode == "standalone" else None)
    directory = api.client.get(BASE + "/directory").json()
    assert directory == {"state": "denied", "profiles": []}


def test_read_scope_is_closed_and_invalid_provider_data_cannot_fabricate_an_empty_directory(api):
    profile_provider(api, malformed=True)
    before = api.store.path.read_bytes()
    result = api.client.get(BASE + "/roster")
    assert result.status_code == 200 and len(result.json()["members"]) == 1
    assert result.json()["directory_state"] == "unavailable"
    assert api.client.get(BASE + "/directory").json() == {"state": "unavailable", "profiles": []}
    assert api.client.get(BASE + "/roster?actor_id=forged").status_code == 422
    assert api.client.get(BASE + "/directory?subject=forged").status_code == 422
    assert api.store.path.read_bytes() == before


def test_unconfigured_source_has_explicit_unavailable_facts_without_invented_profiles(tmp_path):
    client, _, _, _, _, _ = standalone_fixture(tmp_path)
    try:
        login(client)
        standalone_setup(client)
        result = client.get(BASE + "/roster")
        assert result.status_code == 200, result.text
        assert result.json()["directory_state"] == "unavailable"
        assert result.json()["members"][0]["metadata"]["state"] == "unavailable"
    finally:
        client.close()


def test_selected_domus_administration_does_not_claim_ha_directory_permission(api):
    from domus.domain.identity import AdministratorMapping, MappingMode, MemberStatus, Role

    profile_provider(api, denied=api.mode == "standalone")
    api.user("b" * 32)
    joined = api.client.post(
        "/api/v1/members/enrollment",
        json={"expected_revision": 0},
        headers=api.headers("join-selected"),
    )
    assert joined.status_code == 200
    with api.store.write() as unit:
        member = unit.members.get("home", joined.json()["result"]["member_id"])
        unit.members.save(
            replace(
                member, role=Role.VIEWER, status=MemberStatus.ACTIVE, revision=member.revision + 1
            ),
            member.revision,
        )
        policy = unit.policies.get("home")
        unit.policies.save(
            replace(
                policy,
                mapping=AdministratorMapping(MappingMode.SELECTED, "b" * 32),
                revision=policy.revision + 1,
            ),
            policy.revision,
        )
    assert api.client.get("/api/v1/session").json()["ha_administrator"] is False
    assert api.client.get("/api/v1/authorization").json()["effective_role"] == "administrator"
    before = api.store.path.read_bytes()
    directory = api.client.get(BASE + "/directory")
    assert directory.status_code == 200, directory.text
    assert directory.json()["state"] == ("denied" if api.mode == "standalone" else "available")
    if api.mode == "standalone":
        assert directory.json()["profiles"] == []
    assert api.store.path.read_bytes() == before
