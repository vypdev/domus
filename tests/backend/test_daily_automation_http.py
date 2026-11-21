"""Both protected HTTP compositions expose reviewed daily control and bounded history."""

from copy import deepcopy
from dataclasses import replace

from test_automation_drafts import DRAFTS, read, save
from test_automation_execution import configure, result
from test_automation_preview import ACTION, CONTEXT, USER
from test_daily_automation_drafts import DAILY
from test_inventory_catalog_http import register
from test_task_runtime import api as api

from domus.domain.errors import IntegrationUnavailable
from domus.domain.identity import Permission, PermissionRule
from domus.infrastructure.application_runtime import SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime


def draft(api):
    api.user(USER, True)
    return result(save(api, "daily", **DAILY, action=ACTION, condition=None))["rule_id"]


def review(api, rule_id):
    response = read(api, f"{DRAFTS}/{rule_id}/daily", params={"revision": "1"})
    assert response.status_code == 200, response.text
    return response.json()


def body(value, *, reviewed=True):
    payload = {
        "rule_revision": value["rule_revision"],
        "expected_control_revision": value["control_revision"],
        "expected_schedule_revision": value["schedule_revision"],
    }
    if reviewed:
        payload["reviewed"] = value["proposed_times"][0]
    return payload


def write(api, rule_id, action, key, payload):
    return api.client.post(
        f"{DRAFTS}/{rule_id}/daily/{action}", json=payload, headers=api.headers(key) | CONTEXT
    )


def original(api, action, key):
    return read(api, f"/api/v1/automation/daily/requests/{action}/{key}")


def test_complete_review_enable_policy_adoption_and_disable_preserve_original_requests(api):
    rule_id = draft(api)
    before = review(api, rule_id)
    assert not before["enabled"] and before["may_enable"]
    assert before["grant_owner"] == "household_rule" and before["capability"] == "task.create"
    assert before["approved_times"] is None and before["active_trigger"] is None
    assert len(before["proposed_times"]) == 5
    assert before["condition"] is None and before["condition_product_ids"] == []
    enabled = write(api, rule_id, "enable", "enable", body(before))
    assert enabled.status_code == 200, enabled.text
    assert original(api, "enable", "enable").json() == enabled.json()
    assert write(api, rule_id, "enable", "enable", body(before)).json() == enabled.json()
    current = review(api, rule_id)
    assert current["enabled"] and current["active_trigger"] == "daily"
    assert current["approved_policy"] == current["proposed_policy"]
    assert read(api, f"{DRAFTS}/{rule_id}/execution").json()["control"]["trigger"] == "daily"
    history = read(api, f"{DRAFTS}/{rule_id}/daily/runs")
    assert history.status_code == 200 and history.json() == {
        "rule_id": rule_id,
        "items": [],
        "next_cursor": None,
    }
    with api.store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, revision=home.revision + 1, time_zone="Europe/Madrid"), home.revision
        )
    changed = review(api, rule_id)
    assert changed["policy_changed"] and changed["approved_policy"] == current["approved_policy"]
    assert changed["proposed_policy"]["zone"] == "Europe/Madrid"
    adopted = write(api, rule_id, "adopt", "adopt", body(changed))
    assert adopted.status_code == 200, adopted.text
    assert original(api, "adopt", "adopt").json() == adopted.json()
    disabled = write(api, rule_id, "disable", "disable", body(review(api, rule_id), reviewed=False))
    assert disabled.status_code == 200, disabled.text
    assert original(api, "disable", "disable").json() == disabled.json()
    assert not review(api, rule_id)["enabled"]
    with api.store.read() as unit:
        assert unit.tasks.definitions("home") == ()


def test_daily_review_describes_the_exact_saved_condition_even_after_a_new_revision(api):
    api.user(USER, True)
    product = register(api, "daily-review-product", "Daily review soap", "piece")
    condition = {"kind": "stock_below_minimum", "product_id": product}
    for _ in range(7):
        condition = {"kind": "all", "children": [condition]}
    rule_id = result(save(api, "deep-daily", **DAILY, condition=condition))["rule_id"]
    result(save(api, "new-manual", rule_id=rule_id, revision="1", condition=None))
    current = review(api, rule_id)
    assert current["rule_revision"] == "1" and current["condition"] == condition
    assert current["condition_product_ids"] == [product]
    assert current["requested_time"] == DAILY["trigger"]["time"]


def test_daily_revocation_remains_reachable_when_time_zone_data_is_unavailable(api, monkeypatch):
    rule_id = draft(api)
    assert write(api, rule_id, "enable", "enable", body(review(api, rule_id))).status_code == 200

    def unavailable(*_args):
        raise IntegrationUnavailable("timezone_data_unavailable")

    monkeypatch.setattr(PinnedRecurrenceTime, "resolve", unavailable)
    current = review(api, rule_id)
    assert current["proposed_unavailable"] and current["proposed_times"] == []
    assert current["approved_unavailable"] and current["approved_times"] is None
    assert current["enabled"]
    assert (
        write(api, rule_id, "disable", "disable", body(current, reviewed=False)).status_code == 200
    )
    assert not review(api, rule_id)["enabled"]


def test_unreviewed_stale_and_expanded_commands_cannot_grant_authority(api):
    rule_id = draft(api)
    current = review(api, rule_id)
    payload = body(current)
    for changes in (
        {"household_id": "other"},
        {"grant_id": "caller-grant"},
        {"principal": "system:admin"},
        {"rule_revision": 1},
        {"reviewed": None},
    ):
        response = write(api, rule_id, "enable", "forged", payload | changes)
        assert response.status_code == 422, response.text
    stale = write(api, rule_id, "enable", "stale", payload | {"expected_control_revision": "1"})
    assert stale.status_code == 409
    no_context = api.client.post(
        f"{DRAFTS}/{rule_id}/daily/enable", json=payload, headers=api.headers("no-context")
    )
    assert no_context.status_code == 422
    no_csrf = api.client.post(f"{DRAFTS}/{rule_id}/daily/enable", json=payload, headers=CONTEXT)
    assert no_csrf.status_code == 403
    assert not review(api, rule_id)["enabled"]


def test_current_task_permission_controls_enablement_and_keeps_revocation_available(api):
    rule_id = draft(api)
    first = review(api, rule_id)
    assert write(api, rule_id, "enable", "enable", body(first)).status_code == 200
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(
                member,
                revision=member.revision + 1,
                exceptions=(PermissionRule(Permission.TASKS_CREATE, False),),
            ),
            member.revision,
        )
    current = review(api, rule_id)
    assert current["enabled"] and not current["may_enable"]
    listing = read(api)
    assert listing.status_code == 200 and listing.json()["may_save"] is False
    assert listing.json()["drafts"][0]["rule_id"] == rule_id
    assert read(api, f"{DRAFTS}/{rule_id}").status_code == 200
    assert original(api, "enable", "enable").status_code == 403
    assert write(api, rule_id, "enable", "reenable", body(current)).status_code == 403
    assert (
        write(api, rule_id, "disable", "disable", body(current, reviewed=False)).status_code == 200
    )


def test_active_daily_discovery_remains_available_with_a_new_manual_draft_and_no_task_create(api):
    rule_id = draft(api)
    route = f"{DRAFTS}/{rule_id}/daily/active"
    assert read(api, route).json() is None
    assert write(api, rule_id, "enable", "enable", body(review(api, rule_id))).status_code == 200
    result(save(api, "new-manual", rule_id=rule_id, revision="1", condition=None))
    with api.store.write() as unit:
        member = unit.members.by_user("home", USER)
        unit.members.save(
            replace(
                member,
                revision=member.revision + 1,
                exceptions=(PermissionRule(Permission.TASKS_CREATE, False),),
            ),
            member.revision,
        )
    assert read(api, f"{DRAFTS}/{rule_id}/execution").status_code == 403
    current = read(api, route)
    assert current.status_code == 200, current.text
    value = current.json()
    assert value["rule_revision"] == "1" and value["active_rule_revision"] == "1"
    assert value["active_trigger"] == "daily" and value["enabled"] and not value["may_enable"]
    assert read(api, route, params={"revision": "2"}).status_code == 422
    assert write(api, rule_id, "disable", "disable", body(value, reviewed=False)).status_code == 200
    assert read(api, route).json() is None


def test_active_daily_discovery_does_not_alias_manual_rules_or_missing_or_denied_scope(api):
    api.user(USER, True)
    rule_id = result(save(api, "manual"))["rule_id"]
    result(configure(api, rule_id, "enable-manual"))
    assert read(api, f"{DRAFTS}/{rule_id}/daily/active").json() is None
    assert read(api, f"{DRAFTS}/missing/daily/active").status_code == 404
    api.user(USER, False)
    rejected = read(api, f"{DRAFTS}/{rule_id}/daily/active")
    assert rejected.status_code == 403 and "active_rule_revision" not in rejected.json()


def test_daily_queries_reject_unknown_duplicate_or_cross_scope_parameters(api):
    rule_id = draft(api)
    for query in (
        {},
        {"revision": "0"},
        {"revision": "1", "household_id": "other"},
        [("revision", "1"), ("revision", "2")],
    ):
        response = read(api, f"{DRAFTS}/{rule_id}/daily", params=query)
        assert response.status_code == 422, response.text
    for query in ({"limit": "0"}, {"limit": "101"}, {"actor": "other"}, {"cursor": "forged"}):
        response = read(api, f"{DRAFTS}/{rule_id}/daily/runs", params=query)
        assert response.status_code == 422, response.text
    foreign = CONTEXT["X-Domus-Context"].replace(USER, "b" * 32)
    response = api.client.get(
        f"{DRAFTS}/{rule_id}/daily", params={"revision": "1"}, headers={"X-Domus-Context": foreign}
    )
    assert response.status_code == 403 and "approved_times" not in response.json()


def test_reviewed_times_are_closed_typed_and_cannot_forge_or_silently_refresh_the_policy(api):
    rule_id = draft(api)
    payload = body(review(api, rule_id))
    for change in ("nominal", "resolution", "offset", "policy", "canonical"):
        altered = deepcopy(payload)
        if change == "nominal":
            altered["reviewed"]["nominal"] = "invalid-local-time!"
        elif change == "resolution":
            altered["reviewed"]["resolution"] = "always_allow"
        elif change == "offset":
            altered["reviewed"]["offset_seconds"] = True
        elif change == "policy":
            altered["reviewed"]["policy"]["admin"] = True
        else:
            altered["reviewed"]["nominal"] += ".000"
        denied = write(api, rule_id, "enable", "invalid-reviewed-" + change, altered)
        assert denied.status_code == 422, denied.text
    altered = deepcopy(payload)
    altered["reviewed"]["zone_digest"] = "f" * 64
    stale = write(api, rule_id, "enable", "changed-time-data", altered)
    assert stale.status_code == 409, stale.text
    assert not review(api, rule_id)["enabled"]


def test_switching_manual_and_daily_revisions_fences_the_real_composed_worker(api, monkeypatch):
    api.user(USER, True)
    rule_id = result(save(api, "manual"))["rule_id"]
    result(configure(api, rule_id, "manual-enable"))
    result(save(api, "daily-revision", rule_id=rule_id, revision="1", **DAILY))
    response = read(api, f"{DRAFTS}/{rule_id}/daily", params={"revision": "2"})
    assert response.status_code == 200, response.text
    current = response.json()
    assert current["active_trigger"] == "manual" and current["active_rule_revision"] == "1"
    result(write(api, rule_id, "enable", "daily-enable", body(current)))
    due_at = current["proposed_times"][0]
    planned = api.runtime.automation_worker
    with api.store.read() as unit:
        schedule = unit.scheduled_automations.schedule("home", rule_id)
    assert schedule.next_time.nominal.local.isoformat() == due_at["nominal"]
    monkeypatch.setattr(SystemClock, "now", lambda _: schedule.next_time.instant_ms + 1)
    admitted = planned._tick(lambda: True)
    assert any(step.status == "admitted" for step in admitted.steps)
    result(save(api, "manual-revision", rule_id=rule_id, revision="2"))
    result(configure(api, rule_id, "manual-again", revision="3", expected="2"))
    planned._tick(lambda: True)
    history = read(api, f"{DRAFTS}/{rule_id}/daily/runs")
    assert history.status_code == 200, history.text
    assert [item["outcome"] for item in history.json()["items"]] == ["cancelled"]
    state = read(api, f"{DRAFTS}/{rule_id}/execution").json()
    assert state["control"]["enabled"] and state["control"]["rule_revision"] == "3"
    with api.store.read() as unit:
        assert unit.tasks.definitions("home") == ()
