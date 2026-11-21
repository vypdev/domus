"""Scheduled history is rule-owned, permission-aware and truthful after real restoration."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_activation_compatibility import identity_at
from test_daily_automation_execution import due, enabled

from domus.application.automation_scheduled_documents import run_document
from domus.application.automation_scheduled_history import ScheduledAutomationHistory
from domus.domain.errors import Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import Permission, PermissionRule, Role
from domus.domain.storage import CommandKey, JsonDocument
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots
from domus.infrastructure.task_cursor import TaskCursor


def history(engine, actor, clock):
    return ScheduledAutomationHistory(
        engine.transactions, engine.scope, actor.current, TaskCursor(clock, b"s" * 32)
    )


def test_empty_pending_and_success_are_distinct_and_success_has_a_current_task_link(tmp_path):
    _, engine, _, actor, clock, schedule = enabled(tmp_path)
    queries = history(engine, actor, clock)
    assert queries.page("daily", limit=25, cursor=None).items == ()
    step = due(engine, clock, schedule)
    queued = queries.page("daily", limit=25, cursor=None).items[0]
    assert (
        queued.outcome == "queued" and not queued.task_created and queued.task_occurrence_id is None
    )
    engine.execute(step.trigger_key)
    created = queries.page("daily", limit=25, cursor=None)
    assert len(created.items) == 1 and created.next_cursor is None
    assert created.items[0].outcome == "created" and created.items[0].task_created
    assert created.items[0].task_occurrence_id is not None and not created.items[0].historical
    assert created.items[0].requested_local == schedule.next_time.nominal.local.isoformat()


def test_signed_keyset_history_is_scoped_and_does_not_repeat_completed_runs(tmp_path):
    _, engine, store, actor, clock, _ = enabled(tmp_path)
    produced = []
    for _ in range(3):
        with store.read() as unit:
            schedule = unit.scheduled_automations.schedule("home", "daily")
        step = due(engine, clock, schedule)
        engine.execute(step.trigger_key)
        produced.append(step.trigger_key)
    queries = history(engine, actor, clock)
    first = queries.page("daily", limit=1, cursor=None)
    second = queries.page("daily", limit=1, cursor=first.next_cursor)
    third = queries.page("daily", limit=1, cursor=second.next_cursor)
    assert [page.items[0].trigger_key for page in (first, second, third)] == produced[::-1]
    assert third.next_cursor is None
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        queries.page("daily", limit=2, cursor=first.next_cursor)
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        queries.page("daily", limit=1, cursor="forged")


def test_current_permissions_hide_task_links_and_deny_private_history_after_role_loss(tmp_path):
    _, engine, store, actor, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    engine.execute(step.trigger_key)
    queries = history(engine, actor, clock)
    with store.write() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(
                member,
                revision=member.revision + 1,
                exceptions=(PermissionRule(Permission.TASKS_READ, False),),
            ),
            member.revision,
        )
    protected = queries.page("daily", limit=1, cursor=None).items[0]
    assert protected.task_created and protected.task_occurrence_id is None
    actor.human = replace(actor.human, is_administrator=False)
    with store.write() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(member, revision=member.revision + 1, role=Role.ADULT), member.revision
        )
    with pytest.raises(Forbidden):
        queries.page("daily", limit=1, cursor=None)


@pytest.mark.parametrize(
    "completed,checkpoint_after", [(False, False), (True, False), (True, True)]
)
def test_archived_admission_or_outcome_remains_visible_without_a_current_task_or_queue(
    tmp_path, completed, checkpoint_after
):
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    _, engine, store, actor, clock, schedule = enabled(data)
    identity_at(data, store.installation)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    snapshots = SQLiteSnapshots(store, archive, store.installation, clock)
    if not checkpoint_after:
        checkpoint = snapshots.create("before-trigger")
    step = due(engine, clock, schedule)
    if checkpoint_after:
        checkpoint = snapshots.create("after-admission")
    if completed:
        engine.execute(step.trigger_key)
    SQLiteRestorations(store, archive, target, store.installation, clock, checkpoint).prepare(
        "restore-history"
    )
    assert SQLiteActivation(data, store.installation, clock, target).activate().state == "active"
    selected = open_storage(data, "edge")
    try:
        queries = history(replace(engine, transactions=selected.database), actor, clock)
        page = queries.page("daily", limit=1, cursor=None)
        assert len(page.items) == 1 and page.next_cursor is None
        row = page.items[0]
        assert row.historical and row.trigger_key == step.trigger_key
        assert row.outcome == ("created" if completed else "queued")
        assert row.task_created is completed and row.task_occurrence_id is None
        with selected.database.read() as unit:
            assert len(unit.scheduled_automations.pending("home")) == int(checkpoint_after)
            assert unit.tasks.definitions("home") == ()
    finally:
        selected.close()


def test_invalid_bounds_and_missing_rule_are_errors_instead_of_an_empty_history(tmp_path):
    _, engine, _, actor, clock, _ = enabled(tmp_path)
    queries = history(engine, actor, clock)
    for limit in (True, 0, 101):
        with pytest.raises(InvalidInput, match="invalid_page_size"):
            queries.page("daily", limit=limit, cursor=None)
    with pytest.raises(NotFound, match="automation_draft_missing"):
        queries.page("missing", limit=25, cursor=None)


@pytest.mark.parametrize("missing", [True, False])
def test_broken_retained_projection_never_displays_a_current_or_missing_receipt_as_history(
    tmp_path, monkeypatch, missing
):
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    _, engine, store, actor, clock, schedule = enabled(data)
    identity_at(data, store.installation)
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, clock).create("before-trigger")
    step = due(engine, clock, schedule)
    engine.execute(step.trigger_key)
    SQLiteRestorations(store, archive, target, store.installation, clock, checkpoint).prepare(
        "restore-history"
    )
    assert SQLiteActivation(data, store.installation, clock, target).activate().state == "active"
    selected = open_storage(data, "edge")
    try:
        with selected.database.read() as unit:
            proof = unit.receipts.get(
                CommandKey(
                    "home", schedule.grant.principal, "automation.scheduled.run", step.trigger_key
                )
            )
        assert proof.historical
        projected = None if missing else replace(proof, restoration=None)
        monkeypatch.setattr(SQLiteReceipts, "get_operation", lambda *args: projected)
        with pytest.raises(StorageFailure, match="invalid_retained_projection"):
            history(replace(engine, transactions=selected.database), actor, clock).page(
                "daily", limit=25, cursor=None
            )
    finally:
        selected.close()


@pytest.mark.parametrize("position", ["invalid", "253402300800000." + "a" * 64])
def test_semantically_invalid_cursor_positions_are_rejected_before_reading_history(
    tmp_path, position
):
    _, engine, _, actor, clock, _ = enabled(tmp_path)
    queries = history(engine, actor, clock)
    cursors = Mock(wraps=queries.cursors)
    cursors.decode.return_value = position
    with pytest.raises(InvalidInput, match="invalid_task_cursor"):
        replace(queries, cursors=cursors).page("daily", limit=1, cursor="injected-position")


def test_cross_household_historical_projection_is_rejected_before_display_or_task_lookup(
    tmp_path, monkeypatch
):
    _, engine, store, actor, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    complete = engine.execute(step.trigger_key)
    with store.read() as unit:
        run = unit.scheduled_automations.run("home", step.trigger_key)
    foreign = replace(run, grant=replace(run.grant, household_id="another-household"))
    proof = replace(
        complete.receipt,
        command=CommandKey(
            "another-household", foreign.grant.principal, "automation.scheduled.run", foreign.key
        ),
        result=JsonDocument.from_value(
            {"trigger_key": foreign.key, "run": run_document(foreign).decode()}
        ),
    )
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "archived_scheduled_runs", lambda *args, **kwargs: (proof,))
        with pytest.raises(StorageFailure, match="invalid_daily_automation_history"):
            history(engine, actor, clock).page("daily", limit=25, cursor=None)


def test_task_creation_requires_its_scoped_task_proof_before_showing_a_link(tmp_path, monkeypatch):
    _, engine, _, actor, clock, schedule = enabled(tmp_path)
    step = due(engine, clock, schedule)
    engine.execute(step.trigger_key)
    read = SQLiteReceipts.get

    def missing_task(self, key):
        return None if key.action == "task.create" else read(self, key)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "get", missing_task)
        with pytest.raises(StorageFailure, match="invalid_daily_automation_task_proof"):
            history(engine, actor, clock).page("daily", limit=25, cursor=None)
