"""Recorded browser inputs stay structurally conformant to both real guarded HTTP providers."""

import json
from pathlib import Path

import pytest
from test_auth_http import login
from test_household_commands import Identifiers
from test_household_http import fixture as standalone_fixture
from test_ingress_sessions import PREFIX
from test_native_http import ORIGIN
from test_native_http import fixture as native_fixture

from domus.composition import ingress
from domus.domain.identity import HumanIdentity

CORPUS = Path(__file__).resolve().parents[2] / "frontend/tests/fixtures/entry-wire.json"


class Epoch:
    def now(self) -> int:
        return 1_800_000_000_000


def capture(tmp_path: Path, patch: pytest.MonkeyPatch, deployment: str) -> dict:
    runtime = None
    if deployment == "native":
        patch.setattr(ingress, "SystemClock", Epoch)
        patch.setattr(ingress, "SecureIdentifiers", Identifiers)
        runtime, client, lookup, _ = native_fixture(tmp_path, patch)
        base, origin = PREFIX + "/", ORIGIN
    else:
        client, _, socket, _, _, _ = standalone_fixture(tmp_path)
        login(client)
        base, origin = "/", "https://domus.example"

    def get(path: str) -> str:
        response = client.get("/api/v1/" + path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        return response.content.decode("utf-8")

    def post(path: str, key: str, body: dict) -> str:
        token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        response = client.post(
            "/api/v1/" + path,
            json=body,
            headers={"Origin": origin, "X-CSRF-Token": token, "Idempotency-Key": key},
        )
        assert response.status_code == 200, response.text
        return response.content.decode("utf-8")

    result = {
        "endpoint": {"origin": origin, "deployment": deployment, "applicationBase": base},
        "session": get("session"),
        "unconfigured": get("authorization"),
    }
    result["setup"] = post(
        "household",
        "wire-setup",
        {
            "name": "Home 🏠",
            "time_zone": "UTC",
            "expected_revision": 0,
            "mapping_mode": "all_ha_administrators",
        },
    )
    result["active"] = get("authorization")
    result["household"] = get("household")
    operation = json.loads(result["setup"])["operation_id"]
    result["operation"] = get("operations/" + operation)
    participant = HumanIdentity("b" * 32, False, True, False)
    if deployment == "native":
        lookup.people[participant.ha_user_id] = participant
        client.headers["X-Remote-User-Id"] = participant.ha_user_id
    else:
        socket.human = participant
        login(client)
    result["participantSession"] = get("session")
    result["eligible"] = get("authorization")
    result["enrollment"] = post("members/enrollment", "wire-enroll", {"expected_revision": 0})
    result["pending"] = get("authorization")
    if runtime:
        runtime.close()
    return result


@pytest.mark.parametrize("deployment", ["native", "standalone"])
def test_recorded_browser_corpus_matches_actual_provider_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment: str
) -> None:
    actual = capture(tmp_path, monkeypatch, deployment)
    expected = json.loads(CORPUS.read_text())[deployment]
    assert actual["endpoint"] == expected["endpoint"]
    for name, raw in actual.items():
        if name == "endpoint":
            continue
        current, recorded = json.loads(raw), json.loads(expected[name])
        # The client ignores bounded provider guidance; copy edits do not change the contract.
        for field in ("message", "action_required"):
            if field in current:
                guidance = current.pop(field)
                assert isinstance(guidance, str) and 1 <= len(guidance) <= (
                    2048 if field == "message" else 4096
                )
                recorded.pop(field)
        assert current == recorded, name
