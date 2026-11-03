"""The browser bridge must preserve wire evidence and own only its isolated container."""

import asyncio
import base64
import json
import runpy
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ImageBridge = runpy.run_path(str(ROOT / "tests/browser/image_bridge.py"))["ImageBridge"]
SOURCE = "a" * 40
IMAGE = "sha256:" + "b" * 64
CONTAINER = "c" * 64


class Docker:
    def __init__(self, *, revision=SOURCE, label_arch="aarch64", architecture="arm64", fail=None):
        self.calls = []
        self.fail = fail
        self.info = [
            {
                "Id": IMAGE,
                "Architecture": architecture,
                "Config": {
                    "Labels": {
                        "org.opencontainers.image.revision": revision,
                        "io.hass.arch": label_arch,
                    }
                },
            }
        ]
        self.reply = {
            "status": 409,
            "headers": [
                ["Content-Type", "application/json"],
                ["Cache-Control", "no-store"],
                ["Set-Cookie", "a=1"],
                ["Set-Cookie", "b=2"],
            ],
            "body": base64.b64encode(b'{"code":"revision_conflict"}').decode(),
        }

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        command = args[1]
        if command == self.fail:
            raise subprocess.CalledProcessError(1, args, stderr="Fictional Docker failure")
        if command == "image":
            output = json.dumps(self.info)
        elif command == "run":
            output = CONTAINER + "\n"
        elif command == "exec" and "-i" in args:
            output = json.dumps(self.reply)
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")


def bridge(docker):
    return ImageBridge("domus-app-ci", "native", 56174, SOURCE, "aarch64", runner=docker)


@pytest.mark.parametrize(
    "values",
    [
        {"revision": "d" * 40},
        {"label_arch": "amd64"},
        {"architecture": "amd64"},
    ],
)
def test_unreviewed_image_or_architecture_never_starts_a_container(values):
    docker = Docker(**values)
    with pytest.raises(ValueError):
        bridge(docker).start()
    assert not any(args[1] in {"run", "cp", "exec", "rm"} for args, _ in docker.calls)


def test_isolated_nonroot_container_uses_the_verified_image_id_and_cleanup_is_idempotent():
    docker = Docker()
    app = bridge(docker)
    app.start()
    arguments = next(args for args, _ in docker.calls if args[1] == "run")
    assert arguments[arguments.index("--network") + 1] == "none"
    assert arguments[arguments.index("--user") + 1] == "65532:65532"
    assert IMAGE in arguments and "domus-app-ci" not in arguments
    assert not any(arg in {"-p", "--publish", "-P", "--publish-all"} for arg in arguments)
    with pytest.raises(ValueError):
        app.start()
    app.close()
    app.close()
    assert [args for args, _ in docker.calls if args[1] == "rm"] == [
        ["docker", "rm", "--force", CONTAINER]
    ]


def test_failure_after_creation_cleans_only_the_returned_owned_container():
    docker = Docker(fail="cp")
    app = bridge(docker)
    with pytest.raises(subprocess.CalledProcessError):
        app.start()
    app.close()
    assert [args for args, _ in docker.calls if args[1] == "rm"] == [
        ["docker", "rm", "--force", CONTAINER]
    ]


def test_wire_exchange_preserves_original_binary_payload_context_and_non_success_reply():
    docker = Docker()
    app = bridge(docker)
    app.start()
    body = b'{"expected_revision":9007199254740993,"alias":"<b>literal</b>"}'
    headers = [
        ["Origin", "http://127.0.0.1:56174"],
        ["X-Domus-Context", "original"],
        ["Idempotency-Key", "original-key"],
    ]
    assert app.exchange("PUT", "/api/v1/household?exact=%2F", headers, body) == docker.reply
    _, options = next((args, kw) for args, kw in docker.calls if args[1] == "exec" and "-i" in args)
    encoded = json.loads(options["input"])
    assert encoded["method"] == "PUT" and encoded["path"] == "/api/v1/household?exact=%2F"
    assert encoded["headers"] == headers and base64.b64decode(encoded["body"]) == body
    app.close()


async def request(app, events, path="/api/v1/household"):
    responses = []
    pending = iter(events)

    async def receive():
        return next(pending)

    async def send(value):
        responses.append(value)

    await app(
        {
            "type": "http",
            "method": "PUT",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
        },
        receive,
        send,
    )
    return responses


def test_disconnect_or_oversized_browser_input_never_reaches_the_image():
    docker = Docker()
    app = bridge(docker)
    app.start()
    assert asyncio.run(request(app, [{"type": "http.disconnect"}])) == []
    result = asyncio.run(request(app, [{"type": "http.request", "body": b"x" * (2**21 + 1)}]))
    assert result[0]["status"] == 413
    assert not any(args[1] == "exec" and "-i" in args for args, _ in docker.calls)
    app.close()


def test_image_metadata_and_binary_error_response_are_readonly_and_not_success_substitutes():
    docker = Docker()
    app = bridge(docker)
    app.start()
    response = asyncio.run(
        request(app, [{"type": "http.request", "body": b""}], "/__fixture__/image")
    )
    assert json.loads(response[1]["body"]) == {
        "source_commit": SOURCE,
        "architecture": "aarch64",
        "image_id": IMAGE,
        "mode": "native",
    }
    response = asyncio.run(request(app, [{"type": "http.request", "body": b"original"}]))
    assert response[0]["status"] == 409
    assert [value for name, value in response[0]["headers"] if name.lower() == b"set-cookie"] == [
        b"a=1",
        b"b=2",
    ]
    assert response[1]["body"] == b'{"code":"revision_conflict"}'
    app.close()


@pytest.mark.parametrize(
    "reply",
    [
        {"status": True, "headers": [], "body": ""},
        {"status": 700, "headers": [], "body": ""},
        {"status": 200, "headers": [], "body": "!not-base64!"},
    ],
)
def test_invalid_image_transport_evidence_never_fabricates_a_success(reply):
    docker = Docker()
    docker.reply = reply
    app = bridge(docker)
    app.start()
    response = asyncio.run(request(app, [{"type": "http.request", "body": b"original"}]))
    assert response[0]["status"] == 502 and response[1]["body"] == b""
    app.close()


def test_failed_forwarding_keeps_a_transport_failure_instead_of_a_product_receipt():
    docker = Docker()
    app = bridge(docker)
    app.start()
    docker.fail = "exec"
    response = asyncio.run(request(app, [{"type": "http.request", "body": b"original"}]))
    assert response[0]["status"] == 502
    app.close()


def test_failed_container_creation_does_not_remove_an_unattributable_container():
    docker = Docker(fail="run")
    with pytest.raises(subprocess.CalledProcessError):
        bridge(docker).start()
    assert not any(args[1] == "rm" for args, _ in docker.calls)
