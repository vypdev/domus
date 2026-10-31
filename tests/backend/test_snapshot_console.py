"""The installed console command creates and inspects private snapshots without an HA grant."""

import io
import json
from pathlib import Path

import pytest
from test_sqlite_snapshots import configured

from domus.composition import admin


def source_options(database) -> list[str]:
    return [
        "--channel",
        database.installation.channel,
        "--database",
        str(database.path),
        "--instance-id",
        database.installation.instance_id,
    ]


def test_console_creates_then_inspects_snapshot_without_access_to_active_source(
    tmp_path: Path,
) -> None:
    _, _, store, location = configured(tmp_path)
    output, error = io.StringIO(), io.StringIO()
    assert (
        admin.main(
            [*source_options(store), "snapshot", "create", str(location)],
            output_stream=output,
            error_stream=error,
        )
        == 0
    )
    created = json.loads(output.getvalue())
    assert created["state"] == "created" and created["snapshot"]["channel"] == "edge"
    assert created["snapshot"]["last_committed_at"] == 100
    assert error.getvalue() == ""
    store.path.unlink()
    inspected = io.StringIO()
    assert (
        admin.main(
            [
                "--channel",
                "edge",
                "--instance-id",
                store.installation.instance_id,
                "snapshot",
                "inspect",
                str(location),
            ],
            output_stream=inspected,
            error_stream=error,
        )
        == 0
    )
    assert json.loads(inspected.getvalue())["state"] == "verified"
    assert json.loads(inspected.getvalue())["snapshot"] == created["snapshot"]


def test_console_uses_owned_attachment_and_releases_maintenance_guard(tmp_path: Path) -> None:
    from domus.infrastructure.owned_storage import open_storage

    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    owned = open_storage(root, "edge")
    location = tmp_path / "archive"
    try:
        assert (
            admin.main(
                [
                    "--channel",
                    "edge",
                    "--data-directory",
                    str(root),
                    "snapshot",
                    "create",
                    str(location),
                ],
                output_stream=io.StringIO(),
                error_stream=io.StringIO(),
            )
            == 0
        )
    finally:
        owned.close()
    open_storage(root, "edge").close()


@pytest.mark.parametrize(
    "options",
    [[], ["--database", "missing"], ["--data-directory", "missing", "--instance-id", "bad"]],
)
def test_inspection_requires_explicit_identity_and_no_active_source_selection(
    tmp_path: Path, options: list[str]
) -> None:
    error = io.StringIO()
    assert (
        admin.main(
            ["--channel", "edge", *options, "snapshot", "inspect", str(tmp_path / "missing")],
            output_stream=io.StringIO(),
            error_stream=error,
        )
        == 2
    )
    assert "Existing records are retained" in error.getvalue()


def test_snapshot_creation_requires_source_and_rejects_invalid_deadline_or_existing_output(
    tmp_path: Path,
) -> None:
    _, _, store, location = configured(tmp_path)
    error = io.StringIO()
    assert (
        admin.main(["--channel", "edge", "snapshot", "create", str(location)], error_stream=error)
        == 2
    )
    assert (
        admin.main(
            [*source_options(store), "snapshot", "--timeout", "0", "create", str(location)],
            error_stream=error,
        )
        == 2
    )
    assert not location.exists()
    assert (
        admin.main(
            [*source_options(store), "snapshot", "create", str(location)],
            output_stream=io.StringIO(),
            error_stream=error,
        )
        == 0
    )
    before = (location / "manifest.json").read_bytes()
    assert (
        admin.main(
            [*source_options(store), "snapshot", "create", str(location)],
            output_stream=io.StringIO(),
            error_stream=error,
        )
        == 2
    )
    assert (location / "manifest.json").read_bytes() == before


def test_output_failure_after_snapshot_publication_preserves_inspectable_copy(
    tmp_path: Path,
) -> None:
    _, _, store, location = configured(tmp_path)

    class Broken(io.StringIO):
        def write(self, value):
            raise OSError("private output fixture detail")

    error = io.StringIO()
    assert (
        admin.main(
            [*source_options(store), "snapshot", "create", str(location)],
            output_stream=Broken(),
            error_stream=error,
        )
        == 1
    )
    assert "private output fixture detail" not in error.getvalue()
    assert (location / "manifest.json").exists()
    assert (
        admin.main(
            [
                "--channel",
                "edge",
                "--instance-id",
                store.installation.instance_id,
                "snapshot",
                "inspect",
                str(location),
            ],
            output_stream=io.StringIO(),
            error_stream=error,
        )
        == 0
    )
