"""Use cases authorize before replay and commit one durable transition per command."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Event

import pytest

from domus.application.commands import AtomicCommands, Change
from domus.application.ports import UnitOfWork
from domus.domain.errors import Conflict, Forbidden, StorageBusy
from domus.domain.storage import CommandKey, Household, Installation, JsonDocument
from domus.infrastructure.sqlite import SQLiteDatabase


@dataclass
class Authorization:
    allowed: bool = True
    checks: int = 0

    def require(self, command: CommandKey, unit: UnitOfWork) -> None:
        self.checks += 1
        if not self.allowed:
            raise Forbidden("permission_denied")


class Clock:
    def now(self) -> int:
        return 100


class Identifiers:
    def __init__(self) -> None:
        self.calls = 0

    def new(self) -> str:
        self.calls += 1
        return f"operation-{self.calls}"


def store_at(path: Path) -> SQLiteDatabase:
    store = SQLiteDatabase(path, Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"))
    store.initialize()
    return store


def create_home(unit: UnitOfWork) -> Change:
    unit.households.save(Household("home", "Home", "UTC", 1), 0)
    result = JsonDocument.from_value({"household_id": "home", "revision": 1})
    return Change(result, JsonDocument.from_value({"transition": "created"}), result)


def test_identical_retry_does_not_rerun_effect_or_allocate_identifiers(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    policy, identifiers = Authorization(), Identifiers()
    commands = AtomicCommands(store, policy, Clock(), identifiers)
    key = CommandKey("home", "ha_1", "household.create", "request")
    payload = JsonDocument.from_value({"name": "Home", "expected_revision": 0})
    first = commands.execute(key, payload, create_home)

    def forbidden_second_effect(unit: UnitOfWork) -> Change:
        pytest.fail("A receipt replay must not run a new effect")

    assert commands.execute(key, payload, forbidden_second_effect) == first
    assert identifiers.calls == 1
    assert policy.checks == 2
    with store.read() as unit:
        assert unit.receipts.get(key) == first
        assert len(unit.audit.entries("home")) == 1
        assert len(unit.outbox.pending()) == 1
        assert unit.audit.entries("home")[0].detail.decode() == {"transition": "created"}


def test_changed_payload_conflicts_and_revoked_permission_hides_even_old_result(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path / "database")
    policy = Authorization()
    commands = AtomicCommands(store, policy, Clock(), Identifiers())
    key = CommandKey("home", "ha_1", "household.create", "request")
    commands.execute(key, JsonDocument.from_value({"name": "Home"}), create_home)
    with pytest.raises(Conflict, match="idempotency_conflict"):
        commands.execute(key, JsonDocument.from_value({"name": "Changed"}), create_home)
    policy.allowed = False
    with pytest.raises(Forbidden, match="permission_denied"):
        commands.execute(key, JsonDocument.from_value({"name": "Home"}), create_home)
    with store.read() as unit:
        assert unit.households.get("home").revision == 1
        assert len(unit.audit.entries("home")) == 1


def test_restart_replay_returns_original_result_without_fresh_effect(tmp_path: Path) -> None:
    path = tmp_path / "database"
    first = AtomicCommands(store_at(path), Authorization(), Clock(), Identifiers())
    key = CommandKey("home", "ha_1", "household.create", "request")
    payload = JsonDocument.from_value({"name": "Home"})
    result = first.execute(key, payload, create_home)
    restarted_ids = Identifiers()
    restarted = AtomicCommands(store_at(path), Authorization(), Clock(), restarted_ids)
    assert restarted.execute(key, payload, create_home) == result
    assert restarted_ids.calls == 0


def test_failed_effect_preserves_preexisting_state_and_creates_no_receipt(tmp_path: Path) -> None:
    store = store_at(tmp_path / "database")
    commands = AtomicCommands(store, Authorization(), Clock(), Identifiers())
    key = CommandKey("home", "ha_1", "household.create", "request")

    def fails_after_change(unit: UnitOfWork) -> Change:
        create_home(unit)
        raise RuntimeError("external effect failed")

    with pytest.raises(RuntimeError):
        commands.execute(key, JsonDocument.from_value({}), fails_after_change)
    with store.read() as unit:
        assert unit.households.current() is None
        assert unit.receipts.get(key) is None
        assert unit.audit.entries("home") == ()
        assert unit.outbox.pending() == ()


def test_overlapping_identical_commands_commit_once_and_retry_the_winning_receipt(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path / "database")
    commands = AtomicCommands(store, Authorization(), Clock(), Identifiers())
    key = CommandKey("home", "ha_1", "household.create", "request")
    payload = JsonDocument.from_value({"expected_revision": 0})
    entered, release = Event(), Event()

    def held_effect(unit: UnitOfWork) -> Change:
        result = create_home(unit)
        entered.set()
        assert release.wait(timeout=5), "Test coordinator did not release the first writer"
        return result

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(commands.execute, key, payload, held_effect)
        try:
            assert entered.wait(timeout=5), "First writer never reached its transition"
            with pytest.raises(StorageBusy):
                commands.execute(key, payload, create_home)
        finally:
            release.set()
        result = first.result(timeout=5)
    assert commands.execute(key, payload, create_home) == result
    with store.read() as unit:
        assert len(unit.audit.entries("home")) == 1
        assert len(unit.outbox.pending()) == 1
        assert unit.households.get("home").revision == 1
