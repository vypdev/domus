"""Check observable command outcomes and retained failure diagnostics."""

import json
from pathlib import Path

import pytest

from domus_tooling.ci_policy import REQUIRED_JOBS
from domus_tooling.cli import main


def test_successful_aggregate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    results = {name: {"result": "success"} for name in REQUIRED_JOBS}
    monkeypatch.setenv("DOMUS_CI_RESULTS", json.dumps(results))
    assert main(["aggregate"]) == 0
    assert capsys.readouterr().out == "aggregate: all required checks passed\n"


@pytest.mark.parametrize("raw", ["", "not-json", "{broken"])
def test_invalid_aggregate_json(
    raw: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOMUS_CI_RESULTS", raw)
    assert main(["aggregate"]) == 1
    assert "Invalid or missing" in capsys.readouterr().out


@pytest.mark.parametrize("raw", ["[]", "null", '"success"'])
def test_aggregate_requires_object(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOMUS_CI_RESULTS", raw)
    assert main(["aggregate"]) == 1


def test_missing_environment_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOMUS_CI_RESULTS", raising=False)
    assert main(["aggregate"]) == 1


def test_failed_jobs_are_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOMUS_CI_RESULTS", "{}")
    assert main(["aggregate"]) == 1
    assert "documentation: missing" in capsys.readouterr().out


def test_docs_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Documentation", encoding="utf-8")
    assert main(["docs", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "docs: all required checks passed\n"


def test_docs_failure_retains_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["docs", "--root", str(tmp_path)]) == 1
    assert "Missing document: README.md" in capsys.readouterr().out
