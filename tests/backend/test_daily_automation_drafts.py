"""Inactive daily definitions use the existing revision and recovery boundaries."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from test_activation_compatibility import identity_at
from test_automation_draft_storage import service as draft_service
from test_automation_drafts import DRAFTS, effects, read, save
from test_automation_execution import configure, denied, initial_draft, result, run
from test_automation_execution_storage import execution_service
from test_automation_preview import ACTION, CONTEXT, RULE, USER, leaf
from test_inventory_catalog_http import register
from test_sqlite_snapshots import Clock
from test_task_runtime import api as api

from domus.application.automation_drafts import SAVE_DRAFT, SaveDraft
from domus.application.automation_execution import ConfigureAutomation
from domus.domain.automation import AutomationControl, AutomationRule, DailyTrigger, simulate
from domus.domain.errors import DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.identity import MemberStatus
from domus.domain.storage import Installation, JsonDocument
from domus.domain.task_values import TaskContent
from domus.infrastructure import sqlite as storage
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_receipts import SQLiteReceipts
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots, _verify_database

DAILY = {"version": 2, "trigger": {"kind": "daily", "time": "07:30"}}


def test_daily_definition_is_closed_and_cannot_be_manually_simulated():
    rule = AutomationRule(2, DailyTrigger("07:30"), None, TaskContent("Inspect supplies"))
    wire = rule.document()
    assert wire.decode() == {
        **DAILY,
        "condition": None,
        "action": {
            "kind": "task.create",
            "title": "Inspect supplies",
        },
    }
    assert AutomationRule.from_document(wire).document() == wire
    with pytest.raises(InvalidInput, match="automation_requires_manual_trigger"):
        simulate(rule, lambda _product: True)
    for patch in (
        {"version": 1},
        {"trigger": {"kind": "daily", "time": "7:30"}},
        {"trigger": {"kind": "daily", "time": "24:00"}},
        {"trigger": {"kind": "daily", "time": "07:30\n"}},
        {"trigger": {"kind": "daily", "time": 730}},
        {"trigger": {"kind": "daily", "time": "07:30", "zone": "UTC"}},
        {"trigger": {"kind": "manual"}},
    ):
        with pytest.raises(InvalidInput):
            AutomationRule.from_document(JsonDocument.from_value(wire.decode() | patch))


def test_daily_protected_write_round_trips_and_recovers_the_original(api):
    api.user(USER, True)
    product = register(api, "tea", "Tea", "piece")
    before = effects(api)
    definition = DAILY | {"action": ACTION | {"title": "Check the tea"}, "condition": leaf(product)}
    committed = save(api, "daily-original", **definition)
    rule_id = result(committed)["rule_id"]
    original = read(api, DRAFTS + "/requests/daily-original")
    assert original.json() == committed.json()
    assert save(api, "daily-original", **definition).json() == committed.json()
    decision = read(api, f"{DRAFTS}/{rule_id}")
    assert decision.status_code == 200, decision.text
    assert decision.json() == RULE | definition | {
        "rule_id": rule_id,
        "revision": "1",
        "state": "draft",
        "enabled": False,
    }
    denied(
        save(api, "daily-original", version=2, trigger={"kind": "daily", "time": "09:00"}),
        409,
        "idempotency_conflict",
    )
    for index, invalid in enumerate(
        (
            DAILY | {"version": 1},
            DAILY | {"version": 3},
            DAILY | {"version": True},
            {"version": True, "trigger": {"kind": "manual"}},
            {"version": 1.0, "trigger": {"kind": "manual"}},
            DAILY | {"version": 2.0},
            DAILY | {"trigger": {"kind": "manual"}},
            DAILY | {"trigger": {"kind": "daily", "time": "24:00"}},
            DAILY | {"trigger": {"kind": "daily", "time": "07:30", "zone": "UTC"}},
            DAILY | {"trigger": {"kind": "daily", "time": "07:30:00"}},
        )
    ):
        denied(save(api, f"invalid-daily-{index}", **invalid), 422, "invalid_request")
    assert effects(api) == before

    foreign = CONTEXT["X-Domus-Context"].replace(USER, "b" * 32)
    response = api.client.get(f"{DRAFTS}/{rule_id}", headers={"X-Domus-Context": foreign})
    assert response.status_code == 403
    assert "trigger" not in response.json()
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(
                member,
                revision=member.revision + 1,
                status=MemberStatus.SUSPENDED,
            ),
            member.revision,
        )
    denied(read(api, f"{DRAFTS}/{rule_id}"), 403, "permission_denied")
    denied(save(api, "revoked", **DAILY), 403, "permission_denied")


def test_daily_latest_revision_preserves_the_pinned_manual_run(api):
    rule_id = initial_draft(api, action=ACTION | {"title": "Manual pantry check"})
    result(configure(api, rule_id, "manual-enable"))
    before = effects(api)
    result(save(api, "daily-edit", rule_id=rule_id, revision="1", **DAILY))
    configuration = read(api, f"{DRAFTS}/{rule_id}/execution").json()
    assert configuration["latest_revision"] == "2" and configuration["latest_manual"] is False
    assert configuration["control"] == {
        "rule_revision": "1",
        "control_revision": "1",
        "enabled": True,
        "title": "Manual pantry check",
    }
    denied(
        configure(api, rule_id, "daily-enable", revision="2", expected="1"),
        422,
        "automation_requires_manual_trigger",
    )
    denied(run(api, rule_id, "daily-run", revision="2"), 409, "revision_conflict")
    assert effects(api) == before
    committed = result(run(api, rule_id, "old-manual"))
    assert committed["rule_revision"] == "1" and committed["task_occurrence_id"]
    history = read(api, f"{DRAFTS}/{rule_id}/runs").json()
    assert [item["task_occurrence_id"] for item in history["items"]] == [
        committed["task_occurrence_id"]
    ]
    # A forged stored control still cannot admit a daily revision.
    with api.store.write() as unit:
        unit.automation_controls.save("home", AutomationControl(rule_id, 2, 2, True), 1)
    after_manual = effects(api)
    denied(
        run(api, rule_id, "forged-daily", revision="2", control="2"),
        422,
        "automation_requires_manual_trigger",
    )
    assert effects(api) == after_manual


def test_daily_conflict_and_receipt_failure_do_not_leave_extra_revisions(api, monkeypatch):
    api.user(USER, True)
    rule_id = result(save(api, "daily-initial", **DAILY))["rule_id"]
    start = Barrier(2)

    def writer(index):
        start.wait(timeout=5)
        return save(
            api,
            f"daily-writer-{index}",
            rule_id=rule_id,
            revision="1",
            version=2,
            trigger={"kind": "daily", "time": f"0{index}:00"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(writer, (8, 9))) == [200, 409]
    target = f"{DRAFTS}/{rule_id}"
    assert read(api, target).json()["revision"] == "2"
    original_add = SQLiteReceipts.add

    def fail_save(self, receipt):
        if receipt.command.action == SAVE_DRAFT:
            raise StorageFailure("storage_failure")
        return original_add(self, receipt)

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "add", fail_save)
        assert (
            save(api, "daily-rollback", rule_id=rule_id, revision="2", **DAILY).status_code == 500
        )
    denied(read(api, DRAFTS + "/requests/daily-rollback"), 404, "operation_missing")
    assert read(api, target).json()["revision"] == "2"
    assert (
        result(save(api, "daily-rollback", rule_id=rule_id, revision="2", **DAILY))["revision"]
        == "3"
    )


@pytest.mark.parametrize(
    ("version", "fixture"),
    [
        (20, "v20-inventory-history-source.sql"),
        (33, "v32-automation-execution-source.sql"),
    ],
)
def test_daily_definition_after_migration_restart_and_restore(
    tmp_path, monkeypatch, version, fixture
):
    root = tmp_path / "data"
    root.mkdir(mode=0o700)
    path = root / "domus.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as db:
        db.executescript((Path(__file__).parents[1] / "fixtures" / "sqlite" / fixture).read_text())
        installation = Installation(
            *db.execute("SELECT instance_id,channel FROM installation").fetchone()
        )
    path.chmod(0o600)
    identity_at(root, installation)
    store = SQLiteDatabase(path, installation)

    legacy_manual = None
    if version == 33:
        with monkeypatch.context() as previous:
            previous.setattr(storage, "SCHEMA_VERSION", 33)
            store.initialize(require_existing=True)
            legacy_manual = draft_service(store).save(
                "legacy-manual",
                SaveDraft(None, 0, AutomationRule(1, "manual", None, TaskContent("Legacy manual"))),
            )
            legacy_id = legacy_manual.result.decode()["rule_id"]
            execution_service(store).configure(
                "legacy-control", ConfigureAutomation(legacy_id, 1, 0, True)
            )

    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=True) == version
        original_products = db.execute(
            "SELECT * FROM inventory_products ORDER BY product_id"
        ).fetchall()
    store.initialize(require_existing=True)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        assert _verify_database(db, store, previous=False) == 34
        assert (
            db.execute("SELECT * FROM inventory_products ORDER BY product_id").fetchall()
            == original_products
        )
    if legacy_manual is not None:
        assert draft_service(store).original("legacy-manual") == legacy_manual
        assert execution_service(store).state(legacy_id).control.enabled

    daily = AutomationRule(2, DailyTrigger("07:30"), None, TaskContent("Review supplies"))
    first = draft_service(store).save("first-daily", SaveDraft(None, 0, daily))
    rule_id = first.result.decode()["rule_id"]
    archive, target = tmp_path / "checkpoint", tmp_path / "prepared"
    checkpoint = SQLiteSnapshots(store, archive, installation, Clock()).create("daily-revision")
    later_rule = replace(daily, trigger=DailyTrigger("08:00"))
    later = draft_service(store).save("second-daily", SaveDraft(rule_id, 1, later_rule))

    restarted = draft_service(SQLiteDatabase(path, installation))
    assert restarted.reopen(rule_id).rule == later_rule
    assert restarted.original("second-daily") == later
    existing = path.read_bytes()
    with monkeypatch.context() as previous:
        previous.setattr(storage, "SCHEMA_VERSION", 33)
        with pytest.raises(DatabaseRejected, match="unsupported_schema"):
            store.initialize(require_existing=True)
    assert path.read_bytes() == existing

    SQLiteRestorations(store, archive, target, installation, Clock(), checkpoint).prepare(
        "restore-daily"
    )
    assert SQLiteActivation(root, installation, Clock(), target).activate().state == "active"
    selected = open_storage(root, "edge")
    try:
        restored = draft_service(selected.database)
        assert restored.reopen(rule_id).rule == daily
        assert restored.original("first-daily") == first
        historical = restored.save("second-daily", SaveDraft(rule_id, 1, later_rule))
        assert historical.historical and historical.operation_id == later.operation_id
        with selected.database.read() as unit:
            assert unit.automation_controls.get("home", rule_id) is None
    finally:
        selected.close()
