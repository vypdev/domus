"""Enforce the every-PR workflow contract and immutable installed resources."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from domus_tooling.ci_policy import REQUIRED_JOBS

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci_check.yml"
PROTECTED = ROOT / "tests/contracts/copilot-resource-hashes.json"


def workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_every_pr_update_and_merge_queue_run_without_path_filters() -> None:
    config = workflow()
    assert config["name"] == "CI Check"
    assert {"opened", "reopened", "synchronize", "ready_for_review", "converted_to_draft"} <= set(
        config["on"]["pull_request"]["types"]
    )
    assert set(config["on"]["pull_request"]) == {"types"}
    assert config["on"]["merge_group"]["types"] == ["checks_requested"]
    assert set(config["on"]["push"]["branches"]) == {"develop", "master"}


def test_required_jobs_always_reach_a_fail_closed_aggregate() -> None:
    config = workflow()
    jobs = config["jobs"]
    assert set(jobs) == {*REQUIRED_JOBS, "aggregate"}
    aggregate = jobs["aggregate"]
    assert aggregate["name"] == "CI Check"
    assert set(aggregate["needs"]) == set(REQUIRED_JOBS)
    assert aggregate["if"] == "${{ always() }}"
    assert aggregate["env"]["DOMUS_CI_RESULTS"] == "${{ toJSON(needs) }}"
    for name in REQUIRED_JOBS:
        assert "if" not in jobs[name], f"{name} must not skip applicable PR updates"


def test_ci_is_read_only_with_immutable_actions_and_locked_installs() -> None:
    config = workflow()
    assert config["permissions"] == {"contents": "read"}
    for job in config["jobs"].values():
        assert "permissions" not in job
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w/-]+@[a-f0-9]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "uv sync --frozen" in source
    assert "pnpm install --frozen-lockfile" in source
    assert "secrets." not in source


def test_new_runtime_sources_require_an_explicit_coverage_scope() -> None:
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    declared_node_configuration = {"architecture/frontend.mjs", "vitest.config.mjs"}
    for relative in paths:
        if not relative or relative.startswith("tests/"):
            continue
        suffix = Path(relative).suffix
        if suffix == ".py":
            assert relative.startswith("tooling/domus_tooling/"), (
                f"Register {relative} in its own tested coverage/architecture gate before adding it"
            )
        elif suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx"}:
            assert relative in declared_node_configuration, (
                f"Register {relative} in its own tested coverage/architecture gate before adding it"
            )


@pytest.mark.parametrize("relative,expected", sorted(json.loads(PROTECTED.read_text()).items()))
def test_installed_copilot_resources_are_unchanged(relative: str, expected: str) -> None:
    assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
