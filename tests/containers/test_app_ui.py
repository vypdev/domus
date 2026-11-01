"""The actual image must ship the exact built UI and serve it without browser authority."""

import json
import uuid
from pathlib import Path

from test_app_image import data_volume as data_volume
from test_app_image import docker, ready, stopped
from test_app_image import image as image


def test_packaged_ui_bytes_and_same_listener_standalone_delivery(image, data_volume):
    name = "domus-ui-image-" + uuid.uuid4().hex
    prepared = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        data_volume + ":/data",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        "import os; os.mkdir('/data/domus',0o700); os.chown('/data/domus',65532,65532)",
    )
    assert prepared.returncode == 0, prepared.stderr
    source = Path(__file__).with_name("ui_fixture.py").read_text()
    expected = json.loads(
        (
            Path(__file__).resolve().parents[2] / "docs/evidence/household-entry-interface.json"
        ).read_text()
    )["productDelivery"]["actualProductFiles"]
    try:
        started = docker(
            "run",
            "--detach",
            "--init",
            "--network",
            "none",
            "--name",
            name,
            "--user",
            "65532:65532",
            "--volume",
            data_volume + ":/data",
            "--entrypoint",
            "/app/.venv/bin/domus-server",
            image,
            "--channel",
            "edge",
            "--data-directory",
            "/data/domus",
            "--ha-url",
            "http://ha.fixture",
            "--public-origin",
            "https://domus.fixture",
            "--host",
            "0.0.0.0",
        )
        assert started.returncode == 0, started.stderr
        ready(name, standalone=True)
        result = docker("exec", name, "/app/.venv/bin/python", "-c", source, json.dumps(expected))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "ui_files": 4,
            "cookie_issued": False,
            "deployment": "standalone",
        }
        stopped(name)
    finally:
        removed = docker("rm", "--force", name)
        assert removed.returncode == 0 or "No such container" in removed.stderr, removed.stderr
