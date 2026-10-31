"""A durable activation record binds one prepared input and truthful publication state."""

from dataclasses import replace

import pytest
from test_restoration_commands import prepared

from domus.domain.activation import ActivationRecord, ActivationStatus
from domus.domain.errors import InvalidInput
from domus.domain.restoration import RestoreSource


def record():
    value = prepared()
    value = replace(value, source=RestoreSource(value.installation, 4, None, "a" * 64))
    return ActivationRecord(value, "pending")


def test_transition_roundtrips_and_status_never_confuses_selection_with_completion():
    initial = record()
    assert ActivationRecord.from_value(initial.document().decode()) == initial
    materialized = replace(
        initial,
        phase="materialized",
        database_sha256="b" * 64,
        database_bytes=4096,
        rollback_snapshot=initial.prepared.checkpoint,
    )
    assert ActivationStatus(materialized, initial.prepared.restore_id).state == "pending"
    active = replace(materialized, phase="active", activated_at=100)
    assert ActivationStatus(active, initial.prepared.restore_id).state == "active"
    assert ActivationStatus(active, "newer").state == "historical"
    assert ActivationRecord.from_value(active.document().decode()) == active


@pytest.mark.parametrize(
    "change",
    [
        {"phase": "wrong"},
        {"prepared": None},
        {"prepared": prepared()},
        {"database_sha256": "bad"},
        {"phase": "materialized"},
        {"activated_at": 1},
        {"database_bytes": True},
        {
            "phase": "active",
            "database_sha256": "b" * 64,
            "database_bytes": 4096,
            "activated_at": -1,
        },
    ],
)
def test_invalid_or_unbound_transition_cannot_be_published(change):
    with pytest.raises(InvalidInput):
        replace(record(), **change)


@pytest.mark.parametrize("kind", ["list", "missing", "extra", "version", "boolean"])
def test_activation_parser_is_exact_and_versioned(kind):
    value = record().document().decode()
    if kind == "list":
        value = []
    elif kind == "missing":
        del value["phase"]
    elif kind == "extra":
        value["path"] = "untrusted"
    elif kind == "version":
        value["format_version"] = 2
    else:
        value["format_version"] = True
    with pytest.raises(InvalidInput):
        ActivationRecord.from_value(value)


@pytest.mark.parametrize(
    "field,value", [("activated_at", -1), ("activated_at", True), ("activated_at", None)]
)
def test_complete_record_requires_a_real_bounded_completion_timestamp(field, value):
    active = replace(
        record(),
        phase="active",
        database_sha256="b" * 64,
        database_bytes=4096,
        rollback_snapshot=record().prepared.checkpoint,
        activated_at=100,
    )
    with pytest.raises(InvalidInput):
        replace(active, **{field: value})
    with pytest.raises(InvalidInput):
        replace(active, phase="materialized")
    with pytest.raises(InvalidInput):
        ActivationStatus(None, None)


@pytest.mark.parametrize("kind", ["list", "missing", "extra"])
def test_snapshot_record_parser_is_exact(kind):
    from domus.domain.snapshots import Snapshot

    value = record().prepared.checkpoint.document().decode()
    if kind == "list":
        value = []
    elif kind == "missing":
        del value["snapshot_id"]
    else:
        value["extra"] = True
    with pytest.raises(InvalidInput):
        Snapshot.from_value(value)


def test_application_port_validates_selection_and_complete_results():
    from domus.application.activation import ActivationCommands
    from domus.domain.errors import StorageFailure

    pending = ActivationStatus(record(), None)

    class Port:
        value = pending

        def activate(self):
            return self.value

        def resume(self):
            return self.value

        def inspect(self):
            return self.value

    port = Port()
    installation = record().prepared.installation
    with pytest.raises(InvalidInput):
        ActivationCommands(port, installation).activate()
    with pytest.raises(InvalidInput):
        ActivationCommands(
            port, replace(installation, channel="stable"), record().prepared
        ).activate()
    commands = ActivationCommands(port, installation, record().prepared)
    assert commands.inspect() == pending
    for action in (commands.activate, commands.resume):
        with pytest.raises(StorageFailure):
            action()
    port.value = ActivationStatus(
        replace(
            record(),
            phase="active",
            database_sha256="b" * 64,
            database_bytes=4096,
            rollback_snapshot=record().prepared.checkpoint,
            activated_at=100,
        ),
        "restore-1",
    )
    assert commands.activate() == commands.resume() == commands.inspect() == port.value
    with pytest.raises(StorageFailure):
        ActivationCommands(port, installation, restore_id="different").inspect()
    with pytest.raises(StorageFailure):
        ActivationCommands(
            port, installation, replace(record().prepared, restore_id="other")
        ).inspect()
    with pytest.raises(StorageFailure):
        ActivationCommands(
            port, replace(installation, channel="stable"), restore_id="restore-1"
        ).inspect()
