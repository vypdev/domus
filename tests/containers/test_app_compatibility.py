"""The actual previous image upgrades safely and cannot downgrade retained current state."""

import json
import os
import uuid

import pytest
from test_app_image import (
    _STORAGE_COMMAND,
    console,
    docker,
    packaged_fixture,
    ready,
    stopped,
    successful,
)
from test_app_image import data_volume as data_volume
from test_app_image import image as image
from test_app_image import restore_runtime as restore_runtime


@pytest.fixture
def previous_image():
    value = os.environ.get("DOMUS_PREVIOUS_IMAGE")
    assert value, "Set DOMUS_PREVIOUS_IMAGE to the reviewed schema-3 Edge.2 image"
    result = docker("image", "inspect", value)
    assert result.returncode == 0, result.stderr
    labels = json.loads(result.stdout)[0]["Config"]["Labels"]
    assert labels["org.opencontainers.image.revision"] == "d013cf2c8b932d0e00f5858053cbc0e663d5eee1"
    assert labels["io.hass.version"] == "0.0.0-edge.2"
    return value


def inventory(image, volume):
    return successful(
        docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "65532:65532",
            "--volume",
            volume + ":/data",
            "--entrypoint",
            "/app/.venv/bin/python",
            image,
            "-c",
            "import pathlib,hashlib,json; root=pathlib.Path('/data/domus'); "
            "print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() "
            "for p in root.rglob('*') if p.is_file()}))",
        )
    )


def refuse_old_image(image, previous, volume):
    before = inventory(image, volume)
    refused = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        volume + ":/data",
        "--env",
        "SUPERVISOR_TOKEN=fixture-supervisor-token",
        previous,
    )
    assert refused.returncode == 2, refused.stderr
    assert "fixture-supervisor-token" not in refused.stdout + refused.stderr
    assert inventory(image, volume) == before


@pytest.mark.parametrize("restore_runtime", ["native", "standalone"], indirect=True)
def test_actual_older_image_refuses_selected_generation_without_changing_any_file(
    image, previous_image, restore_runtime
):
    name, volume, _, identifier, mode = restore_runtime
    successful(
        console(
            image,
            volume,
            "--data-directory",
            "/data/domus",
            "restore",
            "activate",
            "/data/snapshots/prepared",
        )
    )
    refuse_old_image(image, previous_image, volume)
    assert docker("start", name).returncode == 0
    ready(name, standalone=mode == "standalone")
    assert (
        successful(packaged_fixture(image, volume, "active", "suppressed"))["generation_id"]
        == identifier
    )
    stopped(name)


def test_real_schema_three_image_upgrades_replays_and_restores_its_pre_upgrade_snapshot(
    image, previous_image, data_volume
):
    old = "domus-upgrade-old-" + uuid.uuid4().hex
    new = "domus-upgrade-new-" + uuid.uuid4().hex
    try:
        result = docker(
            "run",
            "--detach",
            "--init",
            "--network",
            "none",
            "--name",
            old,
            "--volume",
            data_volume + ":/data",
            "--env",
            "SUPERVISOR_TOKEN=fixture-supervisor-token",
            previous_image,
        )
        assert result.returncode == 0, result.stderr
        ready(old)
        seeded = docker(
            "exec",
            "--user",
            "65532:65532",
            old,
            "/app/.venv/bin/python",
            "-c",
            _STORAGE_COMMAND,
            "0",
        )
        assert seeded.returncode == 0, seeded.stderr
        result = docker(
            "exec",
            old,
            "/app/.venv/bin/python",
            "-c",
            "import os; os.mkdir('/data/snapshots',0o700); os.chown('/data/snapshots',65532,65532)",
        )
        assert result.returncode == 0, result.stderr
        checkpoint = successful(
            console(
                previous_image,
                data_volume,
                "--data-directory",
                "/data/domus",
                "snapshot",
                "create",
                "/data/snapshots/schema3",
            )
        )
        assert checkpoint["snapshot"]["schema_version"] == 3
        instance_id = checkpoint["snapshot"]["instance_id"]
        stopped(old)
        result = docker(
            "run",
            "--detach",
            "--init",
            "--network",
            "none",
            "--name",
            new,
            "--volume",
            data_volume + ":/data",
            "--env",
            "SUPERVISOR_TOKEN=fixture-supervisor-token",
            image,
        )
        assert result.returncode == 0, result.stderr
        ready(new)
        replay = docker(
            "exec",
            "--user",
            "65532:65532",
            new,
            "/app/.venv/bin/python",
            "-c",
            _STORAGE_COMMAND,
            "1",
        )
        assert replay.returncode == 0, replay.stderr
        current = successful(
            console(
                image,
                data_volume,
                "--data-directory",
                "/data/domus",
                "snapshot",
                "create",
                "/data/snapshots/schema4",
            )
        )
        assert current["snapshot"]["schema_version"] == 4
        assert current["snapshot"]["instance_id"] == instance_id
        inspected = successful(
            console(
                image,
                data_volume,
                "--instance-id",
                instance_id,
                "snapshot",
                "inspect",
                "/data/snapshots/schema3",
            )
        )
        assert inspected["snapshot"] == checkpoint["snapshot"]
        stopped(new)
        # Even without generation selection, the older image must refuse the future schema.
        refuse_old_image(image, previous_image, data_volume)
        successful(
            console(
                image,
                data_volume,
                "--data-directory",
                "/data/domus",
                "restore",
                "prepare",
                "/data/snapshots/schema3",
                "/data/snapshots/prepared3",
            )
        )
        active = successful(
            console(
                image,
                data_volume,
                "--data-directory",
                "/data/domus",
                "restore",
                "activate",
                "/data/snapshots/prepared3",
            )
        )
        assert active["state"] == "active"
        assert docker("start", new).returncode == 0
        ready(new)
        replay = docker(
            "exec",
            "--user",
            "65532:65532",
            new,
            "/app/.venv/bin/python",
            "-c",
            _STORAGE_COMMAND,
            "1",
        )
        assert replay.returncode == 0, replay.stderr
        final = successful(
            console(
                image,
                data_volume,
                "--data-directory",
                "/data/domus",
                "restore",
                "status",
                active["selected_generation"],
            )
        )
        assert final["state"] == "active"
        stopped(new)
    finally:
        for name in (old, new):
            result = docker("rm", "--force", name)
            assert result.returncode == 0 or "No such container" in result.stderr, result.stderr
