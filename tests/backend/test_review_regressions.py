"""Review regressions exercise browser origins, callback contracts and inert approval replay."""

import io
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_auth_http import fixture as auth_fixture
from test_ingress_sessions import HEADERS
from test_native_http import INSTANCE, Lookup
from test_recovery_commands import configured, start

from domus.composition import admin, ingress
from domus.domain.errors import Conflict, InvalidInput
from domus.domain.storage import Installation
from domus.infrastructure.ha_config import HAEndpoint, OAuthConfiguration, PublicOrigins


@pytest.mark.parametrize(
    "configured_origin, serialized",
    [
        ("https://DOMUS.EXAMPLE:443/", "https://domus.example"),
        ("http://domus.example:80", "http://domus.example"),
        ("https://[::1]:443", "https://[::1]"),
        ("http://[::1]:80", "http://[::1]"),
        ("https://domus.example:8443", "https://domus.example:8443"),
        ("http://domus.example:8123", "http://domus.example:8123"),
    ],
)
def test_trusted_origins_use_browser_serialization_without_widening_nondefault_ports(
    configured_origin, serialized
):
    assert PublicOrigins((configured_origin,)).values == (serialized,)
    endpoint = HAEndpoint(configured_origin)
    assert endpoint.origin == serialized
    assert (
        endpoint.websocket_url
        == serialized.replace("https:", "wss:").replace("http:", "ws:") + "/api/websocket"
    )


@pytest.mark.parametrize("scheme,port", [("https", 443), ("http", 80)])
def test_equivalent_public_origins_cannot_bypass_duplicate_configuration_check(scheme, port):
    with pytest.raises(InvalidInput, match="invalid_public_origins"):
        PublicOrigins((f"{scheme}://domus.example", f"{scheme}://domus.example:{port}"))


def test_standalone_oauth_public_client_and_callback_share_canonical_https_origin():
    config = OAuthConfiguration(HAEndpoint("https://ha.example:443"), "https://DOMUS.EXAMPLE:443")
    assert config.client_id == "https://domus.example/"
    assert config.callback_url == "https://domus.example/api/v1/auth/callback"


@pytest.mark.parametrize("scheme,port", [("https", 443), ("http", 80)])
def test_native_browser_can_setup_with_explicit_default_port_in_operator_configuration(
    tmp_path, monkeypatch, scheme, port
):
    lookup = Lookup()
    monkeypatch.setattr(ingress, "HomeAssistantWebSocket", lambda _: lookup)
    origin = f"{scheme}://domus.example"
    runtime = ingress.create_business_runtime(
        "private-supervisor-token",
        "edge",
        tmp_path / "domus.sqlite3",
        INSTANCE,
        (origin + f":{port}",),
    )
    try:
        client = TestClient(
            runtime.app, base_url=origin, client=("172.30.32.2", 12000), headers=dict(HEADERS)
        )
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        headers = {"Origin": origin, "X-CSRF-Token": csrf, "Idempotency-Key": "setup"}
        body = {"name": "Home", "time_zone": "UTC", "expected_revision": 0}
        denied = client.post(
            "/api/v1/household", json=body, headers={**headers, "Origin": origin + ":8443"}
        )
        assert denied.status_code == 403
        accepted = client.post("/api/v1/household", json=body, headers=headers)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["result"]["state"] == "configured"
    finally:
        runtime.close()


@pytest.mark.parametrize("transition", ["consumed", "canceled", "expired", "policy_changed"])
def test_original_console_approval_replays_after_closure_without_rearming_or_extending(
    tmp_path, transition
):
    commands, approval, store, _, clock, console = configured(tmp_path)
    request_id = start(commands)
    original = approval.approve(request_id)
    if transition == "consumed":
        commands.complete("complete", request_id, 2)
    elif transition == "canceled":
        commands.cancel("cancel", request_id, 2)
    elif transition == "expired":
        clock.time = original.result.decode()["expires_at"]
    else:
        with store.write() as unit:
            policy = unit.policies.get("home")
            unit.policies.save(replace(policy, revision=2), 1)
    with store.read() as unit:
        state = unit.recoveries.get("home", request_id)
        members = unit.members.list("home")
        audit = unit.audit.entries("home")
        events = unit.outbox.pending()
    assert approval.approve(request_id) == original
    assert len(console.reviews) == 1
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id) == state
        assert unit.members.list("home") == members
        assert unit.audit.entries("home") == audit and unit.outbox.pending() == events
    with pytest.raises(Conflict):
        commands.complete("another-key", request_id, 2)


@pytest.mark.parametrize("channel", ["stable", "edge"])
def test_retained_console_receipt_never_bypasses_installation_binding(tmp_path, channel):
    commands, approval, store, _, _, _ = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    approval.installation = Installation(
        store.installation.instance_id
        if channel == "stable"
        else "ac03910c-cfb7-4f3b-b36a-86b263681251",
        channel,
    )
    with pytest.raises(Conflict, match="recovery_binding_changed"):
        approval.approve(request_id)


def test_actual_console_retry_after_consumption_describes_original_operation_without_new_approval(
    tmp_path,
):
    from test_recovery_console import options

    commands, approval, store, _, _, console = configured(tmp_path)
    request_id = start(commands)
    receipt = approval.approve(request_id)
    commands.complete("complete", request_id, 2)
    output, error = io.StringIO(), io.StringIO()
    assert (
        admin.main(
            [*options(store.path, store.installation), request_id],
            input_stream=io.StringIO(),
            output_stream=output,
            error_stream=error,
        )
        == 0
    )
    body = json.loads(output.getvalue())
    assert body["operation_id"] == receipt.operation_id
    assert body["result"] == receipt.result.decode() and body["state"] == "committed"
    assert "by this operation" in body["message"] and "current status" in body["message"]
    assert error.getvalue() == "" and len(console.reviews) == 1
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "consumed"
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4


@pytest.mark.parametrize("result", [{}, {"code": "code", "error": "access_denied"}])
def test_callback_contract_names_exclusive_results_and_invalid_combinations_keep_bound_attempt(
    result,
):
    client, _, _, _, _, _ = auth_fixture()
    schema = client.get("/api/v1/openapi.json").json()
    operation = schema["paths"]["/api/v1/auth/callback"]["get"]
    assert "Exactly one of code or error" in operation["description"]
    started = client.get("/api/v1/auth/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    rejected = client.get("/api/v1/auth/callback", params={"state": state, **result})
    assert rejected.status_code == 422 and rejected.json()["code"] == "invalid_request"
    assert client.get("/api/v1/session").status_code == 401
    accepted = client.get("/api/v1/auth/callback", params={"state": state, "code": "code"})
    assert accepted.status_code == 303
    assert client.get("/api/v1/session").status_code == 200
