"""Both deployment compositions expose human recovery; approval remains a console operation."""

import io
from pathlib import Path

import pytest
from test_recovery_commands import Clock
from test_recovery_console import Terminal

from domus.composition import admin, household, ingress
from domus.domain.identity import HumanIdentity
from domus.infrastructure.sqlite import SQLiteDatabase

TARGET = "b" * 32


def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> tuple:
    utc = Clock()
    monkeypatch.setattr(admin, "SystemClock", lambda: utc)
    if mode == "native":
        from test_native_http import fixture, headers

        monkeypatch.setattr(ingress, "SystemClock", lambda: utc)
        runtime, client, lookup, lease = fixture(tmp_path, monkeypatch)
        store = SQLiteDatabase(tmp_path / "domus.sqlite3", runtime.sessions.installation)

        def switch(user_id=TARGET):
            lookup.people[user_id] = HumanIdentity(user_id, True, True, False)
            client.headers["X-Remote-User-Id"] = user_id
            client.headers["Cookie"] = (
                "ingress_session=" + ("d" if user_id == TARGET else "e") * 128
            )

        def unavailable():
            from domus.domain.errors import IdentityUnavailable

            lookup.error = IdentityUnavailable("ha_unavailable")
    else:
        from test_auth_server import INSTANCE
        from test_household_runtime import headers, runtime_at

        from domus.domain.storage import Installation

        monkeypatch.setattr(household, "SystemClock", lambda: utc)
        runtime, client = runtime_at(tmp_path / "domus.sqlite3", monkeypatch)
        store = SQLiteDatabase(tmp_path / "domus.sqlite3", Installation(INSTANCE, "edge"))
        cookie = runtime.app.openapi()["components"]["securitySchemes"]["DomusSession"]["name"]

        def switch(user_id=TARGET):
            runtime.identity.socket.human = HumanIdentity(user_id, True, True, False)
            runtime.identity.sign_in("code", "v" * 43, "session-" + user_id, 100, 3600100)
            client.cookies.set(cookie, "session-" + user_id)

        def unavailable():
            from domus.domain.errors import IdentityUnavailable

            runtime.identity.socket.error = IdentityUnavailable("ha_unavailable")

    response = client.post(
        "/api/v1/household",
        json={
            "name": "Home",
            "time_zone": "UTC",
            "mapping_mode": "setup_administrator",
            "expected_revision": 0,
        },
        headers=headers(client, "setup"),
    )
    assert response.status_code == 200, response.text
    switch()
    return runtime, client, store, headers, switch, unavailable, utc


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_actual_http_and_terminal_journey_needs_both_authorities_and_preserves_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, client, store, headers, switch, _, _ = deployment(tmp_path, monkeypatch, mode)
    try:
        assert client.get("/api/v1/authorization").json()["state"] == "not_enrolled"
        response = client.post(
            "/api/v1/recovery/requests",
            json={"expected_revision": 0},
            headers=headers(client, "request"),
        )
        assert response.status_code == 200, response.text
        request_id = response.json()["result"]["request_id"]
        path = "/api/v1/recovery/requests/" + request_id
        assert client.get(path).json()["state"] == "pending"
        assert (
            client.post(
                path + "/complete",
                json={"expected_revision": 1},
                headers=headers(client, "complete"),
            ).status_code
            == 409
        )
        assert (
            client.post(
                path + "/approve",
                json={"expected_revision": 1},
                headers=headers(client, "forged-console"),
            ).status_code
            == 404
        )
        assert (
            admin.main(
                [
                    "--channel",
                    "edge",
                    "--database",
                    str(store.path),
                    "--instance-id",
                    store.installation.instance_id,
                    "recovery",
                    "approve",
                    request_id,
                ],
                input_stream=Terminal(f"APPROVE {request_id} {TARGET}\n"),
                output_stream=Terminal(),
                error_stream=io.StringIO(),
            )
            == 0
        )
        completed = client.post(
            path + "/complete", json={"expected_revision": 2}, headers=headers(client, "complete")
        )
        assert completed.status_code == 200, completed.text
        assert client.get("/api/v1/authorization").json()["effective_role"] == "administrator"
        assert client.get("/api/v1/policy").json()["mapping"]["target_ha_user_id"] == "a" * 32
        assert client.get(path).json()["state"] == "consumed"
        assert (
            client.get("/api/v1/operations/" + completed.json()["operation_id"]).status_code == 200
        )
        assert (
            client.post(
                path + "/complete",
                json={"expected_revision": 2},
                headers=headers(client, "complete"),
            ).json()
            == completed.json()
        )
        switch("c" * 32)
        assert client.get(path).status_code == 404
    finally:
        runtime.close()


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_strict_recovery_routes_reject_forged_target_and_allow_owner_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, client, _, headers, _, _, _ = deployment(tmp_path, monkeypatch, mode)
    try:
        assert (
            client.post(
                "/api/v1/recovery/requests",
                json={"expected_revision": 0, "target_ha_user_id": "c" * 32},
                headers=headers(client, "forged-target"),
            ).status_code
            == 422
        )
        first = client.post(
            "/api/v1/recovery/requests",
            json={"expected_revision": 0},
            headers=headers(client, "request"),
        ).json()
        path = "/api/v1/recovery/requests/" + first["result"]["request_id"]
        assert client.get(path + "?target_ha_user_id=" + "c" * 32).status_code == 422
        canceled = client.post(
            path + "/cancel", json={"expected_revision": 1}, headers=headers(client, "cancel")
        )
        assert canceled.status_code == 200 and canceled.json()["result"]["state"] == "canceled"
        assert (
            client.post(
                path + "/complete",
                json={"expected_revision": 2},
                headers=headers(client, "complete"),
            ).status_code
            == 409
        )
    finally:
        runtime.close()


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_recovery_status_has_local_outage_grace_and_writes_remain_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, client, _, headers, _, unavailable, _ = deployment(tmp_path, monkeypatch, mode)
    try:
        created = client.post(
            "/api/v1/recovery/requests",
            json={"expected_revision": 0},
            headers=headers(client, "request"),
        ).json()
        path = "/api/v1/recovery/requests/" + created["result"]["request_id"]
        command_headers = headers(client, "cancel")
        unavailable()
        assert client.get(path).status_code == 200
        assert (
            client.post(
                path + "/cancel", json={"expected_revision": 1}, headers=command_headers
            ).status_code
            == 503
        )
    finally:
        runtime.close()
