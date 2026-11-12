"""Loopback-only test transport to an isolated, verified production image.

The disposable provider fixture is copied into the writable test container after image creation.
The image and its installed product modules/UI stay unchanged and contain no fixture dependency.
"""

import asyncio
import base64
import json
import re
import subprocess
import threading
from pathlib import Path

from image_channel import ImageChannel

_CLIENT = r"""
import base64, http.client, json, sys
for line in sys.stdin:
    transport_id = None
    try:
        packet = json.loads(line)
        transport_id, value = packet['transport_id'], packet['request']
        body = base64.b64decode(value['body'], validate=True)
        connection = http.client.HTTPConnection('127.0.0.1', 8099, timeout=15)
        try:
            connection.putrequest(value['method'], value['path'],
                skip_host=True, skip_accept_encoding=True)
            for name, content in value['headers']:
                if name.lower() not in ('connection', 'transfer-encoding', 'content-length'):
                    connection.putheader(name, content)
            connection.putheader('Content-Length', str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            data = response.read(2**21 + 1)
            assert len(data) <= 2**21, 'Fixture response exceeds the transport budget'
            print(json.dumps({'transport_id': transport_id, 'response': {
                'status': response.status, 'headers': response.getheaders(),
                'body': base64.b64encode(data).decode()}}), flush=True)
        finally:
            connection.close()
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        print(json.dumps({'transport_id': transport_id,
            'response': {'transport_error': True}}), flush=True)
"""
_HOP = {b"connection", b"transfer-encoding", b"keep-alive", b"proxy-connection"}
_TRANSPORT_ERRORS = (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError)


class ImageBridge:
    def __init__(
        self,
        image,
        mode,
        port,
        source,
        architecture,
        *,
        runner=subprocess.run,
        channel_factory=ImageChannel,
    ):
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]*", image)
            or mode not in ("native", "standalone")
            or type(port) is not int
            or not 1 <= port <= 65535
            or not re.fullmatch(r"[a-f0-9]{40}", source)
            or architecture not in ("amd64", "aarch64")
        ):
            raise ValueError("Invalid reviewed image fixture configuration")
        self.image, self.mode, self.port = image, mode, port
        self.source, self.architecture = source, architecture
        self.runner, self.container, self.metadata = runner, None, None
        self.channel_factory = channel_factory
        self.channels, self.channels_lock = {}, threading.Lock()

    def run(self, *arguments, **options):
        return self.runner(
            ["docker", *arguments],
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
            **options,
        )

    def start(self):
        if self.container is not None:
            raise ValueError("An image fixture already owns a running container")
        data = json.loads(self.run("image", "inspect", self.image).stdout)[0]
        labels = data["Config"]["Labels"]
        if (
            labels.get("org.opencontainers.image.revision") != self.source
            or labels.get("io.hass.arch") != self.architecture
            or data["Architecture"] != {"amd64": "amd64", "aarch64": "arm64"}[self.architecture]
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", data["Id"])
        ):
            raise ValueError("Image identity or CPU architecture differs from the reviewed source")
        result = self.run(
            "run",
            "--detach",
            "--init",
            "--network",
            "none",
            "--user",
            "65532:65532",
            "--label",
            "domus.browser-fixture=true",
            "--label",
            f"domus.browser-fixture.image={self.image}",
            "--entrypoint",
            "/app/.venv/bin/python",
            data["Id"],
            "-c",
            "import signal; signal.pause()",
        )
        identifier = result.stdout.strip()
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise ValueError("Docker did not return an attributable container identity")
        self.container = identifier
        try:
            self.run(
                "cp",
                str(Path(__file__).with_name("entry_server.py")),
                identifier + ":/tmp/domus_browser_fixture.py",
            )
            self.run(
                "exec",
                "--detach",
                identifier,
                "/app/.venv/bin/python",
                "/tmp/domus_browser_fixture.py",
                "--mode",
                self.mode,
                "--port",
                "8099",
                "--origin-port",
                str(self.port),
            )
        except BaseException:
            self.close()
            raise
        self.metadata = {
            "source_commit": self.source,
            "architecture": self.architecture,
            "image_id": data["Id"],
            "mode": self.mode,
        }

    def close(self):
        with self.channels_lock:
            if self.container is not None:
                self.run("rm", "--force", self.container)
                self.container = None
            channels = tuple(self.channels.values())
            self.channels.clear()
        for channel in channels:
            channel.close()

    def exchange(self, method, path, headers, body):
        if self.container is None:
            raise ValueError("No verified image fixture is running")
        value = {
            "method": method,
            "path": path,
            "headers": headers,
            "body": base64.b64encode(body).decode(),
        }
        # A worker belongs to one host transport thread, preserving concurrent requests.
        # Each frame still creates one inner HTTP request; no mutation is replayed on failure.
        with self.channels_lock:
            if self.container is None:
                raise ValueError("No verified image fixture is running")
            owner = threading.get_ident()
            if owner not in self.channels:
                self.channels[owner] = self.channel_factory(
                    [
                        "docker",
                        "exec",
                        "-i",
                        self.container,
                        "/app/.venv/bin/python",
                        "-u",
                        "-c",
                        _CLIENT,
                    ]
                )
            channel = self.channels[owner]
        response = json.loads(channel.exchange(value))
        if type(response["status"]) is not int or not 100 <= response["status"] <= 599:
            raise ValueError("Invalid image response status")
        base64.b64decode(response["body"], validate=True)
        return response

    async def __call__(self, scope, receive, send):
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
        if scope["path"] == "/__fixture__/image":
            await self.respond(
                send,
                200,
                [[b"content-type", b"application/json"], [b"cache-control", b"no-store"]],
                json.dumps(self.metadata).encode(),
            )
            return
        # The readiness URL follows this proxy too: Playwright waits for the inner HTTP 200.
        # Local image metadata cannot make an unstarted inner fixture appear ready.
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if len(body) > 2**21:
                await self.respond(send, 413, [], b"")
                return
            if not event.get("more_body", False):
                break
        path = scope["raw_path"].decode("ascii")
        if scope["query_string"]:
            path += "?" + scope["query_string"].decode("ascii")
        headers = [
            [name.decode("latin1"), value.decode("latin1")] for name, value in scope["headers"]
        ]
        try:
            response = await asyncio.to_thread(
                self.exchange, scope["method"], path, headers, bytes(body)
            )
            values = [
                [name.encode("latin1"), value.encode("latin1")]
                for name, value in response["headers"]
                if name.lower().encode() not in _HOP
            ]
            payload = base64.b64decode(response["body"], validate=True)
        except _TRANSPORT_ERRORS:
            await self.respond(send, 502, [[b"cache-control", b"no-store"]], b"")
            return
        await self.respond(send, response["status"], values, payload)

    @staticmethod
    async def respond(send, status, headers, body):
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
