"""Atomic reviewed replacement preserves the original history and transfers compatible work."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from test_recurrence_creation import request, setup
from test_recurrence_review import reviewed
from test_task_commands import counts
from test_task_runtime import api as api

from domus.application.fixed_batch_review import FixedReplacement
from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.recurrence_review import RecurrenceReview, ReviewAction
from domus.application.relative_recurrence import RelativeRecurrencePlanner
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import AssignTask, TransitionTask
from domus.domain.errors import Conflict, StorageFailure
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import NominalTime
from domus.domain.task_values import OccurrenceState
from domus.infrastructure.sqlite import SQLiteAudit, SQLiteDatabase


def nominal(day):
    return NominalDate(date(2026, 3, day))


def prepared(tmp_path, *, timed=False):
    creator, _, store, actor, identifiers = setup(tmp_path)
    selected = request(timed=timed)

    def anchor(day: int):
        return NominalTime(datetime(2026, 3, day, 9)) if timed else nominal(day)

    previous = parse_fixed_pattern("FREQ=DAILY;COUNT=3", anchor(27))
    created = creator.create_fixed("old", replace(selected, pattern=previous)).result.decode()
    schedule_id = created["schedule_id"]
    maintenance = FixedMaintenance(
        store,
        MaintenanceScope(store.installation, "home"),
        creator.planner,
        creator.clock,
        identifiers,
    )
    before = anchor(31)
    old = tuple(maintenance.step(schedule_id, before) for _ in range(3))
    assert all(item.status == "created" for item in old)
    review = RecurrenceReview(
        store,
        store.installation,
        actor,
        actor.current,
        creator.clock,
        identifiers,
        RelativeRecurrencePlanner(creator.planner.times),
    )
    command = FixedReplacement(
        schedule_id,
        1,
        parse_fixed_pattern("FREQ=DAILY;COUNT=3;INTERVAL=2", anchor(28)),
        "Change future kitchen work",
    )
    return review, maintenance, command, old


def test_replacement_commits_one_linked_batch_and_recovers_by_original_key(tmp_path):
    review, maintenance, choice, old = prepared(tmp_path)
    store = review.transactions
    tasks = TaskCommands(store, review.actor, review.clock, review.identifiers)
    tasks.assign("assign", AssignTask(old[1].occurrence_id, 1, ("child",)))
    preview, command = reviewed(review, choice)
    plan = preview.result.decode()["plan"]["source"]
    assert [item["occurrence_id"] for item in plan["cancelled_work"]] == [
        old[1].occurrence_id,
        old[2].occurrence_id,
    ]
    assert plan["retained_work"][0]["occurrence_id"] == old[0].occurrence_id
    assert [item["replaces"] for item in plan["prospective_slots"]] == [
        old[1].occurrence_id,
        old[2].occurrence_id,
        None,
    ]
    receipt = review.apply("replace", command)
    result = receipt.result.decode()
    assert result["cancelled"] == [old[1].occurrence_id, old[2].occurrence_id]
    assert len(result["replacements"]) == 2 and len(result["added"]) == 1
    with store.read() as unit:
        for before in old[1:]:
            original = unit.tasks.occurrence("home", before.occurrence_id)
            assert original.state is OccurrenceState.CANCELLED
            assert original.state_reason == choice.reason
            assert (
                unit.recurrence.slot("home", before.receipt.command.key).occurrence_id
                == original.occurrence_id
            )
        after = unit.tasks.occurrence("home", result["replacements"][old[1].occurrence_id])
        assert after.state is OccurrenceState.ASSIGNED and after.assignee_ids == ("child",)
        assert (
            unit.tasks.occurrence("home", old[0].occurrence_id).state is OccurrenceState.AVAILABLE
        )
        progress = unit.recurrence.progress("home", choice.schedule_id)
        assert progress.cursor.closed and progress.pattern_revision == 2
    restarted = replace(review, transactions=SQLiteDatabase(store.path, store.installation))
    assert restarted.original(ReviewAction.APPLY, "replace") == receipt
    assert restarted.apply("replace", command) == receipt
    assert maintenance.step(choice.schedule_id, nominal(31)).status == "current"


def test_concurrent_start_fences_replacement_and_post_effect_failure_rolls_back(
    tmp_path, monkeypatch
):
    review, _, choice, old = prepared(tmp_path)
    store = review.transactions
    tasks = TaskCommands(store, review.actor, review.clock, review.identifiers)
    tasks.assign("assign", AssignTask(old[2].occurrence_id, 1, ("child",)))
    _, draft = reviewed(review, choice)
    tasks.transition("start", TransitionTask(old[2].occurrence_id, 2, OccurrenceState.IN_PROGRESS))
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.apply("old", draft)
    _, current = reviewed(review, choice, "second-preview")
    before = counts(store)
    with monkeypatch.context() as patch:
        append = SQLiteAudit.append

        def fail(self, entry):
            append(self, entry)
            if entry.command.action == "recurrence.review.apply":
                raise StorageFailure("after_batch")

        patch.setattr(SQLiteAudit, "append", fail)
        with pytest.raises(StorageFailure, match="after_batch"):
            review.apply("new", current)
    assert counts(store) == before
    with store.read() as unit:
        assert unit.recurrence.schedule("home", choice.schedule_id).revision == 1
        assert (
            unit.tasks.occurrence("home", old[1].occurrence_id).state is OccurrenceState.AVAILABLE
        )
        assert (
            unit.tasks.occurrence("home", old[2].occurrence_id).state is OccurrenceState.IN_PROGRESS
        )
    assert review.apply("new", current).result.decode()["cancelled"] == [old[1].occurrence_id]


def test_replacement_rejects_occupied_dates_and_work_with_live_dependencies(tmp_path):
    from domus.application.task_requests import CreateTask, UpdateTaskDependencies
    from domus.domain.task_values import TaskContent

    review, _, choice, old = prepared(tmp_path)
    store = review.transactions
    tasks = TaskCommands(store, review.actor, review.clock, review.identifiers)
    tasks.assign("assign", AssignTask(old[1].occurrence_id, 1, ("child",)))
    tasks.transition("start", TransitionTask(old[1].occurrence_id, 2, OccurrenceState.IN_PROGRESS))
    with pytest.raises(Conflict, match="recurrence_reschedule_collision"):
        review.preview("collision", choice)
    dependency = tasks.create(
        "dependent", CreateTask(TaskContent("Clean after setup"))
    ).result.decode()
    tasks.update_dependencies(
        "link", UpdateTaskDependencies(dependency["occurrence_id"], 1, (old[2].occurrence_id,), ())
    )
    with pytest.raises(Conflict, match="recurrence_replacement_assignments_need_review"):
        review.preview("dependency", choice)


def test_replacement_rejects_unsafe_or_stale_scheduling_inputs(tmp_path):
    from datetime import UTC, datetime

    from domus.domain.errors import InvalidInput, NotFound
    from domus.domain.recurrence_time import NominalTime

    review, _, choice, _ = prepared(tmp_path)
    with pytest.raises(InvalidInput, match="invalid_recurrence_pattern"):
        replace(choice, pattern="FREQ=DAILY")
    with pytest.raises(NotFound, match="recurrence_rule_missing"):
        review.preview("missing", replace(choice, schedule_id="missing"))
    with pytest.raises(Conflict, match="recurrence_review_stale"):
        review.preview("stale", replace(choice, schedule_revision=2))
    with pytest.raises(Conflict, match="recurrence_pattern_requires_replacement"):
        review.preview(
            "timing",
            replace(
                choice,
                pattern=parse_fixed_pattern("FREQ=DAILY", NominalTime(datetime(2026, 3, 28, 8))),
            ),
        )
    mismatch = replace(choice, pattern=parse_fixed_pattern("FREQ=WEEKLY;BYDAY=MO", nominal(28)))
    with pytest.raises(InvalidInput, match="recurrence_start_mismatch"):
        review.preview("mismatch", mismatch)
    past_ms = int(datetime(2026, 3, 30, tzinfo=UTC).timestamp() * 1000)
    future_clock = type("Clock", (), {"now": lambda _: past_ms})()
    with pytest.raises(Conflict, match="recurrence_reschedule_in_past"):
        replace(review, clock=future_clock).preview("past", choice)


def test_batch_http_routes_apply_and_recover_in_both_compositions(api):
    from domus.application.fixed_recurrence import FixedRecurrencePlanner
    from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
    from domus.application.task_requests import CreateTask
    from domus.domain.identity import HumanIdentity
    from domus.domain.nominal_recurrence import CalendarNominalExpansion
    from domus.domain.recurrence_time import TimePolicy
    from domus.domain.task_values import TaskContent
    from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    user = "a" * 32
    api.user(user, True)
    context = {"X-Domus-Context": f"v1:{api.store.installation.instance_id}:edge:{user}"}
    times = PinnedRecurrenceTime()
    clock, ids = SystemClock(), SecureIdentifiers()
    human = type("Actor", (), {"current": lambda _: HumanIdentity(user, True, True, False)})()
    planner = FixedRecurrencePlanner(CalendarNominalExpansion(), times)
    service = RecurrenceCommands(api.store, human, clock, ids, planner)
    first = NominalDate(date(2099, 1, 1))
    schedule = service.create_fixed(
        "fixed",
        CreateFixedTask(
            CreateTask(TaskContent("Fixed household work")),
            parse_fixed_pattern("FREQ=DAILY;COUNT=2", first),
            TimePolicy("UTC", times.data_identity),
        ),
    ).result.decode()["schedule_id"]
    maintenance = FixedMaintenance(
        api.store, MaintenanceScope(api.store.installation, "home"), planner, clock, ids
    )
    original = maintenance.step(schedule, NominalDate(date(2099, 1, 4)))
    body = {
        "schedule_id": schedule,
        "schedule_revision": 1,
        "start": {"kind": "date", "local": "2099-01-01"},
        "rrule": "FREQ=DAILY;COUNT=3;INTERVAL=2",
        "reason": "Move the next dates",
    }
    base = "/api/v1/tasks/recurrence/reviews"
    preview = api.client.post(
        base + "/fixed-replacement/preview", json=body, headers=api.headers("preview") | context
    )
    assert preview.status_code == 200, preview.text
    reviewed_body = body | {
        "preview_key": "preview",
        "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
    }
    applied = api.client.post(
        base + "/fixed-replacement/apply",
        json=reviewed_body,
        headers=api.headers("apply") | context,
    )
    assert applied.status_code == 200, applied.text
    assert original.occurrence_id in applied.json()["result"]["replacements"]
    recovered = api.client.get(base + "/requests/recurrence.review.apply/apply", headers=context)
    assert recovered.json() == applied.json()


def test_restored_original_batch_cannot_recreate_the_later_generation(tmp_path):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root, archive, target = (tmp_path / part for part in ("root", "archive", "target"))
    root.mkdir(mode=0o700)
    review, _, choice, old = prepared(root)
    store = review.transactions
    identity_at(root, store.installation)
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before-batch")
    _, request = reviewed(review, choice)
    applied = review.apply("replace", request)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        reopened = replace(review, transactions=restored.database)
        original = reopened.original(ReviewAction.APPLY, "replace")
        assert original.historical and original.operation_id == applied.operation_id
        assert reopened.apply("replace", request) == original
        with pytest.raises(Conflict, match="recurrence_review_source_absent"):
            reopened.preview("fresh", choice)
        with restored.database.read() as unit:
            assert unit.recurrence.schedule("home", choice.schedule_id).revision == 1
            assert {item.occurrence_id for item in unit.tasks.occurrences("home")} == {
                item.occurrence_id for item in old
            }
    finally:
        restored.close()


@pytest.mark.parametrize(
    "stage", ["paused", "inactive", "missing-progress", "missing-work", "no-work"]
)
def test_batch_source_fails_closed_before_effects(tmp_path, monkeypatch, stage):
    from domus.domain.recurrence_records import ScheduleState
    from domus.domain.task_values import DefinitionState
    from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    review, _, choice, old = prepared(tmp_path)
    store = review.transactions
    expected = Conflict
    with store.write() as unit:
        schedule = unit.recurrence.schedule("home", choice.schedule_id)
        if stage == "paused":
            unit.recurrence.save_schedule(
                replace(schedule, revision=2, state=ScheduleState.PAUSED), 1
            )
            choice = replace(choice, schedule_revision=2)
        if stage == "inactive":
            definition = unit.tasks.definition("home", schedule.definition_id)
            unit.tasks.save_definition(
                replace(definition, revision=2, state=DefinitionState.ARCHIVED), 1
            )
    if stage == "missing-progress":
        monkeypatch.setattr(SQLiteRecurrences, "progress", lambda *_: None)
        expected = StorageFailure
    elif stage == "missing-work":
        monkeypatch.setattr(SQLiteTasks, "occurrence", lambda *_: None)
        expected = StorageFailure
    elif stage == "no-work":
        tasks = TaskCommands(store, review.actor, review.clock, review.identifiers)
        for item in old:
            tasks.transition(
                "cancel-" + item.occurrence_id,
                TransitionTask(item.occurrence_id, 1, OccurrenceState.CANCELLED, "Cancelled"),
            )
    before = counts(store)
    with pytest.raises(expected):
        review.preview("unsafe", choice)
    assert counts(store) == before


def test_batch_planning_enforces_scope_budget_and_provider_failure(tmp_path, monkeypatch):
    from domus.application import fixed_batch_review as rules
    from domus.application.fixed_recurrence import FixedRecurrencePlanner
    from domus.domain.errors import IntegrationUnavailable, InvalidInput
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    review, maintenance, choice, _ = prepared(tmp_path)
    with review.transactions.read() as unit:
        source = rules.replacement_source(unit, maintenance.scope, choice)
    planner = maintenance.planner
    with monkeypatch.context() as patch:
        patch.setattr(PinnedRecurrenceTime, "local_at", lambda *_: None)
        with pytest.raises(IntegrationUnavailable, match="recurrence_time_source_invalid"):
            source.prepare(planner, review.clock.now())
    far = NominalDate(date(9999, 12, 31))
    overflow = replace(
        source,
        upcoming=replace(source.upcoming, pattern=replace(source.upcoming.pattern, start=far)),
    )
    with pytest.raises(Conflict, match="recurrence_review_too_large"):
        overflow.prepare(planner, review.clock.now())
    with monkeypatch.context() as patch:
        patch.setattr(rules, "_PERIOD_LIMIT", 1)
        with pytest.raises(Conflict, match="recurrence_review_too_large"):
            source.prepare(planner, review.clock.now())
    with monkeypatch.context() as patch:
        patch.setattr(rules, "_SLOT_LIMIT", 1)
        with pytest.raises(Conflict, match="recurrence_review_too_large"):
            review.preview("slot-budget", choice)
    with monkeypatch.context() as patch:
        patch.setattr(rules, "_SLOT_LIMIT", 2)
        with pytest.raises(Conflict, match="recurrence_review_too_large"):
            review.preview("open-budget", choice)
    stale = source.prepare(planner, review.clock.now())
    with (
        review.transactions.write() as unit,
        pytest.raises(Conflict, match="recurrence_source_changed"),
    ):
        maintenance.commit_reviewed_step(unit, source.upcoming, stale.steps[0], stale.before)
    two_slots = replace(stale.steps[0], slots=stale.steps[0].slots + stale.steps[1].slots)
    with (
        review.transactions.write() as unit,
        pytest.raises(Conflict, match="recurrence_source_changed"),
    ):
        maintenance.commit_reviewed_step(unit, source.current, two_slots, stale.before)
    with monkeypatch.context() as patch:
        patch.setattr(FixedRecurrencePlanner, "expand", lambda *_a, **_kw: stale.steps[0])
        with pytest.raises(Conflict, match="recurrence_review_too_large"):
            source.prepare(planner, review.clock.now())
    with monkeypatch.context() as patch:
        patch.setattr(
            FixedRecurrencePlanner,
            "expand",
            lambda *_a, **_kw: replace(stale.steps[0], slots=(), range_complete=True),
        )
        with pytest.raises(InvalidInput, match="recurrence_start_mismatch"):
            source.prepare(planner, review.clock.now())


def test_replacement_preserves_the_concurrent_original_for_independent_writers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    review, _, choice, _ = prepared(tmp_path)
    _, command = reviewed(review, choice)
    store = review.transactions
    another = replace(review, transactions=SQLiteDatabase(store.path, store.installation))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(review.apply, "shared", command)
        second = pool.submit(another.apply, "shared", command)
        assert first.result() == second.result()
    result = first.result().result.decode()
    with store.read() as unit:
        assert len(unit.recurrence.slots("home", choice.schedule_id)) == 6
        assert len(result["replacements"]) == 2 and len(result["added"]) == 1


def test_second_replacement_distinguishes_proven_old_cancellations_from_retained_work(tmp_path):
    review, _, choice, old = prepared(tmp_path)
    _, first = reviewed(review, choice)
    first_result = review.apply("first", first).result.decode()
    second_choice = replace(
        choice,
        schedule_revision=2,
        pattern=parse_fixed_pattern("FREQ=DAILY;COUNT=3;INTERVAL=3", nominal(28)),
    )
    preview, second = reviewed(review, second_choice, "preview-second")
    retained = preview.result.decode()["plan"]["source"]["retained_work"]
    assert {item["occurrence_id"] for item in retained if item["previously_replaced"]} == {
        old[1].occurrence_id,
        old[2].occurrence_id,
    }
    second_result = review.apply("second", second).result.decode()
    assert first_result["replacements"][old[1].occurrence_id] in second_result["replacements"]


@pytest.mark.parametrize("timed", [False, True])
def test_prior_manual_move_remains_blocking_when_its_effective_deadline_escapes_the_review(
    tmp_path, timed
):
    from domus.application.reschedule_review import RescheduleSelection

    review, _, choice, old = prepared(tmp_path, timed=timed)
    _, request = reviewed(review, choice, "initial-preview")
    assert request.plan_fingerprint
    destination = NominalTime(datetime(2026, 7, 1, 9)) if timed else NominalDate(date(2026, 7, 1))
    first = old[0]
    move = RescheduleSelection(
        choice.schedule_id,
        1,
        first.receipt.command.key,
        first.occurrence_id,
        1,
        destination,
        "Keep an individual move",
    )
    _, change = reviewed(review, move, "move-preview")
    review.apply("move", change)
    with pytest.raises(Conflict, match="recurrence_review_too_large"):
        review.preview("blocked", choice)


def test_replacement_finishes_a_bounded_scan_and_cannot_drop_unmatched_assignments(tmp_path):
    review, _, choice, old = prepared(tmp_path)
    tasks = TaskCommands(review.transactions, review.actor, review.clock, review.identifiers)
    tasks.assign("assignment", AssignTask(old[2].occurrence_id, 1, ("child",)))
    too_short = replace(choice, pattern=parse_fixed_pattern("FREQ=DAILY;COUNT=1", nominal(28)))
    with pytest.raises(Conflict, match="recurrence_replacement_assignments_need_review"):
        review.preview("needs-review", too_short)
    continuing = replace(choice, pattern=parse_fixed_pattern("FREQ=DAILY;INTERVAL=10", nominal(28)))
    _, request = reviewed(review, continuing)
    result = review.apply("continue", request).result.decode()
    assert len(result["added"]) == 4
    with review.transactions.read() as unit:
        progress = unit.recurrence.progress("home", choice.schedule_id)
        assert progress.range_complete and not progress.cursor.closed


def test_complete_plan_byte_bounds_and_mismatched_write_snapshot_fail_closed(tmp_path, monkeypatch):
    from domus.application.fixed_batch_review import ReplacementSource, replacement_source
    from domus.domain.errors import InvalidInput

    review, maintenance, choice, old = prepared(tmp_path)
    store = review.transactions
    with store.read() as unit:
        source = replacement_source(unit, maintenance.scope, choice)
    prepared_plan = source.prepare(maintenance.planner, review.clock.now())
    item = source.replaceable[0]
    big = replace(
        item,
        work=replace(
            item.work,
            state=OccurrenceState.ASSIGNED,
            assignee_ids=tuple(str(index) + "a" * 110 for index in range(16)),
        ),
    )
    oversized = replace(prepared_plan, source=replace(source, retained=(big,) * 100))
    with pytest.raises(Conflict, match="recurrence_review_too_large"):
        oversized.document()
    far = replace(item, original=NominalDate(date(2026, 9, 1)))
    with pytest.raises(Conflict, match="recurrence_review_too_large"):
        replace(source, replaceable=(far,)).prepare(maintenance.planner, review.clock.now())

    def fail(*_args):
        raise InvalidInput("invalid_document")

    with monkeypatch.context() as patch:
        patch.setattr(RecurrenceReview, "_snapshot", fail)
        with pytest.raises(Conflict, match="recurrence_review_too_large"):
            review.preview("large-plan", choice)
    with monkeypatch.context() as patch:
        patch.setattr(RecurrenceReview, "_preview_change", fail)
        with pytest.raises(Conflict, match="recurrence_review_too_large"):
            review.preview("large-receipt", choice)
    run = ReplacementSource.prepare
    tasks = TaskCommands(store, review.actor, review.clock, review.identifiers)

    def interleave(self, *args):
        result = run(self, *args)
        tasks.assign("interleaving-assignment", AssignTask(old[1].occurrence_id, 1, ("child",)))
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ReplacementSource, "prepare", interleave)
        with pytest.raises(Conflict, match="recurrence_review_stale"):
            review.preview("changed-during-prepare", choice)
    with store.read() as unit:
        assert unit.recurrence.schedule("home", choice.schedule_id).revision == 1


def test_batch_does_not_open_a_new_generation_when_the_first_date_passes_before_write(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from domus.application.fixed_batch_review import ReplacementSource, replacement_source

    review, maintenance, choice, _ = prepared(tmp_path)
    with review.transactions.read() as unit:
        source = replacement_source(unit, maintenance.scope, choice)
    deadline = source.prepare(maintenance.planner, review.clock.now()).future_until
    clock = SimpleNamespace(value=deadline - 1000)
    review = replace(review, clock=SimpleNamespace(now=lambda: clock.value))
    _, request = reviewed(review, choice)
    prepare = ReplacementSource.prepare

    def cross(self, *args):
        plan = prepare(self, *args)
        clock.value = plan.future_until
        return plan

    monkeypatch.setattr(ReplacementSource, "prepare", cross)
    before = counts(review.transactions)
    with pytest.raises(Conflict, match="recurrence_reschedule_in_past"):
        review.apply("past", request)
    assert counts(review.transactions) == before


@pytest.mark.parametrize("timed", [False, True])
def test_replacement_cannot_recreate_historically_excluded_work(
    tmp_path, request, timed
):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.application.fixed_exception_review import FixedExceptionChange
    from domus.domain.recurrence_records import FixedException, FixedExceptionKind
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    root = tmp_path / "runtime"
    root.mkdir(mode=0o700)
    review, _, choice, old = prepared(root, timed=timed)
    store = review.transactions
    tasks = TaskCommands(store, review.actor, review.clock, review.identifiers)
    tasks.assign("assignment", AssignTask(old[2].occurrence_id, 1, ("child",)))
    identity_at(root, store.installation)
    archive, target = tmp_path / "archive", tmp_path / "target"
    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("before")
    excluded = choice.pattern.start
    selection = FixedExceptionChange(
        choice.schedule_id,
        1,
        FixedException(FixedExceptionKind.EXCLUDE, excluded, "School break"),
    )
    _, change = reviewed(review, selection, "preview-exclude")
    original = review.apply("exclude", change)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    opened = open_storage(root, "edge")
    request.addfinalizer(opened.close)
    review = replace(review, transactions=opened.database)
    assert review.original(ReviewAction.APPLY, "exclude").historical
    assert review.original(ReviewAction.APPLY, "exclude").operation_id == original.operation_id
    with opened.database.read() as unit:
        assert unit.recurrence.schedule("home", choice.schedule_id).exceptions == ()
    before = opened.database.path.read_bytes()
    before_counts = counts(opened.database)
    with pytest.raises(Conflict, match="recurrence_review_source_absent"):
        review.preview("preview-replacement", choice)
    assert opened.database.path.read_bytes() == before
    assert counts(opened.database) == before_counts
    restarted = replace(
        review, transactions=SQLiteDatabase(opened.database.path, opened.database.installation)
    )
    with pytest.raises(Conflict, match="recurrence_review_source_absent"):
        restarted.preview("restart-preview", choice)
    assert opened.database.path.read_bytes() == before
    assert counts(opened.database) == before_counts
    with opened.database.read() as unit:
        assert unit.recurrence.schedule("home", choice.schedule_id).revision == 1
        assert unit.recurrence.progress("home", choice.schedule_id).cursor.nominal_count == 3
        restored_work = unit.tasks.occurrence("home", old[1].occurrence_id)
        assert restored_work.state is OccurrenceState.AVAILABLE
        assert unit.tasks.occurrence("home", old[2].occurrence_id).assignee_ids == ("child",)
