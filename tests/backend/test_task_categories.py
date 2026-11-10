"""Real task category migration, scope, original receipts and calendar predicates."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest
from test_recurrence_creation import request, setup
from test_recurrence_http import CONTEXT, USER
from test_task_runtime import api as api

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.relative_materialization import RelativeMaintenance
from domus.application.relative_recurrence_commands import (
    CreateRelativeTask,
    RelativeRecurrenceCommands,
)
from domus.application.task_category_commands import TaskCategoryCommands
from domus.application.task_requests import CreateTask
from domus.domain.errors import DatabaseRejected, StorageFailure
from domus.domain.identity import Member, MemberStatus, Role
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import RelativeInterval
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent
from domus.infrastructure import sqlite as storage
from domus.infrastructure.sqlite import SQLiteDatabase

TASKS = "/api/v1/tasks"
CATEGORIES = TASKS + "/categories"
CALENDAR = TASKS + "/calendar"


def test_schema14_category_ddl_rolls_back_to_the_exact_original_bytes(tmp_path, monkeypatch):
    path = tmp_path / "before.sqlite3"
    fixture = Path(__file__).parents[1] / "fixtures/sqlite/v14.sql"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript(fixture.read_text())
        identity = Installation(
            *connection.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
    database = SQLiteDatabase(path, identity)
    source = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(storage, "CATEGORY_STATEMENTS", (*storage.CATEGORY_STATEMENTS, "invalid SQL"))
        with pytest.raises(StorageFailure):
            database.initialize(require_existing=True)
    assert path.read_bytes() == source
    with pytest.raises(DatabaseRejected, match="unsupported_schema"), database.read():
        pytest.fail("Explicit migration must precede a normal read")
    database.initialize(require_existing=True)
    with database.read() as unit:
        assert unit.task_categories.active("home") == ()
        definition = unit.tasks.definition("home", "identity-8")
        assert definition.content.tags == ("Garden",)
        assert definition.content.category_id is None and definition.category_label is None
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (23,)


def test_protected_category_commands_preserve_exact_history_and_calendar_counts(api):
    api.user(USER, True)
    assert api.client.get(CATEGORIES).status_code == 422
    assert api.client.get(CATEGORIES, headers=CONTEXT).json() == {
        "can_manage": True,
        "categories": [],
    }
    headers = api.headers("create-category") | CONTEXT
    for label in (" ", "line\n", "🧹" * 81):
        assert (
            api.client.post(CATEGORIES, headers=headers, json={"label": label}).status_code == 422
        )
    body = {"label": "  Cafe\u0301 <b>  "}
    response = api.client.post(CATEGORIES, headers=headers, json=body)
    assert response.status_code == 200, response.text
    original = response.json()
    category = original["result"]
    category_id = category["category_id"]
    assert category["label"] == "Café <b>" and category["revision"] == 1
    assert api.client.post(CATEGORIES, headers=headers, json=body).json() == original
    assert (
        api.client.post(
            CATEGORIES, headers=api.headers("duplicate") | CONTEXT, json={"label": "CAFÉ <B>"}
        ).status_code
        == 409
    )
    original_path = CATEGORIES + "/requests/task.category.create/create-category"
    assert api.client.get(original_path, headers=CONTEXT).json() == original | {
        "action": "task.category.create",
        "command_key": "create-category",
    }
    for unavailable in ("foreign", "Garden"):
        invalid = api.client.post(
            TASKS + "/definitions",
            headers=api.headers("foreign-category"),
            json={"title": "Retain this draft", "category_id": unavailable},
        )
        assert invalid.status_code == 422 and invalid.json()["code"] == "task_category_unavailable"
    created = api.client.post(
        TASKS + "/definitions",
        headers=api.headers("classify"),
        json={
            "title": "Filter care",
            "category_id": category_id,
            "tags": ["Garden"],
            "priority": "high",
        },
    )
    assert created.status_code == 200, created.text
    definition_id = created.json()["result"]["definition_id"]
    definition = TASKS + f"/definitions/{definition_id}"
    member = api.client.get("/api/v1/authorization").json()["member"]["member_id"]
    for index in (1, 2):
        due = api.client.post(
            definition + "/occurrences",
            headers=api.headers(f"due-{index}"),
            json={"due_at": index, "assignee_ids": [member]},
        )
        assert due.status_code == 200, due.text
    params = {
        "start": "1970-01-01",
        "end": "1970-01-02",
        "category": category_id,
        "limit": 1,
        "timing": "manual",
        "state": "assigned",
        "priority": "high",
        "member_id": member,
    }
    read = api.client.get(CALENDAR, params=params, headers=CONTEXT)
    assert read.status_code == 200, read.text
    first = read.json()
    assert first["count"] == first["occurrence_count"] == 2 and first["next_cursor"]
    assert first["entries"][0]["category_id"] == category_id
    assert first["entries"][0]["categories"] == ["Garden"]
    assert first["entries"][0]["category_label"] == "Café <b>"
    second = api.client.get(
        CALENDAR, params=params | {"cursor": first["next_cursor"]}, headers=CONTEXT
    ).json()
    assert second["count"] == second["occurrence_count"] == 2 and second["next_cursor"] is None
    assert first["entries"][0]["entry_id"] != second["entries"][0]["entry_id"]
    unclassified = api.client.post(
        TASKS + "/definitions",
        headers=api.headers("tag-only"),
        json={"title": "Tag-only work", "tags": ["Garden"]},
    )
    assert unclassified.status_code == 200, unclassified.text
    unclassified_id = unclassified.json()["result"]["definition_id"]
    unclassified_due = api.client.post(
        TASKS + f"/definitions/{unclassified_id}/occurrences",
        headers=api.headers("tag-only-due"),
        json={"due_at": 3},
    )
    assert unclassified_due.status_code == 200, unclassified_due.text
    all_entries = api.client.get(
        CALENDAR, params={"start": params["start"], "end": params["end"]}, headers=CONTEXT
    )
    assert all_entries.status_code == 200, all_entries.text
    (tag_only,) = [row for row in all_entries.json()["entries"] if row["title"] == "Tag-only work"]
    assert tag_only["categories"] == ["Garden"]
    assert tag_only["category_id"] is tag_only["category_label"] is None
    filtered = api.client.get(CALENDAR, params=params, headers=CONTEXT).json()
    assert filtered["count"] == filtered["occurrence_count"] == 2
    assert (
        api.client.get(
            CALENDAR, params=params | {"category": "Garden"}, headers=CONTEXT
        ).status_code
        == 422
    )

    path = CATEGORIES + "/" + category_id
    rename = api.headers("rename") | CONTEXT
    assert (
        api.client.put(
            path, json={"expected_revision": 2, "label": "Kitchen"}, headers=rename
        ).status_code
        == 409
    )
    renamed = api.client.put(
        path, json={"expected_revision": 1, "label": "Kitchen"}, headers=rename
    )
    assert renamed.status_code == 200, renamed.text
    assert api.client.get(definition).json()["category_label"] == "Café <b>"
    edited = api.client.put(
        definition,
        headers=api.headers("legacy-edit"),
        json={"expected_revision": 1, "title": "Changed title", "state": "active"},
    )
    assert edited.status_code == 200, edited.text
    assert api.client.get(definition).json()["content"]["category_id"] == category_id
    edited_with_category = api.client.put(
        definition,
        headers=api.headers("edit-with-current-category"),
        json={
            "expected_revision": 2,
            "title": "Edited with the same category",
            "state": "active",
            "category_id": category_id,
        },
    )
    assert edited_with_category.status_code == 200, edited_with_category.text
    edited_definition = api.client.get(definition).json()
    assert edited_definition["content"]["category_id"] == category_id
    assert edited_definition["category_label"] == "Café <b>"

    archive = api.headers("archive") | CONTEXT
    archived = api.client.post(path + "/archive", json={"expected_revision": 2}, headers=archive)
    assert archived.status_code == 200, archived.text
    assert (
        api.client.post(path + "/archive", json={"expected_revision": 2}, headers=archive).json()
        == archived.json()
    )
    assert (
        api.client.get(CALENDAR, params=params, headers=CONTEXT).json()["code"]
        == "task_category_unavailable"
    )
    assert (
        api.client.post(
            TASKS + "/definitions",
            headers=api.headers("archived-category"),
            json={"title": "New task", "category_id": category_id},
        ).json()["code"]
        == "task_category_unavailable"
    )
    archived_edit = api.client.put(
        definition,
        headers=api.headers("edit-with-archived-category"),
        json={
            "expected_revision": 3,
            "title": "Explicitly selecting an archived category",
            "state": "active",
            "category_id": category_id,
        },
    )
    assert archived_edit.status_code == 422
    assert archived_edit.json()["code"] == "task_category_unavailable"
    cleared = api.client.put(
        definition,
        headers=api.headers("unclassify"),
        json={
            "expected_revision": 3,
            "title": "Changed title",
            "state": "active",
            "category_id": None,
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert api.client.get(definition).json()["content"]["category_id"] is None
    reused = api.client.post(
        CATEGORIES, headers=api.headers("reuse-label") | CONTEXT, json={"label": "Kitchen"}
    )
    assert reused.status_code == 200, reused.text
    reused_id = reused.json()["result"]["category_id"]
    assert reused_id != category_id
    selected = api.client.put(
        definition,
        headers=api.headers("reclassify"),
        json={
            "expected_revision": 4,
            "title": "Changed title",
            "state": "active",
            "category_id": reused_id,
        },
    )
    assert selected.status_code == 200, selected.text
    assert api.client.get(definition).json()["category_label"] == "Kitchen"
    assert (
        api.client.post(
            CATEGORIES + "/" + reused_id + "/archive",
            headers=api.headers("archive-reused") | CONTEXT,
            json={"expected_revision": 1},
        ).status_code
        == 200
    )
    with api.store.write() as unit:
        unit.members.save(
            Member("reader", "home", "b" * 32, Role.RESTRICTED, MemberStatus.ACTIVE, 1), 0
        )
    api.user("b" * 32)
    reader = {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, "b" * 32)}
    assert api.client.get(CATEGORIES, headers=reader).json() == {
        "can_manage": False,
        "categories": [],
    }
    assert (
        api.client.post(
            CATEGORIES, headers=api.headers("unauthorized") | reader, json={"label": "Forbidden"}
        ).status_code
        == 403
    )
    assert api.client.get(original_path, headers=reader).status_code == 403


@pytest.mark.parametrize("timing", ["fixed", "relative"])
def test_scheduled_task_snapshots_share_the_category_without_rewriting_original_receipts(
    tmp_path, timing
):
    fixed, _, store, actor, ids = setup(tmp_path)
    commands = TaskCategoryCommands(store, actor, actor.current, fixed.clock, ids)
    category = commands.create("category", "Kitchen").result.decode()
    category_id = category["category_id"]
    seed = request()
    task = CreateTask(TaskContent("Recurring care", category_id=category_id))
    scope = MaintenanceScope(store.installation, "home")
    if timing == "fixed":
        value = replace(seed, task=task)
        created = fixed.create_fixed("classified", value)
        runner = FixedMaintenance(store, scope, fixed.planner, fixed.clock, ids)
        materialized = runner.step(
            created.result.decode()["schedule_id"],
            NominalDate(seed.pattern.start.local.replace(day=31)),
        )
        replay = partial(fixed.create_fixed, "classified", value)
    else:
        relative = RelativeRecurrenceCommands(store, actor, fixed.clock, ids, fixed.planner.times)
        value = CreateRelativeTask(task, seed.pattern.start, RelativeInterval(30), seed.policy)
        created = relative.create("classified", value)
        runner = RelativeMaintenance(store, scope, fixed.planner.times, fixed.clock, ids)
        materialized = runner.initial(created.result.decode()["schedule_id"])
        replay = partial(relative.create, "classified", value)
    commands.rename("rename", category_id, 1, "Pantry")
    commands.archive("archive", category_id, 2)
    assert replay() == created
    with store.read() as unit:
        work = unit.tasks.occurrence("home", materialized.occurrence_id)
        assert work.definition_snapshot.category_label == "Kitchen"
        assert work.definition_snapshot.content.category_id == category_id


def test_category_capacity_duplicates_and_stale_persistence_are_atomic(tmp_path):
    from domus.domain.errors import Conflict, NotFound
    from domus.domain.task_categories import MAX_ACTIVE_TASK_CATEGORIES, TaskCategory

    creator, _, database, actor, identifiers = setup(tmp_path)
    catalog = TaskCategoryCommands(database, actor, actor.current, creator.clock, identifiers)
    with pytest.raises(NotFound, match="operation_missing"):
        catalog.original("task.category.rename", "unknown")
    created = catalog.create("known", "First").result.decode()["category_id"]
    with pytest.raises(Conflict, match="task_category_unchanged"):
        catalog.rename("unchanged", created, 1, " First ")
    with database.write() as unit:
        assert unit.task_categories.get("another-home", created) is None
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.task_categories.save(TaskCategory("stale", "home", "Stale", 4), 1)
        with pytest.raises(Conflict, match="revision_conflict"):
            unit.task_categories.save(TaskCategory("missing", "home", "Missing", 2), 1)
        for index in range(MAX_ACTIVE_TASK_CATEGORIES - 1):
            unit.task_categories.save(
                TaskCategory(f"category-{index}", "home", f"Label {index}"), 0
            )
    original = database.path.read_bytes()
    with pytest.raises(Conflict, match="task_category_capacity"):
        catalog.create("capacity", "Over the bound")
    assert database.path.read_bytes() == original
    assert catalog.create("known", "First").result.decode()["category_id"] == created
    with database.write() as unit:
        unit.task_categories.save(TaskCategory("corrupt-count", "home", "Over the bound"), 0)
    with pytest.raises(StorageFailure, match="invalid_task_category_record"):
        catalog.catalog()


@pytest.mark.parametrize(
    "field,value", [("label_key", "wrong"), ("archived", 2), ("label", "  bad  ")]
)
def test_invalid_category_records_fail_closed_without_repair(tmp_path, field, value):
    creator, _, database, actor, identifiers = setup(tmp_path)
    catalog = TaskCategoryCommands(database, actor, actor.current, creator.clock, identifiers)
    category = catalog.create("create", "Garden").result.decode()["category_id"]
    with database._connection() as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            f"UPDATE task_categories SET {field}=? WHERE category_id=?", (value, category)
        )
    original = database.path.read_bytes()
    with (
        database.read() as unit,
        pytest.raises(StorageFailure, match="invalid_task_category_record"),
    ):
        unit.task_categories.get("home", category)
    assert database.path.read_bytes() == original


def test_classified_definition_documents_and_missing_snapshot_references_are_rejected(tmp_path):
    from dataclasses import replace

    from domus.domain.errors import InvalidInput
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    creator, tasks, database, actor, identifiers = setup(tmp_path)
    catalog = TaskCategoryCommands(database, actor, actor.current, creator.clock, identifiers)
    category = catalog.create("create", "Garden").result.decode()["category_id"]
    definition = tasks.create(
        "task", CreateTask(TaskContent("Classified", category_id=category))
    ).result.decode()["definition_id"]
    with database.read() as unit:
        item = unit.tasks.definition("home", definition)
        with pytest.raises(InvalidInput, match="invalid_task_category"):
            replace(item, category_label=None)
    with database._connection() as connection:
        original = connection.execute(
            "SELECT document FROM task_definitions WHERE definition_id=?", (definition,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE task_definitions SET document=json_set(document, '$.content.category_id', null)"
            " WHERE definition_id=?",
            (definition,),
        )
    with database.read() as unit, pytest.raises(StorageFailure, match="invalid_task_record"):
        unit.tasks.definition("home", definition)
    with database._connection() as connection:
        connection.execute(
            "UPDATE task_definitions SET document=? WHERE definition_id=?", (original, definition)
        )
        connection.execute("DELETE FROM task_categories WHERE category_id=?", (category,))
    broken = database.path.read_bytes()
    snapshots = SQLiteSnapshots(
        database, tmp_path / "checkpoint", database.installation, creator.clock
    )
    with pytest.raises((DatabaseRejected, StorageFailure)):
        snapshots.create("broken-category")
    assert database.path.read_bytes() == broken


def test_category_restore_keeps_checkpoint_state_and_recovers_later_archive_by_original_key(
    tmp_path,
):
    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    source, archive, target = (tmp_path / part for part in ("source", "checkpoint", "prepared"))
    source.mkdir(mode=0o700)
    creator, tasks, database, actor, identifiers = setup(source)
    identity_at(source, database.installation)
    catalog = TaskCategoryCommands(database, actor, actor.current, creator.clock, identifiers)
    category = catalog.create("category", "Before archive").result.decode()["category_id"]
    saved = tasks.create("task", CreateTask(TaskContent("Classified", category_id=category)))
    checkpoint = SQLiteSnapshots(database, archive, database.installation, Clock()).create(
        "category-state"
    )
    later = catalog.archive("archive", category, 1)
    checkpoint_bytes = (archive / "domus.sqlite3").read_bytes()
    adapter = SQLiteRestorations(
        database, archive, target, database.installation, Clock(), checkpoint
    )
    adapter.prepare("restore-category")
    SQLiteActivation(source, database.installation, Clock(), target).activate()
    with closing(open_storage(source, "edge")) as restored:
        replacement = replace(catalog, transactions=restored.database)
        historical = replacement.original("task.category.archive", "archive")
        assert historical.historical and historical.operation_id == later.operation_id
        assert replacement.archive("archive", category, 1) == historical
        with restored.database.read() as unit:
            current = unit.task_categories.get("home", category)
            assert current.revision == 1 and not current.archived
            work = unit.tasks.occurrence("home", saved.result.decode()["occurrence_id"])
            assert work.definition_snapshot.category_label == "Before archive"
    assert (archive / "domus.sqlite3").read_bytes() == checkpoint_bytes


@pytest.mark.parametrize("kind", ["fixed", "relative"])
def test_protected_scheduled_creation_assigns_active_category_and_recovers_original(api, kind):
    api.user(USER, True)
    category = api.client.post(
        CATEGORIES, json={"label": "Recurring care"}, headers=api.headers("category") | CONTEXT
    ).json()["result"]["category_id"]
    payload = {
        "task": {"title": "Scheduled work", "category_id": category},
        "start": {"kind": "date", "local": "2027-01-02"},
        "policy": api.client.get(TASKS + "/access").json()["schedule_policy"],
    } | ({"rrule": "FREQ=DAILY;COUNT=2"} if kind == "fixed" else {"interval_days": 14})
    route = TASKS + "/recurrence/creation/" + kind
    headers = api.headers("original-schedule") | CONTEXT
    failure = api.client.post(
        route,
        json=payload | {"task": {"title": "Foreign", "category_id": "unknown"}},
        headers=headers,
    )
    assert failure.status_code == 422 and failure.json()["code"] == "task_category_unavailable"
    created = api.client.post(route, json=payload, headers=headers)
    assert created.status_code == 200, created.text
    result = created.json()["result"]
    assert result["first_occurrence_id"] is None
    archived = api.client.post(
        CATEGORIES + f"/{category}/archive",
        json={"expected_revision": 1},
        headers=api.headers("archive") | CONTEXT,
    )
    assert archived.status_code == 200, archived.text
    saved = api.client.get(TASKS + "/definitions/" + result["definition_id"]).json()
    assert (
        saved["category_label"] == "Recurring care" and saved["content"]["category_id"] == category
    )
    assert api.client.post(route, json=payload, headers=headers).json() == created.json()
    original = api.client.get(
        TASKS + f"/recurrence/creation/requests/recurrence.{kind}.create/original-schedule",
        headers=CONTEXT,
    )
    assert original.json()["operation_id"] == created.json()["operation_id"]
    assert api.client.get(TASKS + "/occurrences").json()["items"] == []


def test_category_label_contract_distinguishes_raw_input_and_normalized_length(api):
    schemas = api.client.get("/api/v1/openapi.json").json()["components"]["schemas"]
    for name in ("CreateCategoryBody", "RenameCategoryBody"):
        label = schemas[name]["properties"]["label"]
        assert label["maxLength"] == 256
        assert label["x-domus-normalized-max-length"] == 80
        assert "1 to 80 Unicode code points" in label["description"]

    api.user(USER, True)
    raw = "  " + "e\u0301" * 80 + "  "
    assert len(raw) == 164
    headers = api.headers("raw-label") | CONTEXT
    created = api.client.post(CATEGORIES, json={"label": raw}, headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["result"]["label"] == "é" * 80
    assert (
        api.client.post(CATEGORIES, json={"label": raw}, headers=headers).json() == created.json()
    )
    rejected = api.client.post(
        CATEGORIES, json={"label": raw + "é"}, headers=api.headers("over-bound") | CONTEXT
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "invalid_task_category_label"
