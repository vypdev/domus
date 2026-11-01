"""Dependency reviews derive immutable causal facts without reopening downstream work."""

from dataclasses import replace

import pytest
from test_task_commands import fixture, resource
from test_task_queries import queries
from test_task_runtime import api as api

from domus.application.task_commands import (
    CompleteTask,
    CreateTask,
    ReopenTask,
    UpdateTaskDependencies,
)
from domus.application.task_requests import ReviewTaskDependency
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import Permission, PermissionRule
from domus.domain.storage import JsonDocument
from domus.domain.task_reviews import (
    DependencyReviewDecision,
    dependency_review_cause,
    recorded_dependencies,
    recorded_review,
    validate_completion,
    validate_reopening,
    validate_review_interval,
)
from domus.domain.task_values import TaskContent


def setup(tmp_path, *, both=False):
    commands, store, actor, ids = fixture(tmp_path)
    source = resource(commands.create("source", CreateTask(TaskContent("Prepare equipment"))))[1]
    target = resource(commands.create("target", CreateTask(TaskContent("Use prepared equipment"))))[
        1
    ]
    commands.update_dependencies(
        "edges", UpdateTaskDependencies(target, 1, (source,), (source,) if both else ())
    )
    with store.read() as unit:
        member = unit.members.by_user("home", actor.current().ha_user_id).member_id
    source_done = commands.complete("source-done", CompleteTask(source, 1, (member,), 90))
    target_done = commands.complete("target-done", CompleteTask(target, 2, (member,), 90))
    return commands, store, actor, ids, source, target, member, source_done, target_done


def reopen(commands, store, oid, key):
    with store.read() as unit:
        work = unit.tasks.occurrence("home", oid)
    return commands.reopen(
        key, ReopenTask(oid, work.revision, work.current_cycle_id, "Review required prerequisite")
    )


def perform(commands, store, oid, member, key):
    with store.read() as unit:
        work = unit.tasks.occurrence("home", oid)
    return commands.complete(key, CompleteTask(oid, work.revision, (member,), 90))


def test_reopening_preserves_completed_work_and_exposes_one_cause_for_overlapping_edges(tmp_path):
    commands, store, actor, ids, source, target, _, _, done = setup(tmp_path, both=True)
    service = queries(store, actor.current())
    cycle_id = done.result.decode()["cycle"]["cycle_id"]
    assert service.dependency_reviews(target, cycle_id).items == ()
    original = service.occurrence(target).work
    opened = reopen(commands, store, source, "reopen-source")
    count = ids.count
    page = service.dependency_reviews(target, cycle_id)
    assert len(page.items) == 1 and page.next_cursor is None
    item = page.items[0]
    assert item.cause.source_operation_id == opened.operation_id
    assert item.cause.dependent_cycle_id == cycle_id
    assert tuple(item.cause.relationships) == ("prerequisite", "required_subtask")
    assert not item.source_satisfies_gate and item.source_state.value == "available"
    assert service.occurrence(target).dependency_reviews == page
    assert service.occurrence(target).work == original and ids.count == count
    assert service.dependency_reviews(target, cycle_id) == page


def test_equal_timestamps_use_operation_positions_and_each_dependent_cycle_interval(tmp_path):
    commands, store, actor, _, source, target, member, _, done = setup(tmp_path)
    first = reopen(commands, store, source, "first-reopen")
    perform(commands, store, source, member, "source-again")
    service = queries(store, actor.current())
    old = done.result.decode()["cycle"]["cycle_id"]
    first_view = service.dependency_reviews(target, old).items[0]
    assert first_view.source_satisfies_gate
    reopen(commands, store, target, "target-reopen")
    later = perform(commands, store, target, member, "target-again")
    second = reopen(commands, store, source, "second-reopen")
    current = later.result.decode()["cycle"]["cycle_id"]
    assert [v.cause.source_operation_id for v in service.dependency_reviews(target, old).items] == [
        first.operation_id
    ]
    assert [
        v.cause.source_operation_id for v in service.dependency_reviews(target, current).items
    ] == [second.operation_id]
    assert (
        service.occurrence(target).dependency_reviews.items[0].cause.dependent_cycle_id == current
    )


def test_current_read_revocation_blocks_review_discovery_and_issued_cursor(tmp_path):
    commands, store, actor, _, source, target, member, _, done = setup(tmp_path)
    for number in range(3):
        reopen(commands, store, source, f"reopen-{number}")
        if number < 2:
            perform(commands, store, source, member, f"source-{number}")
    service = queries(store, actor.current())
    cid = done.result.decode()["cycle"]["cycle_id"]
    page = service.dependency_reviews(target, cid, limit=1)
    assert page.next_cursor and len(page.items) == 1
    with store.write() as unit:
        person = unit.members.by_user("home", actor.current().ha_user_id)
        unit.members.save(
            replace(person, exceptions=(PermissionRule(Permission.TASKS_READ, False),), revision=2),
            1,
        )
    with pytest.raises(Forbidden):
        service.dependency_reviews(target, cid, limit=1, cursor=page.next_cursor)


def test_manager_acceptance_preserves_unsatisfied_source_and_does_not_accept_later_causes(tmp_path):
    commands, store, actor, _, source, target, member, _, done = setup(tmp_path)
    first = reopen(commands, store, source, "first-source-reopen")
    cid = done.result.decode()["cycle"]["cycle_id"]
    request = ReviewTaskDependency(target, 1, cid, first.operation_id, "Work remains valid")
    service = queries(store, actor.current())
    original = service.occurrence(target)
    receipt = commands.review_dependency("accept", request)
    item = service.dependency_reviews(target, cid).items[0]
    assert item.state.value == "reviewed" and item.revision == 2
    assert item.acknowledgement.operation_id == receipt.operation_id
    assert item.acknowledgement.reason == "Work remains valid"
    assert item.source_satisfies_gate is False
    assert service.occurrence(target).work == original.work
    assert service.occurrence(target).cycle == original.cycle
    assert not service.occurrence(target).dependency_review_required
    assert commands.review_dependency("accept", request) == receipt
    with pytest.raises(Conflict):
        commands.review_dependency("second-acceptance", request)
    perform(commands, store, source, member, "source-again")
    later = reopen(commands, store, source, "new-reopen")
    detail = service.occurrence(target)
    assert detail.dependency_review_required
    assert [v.cause.source_operation_id for v in detail.dependency_reviews.items] == [
        later.operation_id
    ]
    assert service.dependency_reviews(target, cid, state=item.state).items == (item,)


@pytest.mark.parametrize(
    "changes",
    [
        {"occurrence_id": "bad/id"},
        {"cycle_id": ""},
        {"source_operation_id": "bad/id"},
        {"expected_revision": True},
        {"expected_revision": 0},
        {"reason": "   "},
        {"reason": "x" * 1001},
        {"reason": "\x00"},
    ],
)
def test_review_request_has_strict_scope_revision_and_meaningful_reason(changes):
    values = dict(
        occurrence_id="work",
        expected_revision=1,
        cycle_id="cycle",
        source_operation_id="operation",
        reason="Still valid",
    )
    with pytest.raises(InvalidInput):
        ReviewTaskDependency(**(values | changes))


def test_acceptance_rechecks_current_management_for_new_commands_and_original_receipts(tmp_path):
    commands, store, actor, _, source, target, _, _, done = setup(tmp_path)
    opened = reopen(commands, store, source, "reopen")
    cid = done.result.decode()["cycle"]["cycle_id"]
    request = ReviewTaskDependency(target, 1, cid, opened.operation_id, "Still valid")
    receipt = commands.review_dependency("accept", request)
    service = queries(store, actor.current())
    assert service.operation(receipt.operation_id).receipt == receipt
    assert service.history(target).items[-1].reason == request.reason
    with pytest.raises(Conflict):
        commands.review_dependency("accept", replace(request, reason="Changed request"))
    with pytest.raises(Conflict, match="already_reviewed"):
        commands.review_dependency("new-key", replace(request, expected_revision=2))
    with store.write() as unit:
        member = unit.members.by_user("home", actor.current().ha_user_id)
        unit.members.save(
            replace(
                member, revision=2, exceptions=(PermissionRule(Permission.TASKS_MANAGE, False),)
            ),
            1,
        )
    with pytest.raises(Forbidden):
        commands.review_dependency("accept", request)
    with pytest.raises(Forbidden):
        service.operation(receipt.operation_id)
    assert service.dependency_reviews(target, cid).items[0].state.value == "reviewed"


def test_missing_cause_cycle_and_work_are_separate_authorized_failures(tmp_path):
    commands, store, actor, _, _, target, _, _, done = setup(tmp_path)
    cid = done.result.decode()["cycle"]["cycle_id"]
    with pytest.raises(NotFound):
        commands.review_dependency(
            "missing", ReviewTaskDependency(target, 1, cid, "absent", "Reviewed")
        )
    service = queries(store, actor.current())
    with pytest.raises(NotFound):
        service.dependency_reviews("missing", cid)
    with pytest.raises(NotFound):
        service.dependency_reviews(target, "missing")
    with pytest.raises(InvalidInput):
        service.dependency_reviews(target, cid, state="pending")


def http_review(api):
    from test_task_http import checked, create

    source = create(api, "source")["result"]["occurrence_id"]
    target = create(api, "target")["result"]["occurrence_id"]
    checked(
        api,
        "put",
        f"/occurrences/{target}/dependencies",
        {"expected_revision": 1, "prerequisite_ids": [source]},
        "edges",
    )
    member = api.client.get("/api/v1/members").json()["members"][0]["member_id"]
    receipts = [
        checked(
            api,
            "post",
            f"/occurrences/{oid}/complete",
            {"expected_revision": revision, "performer_ids": [member], "performed_at": 90},
            f"done-{oid}",
        )
        for oid, revision in ((source, 1), (target, 2))
    ]
    opened = checked(
        api,
        "post",
        f"/occurrences/{source}/reopen",
        {
            "expected_revision": 2,
            "cycle_id": receipts[0]["result"]["cycle"]["cycle_id"],
            "reason": "Prepare again",
        },
        "reopen",
    )
    cid = receipts[1]["result"]["cycle"]["cycle_id"]
    path = f"/api/v1/tasks/occurrences/{target}/dependency-reviews"
    return target, cid, path, path + "/" + opened["operation_id"] + "/acknowledgement"


def test_both_compositions_show_source_condition_and_record_explicit_manager_acceptance(api):
    target, cid, path, action = http_review(api)
    page = api.client.get(path, params={"cycle_id": cid})
    assert page.status_code == 200, page.text
    item = page.json()["items"][0]
    assert item["state"] == "pending" and not item["source_satisfies_gate"]
    body = {"expected_revision": 1, "cycle_id": cid, "reason": "Completed work is still valid"}
    response = api.client.post(action, json=body, headers=api.headers("accept"))
    assert response.status_code == 200, response.text
    assert (
        api.client.post(action, json=body, headers=api.headers("accept")).json() == response.json()
    )
    assert api.client.get(path, params={"cycle_id": cid, "state": "pending"}).json()["items"] == []
    viewed = api.client.get(path, params={"cycle_id": cid, "state": "reviewed"}).json()["items"][0]
    assert viewed["state"] == "reviewed" and viewed["revision"] == 2
    assert viewed["acknowledgement"]["reason"] == body["reason"]
    assert not viewed["source_satisfies_gate"]
    detail = api.client.get(f"/api/v1/tasks/occurrences/{target}").json()
    assert detail["work"]["state"] == "completed" and not detail["dependency_review_required"]


@pytest.mark.parametrize("guard", ["origin", "csrf", "ha_unavailable"])
def test_acceptance_retains_existing_authenticated_write_guards(api, guard):
    from domus.domain.errors import IdentityUnavailable

    _, cid, _, action = http_review(api)
    headers = api.headers("guarded-acceptance")
    if guard == "origin":
        headers["Origin"] = "https://other.example"
    elif guard == "csrf":
        headers["X-CSRF-Token"] = "invalid"
    else:
        api.source.error = IdentityUnavailable("ha_unavailable")
    response = api.client.post(
        action,
        json={"cycle_id": cid, "expected_revision": 1, "reason": "Still valid"},
        headers=headers,
    )
    assert response.status_code == (503 if guard == "ha_unavailable" else 403), response.text


def coherent(original, *, request=None, result=None):
    detail = original.audit.detail.decode()
    request = detail["request"] if request is None else request
    result = original.receipt.result.decode() if result is None else result
    return replace(
        original,
        receipt=replace(
            original.receipt,
            result=JsonDocument.from_value(result),
            payload_fingerprint=JsonDocument.from_value(request).fingerprint,
        ),
        audit=replace(
            original.audit,
            detail=JsonDocument.from_value(
                {"transition": detail["transition"], "request": request, "result": result}
            ),
        ),
        event=replace(
            original.event,
            payload=JsonDocument.from_value({"version": 1, "kind": detail["transition"], **result}),
        ),
    )


def proof(tmp_path, *, accept=False, close=False):
    commands, store, actor, _, source, target, _, _, done = setup(tmp_path, both=True)
    opened = reopen(commands, store, source, "reopen-source")
    cid = done.result.decode()["cycle"]["cycle_id"]
    if accept:
        commands.review_dependency(
            "accept", ReviewTaskDependency(target, 1, cid, opened.operation_id, "Still valid")
        )
    if close:
        reopen(commands, store, target, "reopen-target")
    with store.read() as unit:
        evidence = unit.tasks.review_evidence("home", target, cid)
        dependent = unit.tasks.cycle("home", cid)
        source_cycle = unit.tasks.cycle("home", opened.result.decode()["cycle"]["cycle_id"])
    return store, actor, dependent, source_cycle, evidence


@pytest.mark.parametrize(
    "change",
    [
        {"prerequisite_ids": None},
        {"required_subtask_ids": "source"},
        {"prerequisite_ids": ["work"]},
        {"prerequisite_ids": ["source", "source"]},
    ],
)
def test_original_dependency_arrays_reject_invalid_or_self_references(change):
    with pytest.raises(InvalidInput):
        recorded_dependencies(
            {"occurrence_id": "work", "prerequisite_ids": [], "required_subtask_ids": []} | change
        )


@pytest.mark.parametrize(
    "change",
    [
        {"revision": True},
        {"revision": 55},
        {"definition_revision": 2},
        {"state": "available"},
        {"cycle": None},
    ],
)
def test_completion_evidence_cannot_change_immutable_cycle_or_revision(tmp_path, change):
    _, _, dependent, _, evidence = proof(tmp_path)
    with pytest.raises(InvalidInput):
        validate_completion(
            coherent(
                evidence.completion, result=evidence.completion.receipt.result.decode() | change
            ),
            dependent,
        )


def test_completion_requires_original_request_object(tmp_path):
    _, _, dependent, _, evidence = proof(tmp_path)
    bad = replace(
        evidence.completion,
        audit=replace(evidence.completion.audit, detail=JsonDocument.from_value({"request": None})),
    )
    with pytest.raises(InvalidInput):
        validate_completion(bad, dependent)


@pytest.mark.parametrize(
    "change", [{"assignee_ids": None}, {"state": "completed"}, {"dependency_review_required": 1}]
)
def test_source_reopening_evidence_cannot_guess_missing_facts(tmp_path, change):
    _, _, _, source, evidence = proof(tmp_path)
    original = evidence.reopenings[0]
    with pytest.raises(InvalidInput):
        validate_reopening(
            coherent(original, result=original.receipt.result.decode() | change), source
        )


@pytest.mark.parametrize(
    "change",
    [
        {"source_occurrence_id": "target"},
        {"source_cycle_id": "dependent-cycle"},
        {"source_position": 1},
        {"relationships": ()},
        {"relationships": ("prerequisite", "required_subtask")},
    ],
)
def test_cause_identity_and_relationships_are_strict(tmp_path, change):
    _, _, dependent, source, evidence = proof(tmp_path)
    cause = dependency_review_cause(
        evidence.completion, evidence.reopenings[0], dependent, source, None
    )
    values = (
        {"source_occurrence_id": cause.dependent_occurrence_id}
        if "source_occurrence_id" in change
        else {"source_cycle_id": cause.dependent_cycle_id}
        if "source_cycle_id" in change
        else change
    )
    with pytest.raises(InvalidInput):
        replace(cause, **values)
    assert cause.cause_id == replace(cause).cause_id
    assert cause.cause_id != replace(cause, source_operation_id="other-reopening").cause_id


def test_closed_cycle_requires_its_ordered_original_closure(tmp_path):
    _, _, dependent, source, evidence = proof(tmp_path, close=True)
    with pytest.raises(InvalidInput):
        validate_review_interval(evidence.completion, None, dependent)
    with pytest.raises(InvalidInput):
        validate_review_interval(
            evidence.completion,
            replace(evidence.closure, position=evidence.completion.position),
            dependent,
        )
    with pytest.raises(InvalidInput):
        dependency_review_cause(
            evidence.completion,
            replace(evidence.reopenings[0], position=evidence.closure.position),
            dependent,
            source,
            evidence.closure,
        )


@pytest.mark.parametrize("change", [{"cause": None}, {"recorded_at": 99}])
def test_manager_decision_requires_valid_cause_and_ordered_time(tmp_path, change):
    _, _, dependent, source, evidence = proof(tmp_path)
    cause = dependency_review_cause(
        evidence.completion, evidence.reopenings[0], dependent, source, None
    )
    with pytest.raises(InvalidInput):
        DependencyReviewDecision(
            **(
                dict(cause=cause, recorded_by="manager", recorded_at=100, reason="Reviewed")
                | change
            )
        )


@pytest.mark.parametrize(
    "kind",
    [
        "missing_review",
        "extra_review_field",
        "missing_cause",
        "extra_cause_field",
        "relationships",
        "scope",
        "cycle",
    ],
)
def test_original_acknowledgement_scope_is_strict_before_receipt_disclosure(tmp_path, kind):
    _, _, _, _, evidence = proof(tmp_path, accept=True)
    original = evidence.acknowledgements[0]
    result = original.receipt.result.decode()
    if kind == "missing_review":
        result["review"] = None
    elif kind == "extra_review_field":
        result["review"]["extra"] = 1
    elif kind == "missing_cause":
        result["review"]["cause"] = None
    elif kind == "extra_cause_field":
        result["review"]["cause"]["extra"] = 1
    elif kind == "relationships":
        result["review"]["cause"]["relationships"] = "prerequisite"
    elif kind == "scope":
        result["review"]["cause"]["source_operation_id"] = "other-operation"
    else:
        result["cycle"] = None
    with pytest.raises(InvalidInput):
        recorded_review(coherent(original, result=result))


@pytest.mark.parametrize(
    "kind",
    [
        "missing_cycle_snapshot",
        "missing_source_cycle",
        "duplicate_cause",
        "duplicate_acknowledgement",
        "different_acknowledgement",
        "missing_source_work",
    ],
)
def test_review_projection_fails_closed_on_incoherent_live_facts(tmp_path, monkeypatch, kind):
    from domus.application.task_reviews import review_items
    from domus.infrastructure.sqlite_tasks import SQLiteTasks

    store, _, dependent, source, evidence = proof(tmp_path, accept=True)
    if kind == "missing_cycle_snapshot":
        original = evidence.reopenings[0]
        evidence = replace(
            evidence,
            reopenings=(
                coherent(original, result=original.receipt.result.decode() | {"cycle": None}),
            ),
        )
    elif kind == "missing_source_cycle":
        read = SQLiteTasks.cycle
        monkeypatch.setattr(
            SQLiteTasks,
            "cycle",
            lambda self, hh, cid: None if cid == source.cycle_id else read(self, hh, cid),
        )
    elif kind == "duplicate_cause":
        evidence = replace(evidence, reopenings=evidence.reopenings * 2)
    elif kind == "duplicate_acknowledgement":
        evidence = replace(evidence, acknowledgements=evidence.acknowledgements * 2)
    elif kind == "different_acknowledgement":
        original = evidence.acknowledgements[0]
        result = original.receipt.result.decode()
        result["review"]["cause"]["completion_position"] -= 1
        evidence = replace(evidence, acknowledgements=(coherent(original, result=result),))
    else:
        read = SQLiteTasks.occurrence
        monkeypatch.setattr(
            SQLiteTasks,
            "occurrence",
            lambda self, hh, oid: None if oid == source.occurrence_id else read(self, hh, oid),
        )
    with store.read() as unit:
        work = unit.tasks.occurrence("home", dependent.occurrence_id)
        with pytest.raises(StorageFailure):
            review_items(unit, work, dependent, evidence)


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_manager_acceptance_commits_one_decision(tmp_path, same_key):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    commands, store, actor, _, source, target, _, _, done = setup(tmp_path)
    opened = reopen(commands, store, source, "reopen")
    cid = done.result.decode()["cycle"]["cycle_id"]
    request = ReviewTaskDependency(target, 1, cid, opened.operation_id, "Still valid")
    barrier = Barrier(2)

    def accept(number):
        barrier.wait()
        try:
            return commands.review_dependency("accept" if same_key else f"accept-{number}", request)
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, (1, 2)))
    receipts = [value for value in results if not isinstance(value, Conflict)]
    assert len(receipts) == (2 if same_key else 1)
    assert len({value.operation_id for value in receipts}) == 1
    assert len(queries(store, actor.current()).dependency_reviews(target, cid).items) == 1
    with store.read() as unit:
        assert (
            sum(
                row.command.action == "task.dependency.review" for row in unit.audit.entries("home")
            )
            == 1
        )


@pytest.mark.parametrize("point", ["audit", "outbox"])
def test_failed_acceptance_rolls_back_receipt_audit_and_event_together(
    tmp_path, monkeypatch, point
):
    from domus.infrastructure.sqlite import SQLiteAudit, SQLiteOutbox

    commands, store, actor, _, source, target, _, _, done = setup(tmp_path)
    opened = reopen(commands, store, source, "reopen")
    cid = done.result.decode()["cycle"]["cycle_id"]
    service = queries(store, actor.current())
    before = service.occurrence(target)
    cls = SQLiteAudit if point == "audit" else SQLiteOutbox
    append = cls.append

    def fail(self, value):
        append(self, value)
        raise StorageFailure("fixture_failed")

    monkeypatch.setattr(cls, "append", fail)
    with pytest.raises(StorageFailure):
        commands.review_dependency(
            "accept", ReviewTaskDependency(target, 1, cid, opened.operation_id, "Still valid")
        )
    assert service.occurrence(target) == before
    with store.read() as unit:
        assert not any(
            row.command.action == "task.dependency.review" for row in unit.audit.entries("home")
        )


def test_manager_can_accept_original_closed_cycle_without_changing_current_work(tmp_path):
    commands, store, actor, _, source, target, _, _, done = setup(tmp_path)
    opened = reopen(commands, store, source, "reopen-source")
    reopen(commands, store, target, "reopen-target")
    service = queries(store, actor.current())
    original = service.occurrence(target)
    cid = done.result.decode()["cycle"]["cycle_id"]
    receipt = commands.review_dependency(
        "accept",
        ReviewTaskDependency(target, 1, cid, opened.operation_id, "Historical work remains valid"),
    )
    assert service.occurrence(target) == original
    item = service.dependency_reviews(target, cid).items[0]
    assert item.state.value == "reviewed" and not item.source_satisfies_gate
    assert service.operation(receipt.operation_id).receipt == receipt


def test_review_cursor_binds_original_cycle_filter_limit_and_query_kind(tmp_path):
    from domus.domain.task_reviews import DependencyReviewState

    commands, store, actor, _, source, target, member, _, done = setup(tmp_path)
    for number in range(3):
        reopen(commands, store, source, f"reopen-{number}")
        if number < 2:
            perform(commands, store, source, member, f"source-{number}")
    service = queries(store, actor.current())
    cid = done.result.decode()["cycle"]["cycle_id"]
    first = service.dependency_reviews(target, cid, limit=1)
    second = service.dependency_reviews(target, cid, limit=1, cursor=first.next_cursor)
    third = service.dependency_reviews(target, cid, limit=1, cursor=second.next_cursor)
    assert (
        third.next_cursor is None
        and len(
            {
                item.cause.source_operation_id
                for page in (first, second, third)
                for item in page.items
            }
        )
        == 3
    )
    for values in ({"limit": 2}, {"state": DependencyReviewState.PENDING}):
        with pytest.raises(InvalidInput):
            service.dependency_reviews(
                target, cid, cursor=first.next_cursor, **({"limit": 1} | values)
            )
    with pytest.raises(InvalidInput):
        service.history(target, limit=1, cursor=first.next_cursor)


@pytest.mark.parametrize(
    "body",
    [
        {"expected_revision": True},
        {"reason": "   "},
        {"reason": "x" * 1001},
        {"actor_id": "forged"},
        {"cycle_id": "bad/id"},
    ],
)
def test_both_review_routes_reject_invalid_acknowledgement_without_writes(api, body):
    _, cid, path, action = http_review(api)
    response = api.client.post(
        action,
        json={"expected_revision": 1, "cycle_id": cid, "reason": "Still valid"} | body,
        headers=api.headers("invalid"),
    )
    assert response.status_code == 422, response.text
    assert api.client.get(path, params={"cycle_id": cid}).json()["items"][0]["state"] == "pending"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?cycle_id=bad/id",
        "?cycle_id=cycle&state=automatic",
        "?cycle_id=cycle&limit=01",
        "?cycle_id=cycle&actor_id=forged",
        "?cycle_id=cycle&cycle_id=other",
    ],
)
def test_review_query_rejects_invalid_unknown_and_duplicate_values(api, query):
    response = api.client.get("/api/v1/tasks/occurrences/work/dependency-reviews" + query)
    assert response.status_code == 422, response.text
