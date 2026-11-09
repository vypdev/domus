"""A default policy and an explicit skip decision have distinct revisions."""

from dataclasses import replace

import pytest

from domus.domain.errors import Conflict, InvalidInput
from domus.domain.task_values import MissedOccurrencePolicy, MissedOccurrenceSettings


def test_default_and_reviewed_policy_revisions_are_distinct():
    original = MissedOccurrenceSettings("home", "task")
    assert original.policy is MissedOccurrencePolicy.KEEP_VISIBLE and original.revision == 0
    with pytest.raises(Conflict, match="task_unchanged"):
        original.revise(MissedOccurrencePolicy.KEEP_VISIBLE)
    selected = original.revise(MissedOccurrencePolicy.SKIP_AFTER_REVIEW)
    assert selected.revision == 1
    restored = selected.revise(MissedOccurrencePolicy.KEEP_VISIBLE)
    assert restored == replace(original, revision=2)


@pytest.mark.parametrize(
    "fields",
    [
        {"policy": "skip_after_review"},
        {"policy": MissedOccurrencePolicy.SKIP_AFTER_REVIEW},
        {"revision": False},
        {"revision": -1},
        {"revision": 2**63},
    ],
)
def test_policy_settings_reject_invalid_or_unreviewed_values(fields):
    with pytest.raises(InvalidInput, match="invalid_missed_occurrence_settings"):
        MissedOccurrenceSettings("home", "task", **fields)
