"""Production compositions use real sessions/SQLite with explicit fake HA transports."""

from dataclasses import dataclass, replace

import pytest
from fastapi.testclient import TestClient
from test_native_http import INSTANCE, ORIGIN
from test_native_http import fixture as native_fixture
from test_standalone_sessions import fixture as identity_fixture

from domus.composition import server
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.infrastructure.sqlite import SQLiteDatabase


@dataclass
class API:
    client: object
    runtime: object
    store: object
    source: object
    clock: object
    mode: str
    origin: str

    def headers(self, key="command"):
        response = self.client.get("/api/v1/auth/csrf")
        assert response.status_code == 200, response.text
        return {
            "Origin": self.origin,
            "X-CSRF-Token": response.json()["csrf_token"],
            "Idempotency-Key": key,
        }

    def user(self, user_id, administrator=False):
        human = HumanIdentity(user_id, administrator, True, False)
        if self.mode == "native":
            self.source.people[user_id] = human
            self.client.headers["X-Remote-User-Id"] = user_id
            self.client.headers["Cookie"] = "ingress_session=" + user_id * 4
        else:
            self.source.human = human
            session = "session-" + user_id
            if self.runtime.identity.get(session) is None:
                self.runtime.identity.sign_in("code", "v" * 43, session, 100, 3_600_100)
            name = self.runtime.app.openapi()["components"]["securitySchemes"]["DomusSession"][
                "name"
            ]
            self.client.cookies.set(name, session)


@pytest.fixture(params=["native", "standalone"])
def api(tmp_path, monkeypatch, request):
    if request.param == "native":
        runtime, client, source, clock = native_fixture(tmp_path, monkeypatch)
        store = SQLiteDatabase(tmp_path / "domus.sqlite3", Installation(INSTANCE, "edge"))
        value = API(client, runtime, store, source, clock, "native", ORIGIN)
    else:
        _, oauth, source, clock = identity_fixture()
        source.human = replace(source.human, is_administrator=True)
        monkeypatch.setattr(server, "HomeAssistantOAuth", lambda _: oauth)
        monkeypatch.setattr(server, "HomeAssistantWebSocket", lambda _: source)
        monkeypatch.setattr(server, "MonotonicClock", lambda: clock)
        path = tmp_path / "domus.sqlite3"
        runtime = server.create_runtime(
            "http://ha.local", "https://domus.example", INSTANCE, "edge", database=path
        )
        client = TestClient(
            runtime.app, base_url="https://domus.example", raise_server_exceptions=False
        )
        store = SQLiteDatabase(path, Installation(INSTANCE, "edge"))
        value = API(client, runtime, store, source, clock, "standalone", "https://domus.example")
        value.user("a" * 32, True)
    result = value.client.post(
        "/api/v1/household",
        json={"expected_revision": 0, "name": "Home", "time_zone": "UTC"},
        headers=value.headers("setup"),
    )
    assert result.status_code == 200, result.text
    try:
        yield value
    finally:
        runtime.close()


def test_business_compositions_expose_task_services_without_a_second_login(api):
    response = api.client.get("/api/v1/tasks/policy")
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 0
    assert api.client.get("/api/v1/tasks/definitions").json()["items"] == []
    with api.store.read() as unit:
        assert unit.tasks.policy("home") is None and len(unit.audit.entries("home")) == 1


def test_unwired_native_factory_does_not_advertise_task_capability():
    from test_ingress_sessions import Clock

    from domus.entrypoints.native_http import create_native_app

    def unused_context(_):
        pytest.fail("No business request should resolve a session in this registration assertion")

    app = create_native_app(
        unused_context, (ORIGIN,), "edge", Clock(), correlation=lambda: "cor_registration"
    )
    paths = app.openapi()["paths"]
    assert "/api/v1/household" in paths and not any(
        path.startswith("/api/v1/tasks") for path in paths
    )
