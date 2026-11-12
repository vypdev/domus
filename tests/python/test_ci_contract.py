"""Enforce the branch CI workflow contract and immutable installed resources."""

import ast
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


def test_ci_runs_on_every_branch_push_without_accepting_pr_events() -> None:
    config = workflow()
    assert config["name"] == "CI Check"
    assert config["on"] == {"push": {"branches": ["**"]}}


def test_required_jobs_always_reach_a_fail_closed_aggregate() -> None:
    config = workflow()
    jobs = config["jobs"]
    assert set(jobs) == {*REQUIRED_JOBS, "aggregate"}
    aggregate = jobs["aggregate"]
    assert aggregate["name"] == "CI Check"
    assert set(aggregate["needs"]) == set(REQUIRED_JOBS)
    assert aggregate["if"] == "${{ always() }}"
    assert aggregate["env"]["DOMUS_CI_RESULTS"] == "${{ toJSON(needs) }}"
    for name, job in jobs.items():
        if name != "containers":
            assert job["runs-on"] == {
                "group": "vypdev",
                "labels": ["self-hosted", "codex", "Linux"],
            }


def test_linux_app_images_are_built_and_exercised_on_both_cpu_families() -> None:
    jobs = workflow()["jobs"]
    container = jobs["containers"]
    assert container["strategy"]["fail-fast"] == "false"
    platforms = container["strategy"]["matrix"]["include"]
    assert [(row["arch"], row["platform"], row["machine"]) for row in platforms] == [
        ("amd64", "linux/amd64", "x86_64"),
        ("aarch64", "linux/arm64", "aarch64"),
    ]
    assert all(re.fullmatch(r"sha256:[a-f0-9]{64}", row["core_digest"]) for row in platforms)
    assert len({row["core_digest"] for row in platforms}) == 2
    assert container["runs-on"] == {
        "group": "vypdev",
        "labels": ["self-hosted", "macOS", "ARM64"],
    }
    assert container["env"]["DOCKER_DEFAULT_PLATFORM"] == "${{ matrix.platform }}"
    assert container["env"]["DOMUS_HA_CORE_IMAGE"] == (
        "ghcr.io/home-assistant/home-assistant@${{ matrix.core_digest }}"
    )
    assert container["env"]["DOMUS_IMAGE_PREFIX"] == (
        "domus-ci-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.arch }}"
    )
    commands = [step["run"] for step in container["steps"] if "run" in step]
    assert any(
        'docker pull "$DOMUS_HA_CORE_IMAGE"' in command
        and '--entrypoint uname "$DOMUS_HA_CORE_IMAGE" -m' in command
        and 'test "$machine" = "$DOMUS_EXPECTED_MACHINE"' in command
        and 'docker buildx create --name "$DOMUS_IMAGE_PREFIX" --driver docker-container --use'
        in command
        for command in commands
    )
    build = 'docker buildx build --load --platform "$DOCKER_DEFAULT_PLATFORM"'
    assert (
        build + " --build-arg BUILD_ARCH=${{ matrix.arch }}"
        ' -t "$DOMUS_IMAGE_PREFIX:edge5" tests/fixtures/edge5-app' in commands
    )
    assert any(
        f"{build} --file tests/fixtures/current-app/Dockerfile" in command
        and "--build-arg BUILD_ARCH=${{ matrix.arch }}" in command
        and "--build-arg DOMUS_SOURCE_COMMIT=${{ github.sha }}" in command
        and "--build-arg BUILD_VERSION=ci-current" in command
        and command.rstrip().endswith('-t "$DOMUS_IMAGE_PREFIX:current" .')
        for command in commands
    )
    assert any(
        (build + " --build-arg BUILD_ARCH=${{ matrix.arch }}") in command
        and command.rstrip().endswith('-t "$DOMUS_IMAGE_PREFIX:edge" addon-edge')
        for command in commands
    )
    assert "uv run pytest tests/containers --no-cov" in commands
    assert any(
        "DOMUS_SOURCE_COMMIT=d013cf2c8b932d0e00f5858053cbc0e663d5eee1" in command
        and "DOMUS_SOURCE_SHA256=fa58d457bef8a863a1943b4e6ba5c9513da8d3baa8b0a033bdcbe7bf11b09c6c"
        in command
        and "BUILD_VERSION=0.0.0-edge.2" in command
        and '-t "$DOMUS_IMAGE_PREFIX:previous" tests/fixtures/edge3-app' in command
        for command in commands
    )
    verification = next(
        step
        for step in container["steps"]
        if step.get("run") == "uv run pytest tests/containers --no-cov"
    )
    assert verification["env"]["DOMUS_PREVIOUS_IMAGE"] == "${{ env.DOMUS_IMAGE_PREFIX }}:previous"
    assert verification["env"]["DOMUS_UPGRADE_IMAGE"] == "${{ env.DOMUS_IMAGE_PREFIX }}:installed"
    assert verification["env"]["DOMUS_TEST_IMAGE"] == "${{ env.DOMUS_IMAGE_PREFIX }}:current"
    assert verification["env"]["DOMUS_TEST_SOURCE_COMMIT"] == "${{ github.sha }}"
    assert verification["env"]["DOMUS_SCHEMA7_IMAGE"] == "${{ env.DOMUS_IMAGE_PREFIX }}:edge5"
    assert verification["env"]["DOMUS_EDGE_IMAGE"] == "${{ env.DOMUS_IMAGE_PREFIX }}:edge"
    assert any(
        '-t "$DOMUS_IMAGE_PREFIX:installed" tests/fixtures/edge3-app' in command
        for command in commands
    )
    assert "containers" in jobs["aggregate"]["needs"]


def test_ci_is_read_only_with_exact_action_versions_and_locked_installs() -> None:
    config = workflow()
    assert config["permissions"] == {"contents": "read"}
    for job in config["jobs"].values():
        assert "permissions" not in job
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w/-]+@v[0-9]+\.[0-9]+\.[0-9]+", step["uses"])
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
    declared_catalog_configuration = {
        "frontend/.storybook/main.ts",
        "frontend/.storybook/preview.ts",
        "frontend/stories/entry.stories.ts",
        "frontend/stories/administration.stories.ts",
        "frontend/stories/calendar.stories.ts",
        "frontend/stories/tasks.stories.ts",
        "frontend/playwright.config.ts",
        "frontend/playwright.entry.config.ts",
        "frontend/vite.config.ts",
    }
    for relative in paths:
        if not relative or relative.startswith(("tests/", "frontend/tests/")):
            continue
        suffix = Path(relative).suffix
        if suffix == ".py":
            assert relative.startswith(
                (
                    "tooling/domus_tooling/",
                    "backend/src/domus/",
                    "custom_components/domus_calendar/",
                )
            ), f"Register {relative} in its own tested coverage/architecture gate before adding it"
        elif suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"}:
            assert (
                relative in declared_node_configuration
                or relative in declared_catalog_configuration
                or relative == "frontend/vitest.config.ts"
                or relative.startswith("frontend/src/")
            ), f"Register {relative} in its own tested coverage/architecture gate before adding it"


def test_product_frontend_has_its_own_required_chromium_coverage_gate() -> None:
    jobs = workflow()["jobs"]
    job = jobs["frontend"]
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])
    commands = [step["run"] for step in job["steps"] if "run" in step]
    assert commands == [
        "uv sync --frozen",
        "pnpm install --frozen-lockfile",
        "pnpm --filter @domus/frontend exec playwright install chromium",
        "pnpm check:frontend",
        "pnpm test:frontend",
        "pnpm build:frontend",
        "uv build --package domus-server --wheel",
        "uv run pytest tests/packaging --no-cov",
        "flock -w 600 /tmp/domus-ci-entry-browser.lock pnpm test:frontend-entry",
        "pnpm build:frontend-catalog",
        "flock -w 600 /tmp/domus-ci-catalog-browser.lock pnpm test:frontend-catalog",
    ]
    assert "frontend" in REQUIRED_JOBS
    assert "frontend" in jobs["aggregate"]["needs"]
    artifact = next(step for step in job["steps"] if "path" in step.get("with", {}))
    assert artifact["if"] == "${{ always() }}"
    assert artifact["with"]["path"].split() == [
        "frontend/coverage/",
        "frontend/storybook-static/",
        "frontend/test-results/",
        "backend/src/domus/ui/",
        "dist/*.whl",
    ]
    assert artifact["with"]["if-no-files-found"] == "error"
    assert artifact["with"]["include-hidden-files"] == "true"


def test_owned_component_catalog_is_typechecked_built_and_browser_exercised() -> None:
    package = json.loads((ROOT / "frontend/package.json").read_text())
    scripts = package["scripts"]
    assert scripts["check"] == "pnpm run check:runtime && pnpm run check:catalog"
    assert scripts["check:runtime"] == "tsc --noEmit -p tsconfig.json"
    assert scripts["check:catalog"] == "tsc --noEmit -p tsconfig.catalog.json"
    assert scripts["storybook:build"] == "storybook build --disable-telemetry --quiet"
    assert scripts["browser:catalog"] == "playwright test tests/e2e/catalog.spec.ts"
    runtime = json.loads((ROOT / "frontend/tsconfig.json").read_text())
    assert runtime["compilerOptions"]["skipLibCheck"] is False
    assert runtime["compilerOptions"]["strict"] is True
    catalog = json.loads((ROOT / "frontend/tsconfig.catalog.json").read_text())
    assert catalog["extends"] == "./tsconfig.json"
    assert catalog["include"] == ["src", "stories", ".storybook"]
    # Same isolated third-party declaration workaround as the existing toolchain fixture.
    assert catalog["compilerOptions"] == {"skipLibCheck": True}


def test_frontend_toolchain_requires_actual_execution_and_separate_artifacts() -> None:
    jobs = workflow()["jobs"]
    job = jobs["frontend_toolchain"]
    commands = [step["run"] for step in job["steps"] if "run" in step]
    assert commands == [
        "pnpm install --frozen-lockfile",
        "pnpm --filter @domus/frontend-toolchain exec playwright install chromium",
        "pnpm check:frontend-toolchain",
        "pnpm test:frontend-toolchain",
        "pnpm build:frontend-toolchain",
        "flock -w 600 /tmp/domus-ci-toolchain-browser.lock pnpm test:frontend-browser",
        "flock -w 600 /tmp/domus-ci-toolchain-browser.lock pnpm test:frontend-guards",
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


def test_both_cpu_images_run_all_actual_household_browser_journeys() -> None:
    steps = workflow()["jobs"]["containers"]["steps"]
    actual = next(
        step
        for step in steps
        if step.get("name")
        == "Execute household workflows in the actual isolated image from Chromium"
    )
    assert actual["env"] == {
        "DOMUS_BROWSER_IMAGE": "${{ env.DOMUS_IMAGE_PREFIX }}:current",
        "DOMUS_TEST_SOURCE_COMMIT": "${{ github.sha }}",
        "DOMUS_TEST_ARCH": "${{ matrix.arch }}",
    }
    assert (
        "playwright.entry.config.ts tests/e2e/administration.spec.ts tests/e2e/tasks.spec.ts"
        " tests/e2e/workspace-navigation.spec.ts" in actual["run"]
    )
    assert actual["run"].startswith("lockf -k -t 600 /tmp/domus-ci-entry-browser.lock ")
    assert "--grep" not in actual["run"]
    assert "--pass-with-no-tests" not in actual["run"]
    commands = [step["run"] for step in steps if "run" in step]
    assert "pnpm install --frozen-lockfile" in commands
    assert "pnpm --filter @domus/frontend exec playwright install chromium" in commands
    audit = next(
        step
        for step in steps
        if step.get("name") == "Require all fifty-four actual-image household journeys"
    )
    assert all(field in audit["run"] for field in ["expected", "unexpected", "skipped", "flaky"])
    assert "expected']==54" in audit["run"]
    cleanup = next(
        step for step in steps if step.get("name") == "Require no surviving image browser fixtures"
    )
    assert "domus.browser-fixture.image=$DOMUS_IMAGE_PREFIX:current" in cleanup["run"]
    assert 'docker rm --force "$id"' in cleanup["run"]
    assert "exit 1" in cleanup["run"]
    assert steps.index(cleanup) > steps.index(audit)
    images = next(step for step in steps if step.get("name") == "Remove this job's image tags")
    assert images["if"] == "${{ always() }}"
    assert 'image="$DOMUS_IMAGE_PREFIX:$name"' in images["run"]
    assert 'docker image rm "$image"' in images["run"]


def test_both_cpu_images_require_the_immutable_schema9_application_rollback_pair() -> None:
    steps = workflow()["jobs"]["containers"]["steps"]
    build = next(
        step
        for step in steps
        if step.get("name") == "Build the immutable compatible schema-9 rollback application"
    )
    assert build["run"].split() == [
        "docker",
        "buildx",
        "build",
        "--load",
        "--platform",
        '"$DOCKER_DEFAULT_PLATFORM"',
        "--build-arg",
        "BUILD_ARCH=${{",
        "matrix.arch",
        "}}",
        "-t",
        '"$DOMUS_IMAGE_PREFIX:schema9"',
        "tests/fixtures/schema9-app",
    ]
    verify = next(
        step for step in steps if step.get("run") == "uv run pytest tests/containers --no-cov"
    )
    assert verify["env"]["DOMUS_SCHEMA9_IMAGE"] == "${{ env.DOMUS_IMAGE_PREFIX }}:schema9"
    assert steps.index(build) < steps.index(verify)
    fixture = (ROOT / "tests/fixtures/schema9-app/Dockerfile").read_text()
    assert "DOMUS_SOURCE_COMMIT=87d726fa5a6a8cbcb56e0b911d15cc5b8a96a470" in fixture
    assert (
        "DOMUS_SOURCE_SHA256=d8a9c4c1caf3acbb462ac21ec78ccbab05d756031880fd2f5013b4e528b45758"
        in fixture
    )
    assert "sha256sum --check" in fixture
    assert "assert SCHEMA_VERSION == 9" in fixture
    assert "pnpm install --frozen-lockfile" in fixture
    assert "uv sync --frozen --no-dev --package domus-server --no-editable" in fixture


def test_actual_image_browser_evidence_is_retained_per_cpu_even_after_failure() -> None:
    steps = workflow()["jobs"]["containers"]["steps"]
    artifact = next(
        (step for step in steps if step.get("name") == "Retain actual-image browser evidence"),
        None,
    )
    assert artifact is not None, "A failing actual-image browser run must retain its evidence"
    assert artifact["if"] == "${{ always() }}"
    assert artifact["with"]["name"] == "image-browser-${{ matrix.arch }}-${{ github.sha }}"
    assert artifact["with"]["path"] == "frontend/test-results/"
    assert artifact["with"]["include-hidden-files"] == "true"
    assert artifact["with"]["retention-days"] == "7"
    assert artifact["with"]["if-no-files-found"] == "warn"
    execution = next(
        step
        for step in steps
        if step.get("name")
        == "Execute household workflows in the actual isolated image from Chromium"
    )
    assert steps.index(artifact) > steps.index(execution)


def test_actual_image_fixture_retirement_is_checked_even_after_browser_failure() -> None:
    cleanup = next(
        step
        for step in workflow()["jobs"]["containers"]["steps"]
        if step.get("name") == "Require no surviving image browser fixtures"
    )
    assert cleanup.get("if") == "${{ always() }}"
    assert "continue-on-error" not in cleanup


def test_native_calendar_has_required_coverage_and_an_independent_adapter_boundary() -> None:
    jobs = workflow()["jobs"]
    container = jobs["containers"]
    assert "containers" in jobs["aggregate"]["needs"]
    assert "continue-on-error" not in container
    verification = next(
        step
        for step in container["steps"]
        if step.get("run") == "uv run pytest tests/containers --no-cov"
    )
    assert "if" not in verification and "continue-on-error" not in verification
    assert verification["env"]["DOMUS_CALENDAR_COVERAGE_OUT"] == "coverage-ha-calendar.json"
    sources = sorted((ROOT / "custom_components/domus_calendar").rglob("*.py"))
    assert sources
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text())):
            names = (
                [name.name for name in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom) and node.level == 0
                else []
            )
            assert not {name.split(".")[0] for name in names} & {
                "domus",
                "fastapi",
                "sqlite3",
                "sqlalchemy",
                "starlette",
                "uvicorn",
            }, source


def test_recurrence_qualification_preserves_every_case_and_alias() -> None:
    audit = (ROOT / "docs/evidence/recurrence-calendar-qualification.md").read_text()
    rows = re.findall(r"(?m)^\| ([a-z-]+-C\d{2}) \| (Witness|Partial|Gap) \| (.+) \|$", audit)
    observed = {case for case, _, _ in rows}
    assert len(rows) == len(observed) == 121
    owners = {
        "recurrence-calendar": ("recurrence-calendar", 1, 37),
        "recurrence-execution-foundation": ("recurrence-execution", 1, 52),
        "recurrence-storage-continuation": ("recurrence-storage", 1, 4),
        "recurrence-lifecycle-calendar": ("recurrence-lifecycle-calendar", 19, 39),
        "home-assistant-calendar": ("domus-native-calendar", 1, 7),
    }
    expected = set()
    aliases = {}
    for document, (prefix, first, last) in owners.items():
        text = (ROOT / "specs" / f"{document}.md").read_text()
        case_ids = {f"{prefix}-C{index:02}" for index in range(first, last + 1)}
        assert all(f"| {case_id} |" in text for case_id in case_ids)
        expected.update(case_ids)
        for alias, targets in re.findall(
            rf"(?m)^\| ({document}-C\d{{2}}) \| ([^|]+?) \| [^|]*alias[^|]*\|", text
        ):
            aliases[alias] = targets
    assert observed == expected
    retained = dict(re.findall(r"(?m)^\| ([a-z-]+-C\d{2}) \| ([^|]+?) \|$", audit))
    assert retained == aliases and len(aliases) == 22
    for case, status, evidence in rows:
        references = re.findall(r"`((?:frontend/)?tests/[^ `]+)`", evidence)
        assert references, case
        for reference in references:
            path, _, name = reference.partition("::")
            assert (ROOT / path).is_file(), (case, path)
            if name:
                assert re.search(rf"(?m)^def {re.escape(name)}\(", (ROOT / path).read_text()), (
                    case,
                    name,
                )
        if status != "Witness":
            assert evidence.rsplit("`", 1)[1].strip(), case
