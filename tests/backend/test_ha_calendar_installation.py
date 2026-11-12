"""Protect the separate calendar route in both real runtime compositions."""

import hashlib
import json
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_calendar_queries import query
from test_fixed_materialization import configured
from test_ha_app_launcher import ORIGIN
from test_ha_app_launcher import launch as launch
from test_task_commands import fixture

from domus.application.task_requests import CreateTask, CreateTaskOccurrence
from domus.composition import ha_app, ingress, server
from domus.domain.calendar_values import CalendarFilters, CalendarKind, CalendarRange
from domus.domain.errors import Forbidden, InvalidInput
from domus.domain.storage import Installation
from domus.domain.task_values import TaskContent
from domus.entrypoints.ha_calendar_http import CALENDAR_DIGEST_ENV, CALENDAR_PATH, CALENDAR_PORT

PUBLIC = "https://domus.example"
SUPERVISOR = "fixture-supervisor-token"
WINDOW = {"start": "1970-01-01", "end": "1970-01-02", "kind": "due"}


def bearer(installation: Installation, seed: str = "a") -> str:
    return f"{installation.instance_id}.{installation.channel}.{seed * 64}"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def runtime(native, installation, path, fingerprint, *, deadline_fingerprint=None):
    if native:
        return ingress.create_business_runtime(
            SUPERVISOR,
            installation.channel,
            path,
            installation.instance_id,
            (ORIGIN,),
            ha_calendar_digest=fingerprint,
            ha_deadline_digest=deadline_fingerprint,
        )
    return server.create_runtime(
        "https://ha.example",
        PUBLIC,
        installation.instance_id,
        installation.channel,
        database=path,
        ha_calendar_digest=fingerprint,
        ha_deadline_digest=deadline_fingerprint,
    )


@pytest.mark.parametrize("native", [False, True])
def test_calendar_bearer_is_only_for_its_scoped_read_and_rotates(tmp_path, native):
    tasks, store, _, _ = fixture(tmp_path)
    installation = store.installation
    item = tasks.create("manual", CreateTask(TaskContent("Calendar fixture"))).result.decode()
    for number in (1, 2):
        tasks.create_occurrence(
            f"due-{number}", CreateTaskOccurrence(item["definition_id"], due_at=number)
        )
    token = bearer(installation)
    mode = "http://local-domus-edge:8100" if native else PUBLIC
    service = runtime(native, installation, store.path, digest(token))
    client = TestClient(service.app, base_url=mode)
    try:
        result = client.get(CALENDAR_PATH, params={**WINDOW, "limit": 1}, headers=header(token))
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "no-store"
        envelope = result.json()
        assert (envelope["instance_id"], envelope["channel"]) == (
            installation.instance_id,
            installation.channel,
        )
        first = envelope["projection"]
        assert first["count"] == 2 and first["next_cursor"] and first["external_sync"] == "disabled"
        (point,) = first["events"]
        assert point["start"] == "1970-01-01T00:00:00.001000+00:00" and not point["all_day"]
        second = client.get(
            CALENDAR_PATH,
            params={**WINDOW, "limit": 1, "cursor": first["next_cursor"]},
            headers=header(token),
        ).json()["projection"]
        assert second["next_cursor"] is None and second["events"][0]["uid"] != point["uid"]
        other_channel = "stable" if installation.channel == "edge" else "edge"
        for wrong in (
            "",
            SUPERVISOR,
            token[:-1],
            bearer(installation, "b"),
            f"{uuid4()}.{installation.channel}.{'a' * 64}",
            f"{installation.instance_id}.{other_channel}.{'a' * 64}",
        ):
            denied = client.get(CALENDAR_PATH, params=WINDOW, headers=header(wrong))
            assert denied.status_code == 401 and "Calendar fixture" not in denied.text
        assert client.get(CALENDAR_PATH, params=WINDOW).status_code == 401
        assert (
            client.get(
                CALENDAR_PATH,
                params=WINDOW,
                headers=[
                    ("Authorization", f"Bearer {token}"),
                    ("Authorization", f"Bearer {token}"),
                ],
            ).status_code
            == 401
        )
        for args in (
            {**WINDOW, "kind": "performed"},
            {**WINDOW, "member_id": "child"},
            {**WINDOW, "limit": 101},
            {**WINDOW, "cursor": "due~not-a-cursor"},
            {**WINDOW, "start": "1970-02-30"},
            {**WINDOW, "start": "1969-12-31"},
            {**WINDOW, "end": "1970-05-01"},
        ):
            invalid = client.get(CALENDAR_PATH, params=args, headers=header(token))
            assert invalid.status_code == 422 and invalid.json() == {"error": "invalid_request"}
        assert (
            client.get(CALENDAR_PATH + "?kind=due&kind=planned", headers=header(token)).status_code
            == 422
        )
        assert (
            client.get(
                CALENDAR_PATH, params={"cursor": "a" * 2050}, headers=header(token)
            ).status_code
            == 422
        )
        assert (
            client.request(
                "GET", CALENDAR_PATH, params=WINDOW, content=b"unexpected", headers=header(token)
            ).status_code
            == 422
        )
        assert client.post(CALENDAR_PATH, headers=header(token)).status_code == 405
        assert client.get(
            "/api/v1/tasks/calendar/home-assistant", headers=header(token)
        ).status_code in (401, 403, 404, 422)
        if native:
            assert client.get("/health", headers=header(token)).status_code == 404
            with pytest.raises(WebSocketDisconnect) as closed:
                with client.websocket_connect(
                    "ws://local-domus-edge:8100" + CALENDAR_PATH, headers=header(token)
                ):
                    pytest.fail("The calendar listener opened a websocket")
            assert closed.value.code == 1008
            private = TestClient(
                service.app, base_url="http://native:8099", client=("127.0.0.1", 1)
            )
            assert private.get("/health").status_code == 200
            assert private.get(CALENDAR_PATH, params=WINDOW, headers=header(token)).status_code in (
                403,
                404,
                422,
            )
        else:
            assert (
                client.get(
                    CALENDAR_PATH, headers={**header(token), "Host": "other.example"}
                ).status_code
                == 403
            )
            assert client.get("/api/v1/session", headers=header(token)).status_code in (401, 422)
            remote_http = TestClient(
                service.app, base_url="http://domus.example", client=("192.0.2.3", 80)
            )
            assert (
                remote_http.get(
                    CALENDAR_PATH,
                    params=WINDOW,
                    headers={**header(token), "X-Forwarded-Proto": "https"},
                ).status_code
                == 403
            )
            reverse_proxy = TestClient(
                service.app, base_url="http://domus.example", client=("127.0.0.1", 80)
            )
            assert (
                reverse_proxy.get(CALENDAR_PATH, params=WINDOW, headers=header(token)).status_code
                == 200
            )
    finally:
        service.close()
    rotated = bearer(installation, "c")
    service = runtime(native, installation, store.path, digest(rotated))
    try:
        client = TestClient(service.app, base_url=mode)
        assert client.get(CALENDAR_PATH, params=WINDOW, headers=header(token)).status_code == 401
        assert client.get(CALENDAR_PATH, params=WINDOW, headers=header(rotated)).status_code == 200
        assert (
            client.get(
                CALENDAR_PATH,
                params={**WINDOW, "limit": 1, "cursor": first["next_cursor"]},
                headers=header(rotated),
            ).status_code
            == 422
        )
    finally:
        service.close()
    disabled = runtime(native, installation, store.path, None)
    try:
        assert TestClient(disabled.app, base_url=mode).get(
            CALENDAR_PATH, params=WINDOW, headers=header(rotated)
        ).status_code in (403, 404, 422)
    finally:
        disabled.close()


def test_installation_query_cannot_use_human_cursors_filters_or_other_installations(tmp_path):
    planner, store, actor, _, schedule, before = configured(tmp_path, timed=True, count=2)
    planner.step(schedule, before)
    planner.step(schedule, before)
    human = query(store, actor, planner.clock)
    machine = replace(human, human=store.installation)
    start, end = date(2026, 3, 29), date(2026, 4, 1)
    period = CalendarRange(start, end)
    planned = CalendarFilters(CalendarKind.PLANNED)
    page = machine.page(period, planned)
    assert page.entries[0].resolved_local == "2026-03-29T03:00:00"
    for reader, params in (
        (machine, CalendarFilters()),
        (machine, CalendarFilters(CalendarKind.PERFORMED)),
        (machine, CalendarFilters(CalendarKind.PLANNED, member_id="child")),
        (replace(machine, human=Installation(str(uuid4()), store.installation.channel)), planned),
    ):
        with pytest.raises(Forbidden):
            reader.page(period, params)
    with pytest.raises(Forbidden):
        machine.page(CalendarRange(start, date(2026, 8, 1)), planned)
    for source, other in ((human, machine), (machine, human)):
        first = source.page(period, planned, limit=1)
        assert first.next_cursor
        with pytest.raises(InvalidInput, match="invalid_task_cursor"):
            other.page(period, planned, limit=1, cursor=first.next_cursor)


def test_uninitialized_household_is_unavailable_without_leaking_internal_error(tmp_path):
    installation = Installation(str(uuid4()), "edge")
    token = bearer(installation)
    service = runtime(False, installation, tmp_path / "empty.sqlite3", digest(token))
    try:
        with TestClient(service.app, base_url=PUBLIC) as client:
            response = client.get(CALENDAR_PATH, params=WINDOW, headers=header(token))
        assert response.status_code == 503
        assert response.json() == {"error": "calendar_unavailable"}
    finally:
        service.close()


def test_standalone_opt_in_requires_persistent_https_and_a_valid_digest(tmp_path):
    identity = str(uuid4())
    with pytest.raises(InvalidInput, match="ha_calendar_requires_persistent_secure_origin"):
        server.create_runtime(
            "https://ha.example", PUBLIC, identity, "edge", ha_calendar_digest="a" * 64
        )
    with pytest.raises(InvalidInput, match="ha_calendar_requires_persistent_secure_origin"):
        server.create_runtime(
            "https://ha.example",
            "http://localhost",
            identity,
            "edge",
            development_http=True,
            database=tmp_path / "insecure.sqlite3",
            ha_calendar_digest="a" * 64,
        )
    with pytest.raises(InvalidInput, match="invalid_ha_calendar_digest"):
        runtime(False, Installation(identity, "edge"), tmp_path / "invalid.sqlite3", "not-a-digest")


def test_private_launcher_passes_only_valid_digest_in_environment(launch, capsys):
    root, calls = launch
    options = root / "options.json"
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_calendar_digest": 42}))
    assert ha_app.main(["--channel", "edge"]) == 2 and not calls
    assert "42" not in capsys.readouterr().err
    options.write_text(json.dumps({"public_origins": [ORIGIN], "ha_calendar_digest": "a" * 64}))
    assert ha_app.main(["--channel", "edge"]) == 0
    _, arguments, environment = calls[1]
    assert "a" * 64 not in arguments
    assert environment[CALENDAR_DIGEST_ENV] == "a" * 64


def test_native_cli_binds_private_calendar_and_original_ingress_on_one_runtime(
    tmp_path, monkeypatch
):
    import socket

    _, store, _, _ = fixture(tmp_path)
    bindings = []

    def bound(address):
        bindings.append(address)
        return socket.socket()

    def run(_server, *, sockets):
        assert len(sockets) == 2 and all(listener.fileno() != -1 for listener in sockets)

    monkeypatch.setenv("SUPERVISOR_TOKEN", SUPERVISOR)
    monkeypatch.setenv(CALENDAR_DIGEST_ENV, digest(bearer(store.installation)))
    monkeypatch.setattr(ingress.socket, "create_server", bound)
    monkeypatch.setattr(ingress.uvicorn.Server, "run", run)
    assert (
        ingress.main(
            [
                "--channel",
                store.installation.channel,
                "--database",
                str(store.path),
                "--instance-id",
                store.installation.instance_id,
                "--public-origin",
                ORIGIN,
            ]
        )
        == 0
    )
    assert bindings == [("0.0.0.0", 8099), ("0.0.0.0", CALENDAR_PORT)]
    assert CALENDAR_DIGEST_ENV not in ingress.os.environ
    monkeypatch.setenv("SUPERVISOR_TOKEN", SUPERVISOR)
    monkeypatch.setenv(CALENDAR_DIGEST_ENV, "a" * 64)
    assert ingress.main(["--channel", "edge"]) == 2
