"""Verify the exact pinned app installed by the Supervisor, independently of current-source CI."""

import json
import os
from pathlib import Path

import pytest
import test_app_image as app_tests
from test_app_compatibility import previous_image as previous_image
from test_app_compatibility import (
    test_real_older_image_upgrades_replays_and_restores_its_pre_upgrade_snapshot as upgrade_cycle,
)
from test_app_image import data_volume as data_volume
from test_app_image import docker
from test_app_image import image as image
from test_app_ui import exercise_packaged_ui_delivery

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def edge_artifact():
    return json.loads((ROOT / "addon-edge/artifact.json").read_text())


@pytest.fixture
def edge_preview(edge_artifact):
    value = os.environ.get("DOMUS_EDGE_IMAGE")
    assert value, "Set DOMUS_EDGE_IMAGE to the actual pinned Supervisor app image"
    result = docker("image", "inspect", value)
    assert result.returncode == 0, result.stderr
    inspected = json.loads(result.stdout)[0]
    config = inspected["Config"]
    assert config["Labels"]["org.opencontainers.image.revision"] == edge_artifact["sourceCommit"]
    assert config["Labels"]["io.hass.version"] == edge_artifact["version"]
    assert (
        config["Labels"]["io.hass.arch"]
        == {"arm64": "aarch64", "amd64": "amd64"}[inspected["Architecture"]]
    )
    assert config["User"] == "0:0"
    assert config["Entrypoint"] == ["/app/.venv/bin/domus-ha-app", "--channel", "edge"]
    assert not any(value.startswith("SUPERVISOR_TOKEN=") for value in config["Env"])
    return value


def test_pinned_edge_runtime_and_bundle_match_every_reviewed_product_file(
    edge_preview, edge_artifact
):
    probe = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--entrypoint",
        "/app/.venv/bin/python",
        edge_preview,
        "-c",
        """import domus,hashlib,json,pathlib
root=pathlib.Path(domus.__file__).parent
python={
 "domus/"+p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
 for p in root.rglob("*.py")
}
ui={
 p.relative_to(root/"ui").as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
 for p in (root/"ui").rglob("*") if p.is_file()
}
print(json.dumps({"pythonFiles":python,"uiFiles":ui}))
""",
    )
    assert probe.returncode == 0, probe.stderr
    actual = json.loads(probe.stdout)
    assert actual["pythonFiles"] == edge_artifact["pythonFiles"]
    assert actual["uiFiles"] == edge_artifact["uiFiles"]
    assert len(actual["pythonFiles"]) == 218 and len(actual["uiFiles"]) == 4


def test_pinned_edge_native_launcher_authority_storage_and_restart(
    edge_preview, edge_artifact, data_volume
):
    app_tests.test_real_nonroot_listener_rejects_forgery_and_retains_storage_and_replay_on_restart(
        edge_preview, data_volume, expected_schema=edge_artifact["storageSchema"]
    )


def test_pinned_edge_standalone_listener_serves_the_exact_private_bundle(
    edge_preview, edge_artifact, data_volume
):
    exercise_packaged_ui_delivery(edge_preview, data_volume, edge_artifact["uiFiles"])


@pytest.mark.parametrize("previous_image", ["edge5"], indirect=True)
def test_pinned_edge_upgrades_actual_edge_five_and_preserves_original_history(
    edge_preview, edge_artifact, previous_image, data_volume
):
    upgrade_cycle(
        edge_preview, previous_image, data_volume, 7, expected_schema=edge_artifact["storageSchema"]
    )
