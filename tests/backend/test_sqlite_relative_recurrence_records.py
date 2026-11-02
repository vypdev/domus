"""Closed relative records preserve original work without granting execution authority."""

import json
from dataclasses import replace

import pytest
from test_relative_recurrence_records import values

from domus.domain.errors import StorageFailure
from domus.domain.relative_recurrence import RelativeSlot
from domus.domain.storage import JsonDocument
from domus.infrastructure.sqlite_relative_recurrence_records import (
    read_relative_progress,
    read_relative_schedule,
    read_relative_slot,
    relative_progress_document,
    relative_schedule_document,
    relative_slot_document,
)


def records(timed, restricted):
    schedule, progress, successor, _ = values(timed, restricted=restricted)
    initial = RelativeSlot(successor.installation, schedule, schedule.initial, "initial", 101)
    current = replace(
        progress,
        current_occurrence_id=successor.occurrence_id,
        current_slot_key=successor.key,
        source_after=31,
        last_run_at=successor.created_at,
    )
    return (
        (schedule, relative_schedule_document, read_relative_schedule),
        (progress, relative_progress_document, read_relative_progress),
        (current, relative_progress_document, read_relative_progress),
        (initial, relative_slot_document, read_relative_slot),
        (successor, relative_slot_document, read_relative_slot),
    )


@pytest.mark.parametrize("timed", [False, True])
@pytest.mark.parametrize("restricted", [False, True])
def test_relative_records_preserve_full_original_initial_and_successor_facts(timed, restricted):
    for value, encode, decode in records(timed, restricted):
        document = encode(value)
        assert decode(document.encoded) == value
        assert encode(decode(document.encoded)).encoded == document.encoded


@pytest.mark.parametrize(
    "mutation", ["whitespace", "pretty", "order", "version", "boolean-version", "extra"]
)
def test_relative_records_refuse_noncanonical_text_and_unknown_versions_or_fields(mutation):
    for value, encode, decode in records(True, True):
        document = encode(value)
        data = document.decode()
        if mutation == "whitespace":
            text = " " + document.encoded
        elif mutation == "pretty":
            text = json.dumps(data, indent=2)
        elif mutation == "order":
            text = json.dumps(dict(reversed(list(data.items()))), separators=(",", ":"))
        else:
            if mutation == "version":
                data["version"] = 2
            elif mutation == "boolean-version":
                data["version"] = True
            else:
                data["unrecognized"] = None
            text = JsonDocument.from_value(data).encoded
        with pytest.raises(StorageFailure):
            decode(text)


def test_relative_slot_codec_cannot_replace_actual_work_basis_with_approval_time():
    *_, (slot, encode, decode) = records(True, True)
    data = encode(slot).decode()
    data["source"]["cycle"]["performed_at"] += 86_400_000
    with pytest.raises(StorageFailure):
        decode(JsonDocument.from_value(data).encoded)


def test_actual_epoch_local_basis_before1970_round_trips_without_becoming_a_nominal_deadline():
    from datetime import date

    from test_tasks import cycle

    from domus.domain.recurrence_planning import PlannedSlot
    from domus.domain.recurrence_rules import NominalDate
    from domus.domain.recurrence_time import RelativeInterval, TimePolicy
    from domus.domain.relative_recurrence import RelativeSchedule, RelativeSource
    from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

    times = PinnedRecurrenceTime()
    policy = TimePolicy("America/New_York", times.data_identity)
    local = times.local_at(0, policy)
    assert local.local.year == 1969
    schedule, _, example, _ = values(False)
    schedule = RelativeSchedule(
        schedule.schedule_id,
        schedule.household_id,
        schedule.definition_id,
        PlannedSlot(NominalDate(date(1970, 1, 1)), None),
        RelativeInterval(1),
        policy,
        100,
    )
    original = cycle(performed_at=0, recorded_at=1)
    slot = RelativeSlot(
        example.installation,
        schedule,
        schedule.initial,
        "next",
        100,
        RelativeSource.from_cycle(original, local),
    )
    assert read_relative_slot(relative_slot_document(slot).encoded) == slot
