"""Reviewed exceptions preserve nominal rank, work provenance and original recovery."""

from dataclasses import replace
from datetime import date

import pytest
from test_recurrence_creation import request, setup
from test_recurrence_review import reviewed

from domus.application.fixed_exception_review import FixedExceptionChange
from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.recurrence_review import RecurrenceReview, ReviewAction
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.domain.errors import Conflict, DomusError, StorageFailure
from domus.domain.recurrence_records import FixedException, FixedExceptionKind
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import NominalDate


def nominal(day):
    return NominalDate(date(2026, 3, day))


def seed(tmp_path):
    creator, _, store, actor, identifiers = setup(tmp_path)
    pattern = parse_fixed_pattern("FREQ=DAILY;INTERVAL=2;COUNT=2", nominal(27))
    created = creator.create_fixed("schedule", replace(request(), pattern=pattern)).result.decode()
    scope = MaintenanceScope(store.installation, "home")
    maintenance = FixedMaintenance(store, scope, creator.planner, creator.clock, identifiers)
    review = RecurrenceReview(
        store,
        store.installation,
        actor,
        actor.current,
        creator.clock,
        identifiers,
        RelativeRecurrencePlanner(creator.planner.times),
    )
    return review, maintenance, created["schedule_id"]


@pytest.fixture
def recurrence(tmp_path):
    return seed(tmp_path)


def selection(rule, revision, kind, day):
    return FixedExceptionChange(rule, revision, FixedException(kind, nominal(day), "School break"))


def test_exclusion_consumes_a_counted_nominal_and_addition_has_own_proof(recurrence):
    review, maintenance, rule = recurrence
    exclude = selection(rule, 1, FixedExceptionKind.EXCLUDE, 27)
    _, command = reviewed(review, exclude)
    result = review.apply("exclude", command)
    assert review.original(ReviewAction.APPLY, "exclude") == result
    assert review.apply("exclude", command) == result

    skipped = maintenance.step(rule, nominal(31))
    assert skipped.occurrence_id is None
    assert skipped.cursor.nominal_count == 1

    add = selection(rule, 2, FixedExceptionKind.ADD, 28)
    _, command = reviewed(review, add, key="preview-add")
    result = review.apply("add", command)
    occurrence = result.result.decode()["occurrence_id"]
    with review.transactions.read() as unit:
        slot = unit.recurrence.fixed_slot_for_occurrence("home", occurrence)
        assert slot is not None and slot.added
        assert slot.planned.nominal == nominal(28)
        assert unit.recurrence.progress("home", rule).cursor.nominal_count == 1
    next_step = maintenance.step(rule, nominal(31))
    assert next_step.cursor.nominal_count == 2
    assert next_step.cursor.closed
    assert maintenance.step(rule, nominal(31)).status == "current"


def test_addition_cannot_duplicate_the_rule(recurrence):
    review, _, rule = recurrence
    with pytest.raises(Conflict, match="recurrence_reschedule_collision"):
        review.preview("preview", selection(rule, 1, FixedExceptionKind.ADD, 29))


def test_issued_exclusion_cancels_unstarted_task_with_linked_reason(recurrence):
    review, maintenance, rule = recurrence
    original = maintenance.step(rule, nominal(31))
    _, command = reviewed(review, selection(rule, 1, FixedExceptionKind.EXCLUDE, 27))
    receipt = review.apply("exclude", command)
    result = receipt.result.decode()
    with review.transactions.read() as unit:
        work = unit.tasks.occurrence("home", original.occurrence_id)
        assert work.state.value == "cancelled"
        proof = unit.receipts.get_operation(
            "home", receipt.command.actor_id, result["effect_operation_id"]
        )
        assert proof.command.action == "task.transition"
        assert result["exception"]["reason"] == "School break"
        assert unit.recurrence.progress("home", rule).cursor.nominal_count == 1


def test_independent_writer_makes_a_review_stale_and_failure_rolls_back(recurrence, monkeypatch):
    from domus.infrastructure.sqlite import SQLiteDatabase
    from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences

    review, maintenance, rule = recurrence
    _, command = reviewed(review, selection(rule, 1, FixedExceptionKind.EXCLUDE, 27))
    store = review.transactions
    independent = SQLiteDatabase(store.path, store.installation)
    replace(maintenance, transactions=independent).step(rule, nominal(31))
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.apply("exclude", command)

    _, command = reviewed(review, selection(rule, 1, FixedExceptionKind.ADD, 28), "preview-add")
    with monkeypatch.context() as patch:

        def fail(*_args):
            raise StorageFailure("injected_addition_failure")

        patch.setattr(SQLiteRecurrences, "add_slot", fail)
        with pytest.raises(StorageFailure, match="injected_addition_failure"):
            review.apply("add", command)
    with store.read() as unit:
        assert unit.recurrence.schedule("home", rule).exceptions == ()
        assert len(unit.tasks.occurrences("home")) == 1
    restarted = replace(review, transactions=independent)
    result = restarted.apply("add", command)
    assert restarted.original(ReviewAction.APPLY, "add") == result


def test_historical_exception_cannot_restore_later_work(tmp_path, request):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root, archive, target = (tmp_path / part for part in ("root", "archive", "target"))
    root.mkdir(mode=0o700)
    review, maintenance, rule = seed(root)
    store = review.transactions
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before")
    _, exclude = reviewed(review, selection(rule, 1, FixedExceptionKind.EXCLUDE, 27))
    excluded = review.apply("exclude", exclude)
    _, add = reviewed(review, selection(rule, 2, FixedExceptionKind.ADD, 28), "preview-add")
    added = review.apply("add", add)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    request.addfinalizer(restored.close)
    service = replace(review, transactions=restored.database)
    for key, original, payload in (("exclude", excluded, exclude), ("add", added, add)):
        retained = service.apply(key, payload)
        assert retained.historical and retained.operation_id == original.operation_id
    with pytest.raises(Conflict, match="recurrence_exception_incompatible"):
        service.preview("again", selection(rule, 1, FixedExceptionKind.ADD, 28))
    stepped = replace(maintenance, transactions=restored.database).step(rule, nominal(31))
    assert stepped.occurrence_id is None and stepped.cursor.nominal_count == 1
    with restored.database.read() as unit:
        assert unit.tasks.occurrences("home") == ()


@pytest.mark.parametrize(
    "mode,code",
    [
        ("missing", "recurrence_rule_missing"),
        ("stale", "recurrence_review_stale"),
        ("kind", "recurrence_exception_incompatible"),
        ("outside", "recurrence_exception_incompatible"),
        ("retired", "recurrence_exception_incompatible"),
        ("duplicate", "recurrence_exception_incompatible"),
        ("past", "recurrence_reschedule_in_past"),
    ],
)
def test_ineligible_exception_sources(recurrence, mode, code):
    from datetime import UTC, datetime

    from domus.domain.recurrence_records import ScheduleState
    from domus.domain.recurrence_time import NominalTime

    review, _, rule = recurrence
    selected = selection(rule, 1, FixedExceptionKind.EXCLUDE, 27)
    if mode == "missing":
        selected = replace(selected, schedule_id="missing")
    elif mode == "stale":
        selected = replace(selected, schedule_revision=2)
    elif mode == "kind":
        selected = replace(
            selected,
            exception=replace(selected.exception, nominal=NominalTime(datetime(2026, 3, 27, 9))),
        )
    elif mode == "outside":
        selected = selection(rule, 1, FixedExceptionKind.EXCLUDE, 28)
    elif mode == "retired":
        with review.transactions.write() as unit:
            current = unit.recurrence.schedule("home", rule)
            unit.recurrence.save_schedule(
                replace(current, state=ScheduleState.RETIRED, revision=2), 1
            )
        selected = replace(selected, schedule_revision=2)
    elif mode == "duplicate":
        _, command = reviewed(review, selected)
        review.apply("exclude", command)
        selected = replace(selected, schedule_revision=2)
    else:
        from types import SimpleNamespace

        review = replace(
            review,
            clock=SimpleNamespace(
                now=lambda: int(datetime(2026, 4, 1, tzinfo=UTC).timestamp() * 1000)
            ),
        )
        selected = selection(rule, 1, FixedExceptionKind.ADD, 28)
    with pytest.raises(DomusError, match=code):
        review.preview("other", selected)


def test_started_work_cannot_be_excluded_but_a_prior_skip_can_be_retained(recurrence):
    from domus.application.task_commands import TaskCommands
    from domus.application.task_requests import AssignTask, TransitionTask
    from domus.domain.task_values import OccurrenceState

    review, maintenance, rule = recurrence
    first = maintenance.step(rule, nominal(31))
    second = maintenance.step(rule, nominal(31))
    tasks = TaskCommands(review.transactions, review.actor, review.clock, review.identifiers)
    tasks.transition(
        "skip", TransitionTask(first.occurrence_id, 1, OccurrenceState.SKIPPED, "Already skipped")
    )
    _, planned = reviewed(review, selection(rule, 1, FixedExceptionKind.EXCLUDE, 27))
    assert review.apply("exclude", planned).result.decode()["occurrence_id"] is None
    tasks.assign("assign", AssignTask(second.occurrence_id, 1, ("child",)))
    tasks.transition("start", TransitionTask(second.occurrence_id, 2, OccurrenceState.IN_PROGRESS))
    with pytest.raises(Conflict, match="recurrence_exception_incompatible"):
        review.preview("other", selection(rule, 2, FixedExceptionKind.EXCLUDE, 29))


def test_exclusion_consumes_one_unit_of_shared_slot_work(recurrence):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from domus.application.fair_recurrence import FairFixedRunner, RunLimits

    review, maintenance, rule = recurrence
    _, command = reviewed(review, selection(rule, 1, FixedExceptionKind.EXCLUDE, 27))
    review.apply("exclude", command)
    clock = SimpleNamespace(now=lambda: int(datetime(2026, 3, 26, tzinfo=UTC).timestamp() * 1000))
    runner = FairFixedRunner(
        review.transactions,
        maintenance.scope,
        replace(maintenance, clock=clock),
        maintenance.planner.times,
        clock,
        RunLimits(max_slots=1),
    )
    run = runner.tick()
    assert run.status == "budget_exhausted" and run.created == 0
    with review.transactions.read() as unit:
        assert unit.recurrence.progress("home", rule).cursor.nominal_count == 1


def test_preview_rebuild_preserves_exception_identity_and_reuses_only_remaining_slots(recurrence):
    from domus.application.fixed_batch_review import FixedReplacement

    review, maintenance, rule = recurrence
    original = maintenance.step(rule, nominal(31))
    excluded = maintenance.step(rule, nominal(31))
    _, command = reviewed(review, selection(rule, 1, FixedExceptionKind.ADD, 28))
    added = review.apply("add", command).result.decode()["occurrence_id"]
    _, command = reviewed(
        review, selection(rule, 2, FixedExceptionKind.EXCLUDE, 29), "preview-exclude"
    )
    review.apply("exclude", command)
    pattern = parse_fixed_pattern("FREQ=DAILY;COUNT=4", nominal(27))
    plan, command = reviewed(
        review, FixedReplacement(rule, 3, pattern, "Updated daily work"), "preview-batch"
    )
    source = plan.result.decode()["plan"]["source"]
    assert [
        (item["occurrence_id"], item["excluded"], item["previously_replaced"])
        for item in source["retained_work"]
    ] == [(added, False, False), (excluded.occurrence_id, True, False)]
    assert [item["planned"]["nominal"]["local"] for item in source["prospective_slots"]] == [
        "2026-03-27",
        "2026-03-30",
    ]
    applied = review.apply("batch", command)
    assert original.occurrence_id in applied.result.decode()["replacements"]
    with review.transactions.read() as unit:
        assert unit.recurrence.progress("home", rule).cursor.nominal_count == 4
        assert unit.recurrence.fixed_slot_for_occurrence("home", added).added


def test_timed_addition_uses_resolved_instants_for_collisions(tmp_path):
    from datetime import datetime

    from domus.domain.recurrence_time import NominalTime

    creator, _, store, actor, identifiers = setup(tmp_path)
    spec = request(timed=True)
    result = creator.create_fixed("timed", replace(spec, pattern=replace(spec.pattern, count=1)))
    rule = result.result.decode()["schedule_id"]
    review = RecurrenceReview(
        store,
        store.installation,
        actor,
        actor.current,
        creator.clock,
        identifiers,
        RelativeRecurrencePlanner(creator.planner.times),
    )

    def at(minute):
        return FixedExceptionChange(
            rule,
            1,
            FixedException(
                FixedExceptionKind.ADD, NominalTime(datetime(2026, 3, 29, 3, minute)), "One extra"
            ),
        )

    with pytest.raises(Conflict, match="recurrence_reschedule_collision"):
        review.preview("collision", at(0))
    maintenance = FixedMaintenance(
        store,
        MaintenanceScope(store.installation, "home"),
        creator.planner,
        creator.clock,
        identifiers,
    )
    maintenance.step(rule, NominalTime(datetime(2026, 3, 30)))
    _, command = reviewed(review, at(15))
    original = review.apply("timed-add", command)
    oid = original.result.decode()["occurrence_id"]
    with store.read() as unit:
        work = unit.tasks.occurrence("home", oid)
        slot = unit.recurrence.fixed_slot_for_occurrence("home", oid)
        assert work.due_at == slot.planned.resolved.instant_ms


def test_addition_cannot_collide_with_a_rescheduled_task(recurrence):
    from domus.application.reschedule_review import RescheduleSelection

    review, maintenance, rule = recurrence
    original = maintenance.step(rule, nominal(31))
    with review.transactions.read() as unit:
        slot = unit.recurrence.fixed_slot_for_occurrence("home", original.occurrence_id)
    _, command = reviewed(
        review,
        RescheduleSelection(rule, 1, slot.key, slot.occurrence_id, 1, nominal(28), "Move work"),
    )
    review.apply("move", command)
    with pytest.raises(Conflict, match="recurrence_reschedule_collision"):
        review.preview("add", selection(rule, 1, FixedExceptionKind.ADD, 28))
    with pytest.raises(Conflict, match="recurrence_exception_incompatible"):
        review.preview("exclude", selection(rule, 1, FixedExceptionKind.EXCLUDE, 27))


@pytest.mark.parametrize(
    "mode", ["too_many", "byte_bound", "duplicate", "kind", "invalid_item", "collection"]
)
def test_schedule_exceptions_are_closed_bounded_and_canonical(recurrence, mode):
    from datetime import date, datetime, timedelta

    from domus.domain.errors import InvalidInput
    from domus.domain.recurrence_time import NominalTime

    review, _, rule = recurrence
    with review.transactions.read() as unit:
        schedule = unit.recurrence.schedule("home", rule)
    original = FixedException(FixedExceptionKind.EXCLUDE, nominal(27), "Reason")
    if mode == "too_many":
        values = tuple(
            replace(original, nominal=NominalDate(date(2026, 3, 27) + timedelta(days=i)))
            for i in range(129)
        )
    elif mode == "byte_bound":
        values = tuple(
            FixedException(
                FixedExceptionKind.ADD,
                NominalDate(date(2026, 3, 27) + timedelta(days=i)),
                "é" * 1000,
            )
            for i in range(26)
        )
    elif mode == "duplicate":
        values = (original, replace(original, kind=FixedExceptionKind.ADD))
    elif mode == "kind":
        values = (replace(original, nominal=NominalTime(datetime(2026, 3, 27, 9))),)
    elif mode == "invalid_item":
        values = ("invalid",)
    else:
        values = [original]
    with pytest.raises(InvalidInput, match="invalid_recurrence_exception"):
        replace(schedule, exceptions=values)
    with pytest.raises(InvalidInput, match="invalid_recurrence_exception"):
        FixedException("exclude", nominal(27), "Reason")
    with pytest.raises(InvalidInput, match="invalid_recurrence_exception"):
        FixedException(FixedExceptionKind.EXCLUDE, "2026-03-27", "Reason")
    with pytest.raises(InvalidInput, match="invalid_recurrence_exception"):
        FixedExceptionChange(rule, 1, "invalid")


@pytest.mark.parametrize(
    "kind",
    ["definition", "occurrence", "wide_range", "too_many_open", "issued_addition", "large_record"],
)
def test_exception_rejects_incomplete_or_oversized_evidence(recurrence, monkeypatch, kind):
    from datetime import timedelta

    from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    review, maintenance, rule = recurrence
    work = maintenance.step(rule, nominal(31))
    with review.transactions.read() as unit:
        stored = unit.recurrence.fixed_slot_for_occurrence("home", work.occurrence_id)
        occurrence = unit.tasks.occurrence("home", work.occurrence_id)
    change = selection(rule, 1, FixedExceptionKind.EXCLUDE, 27)
    if kind == "definition":
        monkeypatch.setattr(SQLiteTasks, "definition", lambda *_: None)
        error, code = StorageFailure, "invalid_recurrence_source"
    elif kind == "occurrence":
        monkeypatch.setattr(SQLiteTasks, "occurrence", lambda *_: None)
        error, code = StorageFailure, "invalid_recurrence_source"
    elif kind == "wide_range":
        monkeypatch.setattr(SQLiteRecurrences, "fixed_slots_at", lambda *_: (stored,) * 101)
        error, code = Conflict, "recurrence_review_too_large"
    elif kind == "too_many_open":
        monkeypatch.setattr(SQLiteTasks, "occurrences", lambda *_args, **_kw: (occurrence,) * 101)
        change = selection(rule, 1, FixedExceptionKind.ADD, 28)
        error, code = Conflict, "recurrence_review_too_large"
    elif kind == "issued_addition":
        monkeypatch.setattr(SQLiteRecurrences, "fixed_slots_at", lambda *_: (stored,))
        change = selection(rule, 1, FixedExceptionKind.ADD, 28)
        error, code = Conflict, "recurrence_reschedule_collision"
    else:
        entries = tuple(
            FixedException(
                FixedExceptionKind.EXCLUDE,
                NominalDate(nominal(29).local + timedelta(days=i)),
                "Other",
            )
            for i in range(128)
        )
        with review.transactions.write() as unit:
            current = unit.recurrence.schedule("home", rule)
            unit.recurrence.save_schedule(replace(current, revision=2, exceptions=entries), 1)
        change = replace(change, schedule_revision=2)
        error, code = Conflict, "recurrence_review_too_large"
    with pytest.raises(error, match=code):
        review.preview("unsafe", change)


def test_writer_rejects_a_changed_rule_even_at_the_same_revision(recurrence, monkeypatch):
    from domus.application import recurrence_review as application
    from domus.domain.recurrence_records import ScheduleState

    review, _, rule = recurrence
    original = application.exception_schedule
    calls = 0

    def altered(unit, scope, request):
        nonlocal calls
        calls += 1
        value = original(unit, scope, request)
        return value if calls == 1 else replace(value, state=ScheduleState.PAUSED)

    monkeypatch.setattr(application, "exception_schedule", altered)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.preview("stale", selection(rule, 1, FixedExceptionKind.EXCLUDE, 27))


def test_addition_writer_refuses_foreign_or_inconsistent_materialization(recurrence, monkeypatch):
    from domus.application.fixed_exception_review import _AdditionAuthority
    from domus.domain.errors import Forbidden
    from domus.domain.recurrence_records import ScheduledSlot
    from domus.domain.storage import CommandKey

    review, maintenance, rule = recurrence
    _, command = reviewed(review, selection(rule, 1, FixedExceptionKind.ADD, 28))
    with monkeypatch.context() as patch:
        patch.setattr(ScheduledSlot, "matches_receipt", lambda *_: False)
        with pytest.raises(Conflict, match="recurrence_exception_incompatible"):
            review.apply("add", command)
    result = review.apply("add", command)
    with review.transactions.read() as unit:
        slot = unit.recurrence.fixed_slot_for_occurrence(
            "home", result.result.decode()["occurrence_id"]
        )
        authority = _AdditionAuthority(maintenance.scope, slot)
        with pytest.raises(Forbidden, match="maintenance_scope_denied"):
            authority.require(
                CommandKey("home", "foreign", "recurrence.materialize", slot.key), unit
            )
    with review.transactions.write() as unit:
        unit.recurrence.save_schedule(
            replace(slot.schedule, revision=slot.schedule.revision + 1), slot.schedule.revision
        )
        with pytest.raises(Forbidden, match="maintenance_scope_denied"):
            authority.require(slot.command, unit)


def test_batch_rolls_back_when_an_expected_slot_is_unconfirmed(recurrence, monkeypatch):
    from domus.application.fixed_batch_review import FixedReplacement

    review, maintenance, rule = recurrence
    maintenance.step(rule, nominal(31))
    change = FixedReplacement(
        rule, 1, parse_fixed_pattern("FREQ=DAILY;COUNT=3", nominal(27)), "Replacement"
    )
    _, command = reviewed(review, change)
    prior = FixedMaintenance.commit_reviewed_step

    def missing(self, *args, **kwargs):
        return replace(prior(self, *args, **kwargs), occurrence_id=None)

    monkeypatch.setattr(FixedMaintenance, "commit_reviewed_step", missing)
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.apply("replace", command)
    with review.transactions.read() as unit:
        assert unit.recurrence.schedule("home", rule).revision == 1
        assert len(unit.tasks.occurrences("home")) == 1


def test_sqlite_exception_documents_reject_noncanonical_lists_and_addition_tags(recurrence):
    from domus.domain.storage import JsonDocument
    from domus.infrastructure.sqlite_recurrence_records import (
        read_schedule,
        read_slot,
        schedule_document,
        slot_document,
    )

    review, _, rule = recurrence
    _, command = reviewed(review, selection(rule, 1, FixedExceptionKind.ADD, 28))
    added = review.apply("add", command).result.decode()["occurrence_id"]
    _, command = reviewed(
        review, selection(rule, 2, FixedExceptionKind.EXCLUDE, 27), "preview-exclude"
    )
    review.apply("exclude", command)
    with review.transactions.read() as unit:
        schedule = unit.recurrence.schedule("home", rule)
        slot = unit.recurrence.fixed_slot_for_occurrence("home", added)
    record = schedule_document(schedule).decode()
    for invalid in ([], record["exceptions"][::-1]):
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            read_schedule(JsonDocument.from_value(record | {"exceptions": invalid}).encoded)
    data = slot_document(slot).decode()
    with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
        read_slot(JsonDocument.from_value(data | {"added": False}).encoded)
