"""Pure policy for a fail-closed CI aggregate."""

from collections.abc import Mapping

REQUIRED_JOBS = ("python", "backend", "node", "architecture", "documentation")


def evaluate_jobs(results: Mapping[str, object]) -> tuple[str, ...]:
    """Accept exactly the required jobs, each with a successful conclusion."""
    problems = []
    for name in sorted(results.keys() - set(REQUIRED_JOBS)):
        problems.append(f"Unexpected required-job input: {name}")
    for name in REQUIRED_JOBS:
        result = results.get(name)
        if not isinstance(result, dict):
            problems.append(f"{name}: missing or invalid job result")
        elif result.get("result") != "success":
            problems.append(f"{name}: expected success, received {result.get('result', 'missing')}")
    return tuple(problems)
