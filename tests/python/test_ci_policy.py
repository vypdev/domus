"""An aggregate cannot turn absent, skipped or failed checks into success."""

import pytest

from domus_tooling.ci_policy import REQUIRED_JOBS, evaluate_jobs


def successful_jobs() -> dict[str, object]:
    return {name: {"result": "success"} for name in REQUIRED_JOBS}


def test_all_required_jobs_must_succeed() -> None:
    assert evaluate_jobs(successful_jobs()) == ()


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "pending", None])
def test_non_successful_job_blocks_aggregate(conclusion: object) -> None:
    jobs = successful_jobs()
    jobs["python"] = {"result": conclusion}
    assert evaluate_jobs(jobs) == (f"python: expected success, received {conclusion}",)


@pytest.mark.parametrize("invalid", [None, [], "success", 1])
def test_malformed_result_blocks_aggregate(invalid: object) -> None:
    jobs = successful_jobs()
    jobs["node"] = invalid
    assert evaluate_jobs(jobs) == ("node: missing or invalid job result",)


def test_absent_job_blocks_aggregate() -> None:
    jobs = successful_jobs()
    del jobs["architecture"]
    assert evaluate_jobs(jobs) == ("architecture: missing or invalid job result",)


def test_result_without_conclusion_blocks_aggregate() -> None:
    jobs = successful_jobs()
    jobs["documentation"] = {"outputs": {}}
    assert evaluate_jobs(jobs) == ("documentation: expected success, received missing",)


def test_unknown_input_cannot_replace_a_required_job() -> None:
    jobs = successful_jobs()
    jobs["unexpected"] = {"result": "success"}
    assert evaluate_jobs(jobs) == ("Unexpected required-job input: unexpected",)


def test_reports_every_missing_job_in_stable_order() -> None:
    assert evaluate_jobs({}) == tuple(
        f"{name}: missing or invalid job result" for name in REQUIRED_JOBS
    )
