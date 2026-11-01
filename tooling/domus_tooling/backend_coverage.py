"""Compare measured execution with the complete source and an independent static coverage model."""

import hashlib
import json
import math
import os
import re
import stat
import tokenize
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import NoReturn, cast

from coverage.exceptions import CoverageException

from coverage import Coverage, __version__

MAX_REPORT_BYTES = 64 * 1024 * 1024
_MAX_PROBLEMS = 20


class _AuditFailure(Exception):
    pass


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _AuditFailure("Invalid backend coverage report structure.")
    return cast(dict[str, object], value)


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _AuditFailure("Duplicate JSON keys are not allowed in coverage reports.")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise _AuditFailure("Nonfinite JSON numbers are not allowed in coverage reports.")


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        _constant(value)
    return number


def _report(path: Path) -> dict[str, object]:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise _AuditFailure("Backend coverage report must be a regular file.")
    with path.open("rb") as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise _AuditFailure("Backend coverage report is too large.")
    return _object(
        json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=_constant,
            parse_float=_float,
        )
    )


def _abort(error: OSError) -> NoReturn:
    raise error


def _inventory(root: Path) -> dict[str, Path]:
    for relative in ("backend", "backend/src", "backend/src/domus"):
        path = root / relative
        if path.is_symlink() or not path.is_dir():
            raise _AuditFailure("Backend source must be a real backend/src/domus directory.")
    files = {}
    for current, directories, names in os.walk(root / "backend/src/domus", onerror=_abort):
        for name in directories + names:
            path = Path(current) / name
            if path.is_symlink():
                raise _AuditFailure("Backend source must not contain symlinks.")
            if name.endswith(".py") and name in names:
                if not path.is_file():
                    raise _AuditFailure("Backend modules must be regular files.")
                files[path.relative_to(root).as_posix()] = path
    if not files:
        raise _AuditFailure("Backend source inventory is empty.")
    return dict(sorted(files.items()))


def _expected(root: Path, files: dict[str, Path]) -> dict[str, object]:
    # This independent engine never starts tracing or imports application modules.
    engine = Coverage(data_file=None, config_file=False, branch=True)
    pragmas = [
        pattern
        for kind in ("exclude", "partial")
        for pattern in engine.get_exclude_list(kind)
        if "pragma" in pattern.casefold()
    ]
    for name, path in files.items():
        with tokenize.open(path) as stream:
            source = stream.read()
        if any(re.search(pattern, source) for pattern in pragmas):
            raise _AuditFailure(f"{name!r}: explicit coverage pragmas are forbidden.")
    data = engine.get_data()
    try:
        data.add_arcs({})
        data.touch_files([str(path) for path in files.values()])
        output = StringIO()
        with redirect_stdout(output):
            engine.json_report(morfs=[str(path) for path in files.values()], outfile="-")
        result = _object(json.loads(output.getvalue()))
        result["files"] = {
            Path(name).resolve().relative_to(root).as_posix(): value
            for name, value in _object(result["files"]).items()
        }
        return result
    finally:
        data.close(force=True)


def _same(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same(a, b) for a, b in zip(actual, expected, strict=True)
        )
    return actual == expected


def _full_summary(actual: object, expected: dict[str, object]) -> bool:
    if not isinstance(actual, dict):
        return False
    wanted = {
        "num_statements": expected["num_statements"],
        "covered_lines": expected["num_statements"],
        "missing_lines": 0,
        "excluded_lines": expected["excluded_lines"],
        "num_branches": expected["num_branches"],
        "covered_branches": expected["num_branches"],
        "missing_branches": 0,
        "num_partial_branches": 0,
    }
    if any(
        type(actual.get(key)) is not int or actual[key] != value for key, value in wanted.items()
    ):
        return False
    for key in ("percent_covered", "percent_statements_covered", "percent_branches_covered"):
        if type(actual.get(key)) not in (int, float) or actual[key] != 100:
            return False
        display = actual.get(key + "_display")
        if not isinstance(display, str) or re.fullmatch(r"100(?:\.0+)?", display) is None:
            return False
    return True


def validate_backend_coverage(root: Path, report: Path) -> list[str]:
    """Execution remains the preceding pytest gate; this verifies its inventory/denominator/data."""
    try:
        root = root.resolve(strict=True)
        files = _inventory(root)
        hashes = {name: hashlib.sha256(path.read_bytes()).digest() for name, path in files.items()}
        measured = _report(report if report.is_absolute() else root / report)
        meta = _object(measured.get("meta"))
        if (
            type(meta.get("format")) is not int
            or meta["format"] != 3
            or meta.get("version") != __version__
            or meta.get("branch_coverage") is not True
        ):
            raise _AuditFailure(
                "Coverage must use branch-enabled format 3 and the locked Coverage.py version."
            )
        rows = _object(measured.get("files"))
        problems = [
            f"Missing backend coverage file: {name!r}."
            for name in sorted(files.keys() - rows.keys())
        ]
        problems += [
            f"Unexpected backend coverage file: {name!r}."
            for name in sorted(rows.keys() - files.keys())
        ]
        if not problems:
            expected = _expected(root, files)
            totals = _object(expected["totals"])
            if totals["num_statements"] == 0:
                raise _AuditFailure("Backend source has no executable statements.")
            for name, static in _object(expected["files"]).items():
                row, static = _object(rows[name]), _object(static)
                if not _full_summary(row.get("summary"), _object(static["summary"])):
                    problems.append(
                        f"{name!r}: require complete source counts and exact 100% metrics."
                    )
                if any(
                    not _same(row.get(key), value)
                    for key, value in (
                        ("executed_lines", static["missing_lines"]),
                        ("excluded_lines", static["excluded_lines"]),
                        ("executed_branches", static["missing_branches"]),
                        ("missing_lines", []),
                        ("missing_branches", []),
                    )
                ):
                    problems.append(
                        f"{name!r}: execution sets do not cover the complete current source."
                    )
            if not _full_summary(measured.get("totals"), totals):
                problems.append(
                    "Backend coverage totals must match complete source and exact 100% metrics."
                )
        if _inventory(root) != files or any(
            hashlib.sha256(path.read_bytes()).digest() != hashes[name]
            for name, path in files.items()
        ):
            raise _AuditFailure("Backend source changed during coverage verification.")
        return problems[:_MAX_PROBLEMS] + (
            [f"Additional coverage failures: {len(problems) - _MAX_PROBLEMS}."]
            if len(problems) > _MAX_PROBLEMS
            else []
        )
    except _AuditFailure as error:
        return [str(error)]
    except OSError, ValueError, RecursionError, CoverageException:
        return ["Unable to verify coverage report and complete current backend source."]
