"""Genuine restore preserves current moves and never reapplies absent later moves."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from test_activation_compatibility import identity_at
from test_recurrence_review import fixed_move, reviewed
from test_sqlite_snapshots import Clock

from domus.application.recurrence_review import ReviewAction
from domus.application.reschedule_review import effective_deadline
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import NominalTime
from domus.infrastructure.owned_storage import open_storage
from domus.infrastructure.sqlite_activation import SQLiteActivation
from domus.infrastructure.sqlite_restoration import SQLiteRestorations
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("snapshot_after_first_move", [False, True])
def test_restored_deadline_uses_only_effects_in_the_selected_complete_snapshot(
    tmp_path, timed, snapshot_after_first_move
):
    root, archive, target = (tmp_path / part for part in ("root", "archive", "target"))
    root.mkdir(mode=0o700)
    service, original, _, _ = fixed_move(root, timed=timed)
    store = service.transactions
    identity_at(root, store.installation)
    first = None
    current_revision = 1
    if snapshot_after_first_move:
        _, request = reviewed(service, original)
        first = service.apply("first-move", request)
        current_revision = 2
    with store.read() as unit:
        prior_work = unit.tasks.occurrence("home", original.occurrence_id)
        prior_slot = unit.recurrence.fixed_slot_for_occurrence("home", original.occurrence_id)
        prior_deadline = effective_deadline(unit, prior_work, prior_slot)

    checkpoint = SQLiteSnapshots(store, archive, store.installation, Clock()).create("selected")
    later = replace(
        original,
        occurrence_revision=current_revision,
        destination=NominalTime(datetime(2026, 4, 4, 9))
        if timed
        else NominalDate(date(2026, 4, 4)),
    )
    _, request = reviewed(service, later, "preview-later")
    later_receipt = service.apply("later-move", request)
    SQLiteRestorations(store, archive, target, store.installation, Clock(), checkpoint).prepare(
        "restore"
    )
    assert SQLiteActivation(root, store.installation, Clock(), target).activate().state == "active"
    restored = open_storage(root, "edge")
    try:
        reopened = replace(service, transactions=restored.database)
        historical = reopened.original(ReviewAction.APPLY, "later-move")
        assert historical.historical and historical.operation_id == later_receipt.operation_id
        with restored.database.read() as unit:
            work = unit.tasks.occurrence("home", original.occurrence_id)
            slot = unit.recurrence.fixed_slot_for_occurrence("home", original.occurrence_id)
            assert work == prior_work
            assert effective_deadline(unit, work, slot) == prior_deadline
            latest = unit.tasks.latest_reschedule("home", original.occurrence_id)
            assert (latest is not None) == snapshot_after_first_move
            if first is not None:
                assert not reopened.original(ReviewAction.APPLY, "first-move").historical
        final = replace(
            later,
            destination=NominalTime(datetime(2026, 4, 5, 9))
            if timed
            else NominalDate(date(2026, 4, 5)),
        )
        _, request = reviewed(reopened, final, "preview-final")
        assert reopened.apply("final-move", request).result.decode()["kind"] == "reschedule"
    finally:
        restored.close()
