"""Exercise the actual reviewed image without connecting to a real HA installation."""

import json
import os
import subprocess
import time
import uuid

import pytest


def docker(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=45, check=False
    )


@pytest.fixture
def image() -> str:
    value = os.environ.get("DOMUS_TEST_IMAGE")
    assert value, "Set DOMUS_TEST_IMAGE to the freshly built app image"
    return value


def test_image_contains_only_the_nonroot_native_runtime_and_source_identity(image: str) -> None:
    result = docker("image", "inspect", image)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)[0]["Config"]
    assert config["User"] == "65532:65532"
    assert config["Entrypoint"] == ["/app/.venv/bin/domus-ingress", "--channel", "edge"]
    assert config["Labels"]["io.hass.type"] == "app"
    assert config["Labels"]["org.opencontainers.image.revision"] == (
        "98bd12f1bf141ba64053730b2686bd848aee1b1c"
    )
    assert not any(value.startswith("SUPERVISOR_TOKEN=") for value in config["Env"])
    probe = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        "import domus.composition.ingress, os; assert os.getuid() == 65532",
    )
    assert probe.returncode == 0, probe.stderr


def test_image_requires_supervisor_configuration_and_never_falls_back_to_an_admin(
    image: str,
) -> None:
    result = docker("run", "--rm", "--network", "none", image)
    assert result.returncode == 2
    assert "Home Assistant app" in result.stderr
    assert "Traceback" not in result.stderr


def test_real_listener_serves_process_health_and_rejects_forged_direct_ingress(image: str) -> None:
    name = "domus-preview-test-" + uuid.uuid4().hex
    started = docker(
        "run",
        "--detach",
        "--init",
        "--network",
        "none",
        "--name",
        name,
        "--env",
        "SUPERVISOR_TOKEN=fixture-supervisor-token",
        image,
    )
    try:
        assert started.returncode == 0, started.stderr
        deadline = time.monotonic() + 20
        while True:
            ready = docker(
                "exec",
                name,
                "/app/.venv/bin/python",
                "-c",
                "import urllib.request; "
                "urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=2)",
            )
            if ready.returncode == 0 or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        assert ready.returncode == 0, ready.stderr
        probe = docker(
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            """import json, urllib.error, urllib.request
base = 'http://127.0.0.1:8099'
health = json.load(urllib.request.urlopen(base + '/health'))
assert health == {'status': 'ready', 'scope': 'process'}
for path in ('/', '/api/v1/identity'):
    request = urllib.request.Request(base + path, headers={
        'X-Forwarded-For': '172.30.32.2', 'X-Remote-User-Id': 'a' * 32,
        'X-Ingress-Path': '/api/hassio_ingress/' + 'b' * 32,
    })
    try:
        urllib.request.urlopen(request)
    except urllib.error.HTTPError as error:
        assert error.code == 403
        body = error.read().decode()
        assert 'No separate Domus login is required' in body
        assert 'fixture-supervisor-token' not in body
    else:
        raise AssertionError('A forged direct request established protected access')
""",
        )
        assert probe.returncode == 0, probe.stderr
        stopped = docker("stop", "--time", "15", name)
        assert stopped.returncode == 0, stopped.stderr
        state = docker("inspect", "--format", "{{json .State}}", name)
        finished = json.loads(state.stdout)
        # Uvicorn re-raises a captured SIGTERM after draining the server.
        assert finished["ExitCode"] in (0, 143)
        assert finished["OOMKilled"] is False and finished["Error"] == ""
    finally:
        removed = docker("rm", "--force", name)
        assert removed.returncode == 0, removed.stderr
