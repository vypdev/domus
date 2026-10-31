"""The native composed API uses HA Ingress identity, local lease grace and fixed-origin CSRF."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_ingress_sessions import HEADERS, USER, Clock

from domus.composition import ingress
from domus.domain.errors import IdentityRejected, IdentityUnavailable, InvalidInput
from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_config import HAEndpoint

INSTANCE = "047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6"
ORIGIN = "http://homeassistant.local:8123"


class Lookup:
    endpoint = HAEndpoint.supervisor()

    def __init__(self) -> None:
        self.people = {USER: HumanIdentity(USER, True, True, False)}
        self.error = None

    def directory_user(self, token: str, user_id: str) -> HumanIdentity:
        assert token == "private-supervisor-token"
        if self.error:
            raise self.error
        if user_id not in self.people:
            raise IdentityRejected("ha_subject_rejected")
        return self.people[user_id]

    def directory_users(self, token: str, user_ids: tuple[str, ...]) -> tuple[HumanIdentity, ...]:
        return tuple(
            self.directory_user(token, user_id) for user_id in user_ids if user_id in self.people
        )


def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    lookup, clock = Lookup(), Clock()
    monkeypatch.setattr(ingress, "HomeAssistantWebSocket", lambda _: lookup)
    monkeypatch.setattr(ingress, "MonotonicClock", lambda: clock)
    runtime = ingress.create_business_runtime(
        "private-supervisor-token", "edge", tmp_path / "domus.sqlite3", INSTANCE, (ORIGIN,)
    )
    client = TestClient(
        runtime.app,
        base_url=ORIGIN,
        client=("172.30.32.2", 12000),
        headers=dict(HEADERS),
        raise_server_exceptions=False,
    )
    return runtime, client, lookup, clock


def headers(client: TestClient, key: str) -> dict[str, str]:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"], "Idempotency-Key": key}


def setup(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/household",
        json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
        headers=headers(client, "setup"),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_native_session_and_setup_require_no_new_cookie_login_or_submitted_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client, _, _ = fixture(tmp_path, monkeypatch)
    session = client.get("/api/v1/session")
    assert session.status_code == 200 and session.json()["ha_user_id"] == USER
    assert (
        session.json()["access"] == "full" and session.json()["source"] == "home_assistant_ingress"
    )
    assert "set-cookie" not in session.headers and client.cookies == {}
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    created = setup(client)
    assert created["result"]["state"] == "configured"
    assert client.get("/api/v1/household").json()["name"] == "Home"
    assert client.get("/api/v1/operations/" + created["operation_id"]).status_code == 200
    runtime.close()


def test_native_outage_reads_have_original_expiry_and_writes_remain_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client, lookup, clock = fixture(tmp_path, monkeypatch)
    setup(client)
    write = headers(client, "rename")
    lookup.error = IdentityUnavailable("ha_unavailable")
    assert client.get("/api/v1/household").status_code == 200
    assert client.get("/api/v1/session").json()["access"] == "read_only"
    result = client.put(
        "/api/v1/household",
        json={"name": "Changed", "time_zone": "UTC", "expected_revision": 1},
        headers=write,
    )
    assert result.status_code == 503
    clock.value += 3_600_000
    assert client.get("/api/v1/household").status_code == 503
    runtime.close()


@pytest.mark.parametrize("change", ["origin", "forwarded", "csrf", "duplicate_csrf"])
def test_native_write_boundary_cannot_be_replaced_by_forwarding_or_forged_csrf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    runtime, client, _, _ = fixture(tmp_path, monkeypatch)
    write = headers(client, "setup")
    if change in ("origin", "forwarded"):
        write["Origin"] = "https://foreign.invalid"
        if change == "forwarded":
            write.update({"X-Forwarded-Host": "foreign.invalid", "X-Forwarded-Proto": "https"})
    if change == "csrf":
        write["X-CSRF-Token"] = "f" * 64
    final = list(write.items())
    if change == "duplicate_csrf":
        final.append(("X-CSRF-Token", write["X-CSRF-Token"]))
    result = client.post(
        "/api/v1/household",
        json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
        headers=final,
    )
    assert result.status_code == 403
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    runtime.close()


def test_native_rejection_does_not_turn_into_outage_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client, lookup, _ = fixture(tmp_path, monkeypatch)
    setup(client)
    lookup.error = IdentityRejected("ha_subject_rejected")
    assert client.get("/api/v1/household").status_code == 401
    lookup.error = IdentityUnavailable("ha_unavailable")
    assert client.get("/api/v1/household").status_code == 503
    runtime.close()


def test_native_private_listener_rejects_direct_requests_even_with_copied_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _, _, _ = fixture(tmp_path, monkeypatch)
    direct = TestClient(
        runtime.app, base_url=ORIGIN, client=("127.0.0.1", 12000), headers=dict(HEADERS)
    )
    assert direct.get("/api/v1/household").status_code == 403
    assert direct.get("/health").json() == {"status": "ready", "scope": "process"}
    runtime.close()


def test_native_restart_keeps_business_state_but_requires_new_fresh_local_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, client, _, _ = fixture(tmp_path, monkeypatch)
    created = setup(client)
    nonce = headers(client, "setup")
    first.close()
    restarted, client, _, _ = fixture(tmp_path, monkeypatch)
    # Old CSRF cannot bootstrap a new local session after restart.
    response = client.post(
        "/api/v1/household",
        json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
        headers=nonce,
    )
    assert response.status_code == 401
    assert client.get("/api/v1/authorization").json()["state"] == "active"
    assert setup(client) == created
    restarted.close()


@pytest.mark.parametrize(
    "origins",
    [
        (),
        (ORIGIN, ORIGIN),
        ("https://bad.example/path",),
        tuple(f"https://ha{n}.example" for n in range(5)),
    ],
)
def test_bad_native_origins_fail_before_creating_business_database(
    tmp_path: Path, origins: tuple
) -> None:
    path = tmp_path / "domus.sqlite3"
    with pytest.raises(InvalidInput):
        ingress.create_business_runtime("private-supervisor-token", "edge", path, INSTANCE, origins)
    assert not path.exists()


def test_native_root_schema_and_method_bounds_are_verified_without_leaking_cookies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client, _, _ = fixture(tmp_path, monkeypatch)
    root = client.get("/")
    assert root.status_code == 200 and "No additional login is required" in root.text
    assert "set-cookie" not in root.headers and "private-supervisor-token" not in root.text
    schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert "/api/v1/household" in schema.json()["paths"]
    assert (
        schema.json()["components"]["securitySchemes"]["HomeAssistantIngress"]["name"]
        == "ingress_session"
    )
    assert client.delete("/api/v1/household").status_code == 403
    assert client.post("/health", headers={"Origin": ORIGIN}).status_code == 403
    assert client.get("/missing").status_code == 404
    assert client.get("/api/v1/session?actor=forged").status_code == 422
    runtime.close()


def test_native_missing_csrf_and_bad_request_body_never_create_a_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client, _, _ = fixture(tmp_path, monkeypatch)
    client.get("/api/v1/session")
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    assert (
        client.post(
            "/api/v1/household",
            json=payload,
            headers={"Origin": ORIGIN, "Idempotency-Key": "setup"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/household",
            json={**payload, "actor_id": "private-forgery"},
            headers=headers(client, "setup"),
        ).status_code
        == 422
    )
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    runtime.close()


def test_native_response_failure_after_commit_preserves_uncertainty_and_safe_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.entrypoints import household_http

    runtime, client, _, _ = fixture(tmp_path, monkeypatch)
    original = household_http._receipt

    def fail(*_: object):
        raise RuntimeError("private-native-response-detail")

    write = headers(client, "setup")
    monkeypatch.setattr(household_http, "_receipt", fail)
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    response = client.post("/api/v1/household", json=payload, headers=write)
    assert response.status_code == 500 and "could not confirm" in response.json()["message"]
    assert "private-native-response-detail" not in response.text
    assert "No household change was made" not in response.text
    monkeypatch.setattr(household_http, "_receipt", original)
    assert client.post("/api/v1/household", json=payload, headers=write).status_code == 200
    runtime.close()


@pytest.mark.parametrize(
    "options", [["--database", "unused"], ["--instance-id", INSTANCE], ["--public-origin", ORIGIN]]
)
def test_partial_native_persistent_configuration_is_rejected_before_listening(
    monkeypatch: pytest.MonkeyPatch, options: list[str]
) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "private-supervisor-token")
    assert ingress.main(["--channel", "edge"] + options) == 2


def test_native_cli_wires_persistent_runtime_and_always_closes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "private-supervisor-token")
    captured = []
    original = ingress.create_business_runtime

    def create(*args, **kwargs):
        runtime = original(*args, **kwargs)
        captured.append(runtime)
        return runtime

    def run(app, **options):
        assert options["proxy_headers"] is False and options["access_log"] is False
        assert "/api/v1/household" in app.openapi()["paths"]
        raise RuntimeError("listener stopped")

    monkeypatch.setattr(ingress, "create_business_runtime", create)
    monkeypatch.setattr(ingress.uvicorn, "run", run)
    with pytest.raises(RuntimeError, match="listener stopped"):
        ingress.main(
            [
                "--channel",
                "edge",
                "--database",
                str(tmp_path / "domus.sqlite3"),
                "--instance-id",
                INSTANCE,
                "--public-origin",
                ORIGIN,
            ]
        )
    assert captured[0].sessions._closed


def test_selected_ordinary_ha_administrator_can_manage_members_using_only_own_domus_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, client, lookup, _ = fixture(tmp_path, monkeypatch)
    created = setup(client)
    founder = created["result"]["member_id"]
    participant = "b" * 32
    lookup.people[participant] = HumanIdentity(participant, False, True, False)

    def switch(user_id: str, cookie_value: str) -> None:
        client.headers["X-Remote-User-Id"] = user_id
        client.headers["Cookie"] = "ingress_session=" + cookie_value * 128

    switch(participant, "d")
    joined = client.post(
        "/api/v1/members/enrollment", json={"expected_revision": 0}, headers=headers(client, "join")
    )
    assert joined.status_code == 200 and joined.json()["result"]["status"] == "pending"
    member_id = joined.json()["result"]["member_id"]
    assert client.get("/api/v1/household").status_code == 403
    switch(USER, "c")
    activated = client.put(
        "/api/v1/members/" + member_id,
        json={"expected_revision": 1, "role": "viewer", "status": "active"},
        headers=headers(client, "activate"),
    )
    assert activated.status_code == 200
    selected = client.put(
        "/api/v1/policy",
        json={
            "expected_revision": 1,
            "mapping_mode": "selected_ha_user",
            "target_ha_user_id": participant,
        },
        headers=headers(client, "select"),
    )
    assert selected.status_code == 200
    assert client.get("/api/v1/authorization").json()["effective_role"] == "viewer"
    switch(participant, "d")
    assert client.get("/api/v1/session").json()["ha_administrator"] is False
    assert client.get("/api/v1/authorization").json()["effective_role"] == "administrator"
    changed = client.put(
        "/api/v1/members/" + founder,
        json={"expected_revision": 1, "role": "adult", "status": "active"},
        headers=headers(client, "edit-founder"),
    )
    assert changed.status_code == 200 and changed.json()["result"]["role"] == "adult"
    runtime.close()


def test_published_native_openapi_matches_actual_private_session_and_household_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    runtime, client, _, _ = fixture(tmp_path, monkeypatch)
    actual = client.get("/api/v1/openapi.json").json()
    reference = json.loads(
        (
            Path(__file__).resolve().parents[2] / "docs/contracts/native-household-api.openapi.json"
        ).read_text()
    )
    assert actual["paths"] == reference["paths"]
    assert actual["components"] == reference["components"]
    runtime.close()


def test_owned_native_runtime_restarts_with_same_uuid_household_and_original_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    lookup = Lookup()
    monkeypatch.setattr(ingress, "HomeAssistantWebSocket", lambda _: lookup)

    def start():
        runtime = ingress.create_owned_runtime("private-supervisor-token", "edge", root, (ORIGIN,))
        client = TestClient(
            runtime.app, base_url=ORIGIN, client=("172.30.32.2", 12000), headers=dict(HEADERS)
        )
        return runtime, client

    first, client = start()
    original = setup(client)
    identity = first.storage.installation
    first.close()
    second, client = start()
    assert second.storage.installation == identity
    assert client.get("/api/v1/household").json()["name"] == "Home"
    assert setup(client) == original
    second.close()


def test_owned_runtime_closes_directory_lease_if_later_composition_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.domain.errors import StorageFailure
    from domus.infrastructure.owned_storage import open_storage

    root = tmp_path / "owned"
    root.mkdir(mode=0o700)

    def fail(*args):
        raise StorageFailure("injected_composition_failure")

    monkeypatch.setattr(ingress, "_compose_business", fail)
    with pytest.raises(StorageFailure, match="injected_composition_failure"):
        ingress.create_owned_runtime("private-supervisor-token", "edge", root, (ORIGIN,))
    open_storage(root, "edge").close()


@pytest.mark.parametrize(
    "token,origins",
    [("bad token", (ORIGIN,)), ("private-supervisor-token", ("http://invalid/path",))],
)
def test_owned_runtime_rejects_configuration_before_creating_persistent_records(
    tmp_path: Path, token: str, origins: tuple[str, ...]
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    with pytest.raises(InvalidInput):
        ingress.create_owned_runtime(token, "edge", root, origins)
    assert list(root.iterdir()) == []


def test_owned_native_cli_keeps_directory_locked_until_listener_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.domain.errors import StorageBusy
    from domus.infrastructure.owned_storage import open_storage

    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "private-supervisor-token")

    def run(app, **kwargs):
        with pytest.raises(StorageBusy, match="installation_in_use"):
            open_storage(root, "edge")
        assert "/api/v1/household" in app.openapi()["paths"]

    monkeypatch.setattr(ingress.uvicorn, "run", run)
    assert (
        ingress.main(
            ["--channel", "edge", "--data-directory", str(root), "--public-origin", ORIGIN]
        )
        == 0
    )
    open_storage(root, "edge").close()


@pytest.mark.parametrize(
    "options",
    [[], ["--instance-id", INSTANCE], ["--instance-id", INSTANCE, "--public-origin", ORIGIN]],
)
def test_owned_cli_rejects_incomplete_or_competing_identity_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, options: list[str]
) -> None:
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "private-supervisor-token")
    assert ingress.main(["--channel", "edge", "--data-directory", str(root), *options]) == 2
    assert list(root.iterdir()) == []


def test_owned_runtime_initializes_sqlite_once_and_restarts_in_existing_only_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.infrastructure.sqlite import SQLiteDatabase

    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    original = SQLiteDatabase.initialize
    modes = []

    def initialize(self, *, require_existing=False):
        modes.append(require_existing)
        return original(self, require_existing=require_existing)

    monkeypatch.setattr(SQLiteDatabase, "initialize", initialize)
    ingress.create_owned_runtime("private-supervisor-token", "edge", root, (ORIGIN,)).close()
    ingress.create_owned_runtime("private-supervisor-token", "edge", root, (ORIGIN,)).close()
    assert modes == [False, True]
