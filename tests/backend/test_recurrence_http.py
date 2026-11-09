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


def test_protected_relative_state_review_exposes_manual_backlog(api):
    api.user(USER, True)
    manual = seed_manual(api)
    choice = {"schedule_id": manual["schedule_id"], "schedule_revision": 1, "target": "paused"}
    response = api.client.post(
        f"{BASE}/state/preview",
        json=choice | {"target": "retired"},
        headers=api.headers("bad-state") | CONTEXT,
    )
    assert response.status_code == 422
    for index, target in enumerate(("paused", "active"), 1):
        choice |= {"schedule_revision": index, "target": target}
        preview_key = f"preview-state-{index}"
        preview = api.client.post(
            f"{BASE}/state/preview", json=choice, headers=api.headers(preview_key) | CONTEXT
        )
        assert preview.status_code == 200, preview.text
        result = preview.json()["result"]
        expected = "paused" if index == 1 else "initial_review_required"
        assert result["plan"]["backlog"] == {"status": expected, "next_slot": None}
        applied = api.client.post(
            f"{BASE}/state/apply",
            json=choice
            | {"preview_key": preview_key, "plan_fingerprint": result["plan_fingerprint"]},
            headers=api.headers(f"apply-state-{index}") | CONTEXT,
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["result"]["state"] == target


def test_protected_overdue_fixed_skip_recovers_original_exception(api):
    from domus.application.fixed_materialization import FixedMaintenance, MaintenanceScope
    from domus.application.fixed_recurrence import FixedRecurrencePlanner
    from domus.application.recurrence_commands import CreateFixedTask, RecurrenceCommands
    from domus.domain.nominal_recurrence import CalendarNominalExpansion
    from domus.domain.recurrence_rules import FixedPattern, Frequency

    api.user(USER, True)
    times, clock, ids = PinnedRecurrenceTime(), SystemClock(), SecureIdentifiers()
    planner = FixedRecurrencePlanner(CalendarNominalExpansion(), times)
    admin = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    schedule = RecurrenceCommands(api.store, admin, clock, ids, planner).create_fixed(
        "fixed",
        CreateFixedTask(
            CreateTask(TaskContent("Overdue maintenance")),
            FixedPattern(NominalDate(date(2001, 1, 1)), Frequency.DAILY, count=1),
            TimePolicy("UTC", times.data_identity),
        ),
    )
    schedule_id = schedule.result.decode()["schedule_id"]
    step = FixedMaintenance(
        api.store, MaintenanceScope(api.store.installation, "home"), planner, clock, ids
    ).step(schedule_id, NominalDate(date(2001, 1, 2)))
    for index, target in enumerate(("paused", "active"), 1):
        state = {"schedule_id": schedule_id, "schedule_revision": index, "target": target}
        key = f"fixed-state-preview-{index}"
        preview = api.client.post(
            f"{BASE}/fixed-state/preview", json=state, headers=api.headers(key) | CONTEXT
        )
        assert preview.status_code == 200, preview.text
        applied = api.client.post(
            f"{BASE}/fixed-state/apply",
            json=state
            | {
                "preview_key": key,
                "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
            },
            headers=api.headers(f"fixed-state-apply-{index}") | CONTEXT,
        )
        assert applied.status_code == 200, applied.text
    choice = {
        "schedule_id": schedule_id,
        "schedule_revision": 3,
        "slot_key": step.receipt.command.key,
        "occurrence_id": step.occurrence_id,
        "occurrence_revision": 1,
        "reason": "<em>away</em>",
    }
    target = f"{BASE}/targets/{step.occurrence_id}"
    assert "fixed-skip" not in api.client.get(target, headers=CONTEXT).json()["actions"]
    default = api.client.post(
        f"{BASE}/fixed-skip/preview", json=choice, headers=api.headers("default-skip") | CONTEXT
    )
    assert (
        default.status_code == 409 and default.json()["code"] == "recurrence_skip_policy_required"
    )
    policy = {
        "schedule_id": schedule_id,
        "schedule_revision": 3,
        "policy_revision": 0,
        "missed_occurrence_policy": "skip_after_review",
    }
    plan = api.client.post(
        f"{BASE}/fixed-missed-policy/preview",
        json=policy,
        headers=api.headers("policy-preview") | CONTEXT,
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["result"]["plan"]["source"]["previous_policy"] == "keep_visible"
    applied = api.client.post(
        f"{BASE}/fixed-missed-policy/apply",
        json=policy
        | {
            "preview_key": "policy-preview",
            "plan_fingerprint": plan.json()["result"]["plan_fingerprint"],
        },
        headers=api.headers("policy-apply") | CONTEXT,
    )
    assert applied.status_code == 200, applied.text
    current = api.client.get(target, headers=CONTEXT).json()
    assert current["schedule"]["missed_policy"] == {"policy": "skip_after_review", "revision": 1}
    assert "fixed-skip" in current["actions"]
    preview = api.client.post(
        f"{BASE}/fixed-skip/preview",
        json=choice,
        headers=api.headers("preview-skip") | CONTEXT,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["result"]["plan"]["exception"] == "overdue_skip"
    result = api.client.post(
        f"{BASE}/fixed-skip/apply",
        json=choice
        | {
            "preview_key": "preview-skip",
            "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
        },
        headers=api.headers("apply-skip") | CONTEXT,
    )
    assert result.status_code == 200, result.text
    work = result.json()["result"]["work"]
    assert work["state"] == "skipped" and work["state_reason"] == "<em>away</em>"
    original = api.client.get(
        f"{BASE}/requests/recurrence.review.apply/apply-skip", headers=CONTEXT
    )
    assert original.json() == result.json()

    edit = {
        "schedule_id": schedule_id,
        "schedule_revision": 3,
        "start": {"kind": "date", "local": "2090-01-01"},
        "rrule": "FREQ=WEEKLY;COUNT=3",
    }
    preview = api.client.post(
        f"{BASE}/fixed-pattern/preview", json=edit, headers=api.headers("edit-preview") | CONTEXT
    )
    assert preview.status_code == 200, preview.text
    applied = api.client.post(
        f"{BASE}/fixed-pattern/apply",
        json=edit
        | {
            "preview_key": "edit-preview",
            "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
        },
        headers=api.headers("edit-apply") | CONTEXT,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["result"]["pattern_revision"] == 2


def test_protected_attachment_from_ordinary_task_uses_exact_wire_choice(api):
    api.user(USER, True)
    original = api.client.post(
        "/api/v1/tasks/definitions",
        json={"title": "Existing task", "expected_revision": 0},
        headers=api.headers("manual"),
    )
    assert original.status_code == 200, original.text
    task = original.json()["result"]
    choice = {
        "definition_id": task["definition_id"],
        "definition_revision": 1,
        "occurrence_id": task["occurrence_id"],
        "occurrence_revision": 1,
        "initial": {"kind": "date", "local": "2026-12-31"},
        "interval_days": 30,
        "zone": "UTC",
        "repeated_time": "household",
        "choice": "adopt",
    }
    headers = api.headers("attachment-preview") | CONTEXT
    endpoint = f"{BASE}/attachment/preview"
    for initial, status in [
        ({"kind": "date", "local": "2026-02-30"}, 422),
        ({"kind": "time", "local": "2026-12-31T20:30Z"}, 422),
        ({"kind": "time", "local": "2026-12-31T20:30:00.123"}, 409),
    ]:
        invalid = api.client.post(endpoint, json=choice | {"initial": initial}, headers=headers)
        assert invalid.status_code == status, invalid.text
    preview = api.client.post(endpoint, json=choice, headers=headers)
    assert preview.status_code == 200, preview.text
    applied = api.client.post(
        f"{BASE}/attachment/apply",
        json=choice
        | {
            "preview_key": "attachment-preview",
            "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
        },
        headers=api.headers("attachment-apply") | CONTEXT,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["result"]["first_occurrence_id"] == task["occurrence_id"]
    original = api.client.get(
        f"{BASE}/requests/recurrence.review.apply/attachment-apply", headers=CONTEXT
    )
    assert original.json() == applied.json()


def test_protected_relative_settings_review_preserves_manual_work(api):
    api.user(USER, True)
    manual = seed_manual(api)
    selection = {
        "schedule_id": manual["schedule_id"],
        "schedule_revision": 1,
        "interval_days": 45,
        "visibility": "at_verification",
    }
    preview = api.client.post(
        f"{BASE}/relative-settings/preview",
        json=selection,
        headers=api.headers("settings-preview") | CONTEXT,
    )
    assert preview.status_code == 200, preview.text
    applied = api.client.post(
        f"{BASE}/relative-settings/apply",
        json=selection
        | {
            "preview_key": "settings-preview",
            "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
        },
        headers=api.headers("settings-apply") | CONTEXT,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["result"]["interval_days"] == 45
    assert applied.json()["result"]["pattern_revision"] == 2
    with api.store.read() as unit:
        assert len(unit.tasks.occurrences("home")) == 1


def test_protected_reschedule_preserves_slot_and_exposes_task_history(api):
    api.user(USER, True)
    choice = seed_manual(api)
    headers = api.headers("adopt-preview") | CONTEXT
    preview = api.client.post(f"{BASE}/adoption/preview", json=choice, headers=headers)
    assert preview.status_code == 200, preview.text
    adopted = api.client.post(
        f"{BASE}/adoption/apply",
        json=choice
        | {
            "preview_key": "adopt-preview",
            "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
        },
        headers=api.headers("adopt") | CONTEXT,
    )
    assert adopted.status_code == 200, adopted.text
    with api.store.read() as unit:
        slot = unit.recurrence.relative_slot_for_occurrence("home", choice["occurrence_id"])
    move = choice | {
        "slot_key": slot.key,
        "destination": {"kind": "date", "local": "2090-01-04"},
        "reason": "Scheduled absence",
    }
    preview = api.client.post(
        f"{BASE}/reschedule/preview",
        json=move,
        headers=api.headers("move-preview") | CONTEXT,
    )
    assert preview.status_code == 200, preview.text
    moved = api.client.post(
        f"{BASE}/reschedule/apply",
        json=move
        | {
            "preview_key": "move-preview",
            "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
        },
        headers=api.headers("move-apply") | CONTEXT,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["result"]["work"]["revision"] == 2
    history = api.client.get(f"/api/v1/tasks/occurrences/{choice['occurrence_id']}/history")
    assert history.status_code == 200, history.text
    assert history.json()["items"][-1]["reason"] == "Scheduled absence"


def test_recurrence_target_uses_the_current_rule_and_requires_manager_context(api):
    api.user(USER, True)
    choice = seed_manual(api)
    endpoint = f"{BASE}/targets/{choice['occurrence_id']}"
    assert api.client.get(endpoint).status_code == 422
    assert api.client.get(f"{endpoint}?household=other", headers=CONTEXT).status_code == 422
    response = api.client.get(endpoint, headers=CONTEXT)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schedule"]["schedule_id"] == choice["schedule_id"]
    assert payload["schedule"]["nominal_kind"] == "date"
    assert payload["actions"] == ["state", "relative-settings", "adoption"]
    assert payload["slot_key"] is None
    assert api.client.get(f"{BASE}/targets/unknown", headers=CONTEXT).status_code == 404
    member = "b" * 32
    api.user(member)
    assert (
        api.client.get(
            endpoint, headers={"X-Domus-Context": f"v1:{INSTANCE}:edge:{member}"}
        ).status_code
        == 403
    )


def test_fixed_exception_wire_previews_applies_and_recovers_original(api):
    from test_ha_calendar_projection import seed

    api.user(USER, True)
    schedule = seed(api, timed=False)
    route = BASE + "/fixed-exception"
    selection = {
        "schedule_id": schedule,
        "schedule_revision": 1,
        "effect": "exclude",
        "nominal": {"kind": "date", "local": "2026-03-29"},
        "reason": "Holiday",
    }
    headers = api.headers("exception-preview") | CONTEXT
    for invalid in (
        selection | {"effect": "other"},
        selection | {"nominal": {"kind": "date", "local": "2026-02-30"}},
    ):
        assert api.client.post(route + "/preview", json=invalid, headers=headers).status_code == 422
    preview = api.client.post(route + "/preview", json=selection, headers=headers)
    assert preview.status_code == 200, preview.text
    plan = preview.json()["result"]
    applied = api.client.post(
        route + "/apply",
        headers=api.headers("exception-apply") | CONTEXT,
        json={
            **selection,
            "preview_key": "exception-preview",
            "plan_fingerprint": plan["plan_fingerprint"],
        },
    )
    assert applied.status_code == 200, applied.text
    original = BASE + "/requests/recurrence.review.apply/exception-apply"
    assert api.client.get(original, headers=CONTEXT).json() == applied.json()
    assert len(plan["plan"]["source"]["cancelled_work"]) == 1


def test_current_ha_rejection_fences_review_and_original_recovery_until_fresh_proof(api):
    from domus.domain.errors import IdentityRejected, IdentityUnavailable

    api.user(USER, True)
    choice = seed_manual(api)
    preview_url, apply_url = f"{BASE}/adoption/preview", f"{BASE}/adoption/apply"
    preview_headers = api.headers("original-preview") | CONTEXT
    preview = api.client.post(preview_url, json=choice, headers=preview_headers)
    assert preview.status_code == 200
    reviewed = choice | {
        "preview_key": "original-preview",
        "plan_fingerprint": preview.json()["result"]["plan_fingerprint"],
    }
    apply_headers = api.headers("original-apply") | CONTEXT
    applied = api.client.post(apply_url, json=reviewed, headers=apply_headers)
    assert applied.status_code == 200
    original = f"{BASE}/requests/recurrence.review.apply/original-apply"
    original_bytes = api.store.path.read_bytes()
    api.source.error = IdentityRejected("ha_subject_rejected")
    assert api.client.post(preview_url, json=choice, headers=preview_headers).status_code == 401
    assert api.client.post(apply_url, json=reviewed, headers=apply_headers).status_code == 401
    assert api.client.get(original, headers=CONTEXT).status_code == 401
    api.source.error = IdentityUnavailable("ha_unavailable")
    assert api.client.get(original, headers=CONTEXT).status_code in (401, 503)
    assert api.store.path.read_bytes() == original_bytes

    api.source.error = None
    api.user(USER, True)
    assert api.client.get(original, headers=CONTEXT).json() == applied.json()
    assert (
        api.client.post(
            apply_url, json=reviewed, headers=api.headers("original-apply") | CONTEXT
        ).json()
        == applied.json()
    )
    assert api.store.path.read_bytes() == original_bytes
