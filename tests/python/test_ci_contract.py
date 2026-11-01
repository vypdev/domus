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


def test_native_app_images_are_built_and_exercised_on_both_cpu_families() -> None:
    jobs = workflow()["jobs"]
    container = jobs["containers"]
    assert container["strategy"]["fail-fast"] == "false"
    assert container["strategy"]["matrix"]["include"] == [
        {"runner": "ubuntu-latest", "arch": "amd64"},
        {"runner": "ubuntu-24.04-arm", "arch": "aarch64"},
    ]
    assert container["runs-on"] == "${{ matrix.runner }}"
    commands = [step["run"] for step in container["steps"] if "run" in step]
    assert (
        "docker build --build-arg BUILD_ARCH=${{ matrix.arch }} -t domus-app-ci addon-edge"
        in commands
    )
    assert "uv run pytest tests/containers --no-cov" in commands
    assert any(
        "DOMUS_SOURCE_COMMIT=d013cf2c8b932d0e00f5858053cbc0e663d5eee1" in command
        and "DOMUS_SOURCE_SHA256=fa58d457bef8a863a1943b4e6ba5c9513da8d3baa8b0a033bdcbe7bf11b09c6c"
        in command
        and "BUILD_VERSION=0.0.0-edge.2" in command
        and "-t domus-app-previous addon-edge" in command
        for command in commands
    )
    verification = next(
        step
        for step in container["steps"]
        if step.get("run") == "uv run pytest tests/containers --no-cov"
    )
    assert verification["env"]["DOMUS_PREVIOUS_IMAGE"] == "domus-app-previous"
    assert "containers" in jobs["aggregate"]["needs"]


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
    declared_node_configuration = {
        "architecture/frontend.mjs",
        "vitest.config.mjs",
        "tooling/frontend-coverage.mjs",
    }
    for relative in paths:
        if not relative or relative.startswith("tests/"):
            continue
        suffix = Path(relative).suffix
        if suffix == ".py":
            assert relative.startswith(("tooling/domus_tooling/", "backend/src/domus/")), (
                f"Register {relative} in its own tested coverage/architecture gate before adding it"
            )
        elif suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"}:
            assert relative in declared_node_configuration, (
                f"Register {relative} in its own tested coverage/architecture gate before adding it"
            )


def test_frontend_toolchain_requires_actual_execution_and_separate_artifacts() -> None:
    jobs = workflow()["jobs"]
    job = jobs["frontend_toolchain"]
    commands = [step["run"] for step in job["steps"] if "run" in step]
    assert commands == [
        "pnpm install --frozen-lockfile",
        "pnpm --filter @domus/frontend-toolchain exec playwright install --with-deps chromium",
        "pnpm check:frontend-toolchain",
        "pnpm test:frontend-toolchain",
        "pnpm build:frontend-toolchain",
        "pnpm test:frontend-browser",
        "pnpm test:frontend-guards",
    ]
    artifact = next(step for step in job["steps"] if "path" in step.get("with", {}))
    assert artifact["if"] == "${{ always() }}"
    assert artifact["with"]["if-no-files-found"] == "error"
    assert "frontend-toolchain" in artifact["with"]["name"]
    assert "coverage-negative/" in artifact["with"]["path"]
    assert "storybook-static/" in artifact["with"]["path"]
    assert "frontend_toolchain" in jobs["aggregate"]["needs"]


def test_backend_cannot_inherit_the_tooling_coverage_result() -> None:
    jobs = workflow()["jobs"]
    backend_commands = [step["run"] for step in jobs["backend"]["steps"] if "run" in step]
    assert any(
        "pytest tests/backend" in command and "--cov=domus " in command
        for command in backend_commands
    )
    assert "backend" in REQUIRED_JOBS
    assert "backend" in jobs["aggregate"]["needs"]
    steps = jobs["backend"]["steps"]
    audit = next(
        i
        for i, step in enumerate(steps)
        if step.get("run") == "uv run domus-check backend-coverage --report coverage-backend.json"
    )
    assert "pytest tests/backend" in steps[audit - 1]["run"]
    assert "if" not in steps[audit] and "continue-on-error" not in steps[audit]
    assert "continue-on-error" not in jobs["backend"]
    assert all("continue-on-error" not in step for step in steps)
    architecture_commands = [step["run"] for step in jobs["architecture"]["steps"] if "run" in step]
    assert "uv run lint-imports --config architecture/python-application.ini --no-cache" in (
        architecture_commands
    )


@pytest.mark.parametrize("relative,expected", sorted(json.loads(PROTECTED.read_text()).items()))
def test_installed_copilot_resources_are_unchanged(relative: str, expected: str) -> None:
    assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
