"""Real ASGI, sessions and SQLite exercise command DTOs, idempotency and disclosure boundaries."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_auth_http import login
from test_household_commands import Directory, Identifiers, Zones
from test_standalone_sessions import fixture as identity_fixture

from domus.application.authentication import Authentication
from domus.application.household_commands import HouseholdCommands
from domus.application.household_queries import HouseholdQueries
from domus.application.member_commands import MemberCommands
from domus.application.policy_commands import PolicyCommands
from domus.application.recovery_commands import RecoveryCommands, RecoveryQueries
from domus.application.sessions import SessionGuard
from domus.composition.tasks import task_contexts
from domus.domain.errors import IdentityUnavailable
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.entrypoints.entry_context import EntryHTTPContext
from domus.entrypoints.household_http import HouseholdHTTPContext
from domus.entrypoints.http import HTTPSettings, create_app
from domus.infrastructure.memory_attempts import MemoryLoginAttempts
from domus.infrastructure.session_access import SessionActor
from domus.infrastructure.sqlite import SQLiteDatabase


class Entropy:
    count = 0

    def new(self) -> str:
        self.count += 1
        return "v" * 43 if self.count % 4 == 2 else f"{self.count:043d}"


def fixture(tmp_path: Path) -> tuple:
    identity, oauth, socket, clock = identity_fixture()
    socket.human = replace(socket.human, is_administrator=True)
    flow = Authentication(MemoryLoginAttempts(), identity, clock, Entropy())
    settings = HTTPSettings("https://domus.example", "domus-edge", b"k" * 32)
    guard = SessionGuard(identity, identity, clock)
    store = SQLiteDatabase(
        tmp_path / "database", Installation("047cc6fb-dfb0-4fa4-b3c3-e0fe54d116b6", "edge")
    )
    store.initialize()
    directory, identifiers = Directory(), Identifiers()
    directory.people["b" * 32] = HumanIdentity("b" * 32, False, True, False)

    def context(session_id: str) -> HouseholdHTTPContext:
        actor = SimpleNamespace(current=lambda: guard.write(session_id))
        return HouseholdHTTPContext(
            lambda: HouseholdQueries(store, guard.read(session_id)),
            HouseholdCommands(store, actor, directory, Zones(), clock, identifiers),
            MemberCommands(store, actor, directory, clock, identifiers),
            PolicyCommands(store, actor, directory, clock, identifiers),
            RecoveryCommands(store, actor, store.installation, clock, identifiers),
            lambda: RecoveryQueries(store, guard.read(session_id), store.installation, clock),
        )

    task_factory = task_contexts(store, store.installation)
    app = create_app(
        flow,
        guard,
        identity,
        settings,
        correlation=lambda: "cor_api",
        entry=EntryHTTPContext(store.installation, "standalone", clock, clock, True),
        household_context=context,
        task_context=lambda session_id: task_factory(SessionActor(guard, session_id)),
    )
    client = TestClient(
        app, base_url=settings.origin, follow_redirects=False, raise_server_exceptions=False
    )
    return client, store, socket, settings, directory, clock


def write_headers(client: TestClient, key: str = "command") -> dict[str, str]:
    return {
        "Origin": "https://domus.example",
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"],
        "Idempotency-Key": key,
    }


def setup(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/household",
        json={"name": "Home", "time_zone": "UTC", "expected_revision": 0},
        headers=write_headers(client, "setup"),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_explicit_setup_authorization_queries_and_original_receipt(tmp_path: Path) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    assert client.get("/api/v1/authorization").status_code == 401
    login(client)
    assert client.get("/api/v1/authorization").json()["state"] == "unconfigured"
    with store.read() as unit:
        assert unit.households.current() is None
    created = setup(client)
    assert created["state"] == "committed"
    assert created["result"]["state"] == "configured"
    assert client.get("/api/v1/household").json()["name"] == "Home"
    access = client.get("/api/v1/authorization").json()
    assert access["state"] == "active" and access["effective_role"] == "administrator"
    operation = client.get("/api/v1/operations/" + created["operation_id"])
    assert operation.status_code == 200 and operation.json()["delivery"] == "pending"
    assert operation.json()["result"] == created["result"]
    assert setup(client) == created
    assert client.get("/api/v1/policy").json()["revision"] == 1
    assert len(client.get("/api/v1/members").json()["members"]) == 1


def test_household_and_policy_edits_use_revisions_and_durable_idempotency(tmp_path: Path) -> None:
    client, _, _, _, _, _ = fixture(tmp_path)
    login(client)
    setup(client)
    headers = write_headers(client, "rename")
    payload = {"name": "Renamed", "time_zone": "Europe/Madrid", "expected_revision": 1}
    result = client.put("/api/v1/household", json=payload, headers=headers)
    assert result.status_code == 200
    assert client.put("/api/v1/household", json=payload, headers=headers).json() == result.json()
    assert (
        client.put(
            "/api/v1/household", json=payload, headers=write_headers(client, "stale")
        ).status_code
        == 409
    )
    policy = client.put(
        "/api/v1/policy",
        json={
            "expected_revision": 1,
            "mapping_mode": "setup_administrator",
            "target_ha_user_id": "a" * 32,
            "adjustments": [{"role": "viewer", "permission": "shopping.request", "allow": True}],
        },
        headers=write_headers(client, "policy"),
    )
    assert policy.status_code == 200, policy.text
    assert client.get("/api/v1/policy").json()["mapping"]["mode"] == "setup_administrator"


def test_pending_enrollment_and_admin_activation_preserve_bound_actor(tmp_path: Path) -> None:
    client, _, socket, _, _, _ = fixture(tmp_path)
    login(client)
    setup(client)
    admin_human = socket.human
    socket.human = HumanIdentity("b" * 32, False, True, False)
    socket.human = admin_human
    csrf = write_headers(client)
    assert client.post("/api/v1/auth/logout", json={}, headers=csrf).status_code == 200
    socket.human = HumanIdentity("b" * 32, False, True, False)
    login(client)
    joined = client.post(
        "/api/v1/members/enrollment",
        json={"expected_revision": 0},
        headers=write_headers(client, "join"),
    )
    assert joined.status_code == 200 and joined.json()["result"]["status"] == "pending"
    member_id = joined.json()["result"]["member_id"]
    assert client.get("/api/v1/household").status_code == 403
    assert client.get("/api/v1/authorization").json()["state"] == "pending"
    csrf = write_headers(client)
    assert client.post("/api/v1/auth/logout", json={}, headers=csrf).status_code == 200
    socket.human = admin_human
    login(client)
    changed = client.put(
        "/api/v1/members/" + member_id,
        json={
            "expected_revision": 1,
            "role": "restricted",
            "status": "active",
            "exceptions": [{"permission": "shopping.request", "allow": False}],
        },
        headers=write_headers(client, "activate"),
    )
    assert changed.status_code == 200 and changed.json()["result"]["status"] == "active"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Home", "time_zone": "UTC", "expected_revision": 0, "actor_id": "private-forgery"},
        {"name": "Home", "time_zone": "UTC", "expected_revision": True},
        {"name": "Home", "time_zone": "Not/AZone", "expected_revision": 0},
    ],
)
def test_invalid_or_forged_setup_is_safe_and_leaves_no_records(tmp_path: Path, body: dict) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    response = client.post("/api/v1/household", json=body, headers=write_headers(client))
    assert response.status_code == 422
    assert "private-forgery" not in response.text
    with store.read() as unit:
        assert unit.households.current() is None and unit.outbox.pending() == ()


def test_writes_require_origin_csrf_unique_idempotency_and_strict_empty_query(
    tmp_path: Path,
) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    assert client.post("/api/v1/household", json=payload).status_code == 403
    headers = write_headers(client)
    assert (
        client.post(
            "/api/v1/household",
            json=payload,
            headers={**headers, "Origin": "https://foreign.invalid"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/household",
            json=payload,
            headers={key: value for key, value in headers.items() if key != "Idempotency-Key"},
        ).status_code
        == 422
    )
    duplicate = list(headers.items()) + [("Idempotency-Key", "different")]
    assert client.post("/api/v1/household", json=payload, headers=duplicate).status_code == 422
    assert (
        client.post("/api/v1/household?actor=forged", json=payload, headers=headers).status_code
        == 422
    )
    with store.read() as unit:
        assert unit.households.current() is None


def test_ha_outage_allows_existing_local_read_until_expiry_but_blocks_writes(
    tmp_path: Path,
) -> None:
    client, _, socket, _, _, clock = fixture(tmp_path)
    login(client)
    setup(client)
    headers = write_headers(client, "rename")
    socket.error = IdentityUnavailable("ha_unavailable")
    assert client.get("/api/v1/household").status_code == 200
    assert (
        client.put(
            "/api/v1/household",
            json={"name": "Changed", "time_zone": "UTC", "expected_revision": 1},
            headers=headers,
        ).status_code
        == 503
    )
    clock.value += 3_600_001
    assert client.get("/api/v1/household").status_code == 401


def test_missing_operation_returns_safe_scoped_404_and_openapi_declares_all_routes(
    tmp_path: Path,
) -> None:
    client, _, _, settings, _, _ = fixture(tmp_path)
    login(client)
    setup(client)
    assert client.get("/api/v1/operations/missing").status_code == 404
    schema = client.get("/api/v1/openapi.json").json()
    assert {
        "/api/v1/authorization",
        "/api/v1/household",
        "/api/v1/members",
        "/api/v1/members/enrollment",
        "/api/v1/members/{member_id}",
        "/api/v1/policy",
        "/api/v1/operations/{operation_id}",
    } <= schema["paths"].keys()
    for path in ("/api/v1/household", "/api/v1/members/{member_id}", "/api/v1/policy"):
        for method, operation in schema["paths"][path].items():
            assert operation["security"] == [{"DomusSession": []}]
            if method in ("post", "put"):
                assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= {
                    item["name"] for item in operation["parameters"]
                }
    assert (
        schema["components"]["securitySchemes"]["DomusSession"]["name"] == settings.session_cookie
    )


@pytest.mark.parametrize(
    "body",
    [
        b'{"name":"Home","name":"Changed","time_zone":"UTC","expected_revision":0}',
        b'{"name":"Home","time_zone":"UTC","expected_revision":0,"invalid":NaN}',
        b"[]",
        b"{",
        b'{"name":"\xff","time_zone":"UTC","expected_revision":0}',
    ],
)
def test_ambiguous_malformed_or_nonobject_json_never_reaches_a_command(
    tmp_path: Path, body: bytes
) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    response = client.post(
        "/api/v1/household",
        content=body,
        headers={**write_headers(client), "Content-Type": "application/json"},
    )
    assert response.status_code == 422 and response.json()["code"] == "invalid_request"
    with store.read() as unit:
        assert unit.households.current() is None and unit.outbox.pending() == ()


@pytest.mark.parametrize("media", ["text/plain", "application/json; charset=latin-1", "duplicate"])
def test_unsupported_or_duplicate_media_type_cannot_bypass_json_contract(
    tmp_path: Path, media: str
) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    headers = list(write_headers(client).items()) + [
        ("Content-Type", "application/json" if media == "duplicate" else media)
    ]
    if media == "duplicate":
        headers.append(("Content-Type", "text/plain"))
    response = client.post(
        "/api/v1/household",
        content='{"name":"Home","time_zone":"UTC","expected_revision":0}',
        headers=headers,
    )
    assert response.status_code == 422
    with store.read() as unit:
        assert unit.households.current() is None


def test_busy_writer_returns_retry_guidance_without_new_key_or_partial_effect(
    tmp_path: Path,
) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    headers = write_headers(client, "setup")
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    with store.write():
        result = client.post("/api/v1/household", json=payload, headers=headers)
        assert result.status_code == 503 and result.json()["code"] == "storage_busy"
        assert result.headers["retry-after"] == "1"
    assert client.post("/api/v1/household", json=payload, headers=headers).status_code == 200
    with store.read() as unit:
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1


def test_delivery_state_is_observed_and_reads_hide_other_member_private_fields(
    tmp_path: Path,
) -> None:
    client, store, socket, _, _, _ = fixture(tmp_path)
    login(client)
    created = setup(client)
    with store.write() as unit:
        unit.outbox.acknowledge(created["operation_id"])
    result = client.get("/api/v1/operations/" + created["operation_id"])
    assert result.status_code == 200 and result.json()["delivery"] == "delivered"
    assert "private-access" not in result.text and "private-refresh" not in result.text
    # Authenticated reentry through HA binds the new principal to a new local lease.
    socket.human = HumanIdentity("b" * 32, False, True, False)
    login(client)
    joined = client.post(
        "/api/v1/members/enrollment",
        json={"expected_revision": 0},
        headers=write_headers(client, "join"),
    )
    member_id = joined.json()["result"]["member_id"]
    from dataclasses import replace

    from domus.domain.identity import MemberStatus

    with store.write() as unit:
        member = unit.members.get("home", member_id)
        unit.members.save(replace(member, status=MemberStatus.ACTIVE, revision=2), 1)
    roster = client.get("/api/v1/members")
    assert roster.status_code == 200
    other = next(member for member in roster.json()["members"] if member["member_id"] != member_id)
    assert "ha_user_id" not in other and "exceptions" not in other


def test_last_administrator_cannot_be_removed_through_the_public_api(tmp_path: Path) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    created = setup(client)
    member_id = created["result"]["member_id"]
    response = client.put(
        "/api/v1/members/" + member_id,
        json={"expected_revision": 1, "role": "viewer", "status": "suspended"},
        headers=write_headers(client, "suspend"),
    )
    assert response.status_code == 409 and response.json()["code"] == "last_administrator"
    assert client.get("/api/v1/authorization").json()["state"] == "active"
    with store.read() as unit:
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1


def test_ordinary_rule_cannot_grant_a_protected_administrator_permission(tmp_path: Path) -> None:
    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    created = setup(client)
    member_id = created["result"]["member_id"]
    response = client.put(
        "/api/v1/members/" + member_id,
        json={
            "expected_revision": 1,
            "role": "viewer",
            "status": "active",
            "exceptions": [{"permission": "household.manage", "allow": True}],
        },
        headers=write_headers(client, "exception"),
    )
    assert response.status_code == 422 and response.json()["code"] == "protected_permission"
    with store.read() as unit:
        assert unit.members.get("home", member_id).revision == 1
        assert len(unit.audit.entries("home")) == 1


def test_published_household_openapi_matches_the_composed_server(tmp_path: Path) -> None:
    import json

    client, _, _, _, _, _ = fixture(tmp_path)
    actual = client.get("/api/v1/openapi.json").json()
    reference = json.loads(
        (
            Path(__file__).resolve().parents[2] / "docs/contracts/household-api.openapi.json"
        ).read_text()
    )
    assert actual["paths"] == reference["paths"]
    assert actual["components"] == reference["components"]


def test_response_failure_after_commit_preserves_uncertainty_and_same_key_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from domus.entrypoints import household_http

    client, store, _, _, _, _ = fixture(tmp_path)
    login(client)
    headers = write_headers(client, "setup")
    payload = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
    original = household_http._receipt

    def fail_after_commit(*_: object) -> None:
        raise RuntimeError("private-serialization-detail")

    monkeypatch.setattr(household_http, "_receipt", fail_after_commit)
    response = client.post("/api/v1/household", json=payload, headers=headers)
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "could not confirm" in response.json()["message"]
    assert "No household change was made" not in response.text
    assert "same payload and Idempotency-Key" in response.json()["action_required"]
    assert "private-serialization-detail" not in response.text
    monkeypatch.setattr(household_http, "_receipt", original)
    recovered = client.post("/api/v1/household", json=payload, headers=headers)
    assert recovered.status_code == 200 and recovered.json()["result"]["state"] == "configured"
    with store.read() as unit:
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 1
