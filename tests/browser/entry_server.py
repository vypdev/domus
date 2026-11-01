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
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import pytest
import uvicorn
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from domus.composition import admin, ingress, server
from domus.domain.errors import IdentityRejected, IdentityUnavailable
from domus.domain.identity import HumanIdentity
from domus.infrastructure.ha_config import HAEndpoint
from domus.infrastructure.ha_http import OAuthTokens

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
    def __init__(self, mode: str, port: int) -> None:
        self.mode, self.origin = mode, f"http://127.0.0.1:{port}"
        self.runtime = self.directory = None
        self.writer = None
        self.patch = pytest.MonkeyPatch()
        self.patch.setattr(ingress, "HomeAssistantWebSocket", lambda endpoint: self.ha)
        self.patch.setattr(server, "HomeAssistantWebSocket", lambda endpoint: self.ha)
        self.patch.setattr(server, "HomeAssistantOAuth", lambda config: OAuth(config, self.ha))
        self.reset()

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
                    self.release_writer()
                    self.runtime.close()
                    self.directory.cleanup()
                    self.patch.undo()
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
        elif path == "/__fixture__/operator" and request.method == "POST":
            values = await request.json()
            assert set(values) == {"action"}
            self.operator(values["action"])
            response = JSONResponse({"state": "completed", "fixture": True})
        elif path == "/__fixture__/stats":
            response = JSONResponse(self.stats())
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
    args = parser.parse_args()
    uvicorn.run(
        Fixture(args.mode, args.port),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
        server_header=False,
    )


if __name__ == "__main__":
    main()
