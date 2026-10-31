"""Both transport compositions retain stable, safe English fallback for unsupported locales."""

import io
from contextlib import contextmanager
from dataclasses import replace

import pytest
from test_auth_http import login
from test_household_http import fixture as standalone_fixture
from test_household_http import setup as standalone_setup
from test_household_http import write_headers
from test_native_http import INSTANCE
from test_native_http import fixture as native_fixture
from test_native_http import headers as native_headers
from test_native_http import setup as native_setup

from domus.composition import admin
from domus.domain.identity import HumanIdentity, MemberStatus
from domus.domain.storage import Installation
from domus.infrastructure.sqlite import SQLiteDatabase


@contextmanager
def composition(tmp_path, monkeypatch, mode):
    runtime = None
    if mode == "standalone":
        client, store, source, _, _, _ = standalone_fixture(tmp_path)
        login(client)
        headers, setup = write_headers, standalone_setup

        def select(human):
            response = client.post("/api/v1/auth/logout", json={}, headers=headers(client))
            assert response.status_code == 200
            source.human = human
            login(client)
    else:
        runtime, client, source, _ = native_fixture(tmp_path, monkeypatch)
        store = SQLiteDatabase(tmp_path / "domus.sqlite3", Installation(INSTANCE, "edge"))
        headers, setup = native_headers, native_setup

        def select(human):
            source.people[human.ha_user_id] = human
            client.headers["X-Remote-User-Id"] = human.ha_user_id
            client.headers["Cookie"] = "ingress_session=" + human.ha_user_id * 4
            assert client.get("/api/v1/session").status_code == 200

    try:
        yield client, store, setup, headers, select
    finally:
        if runtime is not None:
            runtime.close()


@pytest.mark.parametrize("mode", ["standalone", "native"])
@pytest.mark.parametrize(
    "state, expected_message, expected_action",
    [
        ("unconfigured_admin", "not configured", "Set up"),
        ("unconfigured_ordinary", "not configured", "Home Assistant administrator"),
        ("not_enrolled", "no membership", "Request"),
        ("pending", "not active", "administrator"),
        ("active", "active", "No membership action"),
        ("suspended", "blocked", "administrator"),
        ("archived", "blocked", "existing membership"),
    ],
)
def test_authorization_explains_current_membership_and_next_action_without_implicit_access(
    tmp_path, monkeypatch, mode, state, expected_message, expected_action
):
    with composition(tmp_path, monkeypatch, mode) as (client, store, setup, headers, select):
        ordinary = HumanIdentity("b" * 32, False, True, False)
        if not state.startswith("unconfigured"):
            setup(client)
            select(ordinary)
            if state != "not_enrolled":
                joined = client.post(
                    "/api/v1/members/enrollment",
                    json={"expected_revision": 0},
                    headers=headers(client, "join"),
                )
                assert joined.status_code == 200
                if state != "pending":
                    with store.write() as unit:
                        member = unit.members.by_user("home", ordinary.ha_user_id)
                        unit.members.save(
                            replace(member, status=MemberStatus(state), revision=2), 1
                        )
        elif state == "unconfigured_ordinary":
            select(ordinary)
        result = client.get("/api/v1/authorization")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["state"] == ("unconfigured" if state.startswith("unconfigured") else state)
        assert expected_message in body["message"] and expected_action in body["action_required"]
        assert body["setup_allowed"] is (state == "unconfigured_admin")
        if state != "active":
            assert body["permissions"] == []
            assert client.get("/api/v1/household").status_code == 403
        if state == "pending":
            assert "linked" in body["message"]
        with store.read() as unit:
            assert len(unit.audit.entries("home")) == (
                0 if state.startswith("unconfigured") else 1 if state == "not_enrolled" else 2
            )


@pytest.mark.parametrize("mode", ["standalone", "native"])
@pytest.mark.parametrize("ha_admin", [False, True])
def test_enrollment_receipt_describes_original_effect_even_after_current_status_changes(
    tmp_path, monkeypatch, mode, ha_admin
):
    with composition(tmp_path, monkeypatch, mode) as (client, store, setup, headers, select):
        setup(client)
        human = HumanIdentity("b" * 32, ha_admin, True, False)
        select(human)

        def enroll():
            return client.post(
                "/api/v1/members/enrollment",
                json={"expected_revision": 0},
                headers=headers(client, "join"),
            )

        first = enroll()
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["result"]["status"] == ("active" if ha_admin else "pending")
        assert "This operation" in body["message"] and "linked" in body["message"]
        assert "current membership status" in body["action_required"]
        if not ha_admin:
            assert "did not activate household access" in body["message"]
            assert "administrator" in body["action_required"]
            with store.write() as unit:
                member = unit.members.by_user("home", human.ha_user_id)
                unit.members.save(replace(member, status=MemberStatus.ACTIVE, revision=2), 1)
        assert enroll().json() == body
        assert client.get("/api/v1/authorization").json()["state"] == "active"
        with store.read() as unit:
            assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 2


def test_historical_enrollment_does_not_claim_membership_survived_restoration(tmp_path):
    from test_restored_commands import frontier, restore_fixture

    client, store, source, _, _, _ = standalone_fixture(tmp_path)
    login(client)
    standalone_setup(client)
    checkpoint, selected = store.path.read_bytes(), frontier(store)
    client.post("/api/v1/auth/logout", json={}, headers=write_headers(client))
    source.human = HumanIdentity("b" * 32, False, True, False)
    login(client)

    def enroll():
        return client.post(
            "/api/v1/members/enrollment",
            json={"expected_revision": 0},
            headers=write_headers(client, "join"),
        )

    first = enroll()
    assert first.status_code == 200
    restore_fixture(store, checkpoint, selected)
    replay = enroll()
    assert replay.status_code == 200, replay.text
    assert replay.json()["state"] == "historical"
    assert replay.json()["operation_id"] == first.json()["operation_id"]
    assert "absent from current state" in replay.json()["message"]
    assert client.get("/api/v1/authorization").json()["state"] == "not_enrolled"
    with store.read() as unit:
        assert unit.members.by_user("home", "b" * 32) is None


@pytest.mark.parametrize("mode", ["standalone", "native"])
@pytest.mark.parametrize("locale", ["en-US", "es-ES,es;q=0.9", "fr-FR"])
def test_missing_operation_is_readable_english_json_without_untrusted_diagnostic_rendering(
    tmp_path, monkeypatch, mode, locale
):
    runtime = None
    if mode == "standalone":
        client, store, _, _, _, _ = standalone_fixture(tmp_path)
        login(client)
        standalone_setup(client)
    else:
        runtime, client, _, _ = native_fixture(tmp_path, monkeypatch)
        store = SQLiteDatabase(tmp_path / "domus.sqlite3", Installation(INSTANCE, "edge"))
        native_setup(client)
    try:
        untrusted = "<script>@everyone $(command) https://untrusted.invalid/"
        result = client.get(
            "/api/v1/operations/missing-operation",
            headers={"Accept-Language": locale, "X-Correlation-ID": untrusted},
        )
        assert result.status_code == 404
        assert result.headers["content-type"].startswith("application/json")
        assert result.headers["x-content-type-options"] == "nosniff"
        body = result.json()
        assert body["state"] == "blocked" and body["code"] == "operation_missing"
        assert "not accepted" in body["message"]
        assert "retained" in body["action_required"] and body["correlation_id"]
        for marker in ("<script>", "@everyone", "$(command)", "untrusted.invalid", "\x1b"):
            assert marker not in result.text
        with store.read() as unit:
            assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
    finally:
        if runtime is not None:
            runtime.close()


@pytest.mark.parametrize(
    "untrusted",
    [
        "<script>alert(1)</script>",
        "@everyone",
        "$(command)",
        "https://untrusted.invalid/",
        "\x1b[31mCONTROL",
        "[review](https://untrusted.invalid/)",
        "<!--copilot-configuration-start-->",
    ],
)
def test_console_rejects_untrusted_request_text_without_echo_prompt_or_saved_effect(
    tmp_path, untrusted
):
    from test_recovery_commands import configured

    _, _, store, _, _, _ = configured(tmp_path)
    output, error = io.StringIO(), io.StringIO()
    code = admin.main(
        [
            "--channel",
            "edge",
            "--database",
            str(store.path),
            "--instance-id",
            store.installation.instance_id,
            "recovery",
            "approve",
            untrusted,
        ],
        input_stream=io.StringIO(),
        output_stream=output,
        error_stream=error,
    )
    assert code == 2 and output.getvalue() == ""
    assert untrusted not in error.getvalue() and "\x1b" not in error.getvalue()
    assert "Existing records are retained" in error.getvalue()
    with store.read() as unit:
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
