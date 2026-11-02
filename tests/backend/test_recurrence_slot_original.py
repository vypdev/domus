"""Historical slot generations must agree with their immutable original materialization proof."""

from dataclasses import replace

import pytest
from test_fixed_materialization import configured
from test_sqlite_snapshots import Clock

from domus.domain.errors import DatabaseRejected, StorageFailure
from domus.domain.recurrence_planning import FixedCursor, cursor_binding
from domus.infrastructure.sqlite_recurrence_records import slot_document
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def historical(tmp_path, timed):
    service, store, _, _, rid, before = configured(tmp_path, timed=timed, count=None)
    result = service.step(rid, before)
    with store.write() as unit:
        original = unit.recurrence.slot("home", result.receipt.command.key)
        progress = unit.recurrence.progress("home", rid)
        current = replace(
            original.schedule,
            revision=2,
            pattern_revision=2,
            pattern=replace(original.schedule.pattern, interval=2),
        )
        unit.recurrence.save_schedule(current, 1)
        unit.recurrence.save_progress(
            replace(
                progress,
                revision=3,
                pattern_revision=2,
                cursor=FixedCursor(cursor_binding(current.pattern, current.policy)),
                evidence=None,
                last_run_at=None,
                range_complete=False,
            ),
            2,
        )
    return store, original


@pytest.mark.parametrize("timed", [False, True])
def test_actual_older_generation_remains_readable_and_checkpointable_after_a_rule_edit(
    tmp_path, timed
):
    store, original = historical(tmp_path, timed)
    with store.read() as unit:
        assert unit.recurrence.slot("home", original.key) == original
        assert unit.recurrence.slots("home", original.schedule.schedule_id) == (original,)
    assert SQLiteSnapshots(store, tmp_path / "good", store.installation, Clock()).create("good")


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("change", ["pattern", "policy", "missing-core"])
@pytest.mark.parametrize("surface", ["read", "page", "snapshot"])
def test_older_generation_cannot_substitute_other_valid_pattern_or_policy(
    tmp_path, timed, change, surface
):
    from domus.domain.storage import JsonDocument

    store, original = historical(tmp_path, timed)
    if change == "pattern":
        altered = replace(
            original,
            schedule=replace(
                original.schedule, pattern=replace(original.schedule.pattern, interval=3)
            ),
        )
    elif change == "policy":
        policy = replace(original.schedule.policy, revision=2)
        planned = original.planned
        if planned.resolved is not None:
            planned = replace(planned, resolved=replace(planned.resolved, policy=policy))
        altered = replace(
            original, schedule=replace(original.schedule, policy=policy), planned=planned
        )
    else:
        altered = original
    assert altered.key == original.key
    with store._connection() as connection:
        connection.execute(
            "UPDATE recurrence_slots SET document=?", (slot_document(altered).encoded,)
        )
        if change == "missing-core":
            with store.read() as unit:
                receipt = unit.receipts.get(original.command)
            body = receipt.result.decode()
            del body["cursor_evidence"]
            connection.execute(
                "UPDATE receipts SET result=? WHERE operation_id=?",
                (JsonDocument.from_value(body).encoded, receipt.operation_id),
            )
    before = store.path.read_bytes()
    if surface == "snapshot":
        with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
            SQLiteSnapshots(store, tmp_path / "bad", store.installation, Clock()).create("bad")
    else:
        with store.read() as unit:
            with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
                if surface == "read":
                    unit.recurrence.slot("home", original.key)
                else:
                    unit.recurrence.slots("home", original.schedule.schedule_id)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "change", ["command", "historical", "core-type", "cursor-type", "policy-bool", "planned"]
)
def test_original_proof_does_not_accept_foreign_scope_or_json_value_aliases(tmp_path, change):
    from domus.domain.storage import JsonDocument, RestorationProvenance

    store, original = historical(tmp_path, True)
    with store.read() as unit:
        receipt = unit.receipts.get(original.command)
    assert original.matches_receipt(receipt)
    if change == "command":
        receipt = replace(receipt, command=replace(receipt.command, key="other"))
    elif change == "historical":
        receipt = replace(receipt, restoration=RestorationProvenance("restored", False))
    else:
        data = receipt.result.decode()
        if change == "core-type":
            data["cursor_evidence"] = []
        elif change == "cursor-type":
            data["cursor_evidence"]["cursor"] = None
        elif change == "policy-bool":
            data["cursor_evidence"]["policy"]["revision"] = True
        else:
            data["cursor_evidence"]["last"]["resolved"]["zone_digest"] = "b" * 64
        receipt = replace(receipt, result=JsonDocument.from_value(data))
    assert not original.matches_receipt(receipt)


def test_bad_original_json_fails_as_a_safe_slot_record_error(tmp_path):
    store, original = historical(tmp_path, False)
    with store._connection() as connection:
        connection.execute(
            "UPDATE receipts SET result='invalid JSON' WHERE command_key=?", (original.key,)
        )
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            unit.recurrence.slot("home", original.key)


def test_concrete_slot_adapter_refuses_a_contradictory_historical_projection(tmp_path, monkeypatch):
    from domus.domain.storage import RestorationProvenance
    from domus.infrastructure.sqlite_receipts import SQLiteReceipts

    store, original = historical(tmp_path, False)
    get = SQLiteReceipts.get

    def absent(self, command):
        receipt = get(self, command)
        return replace(receipt, restoration=RestorationProvenance("restored", False))

    monkeypatch.setattr(SQLiteReceipts, "get", absent)
    with store.read() as unit:
        with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
            unit.recurrence.slot("home", original.key)
