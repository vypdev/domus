"""Standalone composition opens owned SQLite and retains household state across restart."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_auth_server import INSTANCE
from test_standalone_sessions import fixture as identity_fixture

from domus.composition import server
from domus.domain.errors import DatabaseRejected, InvalidInput, StorageBusy
from domus.infrastructure.owned_storage import attach_storage, open_storage


def runtime_at(
    path: Path, monkeypatch: pytest.MonkeyPatch, *, channel: str = "edge", owned: bool = False
) -> tuple:
    _, oauth, socket, clock = identity_fixture()
    socket.human = replace(socket.human, is_administrator=True)
    monkeypatch.setattr(server, "HomeAssistantOAuth", lambda _: oauth)
    monkeypatch.setattr(server, "HomeAssistantWebSocket", lambda _: socket)
    monkeypatch.setattr(server, "MonotonicClock", lambda: clock)
    if owned:
        runtime = server.create_owned_runtime(
            "http://ha.local", "https://domus.example", channel, path
        )
    else:
        runtime = server.create_runtime(
            "http://ha.local", "https://domus.example", INSTANCE, channel, database=path
        )
    cookie = runtime.app.openapi()["components"]["securitySchemes"]["DomusSession"]["name"]
    runtime.identity.sign_in("code", "v" * 43, "test-session", 100, 3_600_100)
    client = TestClient(runtime.app, base_url="https://domus.example", follow_redirects=False)
    client.cookies.set(cookie, "test-session")
    return runtime, client


def headers(client: TestClient, key: str) -> dict[str, str]:
    return {
        "Origin": "https://domus.example",
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"],
        "Idempotency-Key": key,
    }


def test_actual_runtime_wires_all_household_services_without_implicit_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client = runtime_at(tmp_path / "domus.sqlite3", monkeypatch)
    try:
        assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
        assert (
            client.post(
                "/api/v1/household",
                json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
                headers=headers(client, "setup"),
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/v1/household",
                json={"name": "Updated", "time_zone": "Europe/Madrid", "expected_revision": 1},
                headers=headers(client, "rename"),
            ).status_code
            == 200
        )
        member = client.get("/api/v1/members").json()["members"][0]
        assert (
            client.put(
                "/api/v1/members/" + member["member_id"],
                json={"expected_revision": 1, "role": "viewer", "status": "active"},
                headers=headers(client, "member"),
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/v1/policy",
                json={
                    "expected_revision": 1,
                    "mapping_mode": "setup_administrator",
                    "target_ha_user_id": "a" * 32,
                },
                headers=headers(client, "policy"),
            ).status_code
            == 200
        )
        assert client.get("/api/v1/household").json()["name"] == "Updated"
    finally:
        assert runtime.close() == (1, 0)


def test_restart_reopens_same_household_and_scoped_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "domus.sqlite3"
    runtime, client = runtime_at(path, monkeypatch)
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    try:
        original = client.post(
            "/api/v1/household", json=payload, headers=headers(client, "setup")
        ).json()
    finally:
        runtime.close()
    restarted, client = runtime_at(path, monkeypatch)
    try:
        assert client.get("/api/v1/authorization").json()["state"] == "active"
        assert (
            client.post("/api/v1/household", json=payload, headers=headers(client, "setup")).json()
            == original
        )
    finally:
        restarted.close()


def test_same_database_cannot_be_adopted_by_the_other_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "domus.sqlite3"
    runtime, _ = runtime_at(path, monkeypatch)
    runtime.close()
    before = path.read_bytes()
    with pytest.raises(DatabaseRejected):
        runtime_at(path, monkeypatch, channel="stable")
    assert path.read_bytes() == before


def test_cli_database_option_activates_household_routes_without_starting_an_unreviewed_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_auth_server import arguments

    captured = []

    def run(app: object, **options: object) -> None:
        captured.append(app.openapi())
        assert options["proxy_headers"] is False and options["host"] == "127.0.0.1"

    monkeypatch.setattr(server.uvicorn, "run", run)
    assert server.main(arguments() + ["--database", str(tmp_path / "domus.sqlite3")]) == 0
    assert "/api/v1/household" in captured[0]["paths"]
    assert (tmp_path / "domus.sqlite3").exists()


def test_owned_standalone_restart_preserves_identity_household_and_replay_not_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    first, client = runtime_at(root, monkeypatch, owned=True)
    identity = first.storage.installation
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    try:
        assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
        original = client.post(
            "/api/v1/household", json=payload, headers=headers(client, "setup")
        ).json()
        with pytest.raises(StorageBusy):
            server.create_owned_runtime("http://ha.local", "https://domus.example", "edge", root)
        with closing(attach_storage(root, "edge")) as attached:
            assert attached.installation == identity
    finally:
        assert first.close() == (1, 0)
    second = server.create_owned_runtime("http://ha.local", "https://domus.example", "edge", root)
    try:
        assert second.storage.installation == identity
        assert (
            TestClient(second.app, base_url="https://domus.example")
            .get("/api/v1/session")
            .status_code
            == 401
        )
    finally:
        second.close()
    third, client = runtime_at(root, monkeypatch, owned=True)
    try:
        assert third.storage.installation == identity
        assert client.get("/api/v1/household").json()["name"] == "Home"
        assert (
            client.post("/api/v1/household", json=payload, headers=headers(client, "setup")).json()
            == original
        )
    finally:
        third.close()


@pytest.mark.parametrize(
    "ha,public,channel",
    [
        ("http://ha.local/path", "https://domus.example", "edge"),
        ("http://ha.local", "https://domus.example/path", "edge"),
        ("http://ha.local", "http://127.0.0.1:8099", "edge"),
        ("http://ha.local", "https://domus.example", "other"),
    ],
)
def test_owned_standalone_rejects_configuration_before_storage_mutation(
    tmp_path: Path, ha: str, public: str, channel: str
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    with pytest.raises(InvalidInput):
        server.create_owned_runtime(ha, public, channel, root)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_owned_standalone_releases_storage_on_late_composition_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[BaseException]
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)

    def fail(*args):
        raise error("injected composition failure")

    monkeypatch.setattr(server, "_compose", fail)
    with pytest.raises(error, match="injected composition failure"):
        server.create_owned_runtime("http://ha.local", "https://domus.example", "edge", root)
    open_storage(root, "edge").close()


def test_owned_standalone_releases_lease_even_when_credential_shutdown_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    runtime = server.create_owned_runtime("http://ha.local", "https://domus.example", "edge", root)

    def fail():
        raise RuntimeError("injected shutdown failure")

    monkeypatch.setattr(runtime.identity, "shutdown", fail)
    with pytest.raises(RuntimeError, match="injected shutdown failure"):
        runtime.close()
    open_storage(root, "edge").close()


def test_owned_standalone_initializes_once_and_keeps_channel_and_cookie_names_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.infrastructure.sqlite import SQLiteDatabase

    initialize = SQLiteDatabase.initialize
    modes = []

    def capture(self, *, require_existing=False):
        modes.append(require_existing)
        return initialize(self, require_existing=require_existing)

    monkeypatch.setattr(SQLiteDatabase, "initialize", capture)
    identities, names = [], []
    for channel in ("edge", "stable"):
        root = tmp_path / channel
        root.mkdir(mode=0o700)
        for _ in range(2):
            runtime = server.create_owned_runtime(
                "http://ha.local", "https://domus.example", channel, root
            )
            identities.append(runtime.storage.installation)
            names.append(
                runtime.app.openapi()["components"]["securitySchemes"]["DomusSession"]["name"]
            )
            runtime.close()
    assert modes == [False, True, False, True]
    assert identities[0] == identities[1] and identities[2] == identities[3]
    assert identities[0].instance_id != identities[2].instance_id
    assert names[0] == names[1] and names[2] == names[3] and names[0] != names[2]
    before = (tmp_path / "edge" / "domus.sqlite3").read_bytes()
    with pytest.raises(DatabaseRejected, match="installation_channel_mismatch"):
        server.create_owned_runtime(
            "http://ha.local", "https://domus.example", "stable", tmp_path / "edge"
        )
    assert (tmp_path / "edge" / "domus.sqlite3").read_bytes() == before


def owned_arguments(root: Path) -> list[str]:
    return [
        "--ha-url",
        "http://ha.local",
        "--public-origin",
        "http://127.0.0.1:8099",
        "--channel",
        "edge",
        "--development-http",
        "--data-directory",
        str(root),
    ]


@pytest.mark.parametrize("failure", [False, True])
def test_owned_standalone_cli_holds_storage_through_listener_and_releases_on_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    ran = []

    def run(app, **options):
        with pytest.raises(StorageBusy):
            open_storage(root, "edge")
        assert "/api/v1/household" in app.openapi()["paths"]
        assert options["host"] == "127.0.0.1" and options["proxy_headers"] is False
        ran.append(True)
        if failure:
            raise RuntimeError("injected listener failure")

    monkeypatch.setattr(server.uvicorn, "run", run)
    if failure:
        with pytest.raises(RuntimeError, match="injected listener failure"):
            server.main(owned_arguments(root))
    else:
        assert server.main(owned_arguments(root)) == 0
    assert ran == [True]
    open_storage(root, "edge").close()


@pytest.mark.parametrize(
    "mode", ["preview_missing_id", "file_missing_id", "owned_with_id", "owned_with_empty_id"]
)
def test_standalone_cli_refuses_missing_or_competing_identity_before_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    options = owned_arguments(root)
    if mode.startswith("owned_with"):
        options += ["--instance-id", "" if mode == "owned_with_empty_id" else INSTANCE]
    else:
        options = options[:-2]
        if mode == "file_missing_id":
            options += ["--database", str(root / "domus.sqlite3")]
    monkeypatch.setattr(
        server.uvicorn, "run", lambda *args, **kwargs: pytest.fail("listener started")
    )
    assert server.main(options) == 2
    assert list(root.iterdir()) == []


def test_standalone_cli_rejects_both_data_selections_at_parser_boundary(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        server.main(owned_arguments(tmp_path) + ["--database", str(tmp_path / "domus.sqlite3")])
    assert error.value.code == 2
