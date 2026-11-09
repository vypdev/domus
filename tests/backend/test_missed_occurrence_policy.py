"""Reviewable fixed backlog handling keeps the original work and the exact decision."""

from dataclasses import replace

import pytest
from test_recurrence_review import fixed_skip_fixture, reviewed
from test_sqlite_member_profiles import facts, frozen
from test_task_commands import counts

from domus.application.fixed_missed_policy import FixedMissedPolicy
from domus.application.recurrence_review import ReviewAction
from domus.domain.errors import Conflict, InvalidInput, NotFound, StorageFailure
from domus.domain.recurrence_records import ScheduleState
from domus.domain.task_values import MissedOccurrencePolicy, MissedOccurrenceSettings
from domus.infrastructure.sqlite import SCHEMA_VERSION, SQLiteDatabase, SQLiteReceipts
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database

KEEP = MissedOccurrencePolicy.KEEP_VISIBLE
SKIP = MissedOccurrencePolicy.SKIP_AFTER_REVIEW


def test_default_keeps_each_slot_pending_and_switch_requires_an_explicit_skip(tmp_path):
    from datetime import date

    from domus.domain.recurrence_rules import NominalDate

    service, first, maintenance, _ = fixed_skip_fixture(tmp_path, opt_in=False, count=5)
    store = service.transactions
    with pytest.raises(Conflict, match="recurrence_skip_policy_required"):
        service.preview("disabled", first)
    before = NominalDate(date(2026, 4, 2))
    issued = tuple(maintenance.step(first.schedule_id, before) for _ in range(3))
    assert all(step.status == "created" for step in issued)
    setting = FixedMissedPolicy(first.schedule_id, 1, 0, SKIP)
    with pytest.raises(Conflict, match="task_unchanged"):
        service.preview("unchanged", replace(setting, policy=KEEP))
    before_counts = counts(store)
    _, request = reviewed(service, setting, "enable")
    assert counts(store)[:2] == before_counts[:2]
    enabled = service.apply("enable-apply", request)
    with store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 4
        assert all(item.state.value == "available" for item in unit.tasks.occurrences("home"))
        rule = unit.recurrence.schedule("home", first.schedule_id)
        state = unit.tasks.missed_occurrence_settings("home", rule.definition_id)
        assert state.policy is SKIP and state.revision == 1
    _, skip = reviewed(service, first, "skip")
    skipped = service.apply("skip-apply", skip)
    _, disable = reviewed(service, replace(setting, policy=KEEP, policy_revision=1), "disable")
    service.apply("disable-apply", disable)
    restarted = replace(service, transactions=SQLiteDatabase(store.path, store.installation))
    assert restarted.apply("skip-apply", skip) == skipped
    assert restarted.apply("enable-apply", request) == enabled
    with store.read() as unit:
        assert unit.tasks.occurrence("home", first.occurrence_id).state.value == "skipped"
        assert all(
            unit.tasks.occurrence("home", step.occurrence_id).state.value == "available"
            for step in issued
        )
        assert unit.tasks.missed_occurrence_settings("home", rule.definition_id).policy is KEEP
        assert unit.tasks.cycles("home") == ()
    future = maintenance.step(first.schedule_id, NominalDate(date(2026, 4, 3)))
    assert future.status == "created"
    with store.read() as unit:
        slot = unit.recurrence.slot("home", future.receipt.command.key)
        assert slot.planned.nominal.local == date(2026, 4, 2)
    snap = SQLiteSnapshots(store, tmp_path / "checkpoint", store.installation, service.clock)
    checkpoint = snap.create("missed-policy")
    assert snap.inspect() == checkpoint


def test_stale_policy_review_and_failed_receipt_leave_no_partial_effect(tmp_path, monkeypatch):
    service, slot, _, _ = fixed_skip_fixture(tmp_path, opt_in=False)
    store = service.transactions
    selection = FixedMissedPolicy(slot.schedule_id, 1, 0, SKIP)
    _, request = reviewed(service, selection, "first")
    _, other = reviewed(service, selection, "second")
    before = counts(store)
    with monkeypatch.context() as patch:

        def fail(*_):
            raise StorageFailure("receipt_failure")

        patch.setattr(SQLiteReceipts, "add", fail)
        with pytest.raises(StorageFailure, match="receipt_failure"):
            service.apply("failed", request)
    assert counts(store) == before
    with pytest.raises(NotFound):
        service.original(ReviewAction.APPLY, "failed")
    service.apply("winner", other)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("stale", request)
    _, preview = reviewed(service, slot, "skip-before-toggle")
    _, toggle = reviewed(service, replace(selection, policy=KEEP, policy_revision=1), "off")
    service.apply("off-apply", toggle)
    with pytest.raises(Conflict, match="recurrence_skip_policy_required"):
        service.apply("old-skip", preview)
    _, toggle = reviewed(service, replace(selection, policy_revision=2), "back")
    service.apply("back-apply", toggle)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("old-skip", preview)


def test_policy_state_guards_and_corrupt_persistence(tmp_path, monkeypatch):
    service, slot, _, _ = fixed_skip_fixture(tmp_path, opt_in=False)
    store = service.transactions
    for bad in (-1, False, 2**63):
        with pytest.raises(InvalidInput, match="invalid_missed_occurrence_settings"):
            FixedMissedPolicy(slot.schedule_id, 1, bad, SKIP)
        with pytest.raises(InvalidInput, match="invalid_missed_occurrence_settings"):
            MissedOccurrenceSettings("home", "def", KEEP, bad)
    with pytest.raises(InvalidInput, match="invalid_missed_occurrence_settings"):
        MissedOccurrenceSettings("home", "def", SKIP)
    with pytest.raises(NotFound, match="recurrence_rule_missing"):
        service.preview("missing", FixedMissedPolicy("missing", 1, 0, SKIP))
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.preview("wrong-rule", FixedMissedPolicy(slot.schedule_id, 2, 0, SKIP))
    selection = FixedMissedPolicy(slot.schedule_id, 1, 0, SKIP)
    with store.read() as unit:
        rule = unit.recurrence.schedule("home", slot.schedule_id)
    with monkeypatch.context() as patch:
        from domus.infrastructure.sqlite_tasks import SQLiteTasks

        patch.setattr(SQLiteTasks, "definition", lambda *_: None)
        with pytest.raises(StorageFailure, match="invalid_recurrence_source"):
            service.preview("broken", selection)
    _, enable = reviewed(service, selection)
    service.apply("apply", enable)
    with store.write() as unit:
        definition = unit.tasks.definition("home", rule.definition_id)
        unit.tasks.save_definition(
            replace(definition, state=definition.state.PAUSED, revision=definition.revision + 1),
            definition.revision,
        )
    with pytest.raises(Conflict, match="recurrence_state_change_unavailable"):
        service.preview("paused-definition", replace(selection, policy=KEEP, policy_revision=1))
    with store.write() as unit:
        unit.recurrence.save_schedule(replace(rule, state=ScheduleState.RETIRED, revision=2), 1)
    with pytest.raises(Conflict, match="recurrence_state_change_unavailable"):
        service.preview(
            "retired-rule", replace(selection, schedule_revision=2, policy=KEEP, policy_revision=1)
        )
    with store._connection() as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("UPDATE task_missed_occurrence_settings SET policy='unknown'")
    with store.read() as unit, pytest.raises(StorageFailure, match="invalid_task_record"):
        unit.tasks.missed_occurrence_settings("home", rule.definition_id)


def test_previous_schema_keeps_original_rows_and_defaults_to_visible(tmp_path, monkeypatch):
    from domus.infrastructure import sqlite as adapter

    previous = SCHEMA_VERSION - 1
    store = frozen(tmp_path, previous)
    with store._connection() as connection:
        assert _verify_database(connection, store, previous=True) == previous
        tables = tuple(
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
    original = facts(store.path, tables)
    before = store.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "MISSED_OCCURRENCE_STATEMENT", "INVALID SQL")
        with pytest.raises(StorageFailure, match="storage_failure"):
            store.initialize(require_existing=True)
    assert store.path.read_bytes() == before
    store.initialize(require_existing=True)
    assert facts(store.path, tables) == original
    with store.read() as unit:
        home = unit.households.current()
        assert home.materialization_horizon_days == 31
        assert home.repeated_time.value == "second_instant"
        for definition in unit.tasks.definitions("home"):
            value = unit.tasks.missed_occurrence_settings("home", definition.definition_id)
            assert value.policy is KEEP and value.revision == 0


def test_restore_retains_original_review_proof_without_reviving_the_policy(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations

    root, archive, target = (tmp_path / part for part in ("root", "archive", "target"))
    root.mkdir(mode=0o700)
    service, slot, _, _ = fixed_skip_fixture(root, opt_in=False)
    store = service.transactions
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("keep")
    _, request = reviewed(service, FixedMissedPolicy(slot.schedule_id, 1, 0, SKIP))
    applied = service.apply("original", request)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        reopened = replace(service, transactions=restored.database)
        historical = reopened.original(ReviewAction.APPLY, "original")
        assert historical.historical and historical.operation_id == applied.operation_id
        assert reopened.apply("original", request) == historical
        with restored.database.read() as unit:
            rule = unit.recurrence.schedule("home", slot.schedule_id)
            settings = unit.tasks.missed_occurrence_settings("home", rule.definition_id)
            assert settings.policy is KEEP and settings.revision == 0
            assert unit.tasks.occurrence("home", slot.occurrence_id).state.value == "available"
    finally:
        restored.close()


def test_changed_definition_invalidates_policy_review(tmp_path):
    service, slot, _, _ = fixed_skip_fixture(tmp_path, opt_in=False)
    store = service.transactions
    _, request = reviewed(service, FixedMissedPolicy(slot.schedule_id, 1, 0, SKIP))
    with store.write() as unit:
        rule = unit.recurrence.schedule("home", slot.schedule_id)
        old = unit.tasks.definition("home", rule.definition_id)
        unit.tasks.save_definition(
            replace(old, content=replace(old.content, title="Updated"), revision=old.revision + 1),
            old.revision,
        )
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        service.apply("stale-definition", request)
