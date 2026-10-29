"""Real import graphs prove that the application policy rejects forbidden edges."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

POLICY = Path(__file__).resolve().parents[2] / "architecture/python-application.ini"
LINTER = Path(sys.executable).with_name("lint-imports")


def check(root: Path, sources: dict[str, str]) -> subprocess.CompletedProcess[str]:
    for package in ("", "domain", "application", "infrastructure", "entrypoints", "composition"):
        target = root / "domus" / package / "__init__.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    for relative, source in sources.items():
        target = root / "domus" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return subprocess.run(
        [str(LINTER), "--config", str(POLICY), "--no-cache", "--no-logo"],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root)},
        text=True,
        capture_output=True,
        check=False,
    )


def test_dependencies_point_inward(tmp_path: Path) -> None:
    result = check(
        tmp_path,
        {
            "domain/model.py": "from dataclasses import dataclass\n",
            "application/service.py": "from domus.domain import model\n",
            "infrastructure/store.py": "from domus.application import service\n",
            "entrypoints/http.py": "from domus.application import service\n",
            "composition/root.py": "\n".join(
                ("from domus.entrypoints import http", "from domus.infrastructure import store", "")
            ),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_inner_layer_cannot_import_infrastructure(tmp_path: Path, layer: str) -> None:
    result = check(
        tmp_path,
        {
            "infrastructure/store.py": "value = 1\n",
            f"{layer}/invalid.py": "from domus.infrastructure import store\n",
        },
    )
    assert result.returncode != 0
    assert "Application dependencies point inward BROKEN" in result.stdout


@pytest.mark.parametrize(
    "dependency", ["fastapi", "homeassistant", "httpx", "sqlite3", "sqlalchemy"]
)
def test_inner_framework_or_io_dependency_is_rejected(tmp_path: Path, dependency: str) -> None:
    result = check(tmp_path, {"domain/invalid.py": f"import {dependency}\n"})
    assert result.returncode != 0
    assert "Domain and application exclude concrete frameworks and I/O BROKEN" in result.stdout


def test_cycle_inside_domain_is_rejected(tmp_path: Path) -> None:
    result = check(
        tmp_path,
        {
            "domain/one.py": "from domus.domain import two\n",
            "domain/two.py": "from domus.domain import one\n",
        },
    )
    assert result.returncode != 0
    assert "Application modules remain acyclic BROKEN" in result.stdout


def test_entrypoint_cannot_import_storage_adapter(tmp_path: Path) -> None:
    result = check(
        tmp_path,
        {
            "infrastructure/store.py": "value = 1\n",
            "entrypoints/http.py": "from domus.infrastructure import store\n",
        },
    )
    assert result.returncode != 0
    assert "Application dependencies point inward BROKEN" in result.stdout
