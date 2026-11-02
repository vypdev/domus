"""Resolved boundaries require original scoped operation proof on every durable advance."""

from dataclasses import replace
from datetime import datetime

import pytest
from test_fixed_materialization import configured as dated
from test_recurrence_until_proof import configured
from test_sqlite_snapshots import Clock
from test_task_commands import counts

from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.recurrence_membership import accepts_fixed_cursor
from domus.domain.recurrence_planning import FixedCursor
from domus.domain.recurrence_time import NominalTime
from domus.domain.storage import JsonDocument
from domus.infrastructure.sqlite_recurrence_records import progress_document, read_progress
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


def facts(tmp_path):
    service, store, rid, before = configured(tmp_path)
    service.step(rid, before)
    with store.read() as unit:
        rule = unit.recurrence.schedule("home", rid)
        progress = unit.recurrence.progress("home", rid)
    return service, store, rid, before, rule, progress


@pytest.mark.parametrize(
    "change",
    [
        "cursor",
        "policy",
        "range",
        "closed-range",
        "last-type",
        "terminal-type",
        "policy-slot",
        "digest",
    ],
)
def test_evidence_value_rejects_untyped_or_inconsistent_temporal_facts(tmp_path, change):
    _, _, _, _, _, progress = facts(tmp_path)
    core = progress.evidence.time
    last = core.last
    changes = {
        "cursor": {"cursor": None},
        "policy": {"policy": None},
        "range": {"range_complete": 1},
        "closed-range": {"cursor": replace(core.cursor, closed=True), "range_complete": False},
        "last-type": {"last": "wrong"},
        "terminal-type": {"terminal": "wrong"},
        "policy-slot": {"policy": replace(core.policy, revision=2)},
        "digest": {
            "terminal": replace(last, resolved=replace(last.resolved, zone_digest="b" * 64))
        },
    }
    with pytest.raises(InvalidInput, match="invalid_recurrence_cursor_evidence"):
        replace(core, **changes[change])


@pytest.mark.parametrize("field,value", [("time", None), ("command", None), ("operation_id", "")])
def test_origin_reference_requires_typed_scope_and_operation(tmp_path, field, value):
    *_, progress = facts(tmp_path)
    with pytest.raises(InvalidInput):
        replace(progress.evidence, **{field: value})
    with pytest.raises(InvalidInput):
        replace(progress, evidence="wrong")


@pytest.mark.parametrize("change", ["cursor", "policy", "range", "household", "actor", "action"])
def test_typed_origin_cannot_rebind_a_progress_relationship(tmp_path, change):
    _, _, _, _, rule, progress = facts(tmp_path)
    evidence = progress.evidence
    if change == "cursor":
        evidence = replace(
            evidence, time=replace(evidence.time, cursor=replace(progress.cursor, offset=0))
        )
    elif change == "policy":
        evidence = replace(
            evidence,
            time=replace(evidence.time, policy=replace(rule.policy, revision=2), last=None),
        )
    elif change == "range":
        evidence = replace(evidence, time=replace(evidence.time, range_complete=True))
    else:
        command = replace(
            evidence.command,
            **{
                "household": {"household_id": "other"},
                "actor": {"actor_id": "ha_admin"},
                "action": {"action": "task.complete"},
            }[change],
        )
        evidence = replace(evidence, command=command)
    assert not replace(progress, evidence=evidence).matches_schedule(rule)


@pytest.mark.parametrize(
    "change",
    [
        "wrong-cursor",
        "missing-last",
        "late-last",
        "earlier-last",
        "zero-with-last",
        "unclosed-terminal",
    ],
)
def test_instant_until_checks_actual_included_rank_and_terminal_state(tmp_path, change):
    service, store, rid, before, rule, first = facts(tmp_path)
    service.step(rid, before)
    with store.read() as unit:
        second = unit.recurrence.progress("home", rid)
    cursor = second.cursor
    core = second.evidence.time
    if change == "wrong-cursor":
        core = replace(core, cursor=first.cursor)
    elif change == "missing-last":
        core = replace(core, last=None)
    elif change == "late-last":
        nominal = NominalTime(datetime(2026, 1, 3, 12))
        core = replace(
            core, last=type(core.last)(nominal, service.planner.times.resolve(nominal, rule.policy))
        )
    elif change == "earlier-last":
        core = replace(core, last=first.evidence.time.last)
    elif change == "zero-with-last":
        cursor = FixedCursor(cursor.binding)
        core = replace(core, cursor=cursor)
    else:
        core = replace(core, terminal=core.last)
    assert not accepts_fixed_cursor(rule.pattern, cursor, core)


def test_a_legitimate_last_included_cursor_waits_for_a_separate_end_check(tmp_path):
    service, store, rid, before, rule, _ = facts(tmp_path)
    second = service.step(rid, before)
    assert not second.cursor.closed and second.cursor.nominal_count == 2
    with store.read() as unit:
        progress = unit.recurrence.progress("home", rid)
        assert progress.matches_schedule(rule)
        assert progress.evidence.time.last.resolved.instant_ms == rule.pattern.until
        assert progress.evidence.time.terminal is None
        assert read_progress(progress_document(progress).encoded) == progress
    final = service.step(rid, before)
    assert final.cursor.closed and final.status == "scan"
    assert counts(store)[1] == 2


@pytest.mark.parametrize("surface", ["read", "snapshot"])
@pytest.mark.parametrize(
    "change",
    [
        "missing-header",
        "header-revision",
        "header-operation",
        "header-fingerprint",
        "missing-original",
        "original-operation",
        "original-schedule",
        "original-core",
        "malformed-original",
    ],
)
def test_durable_temporal_evidence_cannot_outlive_or_disagree_with_its_original(
    tmp_path, surface, change
):
    _, store, rid, _, _, progress = facts(tmp_path)
    evidence = progress.evidence
    with store._connection() as connection:
        if change == "missing-header":
            connection.execute("DELETE FROM recurrence_progress_evidence")
        elif change.startswith("header-"):
            column, value = {
                "header-revision": ("progress_revision", 99),
                "header-operation": ("operation_id", "wrong"),
                "header-fingerprint": ("evidence_fingerprint", "b" * 64),
            }[change]
            connection.execute(f"UPDATE recurrence_progress_evidence SET {column}=?", (value,))
        elif change == "missing-original":
            connection.execute(
                "DELETE FROM receipts WHERE operation_id=?", (evidence.operation_id,)
            )
        elif change == "original-operation":
            connection.execute(
                "UPDATE receipts SET operation_id='wrong' WHERE operation_id=?",
                (evidence.operation_id,),
            )
        else:
            result = progress.evidence.time.document().decode()
            result = {"schedule_id": rid, "cursor_evidence": result}
            if change == "original-schedule":
                result["schedule_id"] = "wrong"
            elif change == "original-core":
                result["cursor_evidence"]["last"] = None
            encoded = (
                "not JSON"
                if change == "malformed-original"
                else JsonDocument.from_value(result).encoded
            )
            connection.execute(
                "UPDATE receipts SET result=? WHERE operation_id=?",
                (encoded, evidence.operation_id),
            )
    original = store.path.read_bytes()
    if surface == "read":
        with store.read() as unit:
            with pytest.raises(StorageFailure, match="invalid_recurrence_record"):
                unit.recurrence.progress("home", rid)
    else:
        error = {
            "header-revision": "invalid_snapshot_database",
            "missing-original": "invalid_snapshot_database",
            "original-operation": "incomplete_snapshot_evidence",
        }.get(change, "invalid_snapshot_records")
        with pytest.raises(DatabaseRejected, match=error):
            SQLiteSnapshots(store, tmp_path / "bad", store.installation, Clock()).create("bad")
    assert store.path.read_bytes() == original


@pytest.mark.parametrize("claim", ["last-run", "range", "consumed"])
def test_nominal_date_progress_also_requires_origin_for_any_execution_claim(tmp_path, claim):
    _, store, _, _, rid, _ = dated(tmp_path)
    with store.read() as unit:
        progress = unit.recurrence.progress("home", rid)
    changes = {
        "last-run": {"last_run_at": 100},
        "range": {"range_complete": True},
        "consumed": {"cursor": replace(progress.cursor, offset=1, nominal_count=1)},
    }
    with pytest.raises(Conflict, match="recurrence_cursor_mismatch"):
        with store.write() as unit:
            unit.recurrence.save_progress(replace(progress, revision=2, **changes[claim]), 1)
    with store.read() as unit:
        assert unit.recurrence.progress("home", rid) == progress


@pytest.mark.parametrize("stage", ["insert", "update"])
def test_evidence_header_failure_rolls_back_progress_tasks_and_original_operation(
    tmp_path, monkeypatch, stage
):
    from domus.infrastructure.sqlite_recurrence import SQLiteRecurrences

    service, store, rid, before = configured(tmp_path)
    if stage == "update":
        service.step(rid, before)
    with store.read() as unit:
        previous = unit.recurrence.progress("home", rid)
    initial = counts(store)
    save = SQLiteRecurrences.save_progress

    def fail_after_header(self, *args):
        save(self, *args)
        assert (
            self.connection.execute("SELECT count(*) FROM recurrence_progress_evidence").fetchone()[
                0
            ]
            == 1
        )
        raise StorageFailure("injected")

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteRecurrences, "save_progress", fail_after_header)
        with pytest.raises(StorageFailure, match="injected"):
            service.step(rid, before)
    with store.read() as unit:
        assert unit.recurrence.progress("home", rid) == previous
    assert counts(store) == initial
    assert service.step(rid, before).status == "created"


def test_empty_utc_periods_close_only_after_the_conservative_lower_bound_proves_exhaustion():
    from test_fixed_recurrence_planning import pattern, planner, policy

    from domus.domain.recurrence_planning import CursorTimeEvidence

    rule = pattern(
        "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30;UNTIL=20260103T000000Z",
        NominalTime(datetime(2026, 1, 1, 12)),
    )
    zone = policy("UTC")
    first = planner().expand(rule, zone, period_limit=1)
    assert not first.cursor.closed and first.cursor.nominal_count == 0
    first_core = CursorTimeEvidence(first.cursor, zone, first.range_complete)
    assert accepts_fixed_cursor(rule, first.cursor, first_core)
    initial = FixedCursor(first.cursor.binding, closed=True)
    assert not accepts_fixed_cursor(rule, initial, CursorTimeEvidence(initial, zone, True))
    final = planner().expand(rule, zone, cursor=first.cursor)
    assert final.cursor.closed and final.terminal is None
    assert accepts_fixed_cursor(rule, final.cursor, CursorTimeEvidence(final.cursor, zone, True))


def test_utc_natural_calendar_exhaustion_needs_no_fabricated_terminal_instant():
    from test_fixed_recurrence_planning import pattern, planner, policy

    from domus.domain.recurrence_planning import CursorTimeEvidence

    rule = pattern("FREQ=DAILY", NominalTime(datetime(9999, 12, 31, 12)))
    zone = policy("UTC")
    rule = replace(rule, until=planner().times.resolve(rule.start, zone).instant_ms)
    first = planner().expand(rule, zone, slot_limit=1)
    final = planner().expand(rule, zone, cursor=first.cursor)
    core = CursorTimeEvidence(final.cursor, zone, True, first.slots[-1])
    assert final.cursor.closed and final.terminal is None
    assert accepts_fixed_cursor(rule, final.cursor, core)


@pytest.mark.parametrize("change", ["absent", "cursor"])
def test_replay_cannot_consume_an_altered_original_temporal_boundary(tmp_path, change):
    from test_fixed_materialization import rewind

    service, store, rid, before, _, progress = facts(tmp_path)
    original = progress.evidence
    with store.read() as unit:
        receipt = unit.receipts.get(original.command)
    rewind(store, rid)
    data = receipt.result.decode()
    if change == "absent":
        del data["cursor_evidence"]
    else:
        data["cursor_evidence"]["cursor"]["nominal_count"] = 0
    with store._connection() as connection:
        connection.execute(
            "UPDATE receipts SET result=? WHERE operation_id=?",
            (JsonDocument.from_value(data).encoded, receipt.operation_id),
        )
    initial = counts(store)
    with pytest.raises(StorageFailure, match="invalid_recurrence_effect"):
        service.step(rid, before)
    assert counts(store) == initial
    with store.read() as unit:
        current = unit.recurrence.progress("home", rid)
        assert current.pristine


def test_first_excluded_slot_must_be_the_actual_cursor_candidate(tmp_path):
    service, store, rid, before, rule, _ = facts(tmp_path)
    service.step(rid, before)
    service.step(rid, before)
    with store.read() as unit:
        progress = unit.recurrence.progress("home", rid)
    core = progress.evidence.time
    assert accepts_fixed_cursor(rule.pattern, progress.cursor, core)
    assert not accepts_fixed_cursor(rule.pattern, progress.cursor, replace(core, terminal=None))
    assert not accepts_fixed_cursor(
        rule.pattern, progress.cursor, replace(core, terminal=core.last)
    )


@pytest.mark.parametrize("claim", [{"last_run_at": 100}, {"range_complete": True}])
def test_utc_bootstrap_without_original_cannot_claim_a_completed_run(tmp_path, claim):
    _, store, rid, _ = configured(tmp_path)
    with store.read() as unit:
        rule = unit.recurrence.schedule("home", rid)
        progress = unit.recurrence.progress("home", rid)
    assert progress.pristine and progress.matches_schedule(rule)
    assert not replace(progress, **claim).matches_schedule(rule)
