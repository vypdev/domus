"""Daily grants and reviewed policy adoption use current permissions and durable originals."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_automation_scheduling_values import grant
from test_daily_automation_planning import instant
from test_task_commands import fixture

from domus.application.automation_scheduled_control import (
    ADOPT_DAILY_POLICY,
    DISABLE_DAILY_AUTOMATION,
    ENABLE_DAILY_AUTOMATION,
    DailyAutomationControl,
    DailyControlRequest,
    ReviewedDailyRequest,
)
from domus.application.automation_scheduled_planning import DailyAutomationPlanner
from domus.application.fixed_materialization import MaintenanceScope
from domus.domain.automation import AutomationDraft, AutomationRule
from domus.domain.automation_scheduling import ScheduledAutomationRun, ScheduledOutcome
from domus.domain.errors import Conflict, Forbidden, IntegrationUnavailable, InvalidInput, NotFound
from domus.domain.identity import MemberStatus, Permission, PermissionRule, Role
from domus.domain.storage import CommandKey, JsonDocument
from domus.domain.task_values import TaskContent
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite_receipts import SQLiteReceipts


def setup(tmp_path):
    _, store, actor, identifiers = fixture(tmp_path)
    clock = Mock()
    clock.now.return_value = instant("2026-11-21T00:00:00Z")
    service = DailyAutomationControl(
        store,
        MaintenanceScope(store.installation, "home"),
        actor,
        actor.current,
        clock,
        identifiers,
        DailyAutomationPlanner(PinnedRecurrenceTime()),
    )
    with store.write() as unit:
        unit.automation_drafts.append("home", grant().draft)
    return service, store, actor, clock


def reviewed(service):
    review = service.review("daily", 1)
    return ReviewedDailyRequest(
        "daily",
        1,
        0 if review.control is None else review.control.control_revision,
        0 if review.schedule is None else review.schedule.revision,
        review.proposed_times[0],
    )


def management(service):
    request = reviewed(service)
    return DailyControlRequest(
        request.rule_id,
        request.rule_revision,
        request.expected_control_revision,
        request.expected_schedule_revision,
    )


def test_draft_is_inactive_until_deliberately_enabled_and_original_survives_loss_of_reply(tmp_path):
    service, store, _, _ = setup(tmp_path)
    review = service.review("daily", 1)
    assert review.control is None and review.schedule is None and review.approved_times is None
    assert len(review.proposed_times) == 5
    request = reviewed(service)
    first = service.enable("enable", request)
    assert service.original(ENABLE_DAILY_AUTOMATION, "enable") == first
    assert service.enable("enable", request) == first
    saved = service.review("daily", 1)
    assert saved.schedule.grant.draft == review.draft and saved.control.enabled
    assert saved.schedule.next_time == request.reviewed
    assert saved.approved_times == saved.proposed_times
    with store.read() as unit:
        assert unit.scheduled_automations.pending("home") == ()
        assert unit.tasks.definitions("home") == ()
        assert all(event.event_id != first.operation_id for event in unit.outbox.pending())


def test_saving_a_new_draft_never_rebinds_the_existing_grant(tmp_path):
    service, store, _, _ = setup(tmp_path)
    service.enable("enable", reviewed(service))
    before = service.review("daily", 1).schedule
    with store.write() as unit:
        newer = replace(
            before.grant.draft,
            revision=2,
            rule=replace(before.grant.draft.rule, task=TaskContent("New draft title")),
        )
        unit.automation_drafts.append("home", newer)
    assert service.review("daily", 2).schedule == before
    request = reviewed(service)
    switched = replace(request, rule_revision=2)
    service.enable("switch", switched)
    after = service.review("daily", 2).schedule
    assert after.grant.draft == newer and after.grant.grant_id != before.grant.grant_id
    assert after.grant.principal == before.grant.principal


def test_disable_cancels_queued_work_and_reenable_uses_a_new_grant_and_future_time(tmp_path):
    service, store, _, clock = setup(tmp_path)
    service.enable("enable", reviewed(service))
    saved = service.review("daily", 1).schedule
    queued = ScheduledAutomationRun(
        saved.grant, saved.control_revision, saved.next_time, saved.next_time.instant_ms
    )
    with store.write() as unit:
        unit.scheduled_automations.admit(queued)
    clock.now.return_value = saved.next_time.instant_ms + 1000
    request = management(service)
    disabled = service.disable("disable", request)
    assert service.disable("disable", request) == disabled
    assert service.original(DISABLE_DAILY_AUTOMATION, "disable") == disabled
    with store.read() as unit:
        assert (
            unit.scheduled_automations.run("home", queued.key).outcome is ScheduledOutcome.CANCELLED
        )
    service.enable("reenable", reviewed(service))
    after = service.review("daily", 1)
    assert after.control.enabled and after.schedule.grant.grant_id != saved.grant.grant_id
    assert after.schedule.next_time.instant_ms > clock.now()
    with store.read() as unit:
        assert unit.scheduled_automations.pending("home") == ()


def test_household_timing_change_keeps_approved_policy_until_explicit_reviewed_adoption(tmp_path):
    service, store, _, _ = setup(tmp_path)
    service.enable("enable", reviewed(service))
    approved = service.review("daily", 1).schedule
    queued = ScheduledAutomationRun(
        approved.grant, approved.control_revision, approved.next_time, approved.next_time.instant_ms
    )
    with store.write() as unit:
        unit.scheduled_automations.admit(queued)
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone="Europe/Madrid", revision=home.revision + 1), home.revision
        )
    changed = service.review("daily", 1)
    assert changed.schedule == approved
    assert changed.approved_times[0].policy.zone == "UTC"
    assert changed.proposed_times[0].policy.zone == "Europe/Madrid"
    request = reviewed(service)
    outcome = service.adopt("adopt", request)
    assert service.adopt("adopt", request) == outcome
    assert service.original(ADOPT_DAILY_POLICY, "adopt") == outcome
    adopted = service.review("daily", 1).schedule
    assert adopted.policy.zone == "Europe/Madrid" and adopted.grant == approved.grant
    with store.read() as unit:
        assert unit.scheduled_automations.run("home", queued.key) == queued


def test_policy_adoption_cannot_replay_an_admitted_nominal_date_after_clock_rollback(tmp_path):
    service, store, _, clock = setup(tmp_path)
    service.enable("enable", reviewed(service))
    old = service.review("daily", 1).schedule
    clock.now.return_value = old.next_time.instant_ms + 1000
    with store.write() as unit:
        next_time = service.planner.next("02:30", old.policy, clock.now())
        unit.scheduled_automations.save_schedule(
            replace(
                old,
                revision=2,
                next_time=next_time,
                last_nominal=old.next_time.nominal.local.date(),
            ),
            1,
        )
        home = unit.households.current()
        unit.households.save(
            replace(home, time_zone="Europe/Madrid", revision=home.revision + 1), home.revision
        )
    clock.now.return_value -= 86_400_000
    service.adopt("adopt", reviewed(service))
    after = service.review("daily", 1).schedule
    assert after.next_time.nominal.local.date() > old.next_time.nominal.local.date()


@pytest.mark.parametrize("permission", [Permission.AUTOMATIONS_CONFIGURE, Permission.TASKS_CREATE])
def test_grant_creation_rechecks_current_permissions_before_original_lookup(tmp_path, permission):
    service, store, actor, _ = setup(tmp_path)
    request = reviewed(service)
    first = service.enable("enable", request)
    with store.write() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        if permission is Permission.AUTOMATIONS_CONFIGURE:
            actor.human = replace(actor.human, is_administrator=False)
            updated = replace(member, revision=member.revision + 1, role=Role.ADULT)
        else:
            updated = replace(
                member,
                revision=member.revision + 1,
                exceptions=(PermissionRule(permission, False),),
            )
        unit.members.save(updated, member.revision)
    with pytest.raises(Forbidden):
        service.enable("enable", request)
    with pytest.raises(Forbidden):
        service.original(ENABLE_DAILY_AUTOMATION, "enable")
    with store.read() as unit:
        assert unit.receipts.get(first.command) == first


def test_revocation_requires_administration_without_regranting_task_creation(tmp_path):
    service, store, actor, _ = setup(tmp_path)
    service.enable("enable", reviewed(service))
    request = management(service)
    with store.write() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(
                member,
                revision=member.revision + 1,
                exceptions=(PermissionRule(Permission.TASKS_CREATE, False),),
            ),
            member.revision,
        )
    assert not service.disable("disable", request).result.decode()["enabled"]


def test_activator_leaving_does_not_revoke_the_persisted_rule_owned_grant(tmp_path):
    service, store, actor, _ = setup(tmp_path)
    service.enable("enable", reviewed(service))
    before = service.review("daily", 1).schedule
    with store.write() as unit:
        member = unit.members.by_user("home", actor.human.ha_user_id)
        unit.members.save(
            replace(member, revision=member.revision + 1, status=MemberStatus.SUSPENDED),
            member.revision,
        )
    with store.read() as unit:
        after = unit.scheduled_automations.schedule("home", "daily")
        assert after == before
        assert after.grant.permits(
            store.installation,
            "home",
            unit.automation_controls.get("home", "daily"),
            after.grant.grant_id,
        )


def test_stale_revisions_and_elapsed_review_never_enable_silently(tmp_path):
    service, store, _, clock = setup(tmp_path)
    request = reviewed(service)
    with pytest.raises(Conflict, match="revision_conflict"):
        service.enable("stale", replace(request, expected_control_revision=1))
    with pytest.raises(Conflict, match="revision_conflict"):
        service.enable("stale-schedule", replace(request, expected_schedule_revision=1))
    clock.now.return_value = request.reviewed.instant_ms
    with pytest.raises(Conflict, match="automation_timing_review_changed"):
        service.enable("elapsed", request)
    with store.read() as unit:
        assert unit.automation_controls.get("home", "daily") is None


def test_unavailable_approved_policy_is_exposed_without_substituting_the_proposed_policy(tmp_path):
    service, _, _, _ = setup(tmp_path)
    service.enable("enable", reviewed(service))
    times = Mock(wraps=service.planner.times)
    times.data_identity = service.planner.times.data_identity
    real = service.planner.upcoming
    old = service.review("daily", 1).schedule
    planner = Mock(wraps=service.planner)
    planner.times = times
    calls = 0

    def upcoming(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise IntegrationUnavailable("approved_policy_unavailable")
        return real(*args, **kwargs)

    planner.upcoming.side_effect = upcoming
    review = replace(service, planner=planner).review("daily", 1)
    assert review.approved_times is None and review.approved_error == "approved_policy_unavailable"
    assert review.schedule == old and len(review.proposed_times) == 5


def test_revocation_stays_available_when_neither_approved_nor_proposed_time_can_be_resolved(
    tmp_path,
):
    service, store, _, _ = setup(tmp_path)
    service.enable("enable", reviewed(service))
    before = service.review("daily", 1)
    planner = Mock(wraps=service.planner)
    planner.times = service.planner.times
    planner.upcoming.side_effect = IntegrationUnavailable("timezone_data_unavailable")
    unavailable = replace(service, planner=planner)
    current = unavailable.review("daily", 1)
    assert current.proposed_times == () and current.proposed_error == "timezone_data_unavailable"
    assert current.approved_times is None and current.approved_error == "timezone_data_unavailable"
    assert current.schedule == before.schedule and current.control.enabled
    request = DailyControlRequest(
        "daily", 1, current.control.control_revision, current.schedule.revision
    )
    unavailable.disable("disable-unavailable", request)
    with store.read() as unit:
        assert not unit.automation_controls.get("home", "daily").enabled
        assert unit.tasks.definitions("home") == ()


def test_unrelated_household_revision_does_not_become_a_timing_change(tmp_path):
    service, store, _, _ = setup(tmp_path)
    assert not service.review("daily", 1).policy_changed
    service.enable("enable", reviewed(service))
    original = service.review("daily", 1).schedule
    with store.write() as unit:
        home = unit.households.current()
        unit.households.save(
            replace(home, name="Renamed home", revision=home.revision + 1), home.revision
        )
    current = service.review("daily", 1)
    assert current.schedule == original and not current.policy_changed
    with pytest.raises(Conflict, match="automation_timing_unchanged"):
        service.adopt("not-a-timing-change", reviewed(service))


def test_invalid_non_daily_and_absent_commands_do_not_grant_authority(tmp_path):
    service, store, _, _ = setup(tmp_path)
    with pytest.raises(NotFound, match="automation_draft_missing"):
        service.review("missing", 1)
    with store.write() as unit:
        unit.automation_drafts.append(
            "home",
            AutomationDraft("manual", 1, AutomationRule(1, "manual", None, TaskContent("Manual"))),
        )
    with pytest.raises(InvalidInput, match="automation_requires_daily_trigger"):
        service.review("manual", 1)
    with pytest.raises(NotFound, match="operation_missing"):
        service.original(ENABLE_DAILY_AUTOMATION, "missing")
    with pytest.raises(InvalidInput, match="invalid_automation_action"):
        service.original("task.create", "fake")
    with pytest.raises(Conflict, match="automation_disabled"):
        service.disable("not-enabled", DailyControlRequest("daily", 1, 0, 0))
    service.enable("enable", reviewed(service))
    with pytest.raises(Conflict, match="automation_timing_unchanged"):
        service.adopt("same", reviewed(service))


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_control_revision", True),
        ("expected_schedule_revision", -1),
        ("expected_control_revision", 2**63),
        ("reviewed", None),
    ],
)
def test_control_requests_reject_coercion_and_missing_review(tmp_path, field, value):
    service, _, _, _ = setup(tmp_path)
    with pytest.raises(InvalidInput):
        replace(reviewed(service), **{field: value})


def test_a_receipt_with_another_membership_is_not_authorized_by_key_possession(
    tmp_path, monkeypatch
):
    service, store, _, _ = setup(tmp_path)
    first = service.enable("enable", reviewed(service))
    read = SQLiteReceipts.get

    def mismatched(self, key):
        value = read(self, key)
        if key != first.command:
            return value
        return replace(
            value,
            result=JsonDocument.from_value(
                {
                    **value.result.decode(),
                    "member_id": "other-membership",
                }
            ),
        )

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteReceipts, "get", mismatched)
        with pytest.raises(Forbidden, match="permission_denied"):
            service.original(ENABLE_DAILY_AUTOMATION, "enable")
    with store.read() as unit:
        assert unit.receipts.get(first.command) == first


def test_control_authority_is_not_transferable_to_another_command_or_stale_rule_revision(tmp_path):
    service, store, actor, _ = setup(tmp_path)
    authority = service._authority(actor.current(), DISABLE_DAILY_AUTOMATION, "disable")
    with store.read() as unit:
        for command in (
            replace(authority.command, key="other"),
            CommandKey("home", actor.human.ha_user_id, "task.complete", "other"),
        ):
            with pytest.raises(Forbidden):
                authority.require(command, unit)
    service.enable("enable", reviewed(service))
    with pytest.raises(Conflict, match="revision_conflict"):
        service.disable("wrong-revision", replace(management(service), rule_revision=2))
