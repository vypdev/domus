"""Disposable loopback HA/Supervisor fixtures around the unchanged product trust boundaries.

This executable is test-only, never packaged. Its control routes replace fictional identities and
owned temporary databases. No real HA instance, credentials, host storage or authentication bypass
flag is used by the product. The native wrapper represents the outer trusted Supervisor peer.
"""

import argparse
import base64
import hashlib
import html
import io
import json
import os
import secrets
import sqlite3
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode

import uvicorn
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
from domus.application.fixed_recurrence import FixedRecurrencePlanner
from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import (
    AssignTask,
    CompleteTask,
    CreateTask,
    TransitionTask,
    VerifyTask,
)
from domus.composition import admin, ingress, server
from domus.domain.errors import Forbidden, IdentityRejected, IdentityUnavailable
from domus.domain.identity import HumanIdentity
from domus.domain.nominal_recurrence import CalendarNominalExpansion
from domus.domain.recurrence_rule_text import parse_fixed_pattern
from domus.domain.recurrence_time import NominalTime, TimePolicy
from domus.domain.task_values import (
    OccurrenceState,
    TaskContent,
    TaskOverrides,
    VerificationMode,
    VerificationState,
)
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_http import OAuthTokens
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

PREFIX = "/api/hassio_ingress/fixture_domus_supervisor_1234567890"


class HomeAssistant:
    def __init__(self, endpoint: HAEndpoint) -> None:
        self.endpoint = endpoint
        self.people = {
            "a" * 32: HumanIdentity("a" * 32, True, True, False),
            "b" * 32: HumanIdentity("b" * 32, False, True, False),
            "c" * 32: HumanIdentity("c" * 32, True, True, False),
        }
        self.subject = "a" * 32
        self.outage = False
        self.rejected = False
        self.grants = {}
        self.token_subjects = {}
        self.revoked = 0

    def person(self, user_id: str) -> HumanIdentity:
        if self.rejected:
            raise IdentityRejected("ha_subject_rejected")
        if self.outage:
            raise IdentityUnavailable("ha_unavailable")
        if user_id not in self.people:
            raise IdentityRejected("ha_subject_rejected")
        return self.people[user_id]

    def current_user(self, tokens: OAuthTokens) -> HumanIdentity:
        return self.person(self.token_subjects[tokens.access_token])

    def directory_user(self, token: str, user_id: str) -> HumanIdentity:
        assert token == "fixture-supervisor-token" or token.startswith("fixture-access-")
        return self.person(user_id)

    def directory_users(self, token: str, user_ids: tuple[str, ...]) -> tuple:
        return tuple(self.directory_user(token, user_id) for user_id in user_ids)

    def _request(self, token: str, operation: str):
        """Fixed fictional account responses for the real bounded presentation adapter."""
        assert token == "fixture-supervisor-token" or token in self.token_subjects
        actor = self.person(
            self.subject if token == "fixture-supervisor-token" else self.token_subjects[token]
        )
        if operation == "config/auth/list":
            if token != "fixture-supervisor-token" and not actor.is_administrator:
                raise Forbidden("ha_directory_forbidden")
            return [
                {
                    "id": person.ha_user_id,
                    "name": "Fictional account " + person.ha_user_id[0],
                    "is_active": True,
                    "system_generated": False,
                }
                for person in self.people.values()
            ]
        assert operation == "auth/current_user" and token != "fixture-supervisor-token"
        return {
            "id": actor.ha_user_id,
            "name": "Fictional account " + actor.ha_user_id[0],
            "is_admin": actor.is_administrator,
            "credentials": [{"auth_provider_type": "homeassistant"}],
        }


class OAuth:
    def __init__(self, configuration, ha: HomeAssistant) -> None:
        self.configuration, self.ha = configuration, ha

    def exchange(self, code: str, verifier: str) -> OAuthTokens:
        expected = self.ha.grants.pop(code, None)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        if expected is None or expected[0] != challenge:
            raise IdentityRejected("ha_rejected")
        access, refresh = "fixture-access-" + code, "fixture-refresh-" + code
        self.ha.token_subjects[access] = expected[1]
        self.ha.token_subjects[refresh] = expected[1]
        return OAuthTokens(access, refresh, 3600, "homeassistant")

    def refresh(self, token: str, provider: str) -> OAuthTokens:
        assert provider == "homeassistant" and token in self.ha.token_subjects
        access = "fixture-access-" + secrets.token_urlsafe(16)
        self.ha.token_subjects[access] = self.ha.token_subjects[token]
        return OAuthTokens(access, token, 3600, provider)

    def revoke(self, token: str) -> None:
        self.ha.revoked += 1
        self.ha.token_subjects.pop(token, None)


class Fixture:
    def __init__(self, mode: str, port: int, origin_port: int | None = None) -> None:
        self.mode, self.origin = mode, f"http://127.0.0.1:{origin_port or port}"
        self.runtime = self.directory = None
        self.writer = None
        self.patch = ExitStack()
        self.patch.enter_context(
            patch.object(ingress, "HomeAssistantWebSocket", lambda endpoint: self.ha)
        )
        self.patch.enter_context(
            patch.object(server, "HomeAssistantWebSocket", lambda endpoint: self.ha)
        )
        self.patch.enter_context(
            patch.object(server, "HomeAssistantOAuth", lambda config: OAuth(config, self.ha))
        )
        self.reset()

    def close(self) -> None:
        self.release_writer()
        if self.runtime is not None:
            self.runtime.close()
            self.runtime = None
        if self.directory is not None:
            self.directory.cleanup()
            self.directory = None
        self.patch.close()

    def reset(self, channel: str = "edge") -> None:
        assert channel in ("edge", "stable")
        self.release_writer()
        if self.runtime is not None:
            self.runtime.close()
        if self.directory is not None:
            self.directory.cleanup()
        self.directory = tempfile.TemporaryDirectory(prefix=f"domus-entry-browser-{self.mode}-")
        parent = Path(self.directory.name)
        # Own fixtures use the actual private directory contract, including BSD group inheritance.
        os.chown(parent, -1, os.getegid())
        self.data_directory = parent / "data"
        self.data_directory.mkdir(mode=0o700)
        self.channel = channel
        self.ha = HomeAssistant(
            HAEndpoint.supervisor() if self.mode == "native" else HAEndpoint(self.origin)
        )
        self.start()

    def release_writer(self) -> None:
        if self.writer is not None:
            self.writer.close()  # Closing the independent fixture connection rolls back its lock.
            self.writer = None

    def start(self) -> None:
        if self.mode == "native":
            self.runtime = ingress.create_owned_runtime(
                "fixture-supervisor-token", self.channel, self.data_directory, (self.origin,)
            )
        else:
            self.runtime = server.create_owned_runtime(
                self.origin,
                self.origin,
                self.channel,
                self.data_directory,
                development_http=True,
            )
        assert self.runtime.storage is not None
        self.database = self.runtime.storage.database.path
        # The fixture's wrapper serves HTTP directly; production starts this worker in lifespan.
        points = self.runtime.points_worker
        assert points is not None
        points.start()

    def console(self, *arguments: str) -> dict:
        output, errors = io.StringIO(), io.StringIO()
        result = admin.main(
            ["--channel", self.channel, "--data-directory", str(self.data_directory), *arguments],
            output_stream=output,
            error_stream=errors,
        )
        assert result == 0, errors.getvalue()
        return json.loads(output.getvalue())

    def operator(self, action: str) -> None:
        # Real installation-console operations on disposable data only; never a product bypass.
        checkpoint = Path(self.directory.name) / "checkpoint"
        prepared = Path(self.directory.name) / "prepared"
        if action == "snapshot":
            assert self.console("snapshot", "create", str(checkpoint))["state"] == "created"
        else:
            assert action == "restore"
            self.runtime.close()
            self.runtime = None
            try:
                assert (
                    self.console("restore", "prepare", str(checkpoint), str(prepared))["state"]
                    == "prepared"
                )
                assert self.console("restore", "activate", str(prepared))["state"] == "active"
            finally:
                self.start()

    def seed_calendar_review(self) -> dict:
        storage = self.runtime.storage
        assert storage is not None
        database, installation = storage.database, storage.installation
        actor = SimpleNamespace(current=lambda: self.ha.person("a" * 32))
        identifiers = SecureIdentifiers()
        clock = SystemClock()
        times = PinnedRecurrenceTime()
        planner = FixedRecurrencePlanner(CalendarNominalExpansion(), times)
        with database.read() as unit:
            member = unit.members.by_user("home", "a" * 32)
            household = unit.households.current()
            assert member is not None and household is not None
        today = datetime.now(UTC).date()
        first = datetime.combine(today - timedelta(days=2), time(7, 0))
        final = first + timedelta(days=4)
        title = "Fictional calendar work <img src=x onerror=alert(1)>"
        schedule = (
            RecurrenceCommands(database, actor, clock, identifiers, planner)
            .create_fixed(
                "calendar-fixture-rule",
                CreateFixedTask(
                    CreateTask(
                        TaskContent(title),
                        overrides=TaskOverrides(verification=VerificationMode.ADULT),
                    ),
                    parse_fixed_pattern("FREQ=DAILY;COUNT=5", NominalTime(first)),
                    TimePolicy(household.time_zone, times.data_identity),
                ),
            )
            .result.decode()["schedule_id"]
        )
        maintenance = FixedMaintenance(
            database, MaintenanceScope(installation, "home"), planner, clock, identifiers
        )
        horizon = NominalTime(final + timedelta(days=1))
        steps = [maintenance.step(schedule, horizon) for _ in range(5)]
        assert all(step.status == "created" for step in steps), [step.status for step in steps]
        work = [step.occurrence_id for step in steps]
        commands = TaskCommands(database, actor, clock, identifiers)
        completed = commands.complete(
            "calendar-fixture-complete",
            CompleteTask(work[0], 1, (member.member_id,), clock.now() - 60_000),
        ).result.decode()
        commands.verify(
            "calendar-fixture-approval",
            VerifyTask(
                work[0],
                2,
                completed["cycle"]["cycle_id"],
                VerificationState.APPROVED,
            ),
        )
        commands.assign("calendar-fixture-assigned", AssignTask(work[3], 1, (member.member_id,)))
        commands.transition(
            "calendar-fixture-start", TransitionTask(work[3], 2, OccurrenceState.IN_PROGRESS)
        )
        return {
            "title": title,
            "completed": work[0],
            "started": work[3],
            "future": work[4],
            "first": first.date().isoformat(),
            "new_date": final.date().isoformat(),
        }

    def stats(self) -> dict:
        with sqlite3.connect(f"file:{self.database}?mode=ro", uri=True) as connection:
            counts = {
                name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                if name
                in {"households", "receipts", "audit", "outbox", "members", "retained_operations"}
            }
        return {"counts": counts, "revoked": self.ha.revoked, "mode": self.mode}

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    self.close()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        request = Request(scope, receive)
        path = scope["path"]
        response = None
        if path == "/__fixture__/ready":
            response = JSONResponse({"state": "ready", "fixture": True})
        elif path == "/__fixture__/reset" and request.method == "POST":
            values = (
                await request.json()
                if request.headers.get("content-type") == "application/json"
                else {}
            )
            assert set(values) <= {"channel"}
            self.reset(values.get("channel", "edge"))
            response = JSONResponse(self.stats())
        elif path == "/__fixture__/calendar-review" and request.method == "POST":
            response = JSONResponse(self.seed_calendar_review())
        elif path == "/__fixture__/operator" and request.method == "POST":
            values = await request.json()
            assert set(values) == {"action"}
            self.operator(values["action"])
            response = JSONResponse({"state": "completed", "fixture": True})
        elif path == "/__fixture__/stats":
            response = JSONResponse(self.stats())
        elif path == "/__fixture__/revision" and request.method == "POST":
            # Direct disposable fixture setup, not a product command or migration/history claim.
            values = await request.json()
            assert (
                set(values) in ({"revision"}, {"revision", "calendar"})
                and type(values["revision"]) is str
            )
            assert "calendar" not in values or values["calendar"] is True
            revision = int(values["revision"])
            assert str(revision) == values["revision"] and 1 <= revision <= 2**63 - 1
            with sqlite3.connect(self.database) as connection:
                tables = (
                    ("calendar_preferences",)
                    if values.get("calendar")
                    else ("households", "members", "household_policy")
                )
                for table in tables:
                    cursor = connection.execute(f'UPDATE "{table}" SET revision=?', (revision,))
                    assert cursor.rowcount > 0
            response = JSONResponse({"state": "changed", "fixture": True})
        elif path == "/__fixture__/writer" and request.method == "POST":
            values = await request.json()
            assert set(values) == {"action"}
            assert values["action"] in ("acquire", "release")
            if values["action"] == "acquire":
                assert self.writer is None
                self.writer = sqlite3.connect(self.database, autocommit=True)
                self.writer.execute("BEGIN IMMEDIATE")
            else:
                self.release_writer()
            response = JSONResponse({"state": values["action"], "fixture": True})
        elif path == "/__fixture__/identity" and request.method == "POST":
            values = await request.json()
            assert set(values) <= {"subject", "outage", "rejected"}
            if "subject" in values:
                assert values["subject"] in self.ha.people
                self.ha.subject = values["subject"]
            if "outage" in values:
                assert type(values["outage"]) is bool
                self.ha.outage = values["outage"]
            if "rejected" in values:
                assert type(values["rejected"]) is bool
                self.ha.rejected = values["rejected"]
            response = JSONResponse({"state": "changed", "fixture": True})
        elif self.mode == "standalone" and path == "/auth/authorize":
            query = parse_qs(scope["query_string"].decode())
            assert query["client_id"] == [self.origin + "/"]
            assert query["redirect_uri"] == [self.origin + "/api/v1/auth/callback"]
            assert query["code_challenge_method"] == ["S256"]
            code = secrets.token_urlsafe(24)
            self.ha.grants[code] = (query["code_challenge"][0], self.ha.subject)
            target = (
                self.origin
                + "/api/v1/auth/callback?"
                + urlencode({"state": query["state"][0], "code": code})
            )
            response = HTMLResponse(
                '<!doctype html><html lang="en"><title>Fictional HA</title>'
                '<h1>Fictional Home Assistant</h1><a href="'
                + html.escape(target, quote=True)
                + '">Continue as fixture user</a></html>'
            )
        if response is not None:
            await response(scope, receive, send)
            return
        if self.mode == "native":
            if not (path == PREFIX or path.startswith(PREFIX + "/")):
                await JSONResponse({"state": "missing"}, 404)(scope, receive, send)
                return
            relative = path[len(PREFIX) :] or "/"
            headers = [
                (key, value)
                for key, value in scope["headers"]
                if not key.lower().startswith(b"x-remote-user-")
                and key.lower() != b"x-ingress-path"
            ]
            headers += [
                (b"x-ingress-path", PREFIX.encode()),
                # Fictional Supervisor session lookup, never a browser-supplied actor header.
                (
                    b"x-remote-user-id",
                    (
                        "c" * 32
                        if request.cookies.get("ingress_session") == "e" * 128
                        else self.ha.subject
                    ).encode(),
                ),
            ]
            scope = {
                **scope,
                "client": ("172.30.32.2", 1234),
                "path": relative,
                "raw_path": scope["raw_path"][len(PREFIX) :] or b"/",
                "root_path": "",
                "headers": headers,
            }
        await self.runtime.app(scope, receive, send)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("native", "standalone"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--origin-port", type=int)
    args = parser.parse_args()
    image = os.environ.get("DOMUS_BROWSER_IMAGE")
    if image:
        from image_bridge import ImageBridge

        fixture = ImageBridge(
            image,
            args.mode,
            args.port,
            os.environ["DOMUS_TEST_SOURCE_COMMIT"],
            os.environ["DOMUS_TEST_ARCH"],
        )
        fixture.start()
    else:
        fixture = Fixture(args.mode, args.port, args.origin_port)
    try:
        uvicorn.run(
            fixture,
            host="127.0.0.1",
            port=args.port,
            access_log=False,
            log_level="warning",
            server_header=False,
        )
    finally:
        fixture.close()


if __name__ == "__main__":
    main()
