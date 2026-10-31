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


def test_image_pins_the_private_launcher_and_installs_a_nonroot_readable_runtime(
    image: str,
) -> None:
    result = docker("image", "inspect", image)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)[0]["Config"]
    assert config["User"] == "0:0"
    assert config["Entrypoint"] == ["/app/.venv/bin/domus-ha-app", "--channel", "edge"]
    assert config["Labels"]["io.hass.type"] == "app"
    assert config["Labels"]["org.opencontainers.image.revision"] == (
        "d013cf2c8b932d0e00f5858053cbc0e663d5eee1"
    )
    assert not any(value.startswith("SUPERVISOR_TOKEN=") for value in config["Env"])
    probe = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
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
    assert "Domus could not start" in result.stderr
    assert "Traceback" not in result.stderr


def ready(name: str) -> None:
    deadline = time.monotonic() + 20
    while True:
        result = docker(
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            "import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=2)",
        )
        if result.returncode == 0 or time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    assert result.returncode == 0, result.stderr


def stopped(name: str) -> None:
    result = docker("stop", "--time", "15", name)
    assert result.returncode == 0, result.stderr
    state = docker("inspect", "--format", "{{json .State}}", name)
    finished = json.loads(state.stdout)
    assert finished["ExitCode"] in (0, 143)
    assert finished["OOMKilled"] is False and finished["Error"] == ""


@pytest.fixture
def data_volume(image: str):
    volume = "domus-persistent-data-" + uuid.uuid4().hex
    assert docker("volume", "create", volume).returncode == 0
    try:
        prepared = docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--volume",
            volume + ":/data",
            "--entrypoint",
            "/app/.venv/bin/python",
            image,
            "-c",
            "import pathlib,json,os; p=pathlib.Path('/data/options.json'); "
            "p.write_text(json.dumps({'public_origins':['http://homeassistant.local:8123']})); "
            "p.chmod(0o600); os.chmod('/data',0o755)",
        )
        assert prepared.returncode == 0, prepared.stderr
        yield volume
    finally:
        removed = docker("volume", "rm", volume)
        assert removed.returncode == 0, removed.stderr


def test_real_nonroot_listener_rejects_forgery_and_retains_storage_and_replay_on_restart(
    image: str,
    data_volume: str,
) -> None:
    name = "domus-persistent-test-" + uuid.uuid4().hex
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
            data_volume + ":/data",
            "--env",
            "SUPERVISOR_TOKEN=fixture-supervisor-token",
            image,
        )
        assert started.returncode == 0, started.stderr
        ready(name)
        probe = docker(
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            r"""import json, pathlib, urllib.error, urllib.request
servers = []
for process in pathlib.Path('/proc').iterdir():
    if process.name.isdecimal():
        try:
            command = (process / 'cmdline').read_bytes().split(b'\0')
            if b'/app/.venv/bin/domus-ingress' in command:
                servers.append((process / 'status').read_text())
        except FileNotFoundError:
            pass
assert len(servers) == 1
status = dict(line.split(':', 1) for line in servers[0].splitlines() if ':' in line)
assert status['Uid'].split() == status['Gid'].split() == ['65532'] * 4
assert status['Groups'].strip() == ''
assert all(int(status[key].strip(), 16) == 0 for key in ('CapEff','CapPrm','CapAmb'))
root = pathlib.Path('/data/domus')
assert root.stat().st_uid == root.stat().st_gid == 65532
assert root.stat().st_mode & 0o777 == 0o700
for path in root.iterdir():
    assert path.stat().st_uid == 65532 and path.stat().st_mode & 0o777 == 0o600
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
        before = docker(
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            "print(open('/data/domus/installation.json').read())",
        )
        assert before.returncode == 0, before.stderr
        for retry in range(2):
            result = docker(
                "exec",
                "--user",
                "65532:65532",
                name,
                "/app/.venv/bin/python",
                "-c",
                _STORAGE_COMMAND,
                str(retry),
            )
            assert result.returncode == 0, result.stderr
            if retry == 0:
                stopped(name)
                assert docker("start", name).returncode == 0
                ready(name)
        after = docker(
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            "print(open('/data/domus/installation.json').read())",
        )
        assert after.returncode == 0 and after.stdout == before.stdout
        snapshot_roundtrip(name, json.loads(after.stdout)["instance_id"])
        stopped(name)
    finally:
        removed = docker("rm", "--force", name)
        assert removed.returncode == 0 or "No such container" in removed.stderr, removed.stderr


def snapshot_roundtrip(name: str, instance_id: str) -> None:
    prepared = docker(
        "exec",
        name,
        "/app/.venv/bin/python",
        "-c",
        "import os; os.mkdir('/data/snapshots',0o700); os.chown('/data/snapshots',65532,65532)",
    )
    assert prepared.returncode == 0, prepared.stderr
    created = docker(
        "exec",
        "--user",
        "65532:65532",
        name,
        "/app/.venv/bin/domus-admin",
        "--channel",
        "edge",
        "--data-directory",
        "/data/domus",
        "snapshot",
        "create",
        "/data/snapshots/manual-001",
    )
    assert created.returncode == 0, created.stderr
    original = json.loads(created.stdout)
    assert original["state"] == "created"
    assert original["snapshot"]["schema_version"] == 3
    assert original["snapshot"]["last_committed_at"] == 100
    inspected = docker(
        "exec",
        "--user",
        "65532:65532",
        name,
        "/app/.venv/bin/domus-admin",
        "--channel",
        "edge",
        "--instance-id",
        instance_id,
        "snapshot",
        "inspect",
        "/data/snapshots/manual-001",
    )
    assert inspected.returncode == 0, inspected.stderr
    verified = json.loads(inspected.stdout)
    assert verified["state"] == "verified" and verified["snapshot"] == original["snapshot"]


def test_real_launcher_refuses_invalid_options_without_provisioning(
    image: str, data_volume: str
) -> None:
    changed = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        data_volume + ":/data",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        "open('/data/options.json','w').write('{\"public_origins\":[]}')",
    )
    assert changed.returncode == 0, changed.stderr
    result = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        data_volume + ":/data",
        "--env",
        "SUPERVISOR_TOKEN=fixture-supervisor-token",
        image,
    )
    assert result.returncode == 2 and "Domus could not start" in result.stderr
    inspected = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        data_volume + ":/data",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        "import pathlib; assert not pathlib.Path('/data/domus').exists()",
    )
    assert inspected.returncode == 0, inspected.stderr


_STORAGE_COMMAND = """import os,sys
from contextlib import closing
from pathlib import Path
from domus.application.commands import AtomicCommands, Change
from domus.domain.storage import CommandKey, Household, JsonDocument
from domus.infrastructure.owned_storage import attach_storage, open_storage
from domus.domain.errors import StorageBusy
assert os.getuid() == 65532 and not os.access('/data/options.json', os.W_OK)
try:
    os.setuid(0)
except PermissionError:
    pass
else:
    raise AssertionError('Runtime can regain root')
try:
    open_storage(Path('/data/domus'),'edge')
except StorageBusy:
    pass
else:
    raise AssertionError('A second runtime bypassed the lease')
class Authorization:
    def require(self, command, unit): pass
class Clock:
    def now(self): return 100
class Identifiers:
    def new(self): return 'container-fixture-operation'
def apply(unit):
    assert sys.argv[1] == '0', 'Replay ran the effect again'
    unit.households.save(Household('container-home','Container fixture','UTC',1),0)
    value=JsonDocument.from_value({'household_id':'container-home','revision':1})
    return Change(value,value,value)
with closing(attach_storage(Path('/data/domus'),'edge')) as storage:
    key=CommandKey('container-home','fixture-actor','fixture.create','fixture-request')
    receipt=AtomicCommands(storage.database,Authorization(),Clock(),Identifiers()).execute(
        key,JsonDocument.from_value({'name':'Container fixture'}),apply)
    assert receipt.operation_id == 'container-fixture-operation'
    with storage.database.read() as unit:
        assert unit.households.current().name == 'Container fixture'
        assert len(unit.audit.entries('container-home')) == len(unit.outbox.pending()) == 1
"""
