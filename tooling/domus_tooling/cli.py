"""Command adapter for local documentation checks and the GitHub CI aggregate."""

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from domus_tooling.ci_policy import evaluate_jobs
from domus_tooling.docs import validate_links


def main(argv: Sequence[str] | None = None) -> int:
    """Return a process status without executing publication or remote mutations."""
    parser = argparse.ArgumentParser(prog="domus-check")
    parser.add_argument("command", choices=("aggregate", "docs"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    if args.command == "docs":
        problems = validate_links(args.root)
    else:
        try:
            results = json.loads(os.environ.get("DOMUS_CI_RESULTS", ""))
        except json.JSONDecodeError:
            print("Invalid or missing DOMUS_CI_RESULTS JSON")
            return 1
        if not isinstance(results, dict):
            print("DOMUS_CI_RESULTS must be a job-result object")
            return 1
        problems = evaluate_jobs(results)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"{args.command}: all required checks passed")
    return 0
