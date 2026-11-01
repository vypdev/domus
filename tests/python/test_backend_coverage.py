"""Real measured miniature backends prove complete-source auditing and fail-closed negatives."""

import builtins
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from domus_tooling import backend_coverage as audit
from domus_tooling.backend_coverage import validate_backend_coverage
from domus_tooling.cli import main

PROGRAM = """from pathlib import Path
Path(__file__).with_suffix(".ran").write_text("executed", encoding="utf-8")

def choose(enabled):
    if enabled:
        return "yes"
    return "no"

choose(True)
choose(False)
"""
WORK = "backend/src/domus/work.py"


def measured(tmp_path, monkeypatch, *, program=PROGRAM, branch=True, exclude=""):
    source = tmp_path / "backend/src/domus"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "work.py").write_text(program, encoding="utf-8")
    report = tmp_path / "coverage-backend.json"
    script = """import runpy, sys
from coverage import Coverage
source, report, branch, exclude = sys.argv[1:]
collector = Coverage(data_file=None, config_file=False, branch=(branch == "1"), source=[source])
if exclude:
    collector.exclude(exclude)
collector.start()
try:
    runpy.run_path(source + "/work.py")
finally:
    collector.stop()
try:
    collector.json_report(outfile=report)
finally:
    collector.get_data().close(force=True)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(source), str(report), "1" if branch else "0", exclude],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return tmp_path, report, json.loads(report.read_text())


def write(report, value):
    report.write_text(json.dumps(value), encoding="utf-8")


def test_real_complete_statement_and_branch_measurement_passes_without_reexecuting_source(
    tmp_path, monkeypatch
):
    root, report, document = measured(tmp_path, monkeypatch)
    marker = root / "backend/src/domus/work.ran"
    assert marker.read_text() == "executed"
    marker.unlink()
    assert document["files"][WORK]["summary"]["num_branches"] == 2
    assert validate_backend_coverage(root, report) == []
    assert not marker.exists()
    assert document["files"]["backend/src/domus/__init__.py"]["summary"]["num_statements"] == 0


def test_cli_accepts_the_actual_complete_report_and_preserves_original_measurement(
    tmp_path, monkeypatch, capsys
):
    root, report, _ = measured(tmp_path, monkeypatch)
    original = report.read_bytes()
    assert main(["backend-coverage", "--root", str(root), "--report", str(report)]) == 0
    assert capsys.readouterr().out == "backend-coverage: all required checks passed\n"
    assert report.read_bytes() == original


def test_unmeasured_new_module_cannot_disappear_from_the_authored_inventory(tmp_path, monkeypatch):
    root, report, _ = measured(tmp_path, monkeypatch)
    (root / "backend/src/domus/unmeasured.py").write_text("value = 1\n")
    problems = validate_backend_coverage(root, report)
    assert problems and "unmeasured.py" in "\n".join(problems)


def test_a_forged_zero_statement_module_cannot_pass_even_with_consistent_totals(
    tmp_path, monkeypatch
):
    root, report, document = measured(tmp_path, monkeypatch)
    empty = deepcopy(document["files"]["backend/src/domus/__init__.py"])
    document["files"][WORK] = empty
    document["totals"] = deepcopy(empty["summary"])
    write(report, document)
    assert validate_backend_coverage(root, report)


def test_real_uncovered_branch_is_rejected_even_if_percentage_is_overwritten(tmp_path, monkeypatch):
    root, report, document = measured(
        tmp_path, monkeypatch, program=PROGRAM.replace("choose(False)", "pass")
    )
    assert document["files"][WORK]["missing_branches"]
    document["files"][WORK]["summary"]["percent_covered"] = 100
    document["totals"]["percent_covered"] = 100
    write(report, document)
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize("shape", [None, [], {}, {"meta": []}])
def test_report_requires_structured_metadata_files_and_totals(tmp_path, monkeypatch, shape):
    root, report, _ = measured(tmp_path, monkeypatch)
    write(report, shape)
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        '{"meta":{},"meta":{}}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":1e999}',
        '"\\ud800"',
    ],
)
def test_invalid_duplicate_and_nonfinite_json_never_passes(tmp_path, monkeypatch, raw):
    root, report, _ = measured(tmp_path, monkeypatch)
    report.write_text(raw)
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize(
    "change",
    [
        {"format": 2},
        {"format": 3.0},
        {"version": "0.0"},
        {"branch_coverage": False},
        {"branch_coverage": 1},
    ],
)
def test_measured_protocol_must_match_branch_enabled_locked_runtime(tmp_path, monkeypatch, change):
    root, report, document = measured(tmp_path, monkeypatch)
    document["meta"].update(change)
    write(report, document)
    assert validate_backend_coverage(root, report)


def test_actual_line_only_measurement_cannot_replace_branch_evidence(tmp_path, monkeypatch):
    root, report, document = measured(tmp_path, monkeypatch, branch=False)
    assert not document["meta"]["branch_coverage"]
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("covered_lines", 0),
        ("missing_lines", False),
        ("num_partial_branches", False),
        ("num_branches", 0),
        ("percent_covered", 99.99999),
        ("percent_statements_covered", "100"),
        ("percent_branches_covered_display", "99.99"),
        ("percent_covered_display", None),
    ],
)
def test_each_file_needs_exact_counts_and_unrounded_full_coverage(
    tmp_path, monkeypatch, field, value
):
    root, report, document = measured(tmp_path, monkeypatch)
    document["files"][WORK]["summary"][field] = value
    write(report, document)
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("executed_lines", None),
        ("executed_lines", []),
        ("excluded_lines", [1]),
        ("executed_branches", [[1, 2], [1, 2]]),
        ("missing_lines", [1]),
        ("missing_branches", [[1, 2]]),
    ],
)
def test_execution_vectors_must_equal_independent_complete_source_model(
    tmp_path, monkeypatch, field, value
):
    root, report, document = measured(tmp_path, monkeypatch)
    document["files"][WORK][field] = value
    write(report, document)
    assert validate_backend_coverage(root, report)


def test_boolean_alias_for_line_one_is_not_an_executed_line(tmp_path, monkeypatch):
    root, report, document = measured(tmp_path, monkeypatch)
    assert document["files"][WORK]["executed_lines"][0] == 1
    document["files"][WORK]["executed_lines"][0] = True
    write(report, document)
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize("part", ["files", "file", "summary", "totals"])
def test_malformed_file_or_summary_sections_cannot_be_success(tmp_path, monkeypatch, part):
    root, report, document = measured(tmp_path, monkeypatch)
    if part == "files":
        document["files"] = []
    elif part == "file":
        document["files"][WORK] = None
    elif part == "summary":
        document["files"][WORK]["summary"] = None
    else:
        document["totals"] = None
    write(report, document)
    assert validate_backend_coverage(root, report)


def test_totals_cannot_hide_a_file_failure_or_contradict_complete_files(tmp_path, monkeypatch):
    root, report, document = measured(tmp_path, monkeypatch)
    document["totals"]["num_statements"] += 1
    write(report, document)
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize(
    "name",
    [
        "outside.py",
        "/private/other.py",
        "backend/src/domus/../domus/work.py",
        "backend\\src\\domus\\work.py",
    ],
)
def test_extra_noncanonical_or_foreign_names_are_rejected_without_loading_them(
    tmp_path, monkeypatch, name
):
    root, report, document = measured(tmp_path, monkeypatch)
    document["files"][name] = deepcopy(document["files"][WORK])
    write(report, document)
    assert any("Unexpected" in item for item in validate_backend_coverage(root, report))


@pytest.mark.parametrize("pragma", ["# pragma: no cover", "# PRAGMA: NO BRANCH"])
def test_source_pragmas_cannot_reduce_the_independent_denominator(tmp_path, monkeypatch, pragma):
    root, report, _ = measured(
        tmp_path, monkeypatch, program=PROGRAM.replace("if enabled:", "if enabled: " + pragma)
    )
    assert any("pragmas" in item for item in validate_backend_coverage(root, report))


@pytest.mark.parametrize("part", ["backend", "directory", "file"])
def test_source_symlinks_cannot_hide_or_alias_modules(tmp_path, monkeypatch, part):
    root, report, _ = measured(tmp_path, monkeypatch)
    if part == "backend":
        original = root / "backend"
        original.rename(root / "original")
        original.symlink_to(root / "original", target_is_directory=True)
    elif part == "directory":
        (root / "backend/src/domus/linked").symlink_to(root / "original", target_is_directory=True)
    else:
        (root / "backend/src/domus/link.py").symlink_to(root / "missing.py")
    assert validate_backend_coverage(root, report)


def test_nonregular_module_is_rejected_without_reading_the_fifo(tmp_path, monkeypatch):
    root, report, _ = measured(tmp_path, monkeypatch)
    os.mkfifo(root / "backend/src/domus/fifo.py")
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize("kind", ["missing_root", "empty_inventory", "empty_backend"])
def test_absent_or_zero_executable_backend_cannot_claim_full_coverage(tmp_path, monkeypatch, kind):
    root, report, document = measured(tmp_path, monkeypatch)
    if kind == "missing_root":
        root = root / "missing"
    else:
        (root / WORK).unlink()
        if kind == "empty_inventory":
            (root / "backend/src/domus/__init__.py").unlink()
        else:
            del document["files"][WORK]
            document["totals"] = deepcopy(
                document["files"]["backend/src/domus/__init__.py"]["summary"]
            )
            write(report, document)
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "too_large", "invalid_utf8"])
def test_report_io_or_resource_failures_are_fail_closed(tmp_path, monkeypatch, kind):
    root, report, _ = measured(tmp_path, monkeypatch)
    if kind == "missing":
        report.unlink()
    elif kind == "directory":
        report.unlink()
        report.mkdir()
    elif kind == "symlink":
        report.rename(root / "original.json")
        report.symlink_to(root / "original.json")
    elif kind == "too_large":
        monkeypatch.setattr(audit, "MAX_REPORT_BYTES", 10)
    else:
        report.write_bytes(b"\xff")
    assert validate_backend_coverage(root, report)


def test_source_walk_error_cannot_silently_omit_a_directory(tmp_path, monkeypatch):
    root, report, _ = measured(tmp_path, monkeypatch)

    def unreadable(*args, **kwargs):
        kwargs["onerror"](PermissionError("fixture directory inaccessible"))

    monkeypatch.setattr(audit.os, "walk", unreadable)
    assert validate_backend_coverage(root, report)


def test_invalid_python_analysis_is_a_failed_audit_not_a_skipped_module(tmp_path, monkeypatch):
    root, report, _ = measured(tmp_path, monkeypatch)
    (root / WORK).write_text("def invalid(\n")
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize("change", ["content", "inventory"])
def test_source_must_stay_unchanged_through_independent_analysis(tmp_path, monkeypatch, change):
    root, report, _ = measured(tmp_path, monkeypatch)
    expected = audit._expected

    def changed(base, files):
        result = expected(base, files)
        path = root / (WORK if change == "content" else "backend/src/domus/late.py")
        path.write_text(PROGRAM + "\nextra = 1\n")
        return result

    monkeypatch.setattr(audit, "_expected", changed)
    assert any("changed" in item for item in validate_backend_coverage(root, report))


def test_many_inventory_failures_have_bounded_diagnostics(tmp_path, monkeypatch):
    root, report, _ = measured(tmp_path, monkeypatch)
    for number in range(25):
        (root / f"backend/src/domus/new_{number}.py").write_text("value = 1\n")
    problems = validate_backend_coverage(root, report)
    assert len(problems) == 21 and problems[-1] == "Additional coverage failures: 5."


@pytest.mark.parametrize("explicit", [False, True])
def test_cli_default_and_relative_report_paths_resolve_within_selected_root(
    tmp_path, monkeypatch, capsys, explicit
):
    root, _, _ = measured(tmp_path, monkeypatch)
    args = ["backend-coverage", "--root", str(root)]
    if explicit:
        args.extend(["--report", "coverage-backend.json"])
    assert main(args) == 0
    assert capsys.readouterr().out == "backend-coverage: all required checks passed\n"


def test_cli_failure_keeps_actionable_file_diagnostic(tmp_path, monkeypatch, capsys):
    root, report, document = measured(tmp_path, monkeypatch)
    del document["files"][WORK]
    write(report, document)
    assert main(["backend-coverage", "--root", str(root)]) == 1
    assert WORK in capsys.readouterr().out


@pytest.mark.parametrize("command,status", [("docs", 0), ("backend-coverage", 1)])
def test_nondev_documentation_does_not_import_optional_coverage_dependency(
    tmp_path, command, status
):
    (tmp_path / "README.md").write_text("# Documentation\n")
    script = (
        "import sys; sys.modules['coverage']=None; "
        "from domus_tooling.cli import main; raise SystemExit(main(sys.argv[1:]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, command, "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == status, result.stderr
    if status:
        assert "uv sync --frozen" in result.stdout
    else:
        assert "all required checks passed" in result.stdout


def test_missing_optional_verifier_dependency_has_a_bounded_cli_action(monkeypatch, capsys):
    real_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "domus_tooling.backend_coverage":
            raise ImportError("fixture development dependency missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    assert main(["backend-coverage"]) == 1
    assert capsys.readouterr().out == (
        "backend-coverage requires locked development dependencies: uv sync --frozen\n"
    )


def test_real_report_custom_exclusions_cannot_narrow_the_default_source_model(
    tmp_path, monkeypatch
):
    root, report, document = measured(tmp_path, monkeypatch, exclude="if enabled:")
    assert document["files"][WORK]["excluded_lines"]
    assert document["files"][WORK]["summary"]["percent_covered"] == 100
    assert validate_backend_coverage(root, report)


@pytest.mark.parametrize("target", ["source", "report"])
def test_unreadable_source_or_report_cannot_be_treated_as_empty(tmp_path, monkeypatch, target):
    root, report, _ = measured(tmp_path, monkeypatch)
    read = Path.open
    denied = root / WORK if target == "source" else report

    def inaccessible(self, *args, **kwargs):
        if self == denied:
            raise PermissionError("fixture read denied")
        return read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", inaccessible)
    assert validate_backend_coverage(root, report)


def test_report_size_limit_is_inclusive_and_matches_the_declared_policy(tmp_path, monkeypatch):
    root, report, _ = measured(tmp_path, monkeypatch)
    assert audit.MAX_REPORT_BYTES == 64 * 1024 * 1024
    monkeypatch.setattr(audit, "MAX_REPORT_BYTES", report.stat().st_size)
    assert validate_backend_coverage(root, report) == []
