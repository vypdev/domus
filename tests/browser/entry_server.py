"""Disposable loopback HA/Supervisor fixtures around the unchanged product trust boundaries.

This executable is test-only, never packaged. Its control routes replace fictional identities and
owned temporary databases. No real HA instance, credentials, host storage or authentication bypass
flag is used by the product. The native wrapper represents the outer trusted Supervisor peer.
"""

import argparse
import base64
import hashlib
import html
import secrets
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlencode
from uuid import uuid4

import pytest
import uvicorn
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from domus.composition import ingress, server
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
        }
        self.subject = "a" * 32
        self.outage = False
        self.grants = {}
        self.token_subjects = {}
        self.revoked = 0

    def person(self, user_id: str) -> HumanIdentity:
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
        self.patch = pytest.MonkeyPatch()
        self.patch.setattr(ingress, "HomeAssistantWebSocket", lambda endpoint: self.ha)
        self.patch.setattr(server, "HomeAssistantWebSocket", lambda endpoint: self.ha)
        self.patch.setattr(server, "HomeAssistantOAuth", lambda config: OAuth(config, self.ha))
        self.reset()

    def reset(self) -> None:
        if self.runtime is not None:
            self.runtime.close()
        if self.directory is not None:
            self.directory.cleanup()
        self.directory = tempfile.TemporaryDirectory(prefix=f"domus-entry-browser-{self.mode}-")
        self.database = Path(self.directory.name) / "household.sqlite3"
        self.ha = HomeAssistant(
            HAEndpoint.supervisor() if self.mode == "native" else HAEndpoint(self.origin)
        )
        instance = str(uuid4())
        if self.mode == "native":
            self.runtime = ingress.create_business_runtime(
                "fixture-supervisor-token", "edge", self.database, instance, (self.origin,)
            )
        else:
            self.runtime = server.create_runtime(
                self.origin,
                self.origin,
                instance,
                "edge",
                development_http=True,
                database=self.database,
            )

    def stats(self) -> dict:
        with sqlite3.connect(f"file:{self.database}?mode=ro", uri=True) as connection:
            counts = {
                name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                if name in {"households", "receipts", "audit", "outbox", "members"}
            }
        return {"counts": counts, "revoked": self.ha.revoked, "mode": self.mode}

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
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
            self.reset()
            response = JSONResponse(self.stats())
        elif path == "/__fixture__/stats":
            response = JSONResponse(self.stats())
        elif path == "/__fixture__/identity" and request.method == "POST":
            values = await request.json()
            assert set(values) <= {"subject", "outage"}
            if "subject" in values:
                assert values["subject"] in self.ha.people
                self.ha.subject = values["subject"]
            if "outage" in values:
                assert type(values["outage"]) is bool
                self.ha.outage = values["outage"]
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
                (b"x-remote-user-id", self.ha.subject.encode()),
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
