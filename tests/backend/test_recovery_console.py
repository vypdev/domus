"""Real console composition requires explicit terminal confirmation and keeps approval local."""

import io
import runpy
import sys
from pathlib import Path

import pytest
from test_recovery_commands import configured, start

from domus.composition import admin


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def options(path: Path, identity) -> list[str]:
    return [
        "--channel",
        identity.channel,
        "--database",
        str(path),
        "--instance-id",
        identity.instance_id,
        "recovery",
        "approve",
    ]


def test_explicit_console_approves_exact_displayed_target_and_cannot_complete_human_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, _, store, _, clock, _ = configured(tmp_path)
    request_id = start(commands)
    monkeypatch.setattr(admin, "SystemClock", lambda: clock)
    output, error = Terminal(), io.StringIO()
    result = admin.main(
        [*options(store.path, store.installation), request_id],
        input_stream=Terminal(f"APPROVE {request_id} ha_new\n"),
        output_stream=output,
        error_stream=error,
    )
    assert result == 0 and error.getvalue() == ""
    assert store.installation.instance_id in output.getvalue()
    assert "ha_new" in output.getvalue() and "setup_administrator" in output.getvalue()
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "approved"
        assert unit.members.by_user("home", "ha_new") is None
    assert commands.complete("finish", request_id, 2).result.decode()["state"] == "recovered"


@pytest.mark.parametrize(
    "answer,tty",
    [
        ("yes\n", True),
        ("", True),
        ("APPROVE wrong wrong\n", True),
        ("ignored", False),
        ("x" * 2000, True),
    ],
)
def test_console_refuses_wrong_empty_oversized_or_noninteractive_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str, tty: bool
) -> None:
    commands, _, store, _, clock, _ = configured(tmp_path)
    request_id = start(commands)
    monkeypatch.setattr(admin, "SystemClock", lambda: clock)
    incoming = Terminal(answer) if tty else io.StringIO(answer)
    output, error = Terminal(), io.StringIO()
    assert (
        admin.main(
            [*options(store.path, store.installation), request_id],
            input_stream=incoming,
            output_stream=output,
            error_stream=error,
        )
        == 2
    )
    assert "Existing records are retained" in error.getvalue()
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "pending"


def test_console_rejects_competing_configuration_without_touching_files(tmp_path: Path) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    error = io.StringIO()
    assert (
        admin.main(
            [
                "--channel",
                "edge",
                "--data-directory",
                str(root),
                "--instance-id",
                "invalid",
                "recovery",
                "approve",
                "request",
            ],
            error_stream=error,
        )
        == 2
    )
    assert list(root.iterdir()) == []
    assert (
        admin.main(
            [
                "--channel",
                "edge",
                "--database",
                str(root / "missing"),
                "recovery",
                "approve",
                "request",
            ],
            error_stream=error,
        )
        == 2
    )
    assert list(root.iterdir()) == []


def test_owned_console_attaches_to_running_native_storage_and_releases_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.application.household_commands import HouseholdCommands, SetupHousehold
    from domus.application.recovery_commands import RecoveryCommands
    from domus.domain.identity import MappingMode
    from domus.infrastructure.owned_storage import open_storage

    commands, _, source, actor, clock, _ = configured(tmp_path)
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    owned = open_storage(root, "edge")
    # Set up a separate real owned installation using the existing pure provider fixtures.
    from test_household_commands import Actor, Directory, Identifiers, Zones

    creator = Actor()
    identifiers = Identifiers()
    household = HouseholdCommands(owned.database, creator, Directory(), Zones(), clock, identifiers)
    household.setup("setup", SetupHousehold("Home", "UTC", MappingMode.SETUP))
    commands = RecoveryCommands(owned.database, actor, owned.installation, clock, identifiers)
    request_id = start(commands)
    monkeypatch.setattr(admin, "SystemClock", lambda: clock)
    assert (
        admin.main(
            ["--channel", "edge", "--data-directory", str(root), "recovery", "approve", request_id],
            input_stream=Terminal(f"APPROVE {request_id} ha_new\n"),
            output_stream=Terminal(),
            error_stream=io.StringIO(),
        )
        == 0
    )
    commands.complete("finish", request_id, 2)
    owned.close()
    open_storage(root, "edge").close()


def test_output_failure_after_commit_preserves_uncertainty_and_allows_same_request_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, _, store, _, clock, _ = configured(tmp_path)
    request_id = start(commands)
    monkeypatch.setattr(admin, "SystemClock", lambda: clock)

    class BrokenOutput(Terminal):
        def write(self, value):
            if "operation_id" in value:
                raise OSError("private output failure")
            return super().write(value)

    error = io.StringIO()
    assert (
        admin.main(
            [*options(store.path, store.installation), request_id],
            input_stream=Terminal(f"APPROVE {request_id} ha_new\n"),
            output_stream=BrokenOutput(),
            error_stream=error,
        )
        == 1
    )
    assert "private output failure" not in error.getvalue()
    assert "confirm" in error.getvalue()
    assert (
        admin.main(
            [*options(store.path, store.installation), request_id],
            input_stream=Terminal(),
            output_stream=Terminal(),
            error_stream=io.StringIO(),
        )
        == 0
    )
    with store.read() as unit:
        assert len(unit.audit.entries("home")) == 3


def test_console_interrupt_does_not_approve_and_help_needs_no_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands, _, store, _, clock, _ = configured(tmp_path)
    request_id = start(commands)
    monkeypatch.setattr(admin, "SystemClock", lambda: clock)

    class Interrupted(Terminal):
        def readline(self, *args):
            raise KeyboardInterrupt

    assert (
        admin.main(
            [*options(store.path, store.installation), request_id],
            input_stream=Interrupted(),
            output_stream=Terminal(),
            error_stream=io.StringIO(),
        )
        == 130
    )
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "pending"
    monkeypatch.delitem(sys.modules, "domus.composition.admin", raising=False)
    monkeypatch.setattr(sys, "argv", ["domus-admin", "--help"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("domus.composition.admin", run_name="__main__")
    assert stopped.value.code == 0


def test_actual_console_process_requires_and_accepts_a_real_pty(tmp_path: Path) -> None:
    import os
    import pty
    import select
    import subprocess
    import time

    commands, _, store, _, clock, _ = configured(tmp_path)
    clock.time = int(time.time() * 1000)
    request_id = start(commands)
    master, slave = pty.openpty()
    process = None
    captured = b""
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "domus.composition.admin",
                *options(store.path, store.installation),
                request_id,
            ],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
        os.close(slave)
        slave = None
        deadline = time.monotonic() + 10
        while b"\n> " not in captured:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "Console did not display its exact confirmation prompt"
            ready, _, _ = select.select([master], [], [], remaining)
            assert ready, "Console prompt timed out"
            captured += os.read(master, 4096)
            assert len(captured) < 16384
        os.write(master, f"APPROVE {request_id} ha_new\n".encode())
        assert process.wait(timeout=10) == 0, captured.decode(errors="replace")
        with store.read() as unit:
            assert unit.recoveries.get("home", request_id).state.value == "approved"
            assert unit.members.by_user("home", "ha_new") is None
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if slave is not None:
            os.close(slave)
        os.close(master)
