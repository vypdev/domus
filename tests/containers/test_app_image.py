"""Exercise the actual reviewed image without connecting to a real HA installation."""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from shutil import copyfile

import coverage
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
    expected = os.environ.get("DOMUS_TEST_SOURCE_COMMIT")
    assert expected, "Set DOMUS_TEST_SOURCE_COMMIT to the exact checked-out CI revision"
    assert config["Labels"]["org.opencontainers.image.revision"] == expected
    assert config["Labels"]["io.hass.version"] == "ci-current"
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


def ready(name: str, *, standalone: bool = False) -> None:
    deadline = time.monotonic() + 20
    while True:
        result = docker(
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            "import urllib.request,urllib.error; "
            + (
                "\ntry: urllib.request.urlopen(urllib.request.Request("
                "'http://127.0.0.1:8099/api/v1/session',"
                "headers={'Host':'domus.fixture'}), timeout=2)"
                "\nexcept urllib.error.HTTPError as error: assert error.code==401"
                "\nelse: raise AssertionError('Unauthenticated session was accepted')"
                if standalone
                else "urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=2)"
            ),
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
    expected_schema: int = 14,
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
        snapshot_roundtrip(name, json.loads(after.stdout)["instance_id"], expected_schema)
        stopped(name)
    finally:
        removed = docker("rm", "--force", name)
        assert removed.returncode == 0 or "No such container" in removed.stderr, removed.stderr


def snapshot_roundtrip(name: str, instance_id: str, expected_schema: int) -> None:
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
    assert original["snapshot"]["schema_version"] == expected_schema
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


def packaged_fixture(image: str, volume: str, operation: str, *arguments: str):
    source = Path(__file__).with_name("restore_fixture.py").read_text()
    return docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--volume",
        volume + ":/data",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        source,
        operation,
        *arguments,
    )


def console(image: str, volume: str, *arguments: str):
    return docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--volume",
        volume + ":/data",
        "--entrypoint",
        "/app/.venv/bin/domus-admin",
        image,
        "--channel",
        "edge",
        *arguments,
    )


def successful(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def restore_runtime(image: str, data_volume: str, request):
    mode = request.param
    delivery = request.node.callspec.params.get("delivery", "suppressed")
    prepared = docker(
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
        "import os; os.mkdir('/data/snapshots',0o700); os.chown('/data/snapshots',65532,65532); "
        + (
            "os.mkdir('/data/domus',0o700); os.chown('/data/domus',65532,65532)"
            if mode == "standalone"
            else ""
        ),
    )
    assert prepared.returncode == 0, prepared.stderr
    name = "domus-restore-test-" + uuid.uuid4().hex
    configuration = (
        [
            "--user",
            "65532:65532",
            "--entrypoint",
            "/app/.venv/bin/domus-server",
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
        ]
        if mode == "standalone"
        else ["--env", "SUPERVISOR_TOKEN=fixture-supervisor-token", image]
    )
    try:
        result = docker(
            "run",
            "--detach",
            "--init",
            "--network",
            "none",
            "--name",
            name,
            "--volume",
            data_volume + ":/data",
            *configuration,
        )
        assert result.returncode == 0, result.stderr
        ready(name, standalone=mode == "standalone")
        identity = successful(packaged_fixture(image, data_volume, "initialize"))
        successful(
            console(
                image,
                data_volume,
                "--data-directory",
                "/data/domus",
                "snapshot",
                "create",
                "/data/snapshots/manual",
            )
        )
        successful(packaged_fixture(image, data_volume, "later", delivery))
        stopped(name)
        prepared = successful(
            console(
                image,
                data_volume,
                "--data-directory",
                "/data/domus",
                "restore",
                "prepare",
                "/data/snapshots/manual",
                "/data/snapshots/prepared",
            )
        )
        assert prepared["state"] == "prepared"
        verified = successful(
            console(
                image,
                data_volume,
                "--instance-id",
                identity["instance_id"],
                "restore",
                "inspect",
                "/data/snapshots/prepared",
            )
        )
        assert verified["state"] == "verified" and verified["prepared"] == prepared["prepared"]
        yield name, data_volume, identity, prepared["prepared"]["restore_id"], mode
    finally:
        result = docker("rm", "--force", name)
        assert result.returncode == 0 or "No such container" in result.stderr, result.stderr


@pytest.mark.parametrize("restore_runtime", ["native", "standalone"], indirect=True)
@pytest.mark.parametrize("delivery", ["suppressed", "delivered"])
def test_packaged_console_restore_restart_and_latest_history_rollback(
    image: str, restore_runtime, delivery
):
    name, volume, identity, identifier, mode = restore_runtime
    activated = successful(
        console(
            image,
            volume,
            "--data-directory",
            "/data/domus",
            "restore",
            "activate",
            "/data/snapshots/prepared",
        )
    )
    assert activated["state"] == "active"
    assert activated["activation"]["rollback_snapshot"]["schema_version"] == 14
    assert docker("start", name).returncode == 0
    ready(name, standalone=mode == "standalone")
    active = successful(packaged_fixture(image, volume, "active", delivery))
    assert active["generation_id"] == identifier
    state = successful(
        console(image, volume, "--data-directory", "/data/domus", "restore", "status", identifier)
    )
    assert state["state"] == "active"
    assert (
        console(
            image, volume, "--data-directory", "/data/domus", "restore", "resume", identifier
        ).returncode
        == 2
    )
    successful(packaged_fixture(image, volume, "after"))
    stopped(name)
    checkpoint = "/data/domus/activations/" + identifier + "/source-checkpoint"
    successful(
        console(
            image,
            volume,
            "--data-directory",
            "/data/domus",
            "restore",
            "prepare",
            checkpoint,
            "/data/snapshots/rollback",
        )
    )
    second = successful(
        console(
            image,
            volume,
            "--data-directory",
            "/data/domus",
            "restore",
            "activate",
            "/data/snapshots/rollback",
        )
    )
    assert second["state"] == "active"
    historical = successful(
        console(
            image,
            volume,
            "--data-directory",
            "/data/domus",
            "restore",
            "activate",
            "/data/snapshots/prepared",
        )
    )
    assert historical["state"] == "historical"
    assert docker("start", name).returncode == 0
    ready(name, standalone=mode == "standalone")
    rollback = successful(packaged_fixture(image, volume, "rollback"))
    assert (
        rollback["instance_id"] == identity["instance_id"]
        and rollback["flat_sha256"] == active["flat_sha256"]
    )
    stopped(name)


@pytest.mark.parametrize("restore_runtime", ["native", "standalone"], indirect=True)
@pytest.mark.parametrize("point", ["pending", "selected"])
def test_packaged_process_death_blocks_start_and_resumes_the_exact_transition(
    image: str, restore_runtime, point
):
    name, volume, _, identifier, mode = restore_runtime
    terminated = packaged_fixture(image, volume, "fault", point)
    assert terminated.returncode == 37, terminated.stderr
    status = successful(
        console(image, volume, "--data-directory", "/data/domus", "restore", "status", identifier)
    )
    assert status["state"] == "pending"
    assert docker("start", name).returncode == 0
    assert docker("wait", name).stdout.strip() == "2"
    logs = docker("logs", name)
    assert "fixture-supervisor-token" not in logs.stdout + logs.stderr
    if point == "pending":
        assert (
            console(
                image, volume, "--data-directory", "/data/domus", "restore", "resume", identifier
            ).returncode
            == 2
        )
        resumed = successful(
            console(
                image,
                volume,
                "--data-directory",
                "/data/domus",
                "restore",
                "activate",
                "/data/snapshots/prepared",
            )
        )
    else:
        resumed = successful(
            console(
                image, volume, "--data-directory", "/data/domus", "restore", "resume", identifier
            )
        )
    assert resumed["state"] == "active"
    assert docker("start", name).returncode == 0
    ready(name, standalone=mode == "standalone")
    assert (
        successful(packaged_fixture(image, volume, "active", "suppressed"))["generation_id"]
        == identifier
    )
    stopped(name)


_CALENDAR_FIXTURE = """import hashlib, os, sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.application.recurrence_sources import RecurrenceSourceObservations
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CreateTask, CreateTaskOccurrence
from domus.composition.server import create_runtime
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.sqlite import SQLiteDatabase

class Actor:
    def current(self):
        return HumanIdentity("calendar-fixture-admin", True, True, False)

class Directory:
    def get(self, _identifier):
        raise AssertionError("The calendar fixture does not query a human directory")

mode, instance = sys.argv[1:]
channel = "edge" if mode == "native" else "stable"
installation = Installation(instance, channel)
path = Path("/tmp/domus-calendar-fixture.sqlite3")
store = SQLiteDatabase(path, installation)
store.initialize()
clock, identifiers, actor = SystemClock(), SecureIdentifiers(), Actor()
HouseholdCommands(store, actor, Directory(), TimeZoneCatalog(), clock, identifiers).setup(
    "fixture-household", SetupHousehold("Calendar fixture", "UTC"),
)
tasks = TaskCommands(store, actor, clock, identifiers)
created = tasks.create("fixture-task", CreateTask(TaskContent("Packaged calendar fixture")))
due_at = int((datetime.now(UTC) + timedelta(hours=1)).timestamp() * 1000)
tasks.create_occurrence(
    "fixture-due", CreateTaskOccurrence(created.result.decode()["definition_id"], due_at=due_at)
)
RecurrenceSourceObservations(store, MaintenanceScope(installation, "home")).ingest()
digest = hashlib.sha256(f"{instance}.{channel}.{'d' * 64}".encode()).hexdigest()
if mode == "native":
    launcher = "/app/.venv/bin/domus-ingress"
    os.environ.update(
        SUPERVISOR_TOKEN="disposable-supervisor-token", DOMUS_HA_CALENDAR_DIGEST=digest,
    )
    os.execv(launcher, [
        launcher, "--channel", channel, "--database", str(path), "--instance-id", instance,
        "--public-origin", "http://homeassistant.local:8123",
    ])
else:
    runtime = create_runtime(
        "https://ha.fixture", "https://domus.fixture:8443", instance, channel,
        database=path, ha_calendar_digest=digest,
    )
    try:
        uvicorn.run(
            runtime.app, host="0.0.0.0", port=8443, proxy_headers=False, access_log=False,
            ssl_certfile="/tls/cert.pem", ssl_keyfile="/tls/key.pem",
        )
    finally:
        runtime.close()
"""

_CORE_IMAGE = (
    "ghcr.io/home-assistant/home-assistant:2026.10.4"
    "@sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133"
)


def _calendar_checked(result):
    assert result.returncode == 0, result.stderr
    return result.stdout


def _calendar_core(*arguments, report_directory=None):
    root = Path(__file__).resolve().parents[2]
    instrumentation = ()
    command = ("--entrypoint", "python", _CORE_IMAGE, "/calendar_smoke.py")
    if report_directory is not None:
        package = Path(coverage.__file__).resolve().parent
        instrumentation = (
            "--volume",
            f"{package}:/coverage-lib/coverage:ro",
            "--volume",
            f"{report_directory}:/evidence",
            "--env",
            "PYTHONPATH=/coverage-lib",
            "--env",
            "COVERAGE_CORE=pytrace",
            "--env",
            "COVERAGE_FILE=/evidence/.coverage",
            "--workdir",
            "/config",
        )
        command = (
            "--entrypoint",
            "/bin/sh",
            _CORE_IMAGE,
            "-ec",
            "python -m coverage run --rcfile=/dev/null --branch "
            "--source=custom_components/domus_calendar /calendar_smoke.py && "
            "python -m coverage json --rcfile=/dev/null --fail-under=100 "
            "-o /evidence/coverage.json",
        )
    return _calendar_checked(
        docker(
            "run",
            "--rm",
            *arguments,
            *instrumentation,
            "--volume",
            f"{root / 'custom_components'}:/config/custom_components:ro",
            "--volume",
            f"{root / 'tests/ha/calendar_smoke.py'}:/calendar_smoke.py:ro",
            *command,
        )
    )


def test_calendar_core_uses_both_exact_packaged_compositions(image, tmp_path):
    """Use the native private listener and standalone HTTPS, with no host port mapping."""
    openssl = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            "/CN=domus.fixture",
            "-addext",
            "subjectAltName=DNS:domus.fixture",
            "-keyout",
            str(tmp_path / "key.pem"),
            "-out",
            str(tmp_path / "cert.pem"),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert openssl.returncode == 0, openssl.stderr
    network = "domus-calendar-" + uuid.uuid4().hex
    _calendar_checked(docker("network", "create", "--internal", network))
    names = []
    try:
        for mode, alias in (("native", "local-domus-edge"), ("standalone", "domus.fixture")):
            instance = str(uuid.uuid4())
            channel = "edge" if mode == "native" else "stable"
            url = (
                "http://local-domus-edge:8100" if mode == "native" else "https://domus.fixture:8443"
            )
            name = network + "-" + mode
            names.append(name)
            _calendar_checked(
                docker(
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--network",
                    network,
                    "--network-alias",
                    alias,
                    "--volume",
                    f"{tmp_path}:/tls:ro",
                    "--entrypoint",
                    "/app/.venv/bin/python",
                    image,
                    "-c",
                    _CALENDAR_FIXTURE,
                    mode,
                    instance,
                )
            )
            token = f"{instance}.{channel}.{'d' * 64}"
            if mode == "native":
                ready(name)
                native = (f"DOMUS_NATIVE_URL={url}", f"DOMUS_NATIVE_TOKEN={token}")
            else:
                standalone = (f"DOMUS_STANDALONE_URL={url}", f"DOMUS_STANDALONE_TOKEN={token}")
                _ready_standalone_calendar(name)
        probe = _calendar_core(
            "--network",
            network,
            "--volume",
            f"{tmp_path / 'cert.pem'}:/tls/ca.pem:ro",
            "--env",
            "REQUESTS_CA_BUNDLE=/tls/ca.pem",
            "--env",
            native[0],
            "--env",
            native[1],
            "--env",
            standalone[0],
            "--env",
            standalone[1],
        )
        assert "Home Assistant native calendar acceptance passed" in probe
    finally:
        for name in names:
            docker("rm", "-f", name)
        _calendar_checked(docker("network", "rm", network))


def _ready_standalone_calendar(name):
    deadline = time.monotonic() + 20
    command = (
        "import ssl,urllib.error,urllib.request; "
        "ctx=ssl.create_default_context(cafile='/tls/cert.pem'); "
        "request=urllib.request.Request('https://domus.fixture:8443/api/v1/ha/calendar'); "
        "\ntry: urllib.request.urlopen(request, context=ctx, timeout=1)"
        "\nexcept urllib.error.HTTPError as error: assert error.code == 401"
        "\nelse: raise AssertionError('The dedicated calendar accepted an anonymous read')"
    )
    while True:
        result = docker("exec", name, "/app/.venv/bin/python", "-c", command)
        if result.returncode == 0 or time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    assert result.returncode == 0, result.stderr + docker("logs", name).stderr


def test_calendar_core_read_lifecycle_and_configuration(tmp_path):
    network = "domus-calendar-fixture-" + uuid.uuid4().hex
    _calendar_checked(docker("network", "create", "--internal", network))
    try:
        result = _calendar_core(
            "--network",
            network,
            "--add-host",
            "local-domus-edge:127.0.0.1",
            report_directory=tmp_path,
        )
        assert "Home Assistant native calendar acceptance passed" in result
        report_path = tmp_path / "coverage.json"
        report = json.loads(report_path.read_text())
        assert report["meta"]["branch_coverage"] is True
        assert report["meta"]["version"] == coverage.__version__
        root = Path(__file__).resolve().parents[2]
        source = root / "custom_components/domus_calendar"
        expected = {path.relative_to(root).as_posix() for path in source.rglob("*.py")}
        assert expected and set(report["files"]) == expected
        for name, file in report["files"].items():
            assert not file["excluded_lines"], name
            assert not file["missing_lines"] and not file["missing_branches"], name
            assert file["summary"]["percent_covered"] == 100, name
        assert report["totals"]["percent_covered"] == 100
        if artifact := os.environ.get("DOMUS_CALENDAR_COVERAGE_OUT"):
            copyfile(report_path, artifact)
    finally:
        _calendar_checked(docker("network", "rm", network))
