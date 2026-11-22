"""Qualify manual shopping annotations in each actual installed CPU image."""

import json
from pathlib import Path

import pytest
from test_app_image import docker
from test_app_image import image as image


@pytest.mark.parametrize("version", [20, 36])
def test_packaged_annotations_migrate_restart_and_restore_genuine_previous_data(image, version):
    fixture = Path(__file__).with_name("shopping_annotations_runtime.py")
    sql = Path(__file__).parents[1] / "fixtures/sqlite"
    result = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--volume",
        f"{fixture}:/tmp/shopping_annotations_runtime.py:ro",
        "--volume",
        f"{sql}:/tmp/sqlite-fixtures:ro",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "/tmp/shopping_annotations_runtime.py",
        "/tmp/sqlite-fixtures",
        str(version),
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "source_schema": version,
        "current_schema": 37,
        "all_original_columns_preserved": True,
        "literal_annotations": True,
        "fresh_process_replay": True,
        "snapshot_restoration": True,
        "historical_clear_preserved": True,
    }
