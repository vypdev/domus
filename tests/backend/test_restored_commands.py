"""Synthetic offline fixtures exercise runtime replay, disclosure and recovery after old state."""

from dataclasses import replace

import pytest
from test_auth_http import login
from test_household_http import fixture as http_fixture
from test_household_http import setup, write_headers
from test_recovery_commands import configured, start
from test_sqlite_history import install

from domus.domain.errors import Conflict, NotFound
from domus.domain.restoration import reconcile_operations
from domus.infrastructure.sqlite_history import iter_operations


def frontier(store):
    with store._connection() as connection:
        return tuple(iter_operations(connection))


def restore_fixture(store, checkpoint, selected):
    """Test-only offline substitution; not the production activation protocol."""
    plan = tuple(reconcile_operations(selected, frontier(store), "restore-1"))
    store.path.write_bytes(checkpoint)
    store.initialize(require_existing=True)
    install(store, plan)


@pytest.mark.parametrize("delivered", [False, True])
def test_historical_http_replay_is_truthful_and_requires_current_authority(tmp_path, delivered):
    client, store, _, _, _, _ = http_fixture(tmp_path)
    login(client)
    setup(client)
    checkpoint, selected = store.path.read_bytes(), frontier(store)
    payload = {"name": "Later", "time_zone": "UTC", "expected_revision": 1}
    result = client.put("/api/v1/household", json=payload, headers=write_headers(client, "later"))
    assert result.status_code == 200
    operation_id = result.json()["operation_id"]
    if delivered:
        with store.write() as unit:
            unit.outbox.acknowledge(operation_id)
    restore_fixture(store, checkpoint, selected)
    replay = client.put("/api/v1/household", json=payload, headers=write_headers(client, "later"))
    assert replay.status_code == 200, replay.text
    assert replay.json()["state"] == "historical"
    assert replay.json()["archived_by"] == "restore-1"
    assert replay.json()["result"] == result.json()["result"]
    assert "absent from current state" in replay.json()["message"]
    operation = client.get("/api/v1/operations/" + operation_id).json()
    assert operation["state"] == "historical"
    assert operation["delivery"] == ("delivered" if delivered else "suppressed")
    assert client.get("/api/v1/household").json()["name"] == "Home"
    with store.write() as unit:
        actor = unit.members.list("home")[0]
        unit.members.save(replace(actor, status=type(actor.status).SUSPENDED, revision=2), 1)
    assert (
        client.put(
            "/api/v1/household", json=payload, headers=write_headers(client, "later")
        ).status_code
        == 403
    )
    assert client.get("/api/v1/operations/" + operation_id).status_code == 403


@pytest.mark.parametrize("terminal", ["consume", "cancel"])
def test_restoring_an_approval_cannot_rearm_closed_recovery_with_another_key(tmp_path, terminal):
    commands, approval, store, actor, _, console = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    checkpoint, selected = store.path.read_bytes(), frontier(store)
    if terminal == "consume":
        commands.complete("complete", request_id, 2)
    else:
        commands.cancel("cancel", request_id, 2)
    restore_fixture(store, checkpoint, selected)
    replay = (
        commands.complete("complete", request_id, 2)
        if terminal == "consume"
        else commands.cancel("cancel", request_id, 2)
    )
    assert replay.historical
    for attempt in (
        lambda: commands.complete("new-key", request_id, 2),
        lambda: commands.cancel("new-key", request_id, 2),
        lambda: approval.approve(request_id),
        lambda: commands.status(request_id),
    ):
        with pytest.raises(Conflict, match="recovery_closed"):
            attempt()
    with store.read() as unit:
        assert unit.members.by_user("home", "ha_new") is None
        assert unit.recoveries.pending("home", 1000) == ()
    assert len(console.reviews) == 1
    actor.human = replace(actor.human, ha_user_id="different-human")
    with pytest.raises(NotFound):
        commands.status(request_id)
    actor.human = replace(actor.human, ha_user_id="ha_new")
    assert commands.start("fresh-request").result.decode()["request_id"] != request_id


def test_empty_checkpoint_does_not_claim_historical_setup_created_a_household(tmp_path):
    client, store, _, _, _, _ = http_fixture(tmp_path)
    login(client)
    checkpoint, selected = store.path.read_bytes(), frontier(store)
    original = setup(client)
    restore_fixture(store, checkpoint, selected)
    replay = setup(client)
    assert replay["state"] == "historical" and replay["operation_id"] == original["operation_id"]
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    with store.read() as unit:
        assert unit.households.current() is None and unit.audit.setup_actor("home") is None


def test_native_http_also_returns_historical_state_and_suppressed_delivery(tmp_path, monkeypatch):
    from test_native_http import INSTANCE, headers
    from test_native_http import fixture as native_fixture
    from test_native_http import setup as native_setup

    from domus.domain.storage import Installation
    from domus.infrastructure.sqlite import SQLiteDatabase

    runtime, client, _, _ = native_fixture(tmp_path, monkeypatch)
    try:
        native_setup(client)
        store = SQLiteDatabase(tmp_path / "domus.sqlite3", Installation(INSTANCE, "edge"))
        checkpoint, selected = store.path.read_bytes(), frontier(store)
        payload = {"name": "Later", "time_zone": "UTC", "expected_revision": 1}
        result = client.put("/api/v1/household", json=payload, headers=headers(client, "later"))
        assert result.status_code == 200
        restore_fixture(store, checkpoint, selected)
        replay = client.put("/api/v1/household", json=payload, headers=headers(client, "later"))
        assert replay.status_code == 200 and replay.json()["state"] == "historical"
        operation = client.get("/api/v1/operations/" + result.json()["operation_id"])
        assert operation.json()["delivery"] == "suppressed"
        assert client.get("/api/v1/household").json()["name"] == "Home"
    finally:
        runtime.close()


def test_console_replay_cannot_claim_a_rolled_away_approval_is_current(tmp_path, monkeypatch):
    import io
    import json

    from test_recovery_console import options

    from domus.composition import admin

    commands, approval, store, _, clock, _ = configured(tmp_path)
    request_id = start(commands)
    checkpoint, selected = store.path.read_bytes(), frontier(store)
    approval.approve(request_id)
    restore_fixture(store, checkpoint, selected)
    monkeypatch.setattr(admin, "SystemClock", lambda: clock)
    output, error = io.StringIO(), io.StringIO()
    assert (
        admin.main(
            [*options(store.path, store.installation), request_id],
            input_stream=io.StringIO(),
            output_stream=output,
            error_stream=error,
        )
        == 0
    )
    result = json.loads(output.getvalue())
    assert result["state"] == "historical" and result["archived_by"] == "restore-1"
    assert "no effect in current state" in result["message"] and error.getvalue() == ""
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "pending"
