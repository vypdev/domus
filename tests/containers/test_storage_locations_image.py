"""C06/C08: genuine previous data and restoration in each actual CPU image."""

import json
from pathlib import Path

import pytest
from test_app_image import docker
from test_app_image import image as image


@pytest.mark.parametrize("version", [20, 30, 37])
def test_packaged_location_lifecycle_migrates_restarts_and_restores_real_prior_data(image, version):
    fixture = Path(__file__).with_name("storage_locations_runtime.py")
    sql = Path(__file__).parents[1] / "fixtures/sqlite"
    result = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--volume",
        f"{fixture}:/tmp/storage_locations_runtime.py:ro",
        "--volume",
        f"{sql}:/tmp/sqlite-fixtures:ro",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "/tmp/storage_locations_runtime.py",
        "/tmp/sqlite-fixtures",
        str(version),
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "source_schema": version,
        "current_schema": 38,
        "original_columns_preserved": True,
        "populated_archive_refused": True,
        "paired_transfer_receipt_retained": True,
        "fresh_process_replay": True,
        "snapshot_restoration": True,
        "historical_restore_did_not_reenact": True,
    }
