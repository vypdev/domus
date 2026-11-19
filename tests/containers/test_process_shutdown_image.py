"""Actual SIGTERM must close current CLI runtimes and preserve their durable records."""

import json
import time
import uuid
from pathlib import Path

import pytest
from test_app_image import data_volume as data_volume
from test_app_image import docker, ready
from test_app_image import image as image


def copied_json(name, path, target):
    result = docker("cp", f"{name}:{path}", str(target))
    assert result.returncode == 0, result.stderr
    return json.loads(target.read_text())


def stop_with_repeated_sigterm(name, tmp_path):
    assert docker("kill", "--signal", "SIGTERM", name).returncode == 0
    deadline = time.monotonic() + 12
    while True:
        entered = docker(
            "exec",
            "--user",
            "65532:65532",
            name,
            "/app/.venv/bin/python",
            "-c",
            "from pathlib import Path; "
            "raise SystemExit(not Path('/tmp/domus-shutdown-closing').exists())",
        )
        if entered.returncode == 0:
            break
        state = docker("inspect", "--format", "{{.State.Running}}", name)
        assert state.stdout.strip() == "true", "SIGTERM skipped explicit runtime cleanup"
        assert time.monotonic() < deadline, entered.stderr
        time.sleep(0.05)
    for _ in range(3):
        assert docker("kill", "--signal", "SIGTERM", name).returncode == 0
    released = docker(
        "exec",
        "--user",
        "65532:65532",
        name,
        "/app/.venv/bin/python",
        "-c",
        "from pathlib import Path; Path('/tmp/domus-shutdown-release').touch()",
    )
    assert released.returncode == 0, released.stderr
    ended = docker("wait", name, timeout=25)
    assert ended.returncode == 0 and ended.stdout.strip() == "0", ended.stderr
    state = json.loads(docker("inspect", "--format", "{{json .State}}", name).stdout)
    assert not state["OOMKilled"] and state["Error"] == ""
    return copied_json(
        name, "/tmp/domus-shutdown-finished.json", tmp_path / "shutdown-finished.json"
    )


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("projection", [False, True])
def test_current_cli_sigterm_closes_workers_identity_and_storage_before_restart(
    image, data_volume, tmp_path, native, projection
):
    prepared = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        f"{data_volume}:/data",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        "import json,os,pathlib; "
        "root=pathlib.Path('/data/domus'); root.mkdir(mode=0o700); "
        "os.chown(root,65532,65532); "
        + (
            "path=pathlib.Path('/data/options.json'); options=json.loads(path.read_text()); "
            "options['ha_tasks_digest']='a'*64; path.write_text(json.dumps(options))"
            if projection and native
            else ""
        ),
    )
    assert prepared.returncode == 0, prepared.stderr
    name = "domus-shutdown-test-" + uuid.uuid4().hex
    fixture = Path(__file__).with_name("shutdown_fixture.py")
    entrypoint = "/app/.venv/bin/domus-ingress" if native else "/app/.venv/bin/domus-server"
    executable = tmp_path / "entrypoint"
    executable.write_text("#!/app/.venv/bin/python\n" + fixture.read_text())
    executable.chmod(0o755)
    configuration = ["--env", "SUPERVISOR_TOKEN=fixture-supervisor-token", image]
    if not native:
        configuration = [
            "--user",
            "65532:65532",
            "--entrypoint",
            entrypoint,
            *(["--env", "DOMUS_HA_TASKS_DIGEST=" + "a" * 64] if projection else []),
            image,
            "--channel",
            "edge",
            "--data-directory",
            "/data/domus",
            "--ha-url",
            "http://ha.fixture",
            "--public-origin",
            "https://domus.fixture",
            "--host",
            "0.0.0.0",
            "--port",
            "8099",
        ]
    try:
        started = docker(
            "run",
            "--detach",
            "--init",
            "--network",
            "none",
            "--name",
            name,
            "--volume",
            f"{data_volume}:/data",
            "--volume",
            f"{executable}:{entrypoint}:ro",
            *configuration,
        )
        assert started.returncode == 0, started.stderr
        ready(name, standalone=not native)
        original = copied_json(name, "/tmp/domus-shutdown-started.json", tmp_path / "original.json")
        for _ in range(2):
            report = stop_with_repeated_sigterm(name, tmp_path)
            assert report["workers_stopped"]
            if native:
                assert report["result"] is None
            else:
                assert report["result"] == [1, 2]
                assert report["revoke_calls"] == 2 and report["local_sessions_removed"]
            assert docker("start", name).returncode == 0
            ready(name, standalone=not native)
            recovered = copied_json(
                name, "/tmp/domus-shutdown-started.json", tmp_path / "recovered.json"
            )
            assert recovered == original
        stop_with_repeated_sigterm(name, tmp_path)
    finally:
        assert docker("rm", "--force", name).returncode == 0
