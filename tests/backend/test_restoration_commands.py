"""Semantic preparation ports cannot retarget an installation or the selected checkpoint."""

from dataclasses import replace

import pytest
from test_snapshot_commands import snapshot

from domus.application.restoration import RestorationCommands
from domus.domain.errors import InvalidInput, StorageFailure
from domus.domain.restoration import PreparedRestoration
from domus.domain.storage import Installation


def prepared() -> PreparedRestoration:
    return PreparedRestoration("restore-1", snapshot(), "a" * 64, "b" * 64, "c" * 64, 2, 1, 2, 200)


class Identifiers:
    def new(self):
        return "restore-1"


class Archive:
    def __init__(self, value):
        self.value, self.calls = value, []

    def prepare(self, restore_id):
        self.calls.append(restore_id)
        return self.value

    def inspect(self):
        return self.value


def test_prepared_binding_roundtrips_and_application_validates_both_operations() -> None:
    result = prepared()
    assert PreparedRestoration.from_value(result.document().decode()) == result
    archive = Archive(result)
    commands = RestorationCommands(archive, result.installation, Identifiers(), result.checkpoint)
    assert commands.prepare() == commands.inspect() == result
    assert archive.calls == ["restore-1"]
    assert RestorationCommands(archive, result.installation, Identifiers()).inspect() == result


@pytest.mark.parametrize("change", ["id", "installation", "checkpoint"])
def test_application_rejects_misdirected_results(change: str) -> None:
    result = prepared()
    altered = result
    if change == "id":
        altered = replace(result, restore_id="other")
    elif change == "installation":
        altered = replace(
            result,
            checkpoint=replace(
                result.checkpoint,
                installation=Installation(result.installation.instance_id, "stable"),
            ),
        )
    else:
        altered = replace(result, checkpoint=replace(result.checkpoint, snapshot_id="other"))
    commands = RestorationCommands(
        Archive(altered), result.installation, Identifiers(), result.checkpoint
    )
    with pytest.raises(StorageFailure, match="invalid_restore_result"):
        commands.prepare()
    if change != "id":
        with pytest.raises(StorageFailure):
            commands.inspect()


def test_preparation_requires_an_explicit_matching_checkpoint_before_port_io() -> None:
    archive = Archive(prepared())
    for checkpoint in (
        None,
        replace(
            snapshot(), installation=Installation(snapshot().installation.instance_id, "stable")
        ),
    ):
        with pytest.raises(InvalidInput):
            RestorationCommands(
                archive, snapshot().installation, Identifiers(), checkpoint
            ).prepare()
    assert archive.calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"restore_id": "bad id"},
        {"checkpoint": None},
        {"source_frontier_sha256": "bad"},
        {"operations_sha256": 1},
        {"identity_sha256": "g" * 64},
        {"operation_count": True},
        {"operation_count": -1},
        {"operation_count": 2**63},
        {"current_operations": -1},
        {"current_operations": 3},
        {"highwater": 0},
        {"highwater": 2**63},
        {"prepared_at": -1},
        {"prepared_at": True},
        {"operation_count": 0, "current_operations": 0, "highwater": 1},
    ],
)
def test_prepared_value_rejects_invalid_counts_timestamps_and_digests(change) -> None:
    with pytest.raises(InvalidInput):
        replace(prepared(), **change)


@pytest.mark.parametrize("kind", ["missing", "extra", "list", "checkpoint", "state", "version"])
def test_prepared_parser_is_strict(kind) -> None:
    value = prepared().document().decode()
    if kind == "missing":
        del value["restore_id"]
    elif kind == "extra":
        value["extra"] = True
    elif kind == "list":
        value = []
    elif kind == "checkpoint":
        value["checkpoint"] = []
    elif kind == "version":
        value["format_version"] = True
    else:
        value["state"] = "active"
    with pytest.raises(InvalidInput):
        PreparedRestoration.from_value(value)


def test_empty_preparation_counts_are_valid_without_becoming_an_active_installation() -> None:
    result = replace(prepared(), operation_count=0, current_operations=0, highwater=0)
    assert result.document().decode()["state"] == "prepared"
