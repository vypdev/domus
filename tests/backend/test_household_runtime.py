"""Standalone composition opens owned SQLite and retains household state across restart."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_auth_server import INSTANCE
from test_standalone_sessions import fixture as identity_fixture

from domus.composition import server
from domus.domain.errors import DatabaseRejected


def runtime_at(path: Path, monkeypatch: pytest.MonkeyPatch, *, channel: str = "edge") -> tuple:
    _, oauth, socket, clock = identity_fixture()
    socket.human = replace(socket.human, is_administrator=True)
    monkeypatch.setattr(server, "HomeAssistantOAuth", lambda _: oauth)
    monkeypatch.setattr(server, "HomeAssistantWebSocket", lambda _: socket)
    monkeypatch.setattr(server, "MonotonicClock", lambda: clock)
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
