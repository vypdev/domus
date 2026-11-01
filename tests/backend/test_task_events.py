"""Lifecycle facts retain original snapshots without issuing points or settling materials."""

from dataclasses import replace

import pytest
from test_task_commands import fixture, resource
from test_task_runtime import api as api

from domus.application.task_commands import CompleteTask, CreateTask, ReopenTask, VerifyTask
from domus.application.task_events import TaskEventFeed
from domus.domain.errors import InvalidInput, NotFound, StorageFailure
from domus.domain.storage import Installation
from domus.domain.task_events import TaskEventKind, lifecycle_event
from domus.domain.task_values import TaskContent, VerificationState


def prepared(tmp_path, *, child=False):
    commands, store, actor, ids = fixture(tmp_path)
    oid = resource(commands.create("create", CreateTask(TaskContent("Test lifecycle"))))[1]
    with store.read() as unit:
        member = unit.members.by_user("home", actor.current().ha_user_id).member_id
    done = commands.complete("perform", CompleteTask(oid, 1, ("child" if child else member,), 90))
    return commands, store, actor, ids, oid, done


def test_lifecycle_feed_preserves_completion_approval_and_reopening_snapshots(tmp_path):
    commands, store, _, _, oid, done = prepared(tmp_path, child=True)
    cid = done.result.decode()["cycle"]["cycle_id"]
    approved = commands.verify("approve", VerifyTask(oid, 2, cid, VerificationState.APPROVED))
    opened = commands.reopen("reopen", ReopenTask(oid, 3, cid, "Perform again"))
    feed = TaskEventFeed(store, store.installation)
    rows = feed.read().items
    assert [value.event_id for value in rows] == [
        done.operation_id,
        approved.operation_id,
        opened.operation_id,
    ]
    assert [value.kind for value in rows] == list(TaskEventKind)
    assert [value.cycle.revision for value in rows] == [1, 2, 3]
    assert [value.points_eligible for value in rows] == [False, True, False]
    assert [value.closes_awards for value in rows] == [False, False, True]
    assert len({value.event_key for value in rows}) == 3
    assert len({value.cycle_key for value in rows}) == 1
    assert all(value.cycle.performed_at == 90 for value in rows)
    assert feed.read().items == rows


def test_both_business_compositions_supply_the_same_read_only_event_source(api):
    from test_task_http import checked, create

    oid = create(api)["result"]["occurrence_id"]
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    done = checked(
        api,
        "post",
        f"/occurrences/{oid}/complete",
        {"expected_revision": 1, "performer_ids": [member], "performed_at": 90},
        "perform",
    )
    events = api.runtime.task_events.read()
    assert len(events.items) == 1 and events.items[0].event_id == done["operation_id"]
    assert events.items[0].points_eligible
    assert events.items[0].installation == api.store.installation
    with api.store.read() as unit:
        assert unit.outbox.delivered(done["operation_id"]) is False


def event_proof(tmp_path, *, verify=None, close=False):
    commands, store, actor, ids, oid, done = prepared(tmp_path, child=verify is not None)
    cid = done.result.decode()["cycle"]["cycle_id"]
    revision = 2
    if verify is not None:
        commands.verify("verify", VerifyTask(oid, revision, cid, verify, "Reviewed"))
        revision += 1
    if close:
        commands.reopen("reopen", ReopenTask(oid, revision, cid, "Perform again"))
    with store.read() as unit:
        evidence = unit.tasks.lifecycle_events("home")
        cycle = unit.tasks.cycle("home", cid)
        work = unit.tasks.occurrence("home", oid)
    return store, actor, work, cycle, evidence


@pytest.mark.parametrize(
    "values",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
        {"after": True},
        {"after": -1},
        {"after": 2**63},
    ],
)
def test_internal_feed_rejects_noncanonical_or_unbounded_pages(tmp_path, values):
    _, store, _, _, _, _ = prepared(tmp_path)
    with pytest.raises(InvalidInput):
        TaskEventFeed(store, store.installation).read(**values)


def test_feed_requires_valid_composition_scope_and_existing_household(tmp_path):
    _, store, _, _, _, _ = prepared(tmp_path)
    with pytest.raises(InvalidInput):
        TaskEventFeed(store, None)
    with pytest.raises(InvalidInput):
        TaskEventFeed(store, store.installation, "bad/id")
    with pytest.raises(NotFound):
        TaskEventFeed(store, store.installation, "other").read()


def test_rejected_and_reopened_events_close_awards_without_rewriting_pending_completion(tmp_path):
    store, _, _, _, _ = event_proof(tmp_path, verify=VerificationState.REJECTED, close=True)
    rows = TaskEventFeed(store, store.installation).read().items
    assert [value.points_eligible for value in rows] == [False, False, False]
    assert [value.closes_awards for value in rows] == [False, True, True]
    assert rows[0].cycle.verification is VerificationState.PENDING
    assert (
        rows[1].cycle.verification is VerificationState.REJECTED and rows[1].cycle.closed_at is None
    )
    assert rows[2].cycle.closed_at == 100


@pytest.mark.parametrize(
    "change",
    [
        {"installation": None},
        {"kind": "task.completed"},
        {"cycle": None},
        {"version": True},
        {"version": 2},
        {"position": True},
        {"event_id": "bad/id"},
        {"occurred_at": 99},
        {"occurrence_revision": 0},
    ],
)
def test_lifecycle_model_rejects_unproven_scope_version_identity_and_time(tmp_path, change):
    _, store, _, _, _, _ = prepared(tmp_path)
    event = TaskEventFeed(store, store.installation).read().items[0]
    with pytest.raises(InvalidInput):
        replace(event, **change)


def test_identity_keys_isolate_installations_channels_households_events_and_real_cycles(tmp_path):
    commands, store, _, _, oid, done = prepared(tmp_path)
    first = TaskEventFeed(store, store.installation).read().items[0]
    for installation in (
        replace(store.installation, channel="stable"),
        Installation("147cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge"),
    ):
        changed = replace(first, installation=installation)
        assert changed.event_key != first.event_key and changed.cycle_key != first.cycle_key
    changed = replace(
        first, event_id="another-event", cycle=replace(first.cycle, task_policy_revision=2)
    )
    assert changed.event_key != first.event_key and changed.cycle_key == first.cycle_key
    changed = replace(first, cycle=replace(first.cycle, household_id="other"))
    assert changed.event_key != first.event_key and changed.cycle_key != first.cycle_key
    cid = done.result.decode()["cycle"]["cycle_id"]
    commands.reopen("reopen", ReopenTask(oid, 2, cid, "Perform again"))
    commands.complete(
        "again", CompleteTask(oid, 3, tuple(p.member_id for p in first.cycle.performers), 90)
    )
    later = TaskEventFeed(store, store.installation).read().items[-1]
    assert later.cycle_key != first.cycle_key and later.points_eligible


@pytest.mark.parametrize(
    "change",
    [
        "unknown_action",
        "wrong_definition",
        "wrong_occurrence",
        "future_stage",
        "verified_pending",
        "reopened_open",
        "wrong_snapshot_kind",
    ],
)
def test_event_source_rejects_incoherent_original_scope_and_stage(tmp_path, change):
    from test_task_reviews import coherent

    store, _, work, cycle, evidence = event_proof(
        tmp_path, verify=VerificationState.APPROVED if change == "wrong_snapshot_kind" else None
    )
    row = evidence[0]
    if change == "unknown_action":
        command = replace(row.receipt.command, action="task.assign")
        row = replace(
            row,
            receipt=replace(row.receipt, command=command),
            audit=replace(row.audit, command=command),
            event=replace(row.event, event_type=command.action),
        )
    elif change == "wrong_definition":
        row = coherent(row, result=row.receipt.result.decode() | {"definition_id": "other"})
    elif change == "wrong_occurrence":
        work = replace(work, occurrence_id="other")
    elif change == "future_stage":
        cycle = replace(cycle, revision=5)
    else:
        event = TaskEventFeed(store, store.installation).read().items[-1]
        if change == "verified_pending":
            event = replace(event, cycle=replace(event.cycle, verification=VerificationState.NONE))
            kind = TaskEventKind.VERIFIED
        elif change == "reopened_open":
            kind = TaskEventKind.REOPENED
        else:
            kind = TaskEventKind.COMPLETED
        with pytest.raises(InvalidInput):
            replace(event, kind=kind)
        return
    with pytest.raises(InvalidInput):
        lifecycle_event(row, work, cycle, store.installation)


@pytest.mark.parametrize("change", ["decision", "reason", "state", "cycle"])
def test_verification_source_requires_exact_original_decision_reason_and_snapshot(tmp_path, change):
    from test_task_reviews import coherent

    store, _, work, cycle, evidence = event_proof(tmp_path, verify=VerificationState.APPROVED)
    row = evidence[1]
    request = row.audit.detail.decode()["request"]
    result = row.receipt.result.decode()
    if change in ("decision", "reason"):
        request[change] = "changed"
    elif change == "state":
        result["state"] = "available"
    else:
        result["cycle"] = None
    with pytest.raises(InvalidInput):
        lifecycle_event(
            coherent(row, request=request, result=result), work, cycle, store.installation
        )


@pytest.mark.parametrize(
    "change", ["cycle_snapshot", "cycle_identity", "missing_cycle", "missing_work"]
)
def test_feed_fails_closed_without_guessing_missing_source_facts(tmp_path, monkeypatch, change):
    from test_task_reviews import coherent

    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    store, _, _, _, evidence = event_proof(tmp_path)
    if change in ("cycle_snapshot", "cycle_identity"):
        result = evidence[0].receipt.result.decode()
        result["cycle"] = None if change == "cycle_snapshot" else {"cycle_id": True}
        monkeypatch.setattr(
            SQLiteTasks,
            "lifecycle_events",
            lambda *args, **kwargs: (coherent(evidence[0], result=result),),
        )
    else:
        monkeypatch.setattr(
            SQLiteTasks, "cycle" if change == "missing_cycle" else "occurrence", lambda *args: None
        )
    with pytest.raises(StorageFailure):
        TaskEventFeed(store, store.installation).read()
