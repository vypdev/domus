"""Both business runtimes require current session context for recurrence review."""

from datetime import date
from types import SimpleNamespace

from test_native_http import INSTANCE
from test_task_runtime import api as api

from domus.application.relative_recurrence_commands import (
    CreateRelativeTask,
    RelativeRecurrenceCommands,
)
from domus.application.task_requests import CreateTask
from domus.domain.identity import HumanIdentity
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import RelativeInterval, TimePolicy
from domus.domain.task_values import TaskContent
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime

BASE = "/api/v1/tasks/recurrence/reviews"
USER = "a" * 32
CONTEXT = {"X-Domus-Context": f"v1:{INSTANCE}:edge:{USER}"}


def seed_manual(api):
    times = PinnedRecurrenceTime()
    admin = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    receipt = RelativeRecurrenceCommands(
        api.store, admin, SystemClock(), SecureIdentifiers(), times
    ).create(
        "relative",
        CreateRelativeTask(
            CreateTask(TaskContent("Clean the filter")),
            NominalDate(date(2026, 12, 31)),
            RelativeInterval(30),
            TimePolicy("UTC", times.data_identity),
        ),
    )
    schedule = receipt.result.decode()
    work = api.client.post(
        f"/api/v1/tasks/definitions/{schedule['definition_id']}/occurrences",
        json={"expected_revision": 0},
        headers=api.headers("manual"),
    )
    assert work.status_code == 200, work.text
    return {
        "schedule_id": schedule["schedule_id"],
        "schedule_revision": 1,
        "occurrence_id": work.json()["result"]["occurrence_id"],
        "occurrence_revision": 1,
    }


def test_protected_review_preview_apply_and_original_receipt(api):
    api.user(USER, True)
    choice = seed_manual(api)
    preview_url = f"{BASE}/adoption/preview"
    apply_url = f"{BASE}/adoption/apply"
    headers = api.headers("preview") | CONTEXT
    assert (
        api.client.post(preview_url, json=choice, headers=api.headers("missing")).status_code == 422
    )
    wrong_context = headers | {"X-Domus-Context": "v1:forged"}
    assert api.client.post(preview_url, json=choice, headers=wrong_context).status_code == 403
    assert (
        api.client.post(
            preview_url, json=choice, headers=headers | {"Origin": "https://forged.example"}
        ).status_code
        == 403
    )
    assert (
        api.client.post(
            preview_url, json=choice, headers=headers | {"X-CSRF-Token": "forged"}
        ).status_code
        == 403
    )
    for invalid in (
        {**choice, "actor_id": "system:recurrence"},
        {**choice, "occurrence_revision": True},
        {**choice, "schedule_revision": 2**63},
    ):
        assert api.client.post(preview_url, json=invalid, headers=headers).status_code == 422
    assert (
        api.client.post(f"{preview_url}?limit=1", json=choice, headers=headers).status_code == 422
    )

    preview = api.client.post(preview_url, json=choice, headers=headers)
    assert preview.status_code == 200, preview.text
    plan = preview.json()["result"]
    assert plan["plan"]["retained_occurrence_id"] == choice["occurrence_id"]
    reviewed = {**choice, "preview_key": "preview", "plan_fingerprint": plan["plan_fingerprint"]}
    assert (
        api.client.post(
            apply_url,
            json=reviewed | {"plan_fingerprint": "wrong"},
            headers=api.headers("apply") | CONTEXT,
        ).status_code
        == 422
    )
    stale = api.client.post(
        apply_url,
        json=reviewed | {"plan_fingerprint": "0" * 64},
        headers=api.headers("apply") | CONTEXT,
    )
    assert stale.status_code == 409 and stale.json()["code"] == "recurrence_review_stale"
    committed = api.client.post(apply_url, json=reviewed, headers=api.headers("apply") | CONTEXT)
    assert committed.status_code == 200, committed.text
    assert committed.json()["result"]["occurrence_id"] == choice["occurrence_id"]

    original = f"{BASE}/requests/recurrence.review.apply/apply"
    assert api.client.get(original).status_code == 422
    assert api.client.get(original, headers=CONTEXT).json() == committed.json()
    assert (
        api.client.get(f"{BASE}/requests/recurrence.review.preview/preview", headers=CONTEXT).json()
        == preview.json()
    )
    assert api.client.get(f"{BASE}/requests/task.create/apply", headers=CONTEXT).status_code == 422
    assert (
        api.client.get(
            f"{BASE}/requests/recurrence.review.apply/unknown", headers=CONTEXT
        ).status_code
        == 404
    )
