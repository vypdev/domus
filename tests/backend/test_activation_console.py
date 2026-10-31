"""Installation-console restoration uses bound data, never a human HTTP grant."""

import io
import json

import pytest
from test_sqlite_activation import fixture

from domus.composition import admin
from domus.infrastructure.owned_storage import open_storage


def arguments(root):
    return ["--channel", "edge", "--data-directory", str(root), "restore"]


def run(args):
    output, error = io.StringIO(), io.StringIO()
    code = admin.main(args, input_stream=io.StringIO(), output_stream=output, error_stream=error)
    return code, output.getvalue(), error.getvalue()


def test_actual_console_activation_and_live_shared_status_are_truthful(tmp_path, monkeypatch):
    from test_sqlite_snapshots import Clock

    adapter, root, installation, prepared = fixture(tmp_path)
    monkeypatch.setattr(admin, "SystemClock", Clock)
    code, output, error = run([*arguments(root), "activate", str(adapter.prepared_location)])
    assert code == 0 and error == "", error
    assert json.loads(output)["state"] == "active"
    runtime = open_storage(root, "edge")
    try:
        code, output, error = run([*arguments(root), "status", prepared.restore_id])
        assert code == 0 and json.loads(output)["state"] == "active", error
    finally:
        runtime.close()
    code, output, error = run([*arguments(root), "resume", prepared.restore_id])
    assert code == 0 and json.loads(output)["state"] == "active", error


def test_console_prepare_and_independent_inspection_retain_exact_source_binding(tmp_path):
    adapter, root, installation, prepared = fixture(tmp_path)
    destination = tmp_path / "console-prepared"
    code, output, error = run(
        [*arguments(root), "prepare", str(tmp_path / "snapshot"), str(destination)]
    )
    assert code == 0, error
    value = json.loads(output)
    assert (
        value["state"] == "prepared" and value["prepared"]["source"]["identity_sha256"] is not None
    )
    code, output, error = run(
        [
            "--channel",
            "edge",
            "--instance-id",
            installation.instance_id,
            "restore",
            "inspect",
            str(destination),
        ]
    )
    assert code == 0 and json.loads(output)["state"] == "verified", error


@pytest.mark.parametrize(
    "operation", ["inspect_with_root", "activate_without_root", "wrong_channel"]
)
def test_console_requires_the_exact_owned_configuration(tmp_path, operation):
    adapter, root, _, _ = fixture(tmp_path)
    if operation == "inspect_with_root":
        args = [*arguments(root), "inspect", str(adapter.prepared_location)]
    elif operation == "activate_without_root":
        args = ["--channel", "edge", "restore", "activate", str(adapter.prepared_location)]
    else:
        args = [
            "--channel",
            "stable",
            "--data-directory",
            str(root),
            "restore",
            "activate",
            str(adapter.prepared_location),
        ]
    code, output, error = run(args)
    assert code == 2 and output == "" and "Existing records are retained" in error
    assert not (root / "activation.json").exists()
