"""Private real-file provisioning and launch ordering; kernel UID proof is container-only."""

import json
import os
import runpy
from pathlib import Path

import pytest

from domus.composition import ha_app
from domus.domain.errors import InvalidInput

ORIGIN = "http://homeassistant.local:8123"


@pytest.fixture
def launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "data"
    root.mkdir(mode=0o755)
    # BSD may inherit /private/tmp's group; prepare the simulated runtime's actual owner/group.
    os.chown(root, -1, os.getgid())
    (root / "options.json").write_text(json.dumps({"public_origins": [ORIGIN]}))
    monkeypatch.setattr(ha_app, "_DATA_ROOT", root)
    monkeypatch.setattr(ha_app, "_ROOT_UID", os.getuid())
    monkeypatch.setattr(ha_app, "_RUNTIME_UID", os.getuid())
    monkeypatch.setattr(ha_app, "_RUNTIME_GID", os.getgid())
    monkeypatch.setenv("SUPERVISOR_TOKEN", "fixture-supervisor-token")
    events = []
    monkeypatch.setattr(ha_app, "_drop_privileges", lambda: events.append("drop"))
    monkeypatch.setattr(ha_app.os, "execve", lambda *args: events.append(args))
    previous = os.umask(0o077)
    try:
        yield root, events
    finally:
        os.umask(previous)


def test_launcher_creates_only_private_child_drops_before_exec_and_limits_environment(
    launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, events = launch
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("UNRELATED_PRIVATE_VALUE", "must-not-inherit")
    (root / "options.json").write_text(
        json.dumps({"public_origins": [ORIGIN, "https://HA.EXAMPLE/"]})
    )
    assert ha_app.main(["--channel", "edge"]) == 0
    assert set(p.name for p in root.iterdir()) == {"options.json", "domus"}
    assert (root / "domus").stat().st_mode & 0o777 == 0o700
    assert list((root / "domus").iterdir()) == []
    assert events[0] == "drop"
    executable, arguments, environment = events[1]
    assert executable == "/app/.venv/bin/domus-ingress"
    assert arguments == [
        executable,
        "--channel",
        "edge",
        "--data-directory",
        str(root / "domus"),
        "--public-origin",
        ORIGIN,
        "--public-origin",
        "https://ha.example",
    ]
    assert environment == {
        "PATH": "/app/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "C.UTF-8",
        "SUPERVISOR_TOKEN": "fixture-supervisor-token",
    }


def test_existing_private_child_is_validated_without_chown_or_changes(
    launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, events = launch
    target = root / "domus"
    target.mkdir(mode=0o700)
    record = target / "existing-record"
    record.write_bytes(b"existing-private-data")
    before = record.stat()
    monkeypatch.setattr(ha_app.os, "fchown", lambda *args: pytest.fail("existing chown"))
    assert ha_app.main(["--channel", "stable"]) == 0
    assert events[1][1][2] == "stable"
    assert record.stat() == before
    assert record.read_bytes() == b"existing-private-data"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not json",
        b"\xff",
        b" " * 16385,
        b"[]",
        b"{}",
        b'{"public_origins":null}',
        b'{"public_origins":"http://ha.local"}',
        b'{"public_origins":[],"extra":true}',
        b'{"public_origins":[],"public_origins":["http://ha.local"]}',
        b'{"public_origins":["http://ha.local/path"]}',
        b'{"public_origins":["http://user:password@ha.local"]}',
        b'{"public_origins":[42]}',
        b'{"public_origins":["http://ha.local","http://ha.local/"]}',
        json.dumps({"public_origins": [f"http://ha{i}.local" for i in range(5)]}).encode(),
    ],
)
def test_invalid_bounded_options_never_provision_or_launch(
    launch, content: bytes, capsys: pytest.CaptureFixture
) -> None:
    root, events = launch
    (root / "options.json").write_bytes(content)
    assert ha_app.main(["--channel", "edge"]) == 2
    assert events == [] and not (root / "domus").exists()
    error = capsys.readouterr().err
    assert "Existing household records are retained" in error
    assert "fixture-supervisor-token" not in error and str(root) not in error


@pytest.mark.parametrize("kind", ["missing", "symlink", "hardlink", "fifo", "writable"])
def test_options_are_one_regular_nonwritable_operator_file(launch, kind: str) -> None:
    root, events = launch
    options = root / "options.json"
    if kind == "writable":
        options.chmod(0o666)
    elif kind == "hardlink":
        os.link(options, root / "other")
    else:
        content = options.read_bytes()
        options.unlink()
        if kind == "symlink":
            other = root / "other"
            other.write_bytes(content)
            options.symlink_to(other)
        elif kind == "fifo":
            os.mkfifo(options)
    assert ha_app.main(["--channel", "edge"]) == 2
    assert events == [] and not (root / "domus").exists()


@pytest.mark.parametrize("kind", ["shared_parent", "symlink_parent", "file", "symlink", "mode"])
def test_launcher_rejects_unsafe_parent_or_child_without_repair(launch, kind: str) -> None:
    root, events = launch
    target = root / "domus"
    if kind == "shared_parent":
        root.chmod(0o777)
    elif kind == "symlink_parent":
        actual = root.with_name("actual")
        root.rename(actual)
        root.symlink_to(actual, target_is_directory=True)
    elif kind == "file":
        target.write_bytes(b"retained")
    elif kind == "symlink":
        target.symlink_to(root / "missing", target_is_directory=True)
    else:
        target.mkdir(mode=0o755)
        target.chmod(0o755)
    assert ha_app.main(["--channel", "edge"]) == 2
    assert events == []
    if kind == "mode":
        assert target.stat().st_mode & 0o777 == 0o755
    elif kind == "file":
        assert target.read_bytes() == b"retained"


@pytest.mark.parametrize("field", ["st_uid", "st_gid"])
def test_existing_child_with_another_owner_is_never_adopted(
    launch, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    root, events = launch
    target = root / "domus"
    target.mkdir(mode=0o700)
    monkeypatch.setattr(ha_app, "_RUNTIME_UID" if field == "st_uid" else "_RUNTIME_GID", 123456)
    assert ha_app.main(["--channel", "edge"]) == 2
    assert events == []
    assert target.stat().st_uid == os.getuid() and target.stat().st_gid == os.getgid()


def test_launcher_requires_root_and_valid_transport_before_any_files(
    launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, events = launch
    monkeypatch.setattr(ha_app, "_ROOT_UID", os.getuid() + 1)
    assert ha_app.main(["--channel", "edge"]) == 2
    monkeypatch.setattr(ha_app, "_ROOT_UID", os.getuid())
    monkeypatch.delenv("SUPERVISOR_TOKEN")
    assert ha_app.main(["--channel", "edge"]) == 2
    assert events == [] and not (root / "domus").exists()


@pytest.mark.parametrize("phase", ["ownership", "drop", "exec"])
def test_launch_failure_never_runs_a_root_server_and_preserves_ready_data(
    launch, monkeypatch: pytest.MonkeyPatch, phase: str, capsys: pytest.CaptureFixture
) -> None:
    root, events = launch

    def fail(*args):
        raise PermissionError("private details must stay private")

    if phase == "ownership":
        monkeypatch.setattr(ha_app.os, "fchown", fail)
    elif phase == "drop":
        monkeypatch.setattr(ha_app, "_drop_privileges", fail)
    else:
        monkeypatch.setattr(ha_app.os, "execve", fail)
    assert ha_app.main(["--channel", "edge"]) == 2
    assert events == (["drop"] if phase == "exec" else [])
    assert "private details" not in capsys.readouterr().err


@pytest.mark.parametrize("invalid", [None, "uid", "euid", "gid", "egid", "groups"])
def test_privilege_drop_clears_groups_and_verifies_all_process_ids(
    monkeypatch: pytest.MonkeyPatch, invalid: str | None
) -> None:
    state = {"uid": 0, "euid": 0, "gid": 0, "egid": 0, "groups": [0, 7]}
    events = []

    def groups(value):
        events.append("groups")
        state["groups"] = value

    def gid(value):
        events.append("gid")
        state["gid"] = state["egid"] = value

    def uid(value):
        events.append("uid")
        state["uid"] = state["euid"] = value
        if invalid is not None:
            state[invalid] = [0] if invalid == "groups" else 0

    for name in ("uid", "euid", "gid", "egid", "groups"):
        monkeypatch.setattr(ha_app.os, "get" + name, lambda name=name: state[name])
    monkeypatch.setattr(ha_app.os, "setgroups", groups)
    monkeypatch.setattr(ha_app.os, "setgid", gid)
    monkeypatch.setattr(ha_app.os, "setuid", uid)
    if invalid is not None:
        with pytest.raises(InvalidInput, match="runtime_identity_failure"):
            ha_app._drop_privileges()
    else:
        ha_app._drop_privileges()
        assert state == {"uid": 65532, "euid": 65532, "gid": 65532, "egid": 65532, "groups": []}
    assert events == ["groups", "gid", "uid"]


def test_launcher_help_has_no_operator_path_command_or_uid_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr("sys.argv", ["domus-ha-app", "--help"])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(ha_app.__file__)), run_name="__main__")
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "--channel" in help_text
    assert "--data-directory" not in help_text and "--uid" not in help_text
