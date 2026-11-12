"""Verify count-only access on both Domus transports without changing calendar access."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_ha_app_launcher import launch as launch
from test_ha_calendar_installation import (
    ORIGIN,
    PUBLIC,
    SUPERVISOR,
    WINDOW,
    bearer,
    digest,
    header,
    runtime,
)
from test_task_commands import fixture

from domus.application.task_requests import CreateTask, CreateTaskOccurrence
from domus.composition import ha_app, server
from domus.domain.errors import InvalidInput
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent
from domus.entrypoints.ha_calendar_http import CALENDAR_DIGEST_ENV, CALENDAR_PATH
from domus.entrypoints.ha_deadline_http import DEADLINE_DIGEST_ENV, DEADLINE_PATH

PRIVATE = "http://local-domus-edge:8100"


def deadline_bearer(installation: Installation, seed: str = "a") -> str:
    return f"{installation.instance_id}.{installation.channel}.deadlines.{seed * 64}"


@pytest.mark.parametrize("native", [False, True])
def test_count_projection_requires_its_own_grant_and_does_not_disclose_tasks(tmp_path, native):
    tasks, store, _, _ = fixture(tmp_path)
    installation = store.installation
    calendar = bearer(installation)
    deadlines = deadline_bearer(installation)
    replacement = deadline_bearer(installation, "b")
    mode = PRIVATE if native else PUBLIC
    service = runtime(
        native, installation, store.path, digest(calendar), deadline_fingerprint=digest(deadlines)
    )
    client = TestClient(service.app, base_url=mode)
    try:
        response = client.get(DEADLINE_PATH, headers=header(deadlines))
        assert response.status_code == 200 and response.json() == {"due_today": 0, "overdue": 0}
        assert response.headers["cache-control"] == "no-store"
        task = tasks.create("manual", CreateTask(TaskContent("Private title"))).result.decode()
        tasks.create_occurrence("late", CreateTaskOccurrence(task["definition_id"], due_at=1))
        response = client.get(DEADLINE_PATH, headers=header(deadlines))
        assert response.json() == {"due_today": 0, "overdue": 1}
        assert "Private title" not in response.text
        assert (
            client.get(CALENDAR_PATH, params=WINDOW, headers=header(calendar)).json()["projection"][
                "count"
            ]
            == 1
        )
        assert (
            client.get(CALENDAR_PATH, params=WINDOW, headers=header(deadlines)).status_code == 401
        )
        for wrong in (calendar, SUPERVISOR, replacement, deadlines.replace(".edge.", ".stable.")):
            rejected = client.get(DEADLINE_PATH, headers=header(wrong))
            assert rejected.status_code == 401
            assert rejected.json() == {"error": "invalid_deadline_credential"}
        assert client.get(DEADLINE_PATH).status_code == 401
        assert client.post(DEADLINE_PATH, headers=header(deadlines)).status_code == 405
        assert (
            client.get(DEADLINE_PATH + "?member_id=admin", headers=header(deadlines)).status_code
            == 422
        )
        headers = {**header(deadlines), **{f"x-extra-{index}": "x" for index in range(33)}}
        assert client.get(DEADLINE_PATH, headers=headers).status_code == 422
        if native:
            ingress = TestClient(service.app, base_url="http://native:8099")
            assert ingress.get(DEADLINE_PATH, headers=header(deadlines)).status_code in (
                403,
                404,
                422,
            )
        else:
            remote = TestClient(
                service.app, base_url="http://domus.example", client=("192.0.2.1", 80)
            )
            assert remote.get(DEADLINE_PATH, headers=header(deadlines)).status_code == 403
    finally:
        service.close()

    for fingerprint in (digest(replacement), None):
        service = runtime(
            native, installation, store.path, digest(calendar), deadline_fingerprint=fingerprint
        )
        client = TestClient(service.app, base_url=mode)
        try:
            assert client.get(DEADLINE_PATH, headers=header(deadlines)).status_code in (401, 404)
            response = client.get(DEADLINE_PATH, headers=header(replacement))
            if fingerprint is None:
                assert response.status_code == 404
            else:
                assert response.json() == {"due_today": 0, "overdue": 1}
            assert (
                client.get(CALENDAR_PATH, params=WINDOW, headers=header(calendar)).status_code
                == 200
            )
        finally:
            service.close()


@pytest.mark.parametrize("native", [False, True])
def test_absent_household_does_not_return_zero(tmp_path, native):
    installation = Installation(str(uuid4()), "edge")
    token = deadline_bearer(installation)
    service = runtime(
        native, installation, tmp_path / "empty.sqlite3", None, deadline_fingerprint=digest(token)
    )
    try:
        client = TestClient(service.app, base_url=PRIVATE if native else PUBLIC)
        response = client.get(DEADLINE_PATH, headers=header(token))
        assert response.status_code == 503
        assert response.json() == {"error": "task_deadlines_unavailable"}
    finally:
        service.close()


def test_deadlines_require_owned_storage_secure_origin_and_valid_digest(tmp_path):
    identity = str(uuid4())
    with pytest.raises(InvalidInput, match="ha_deadlines_require_persistent_secure_origin"):
        server.create_runtime(
            "https://ha.example", PUBLIC, identity, "edge", ha_deadline_digest="a" * 64
        )
    with pytest.raises(InvalidInput, match="invalid_ha_deadline_digest"):
        runtime(
            False,
            Installation(identity, "edge"),
            tmp_path / "invalid.sqlite3",
            None,
            deadline_fingerprint="invalid",
        )


def test_private_launcher_accepts_both_digests_without_exposing_them_in_arguments(launch, capsys):
    root, calls = launch
    options = root / "options.json"
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_deadline_digest": 42}))
    assert ha_app.main(["--channel", "edge"]) == 2 and not calls
    assert "42" not in capsys.readouterr().err
    options.write_text(
        json.dumps(
            {
                "public_origins": [ORIGIN],
                "ha_calendar_digest": "a" * 64,
                "ha_deadline_digest": "b" * 64,
            }
        )
    )
    assert ha_app.main(["--channel", "edge"]) == 0
    _, arguments, environment = calls[1]
    assert "a" * 64 not in arguments and "b" * 64 not in arguments
    assert environment[CALENDAR_DIGEST_ENV] == "a" * 64
    assert environment[DEADLINE_DIGEST_ENV] == "b" * 64
