"""Qualify the scoped complete open-task projection for Home Assistant."""

import json
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_ha_app_launcher import launch as launch
from test_ha_calendar_installation import (
    ORIGIN,
    PUBLIC,
    SUPERVISOR,
    WINDOW,
    bearer,
    digest,
    header,
    runtime,
)
from test_ha_deadline_installation import PRIVATE, deadline_bearer
from test_ha_shopping_installation import shopping_bearer, stored_facts
from test_ha_stock_installation import stock_bearer
from test_task_commands import fixture, resource
from test_task_execution_commands import work_at

from domus.application.task_commands import (
    AssignTask,
    CompleteTask,
    CreateTask,
    CreateTaskOccurrence,
    ReopenTask,
    TransitionTask,
    UpdateTaskDefinition,
)
from domus.application.task_queries import HA_TASK_ITEM_LIMIT
from domus.composition import ha_app, ingress, server
from domus.domain.errors import InvalidInput
from domus.domain.storage import Installation
from domus.domain.task_values import DefinitionState, OccurrenceState, TaskContent
from domus.entrypoints.ha_calendar_http import CALENDAR_PATH
from domus.entrypoints.ha_deadline_http import DEADLINE_PATH
from domus.entrypoints.ha_shopping_http import SHOPPING_PATH
from domus.entrypoints.ha_stock_http import STOCK_PATH
from domus.entrypoints.ha_tasks_http import TASKS_DIGEST_ENV, TASKS_PATH
from domus.infrastructure.sqlite_tasks import SQLiteTasks


def tasks_bearer(installation, seed="a"):
    return f"{installation.instance_id}.{installation.channel}.tasks.{seed * 64}"


@pytest.mark.parametrize("native", [False, True], ids=["standalone", "ingress"])
def test_complete_open_selection_keeps_occurrence_identity_and_does_not_write(tmp_path, native):
    commands, store, _, _ = fixture(tmp_path)
    installation = store.installation
    token = tasks_bearer(installation)
    service = runtime(native, installation, store.path, None, tasks_fingerprint=digest(token))
    client = TestClient(service.app, base_url=PRIVATE if native else PUBLIC)
    try:
        assert client.get(TASKS_PATH, headers=header(token)).json() == {"items": []}
        occurrences = {}
        for state in OccurrenceState:
            definition_state = (
                DefinitionState.DRAFT if state is OccurrenceState.DRAFT else DefinitionState.ACTIVE
            )
            receipt = commands.create(
                f"create-{state}", CreateTask(TaskContent("Shared title"), state=definition_state)
            )
            definition_id, occurrence_id = resource(receipt)
            occurrences[state] = occurrence_id
            if state is OccurrenceState.COMPLETED:
                with store.read() as unit:
                    admin = unit.members.by_user("home", "ha_admin").member_id
                commands.complete("complete", CompleteTask(occurrence_id, 1, (admin,), 90))
            elif state in (OccurrenceState.ASSIGNED, OccurrenceState.IN_PROGRESS):
                commands.assign(f"assign-{state}", AssignTask(occurrence_id, 1, ("child",)))
                if state is OccurrenceState.IN_PROGRESS:
                    commands.transition(
                        "start", TransitionTask(occurrence_id, 2, state, "Fixture transition")
                    )
            elif state in (
                OccurrenceState.BLOCKED,
                OccurrenceState.CANCELLED,
                OccurrenceState.SKIPPED,
            ):
                commands.transition(
                    f"transition-{state}",
                    TransitionTask(occurrence_id, 1, state, "Fixture transition"),
                )
        # Separate occurrences of the same definition keep their own identity.
        extra = commands.create_occurrence("same-definition", CreateTaskOccurrence(definition_id))
        before = stored_facts(store)
        response = client.get(TASKS_PATH, headers=header(token))
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        rows = response.json()["items"]
        assert client.get(TASKS_PATH, headers=header(token)).json()["items"] == rows
        assert stored_facts(store) == before
        with store.read() as unit:
            authoritative = unit.tasks.occurrences("home", open_only=True)
        assert [(row["title"], row["state"]) for row in rows] == [
            (work.definition_snapshot.content.title, work.state.value) for work in authoritative
        ]
        assert len(rows) == 6 and len({row["uid"] for row in rows}) == 6
        assert all(set(row) == {"uid", "title", "state"} for row in rows)
        assert all(re.fullmatch("[0-9a-f]{64}", row["uid"]) for row in rows)
        assert {row["state"] for row in rows} == {
            "draft",
            "available",
            "assigned",
            "in_progress",
            "blocked",
        }
        assert all(oid not in response.text for oid in occurrences.values())
        assert "ha_admin" not in response.text and "child" not in response.text
        by_occurrence = dict(zip((work.occurrence_id for work in authoritative), rows, strict=True))
        available = occurrences[OccurrenceState.AVAILABLE]
        commands.assign("change-state", AssignTask(available, 1, ("child",)))
        changed = client.get(TASKS_PATH, headers=header(token)).json()["items"]
        assert [row["uid"] for row in changed] == [row["uid"] for row in rows]
        assert (
            next(row for row in changed if row["uid"] == by_occurrence[available]["uid"])["state"]
            == "assigned"
        )
        completed = occurrences[OccurrenceState.COMPLETED]
        work, cycle = work_at(store, completed)
        commands.reopen("reopen", ReopenTask(completed, work.revision, cycle.cycle_id, "Again"))
        reopened = client.get(TASKS_PATH, headers=header(token)).json()["items"]
        previous_uids = {row["uid"] for row in rows}
        restored = next(row for row in reopened if row["uid"] not in previous_uids)
        assert len(reopened) == 7
        with store.read() as unit:
            admin = unit.members.by_user("home", "ha_admin").member_id
        work, _ = work_at(store, completed)
        commands.complete("complete-again", CompleteTask(completed, work.revision, (admin,), 90))
        assert len(client.get(TASKS_PATH, headers=header(token)).json()["items"]) == 6
        work, cycle = work_at(store, completed)
        commands.reopen(
            "reopen-again", ReopenTask(completed, work.revision, cycle.cycle_id, "Again")
        )
        assert restored in client.get(TASKS_PATH, headers=header(token)).json()["items"]
        # A definition edit preserves existing occurrence snapshots and their identities.
        commands.update_definition(
            "rename-definition",
            UpdateTaskDefinition(
                definition_id, 1, TaskContent("New title"), DefinitionState.ACTIVE
            ),
        )
        assert resource(extra)[1] in {work.occurrence_id for work in authoritative}
        assert client.get(TASKS_PATH, headers=header(token)).json()["items"] == reopened
    finally:
        service.close()


def test_capacity_pages_use_one_read_snapshot_and_fail_without_partial_results(
    tmp_path, monkeypatch
):
    commands, store, _, _ = fixture(tmp_path)
    definition_id, _ = resource(commands.create("base", CreateTask(TaskContent("Fixture"))))
    with store.read() as unit:
        definition = unit.tasks.definition("home", definition_id)
    with store.write() as unit:
        for index in range(HA_TASK_ITEM_LIMIT - 1):
            unit.tasks.save_occurrence(definition.new_occurrence(f"fixture-{index:04}", 100), 0)
    calls, connections = [], []
    original = SQLiteTasks.occurrences

    def observed(repository, household_id, **options):
        calls.append(options)
        connections.append(repository.connection)
        return original(repository, household_id, **options)

    monkeypatch.setattr(SQLiteTasks, "occurrences", observed)
    token = tasks_bearer(store.installation)
    service = runtime(True, store.installation, store.path, None, tasks_fingerprint=digest(token))
    try:
        client = TestClient(service.app, base_url=PRIVATE)
        response = client.get(TASKS_PATH, headers=header(token))
        rows = response.json()["items"]
        assert response.status_code == 200 and len(rows) == HA_TASK_ITEM_LIMIT == 1000
        assert len({row["uid"] for row in rows}) == 1000
        assert len(calls) == 11 and all(call["limit"] == 101 for call in calls)
        assert all(call["open_only"] is True for call in calls)
        assert calls[0]["after"] is None and all(call["after"] for call in calls[1:])
        assert len({id(connection) for connection in connections}) == 1
        with store.write() as unit:
            unit.tasks.save_occurrence(definition.new_occurrence("fixture-overflow", 100), 0)
        before = stored_facts(store)
        response = client.get(TASKS_PATH, headers=header(token))
        assert response.status_code == 503
        assert response.json() == {"error": "task_list_unavailable"}
        assert stored_facts(store) == before
    finally:
        service.close()


@pytest.mark.parametrize("native", [False, True], ids=["standalone", "ingress"])
def test_tasks_grant_is_independent_disabled_by_default_and_revocable(tmp_path, native):
    _, store, _, _ = fixture(tmp_path)
    installation = store.installation
    calendar, deadline, stock, shopping = (
        bearer(installation),
        deadline_bearer(installation),
        stock_bearer(installation),
        shopping_bearer(installation),
    )
    token, rotated = tasks_bearer(installation), tasks_bearer(installation, "b")
    for fingerprint in (None, digest(token), digest(rotated)):
        service = runtime(
            native,
            installation,
            store.path,
            digest(calendar),
            deadline_fingerprint=digest(deadline),
            stock_fingerprint=digest(stock),
            shopping_fingerprint=digest(shopping),
            tasks_fingerprint=fingerprint,
        )
        client = TestClient(service.app, base_url=PRIVATE if native else PUBLIC)
        try:
            assert client.get(CALENDAR_PATH, params=WINDOW, headers=header(calendar)).is_success
            for path, other in (
                (DEADLINE_PATH, deadline),
                (STOCK_PATH, stock),
                (SHOPPING_PATH, shopping),
            ):
                assert client.get(path, headers=header(other)).is_success
                assert client.get(path, headers=header(token)).status_code == 401
            assert (
                client.get(CALENDAR_PATH, params=WINDOW, headers=header(token)).status_code == 401
            )
            response = client.get(TASKS_PATH, headers=header(token))
            if fingerprint is None:
                assert response.status_code == 404
                continue
            if fingerprint == digest(rotated):
                assert response.status_code == 401
                assert client.get(TASKS_PATH, headers=header(rotated)).json() == {"items": []}
                continue
            assert response.status_code == 200 and response.json() == {"items": []}
            for wrong in (
                rotated,
                calendar,
                deadline,
                stock,
                shopping,
                token.replace(installation.instance_id, str(uuid4())),
                token.replace(".edge.", ".stable."),
            ):
                denied = client.get(TASKS_PATH, headers=header(wrong))
                assert denied.status_code == 401
                assert denied.json() == {"error": "invalid_tasks_credential"}
            assert client.get(TASKS_PATH).status_code == 401
            assert client.post(TASKS_PATH, headers=header(token)).status_code == 405
            assert (
                client.get(
                    TASKS_PATH, params={"household": "other"}, headers=header(token)
                ).status_code
                == 422
            )
            headers = {**header(token), **{f"x-extra-{index}": "x" for index in range(33)}}
            assert client.get(TASKS_PATH, headers=headers).status_code == 422
            forbidden = (
                TestClient(service.app, base_url="http://native:8099")
                if native
                else TestClient(
                    service.app, base_url="http://domus.example", client=("192.0.2.1", 80)
                )
            )
            assert not forbidden.get(TASKS_PATH, headers=header(token)).is_success
            before = stored_facts(store)
            business = TestClient(service.app, base_url=ORIGIN if native else PUBLIC)
            assert business.post(
                "/api/v1/tasks/definitions",
                headers={**header(token), "Origin": ORIGIN if native else PUBLIC},
                json={},
            ).status_code in (
                401,
                403,
            )
            assert stored_facts(store) == before
        finally:
            service.close()


def test_tasks_require_persistent_secure_origin_valid_digest_and_existing_household(tmp_path):
    installation = Installation(str(uuid4()), "edge")
    with pytest.raises(InvalidInput, match="ha_tasks_requires_persistent_secure_origin"):
        server.create_runtime(
            "https://ha.example", PUBLIC, installation.instance_id, "edge", ha_tasks_digest="a" * 64
        )
    with pytest.raises(InvalidInput, match="invalid_ha_tasks_digest"):
        runtime(
            False, installation, tmp_path / "invalid.sqlite3", None, tasks_fingerprint="invalid"
        )
    token = tasks_bearer(installation)
    service = runtime(
        False, installation, tmp_path / "empty.sqlite3", None, tasks_fingerprint=digest(token)
    )
    try:
        response = TestClient(service.app, base_url=PUBLIC).get(TASKS_PATH, headers=header(token))
        assert response.status_code == 503 and response.json() == {"error": "task_list_unavailable"}
    finally:
        service.close()


def test_launcher_accepts_tasks_only_and_keeps_digest_out_of_arguments(launch, capsys):
    root, calls = launch
    options = root / "options.json"
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_tasks_digest": 42}))
    assert ha_app.main(["--channel", "edge"]) == 2 and not calls
    assert "42" not in capsys.readouterr().err
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_tasks_digest": "c" * 64}))
    assert ha_app.main(["--channel", "edge"]) == 0
    _, arguments, environment = calls[1]
    assert "c" * 64 not in arguments and environment["DOMUS_HA_TASKS_DIGEST"] == "c" * 64


def test_tasks_only_activates_private_listener_and_removes_secret_from_environment(
    monkeypatch, tmp_path
):
    _, store, _, _ = fixture(tmp_path)
    token = tasks_bearer(store.installation)
    monkeypatch.setenv("SUPERVISOR_TOKEN", SUPERVISOR)
    monkeypatch.setenv(TASKS_DIGEST_ENV, digest(token))

    def serve(app):
        response = TestClient(app, base_url=PRIVATE).get(TASKS_PATH, headers=header(token))
        assert response.json() == {"items": []}

    monkeypatch.setattr(ingress, "_serve_ha_projections", serve)
    assert (
        ingress.main(
            [
                "--channel",
                "edge",
                "--database",
                str(store.path),
                "--instance-id",
                store.installation.instance_id,
                "--public-origin",
                ORIGIN,
            ]
        )
        == 0
    )
    assert TASKS_DIGEST_ENV not in ingress.os.environ
