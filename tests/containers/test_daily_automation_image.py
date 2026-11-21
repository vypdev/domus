"""Exercise the actual scheduled worker in each compiled CPU image and composition."""

from pathlib import Path

import pytest
from test_app_image import docker
from test_app_image import image as image


@pytest.mark.parametrize("mode", ["native", "standalone"])
@pytest.mark.parametrize("restart_admitted", [False, True])
def test_packaged_daily_worker_owns_effects_restart_revocation_and_shutdown(
    image, mode, restart_admitted
):
    fixture = Path(__file__).with_name("daily_runtime.py")
    result = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--volume",
        f"{fixture}:/tmp/daily_runtime.py:ro",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "/tmp/daily_runtime.py",
        mode,
        str(restart_admitted),
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"daily_tasks": 1' in result.stdout and '"worker_joined": true' in result.stdout
    assert '"cancelled_checkpoint_restored_without_a_task": true' in result.stdout
