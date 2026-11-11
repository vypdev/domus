"""Read authoritative Overview counts through both protected task compositions."""

from dataclasses import replace

from test_task_runtime import api as api
from test_tasks import definition

from domus.domain.identity import Member, MemberStatus, Permission, PermissionRule, Role
from domus.domain.task_values import OccurrenceState, TaskRules
from domus.domain.tasks import HouseholdTaskPolicy

OVERVIEW = "/api/v1/tasks/overview"
OTHER_USER = "b" * 32


def test_overview_groups_authorized_records_and_counts_beyond_the_page(api):
    empty = {"total": 0, "items": []}
    assert api.client.get(OVERVIEW).json() == {"assigned": empty, "unclaimed": empty}
    assert api.client.get(OVERVIEW, params={"member_id": "other"}).status_code == 422

    task = definition()
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            Member("other", "home", OTHER_USER, Role.ADULT, MemberStatus.ACTIVE, 1), 0
        )
        unit.tasks.save_policy(HouseholdTaskPolicy("home", TaskRules()), 0)
        unit.tasks.save_definition(task, 0)
        for number in range(27):
            unit.tasks.save_occurrence(task.new_occurrence(f"unclaimed-{number:02}", 20), 0)
            unit.tasks.save_occurrence(
                task.new_occurrence(f"assigned-{number:02}", 20, assignees=(member.member_id,)),
                0,
            )
        blocked = task.new_occurrence("blocked", 20, assignees=(member.member_id,))
        unit.tasks.save_occurrence(blocked, 0)
        unit.tasks.save_occurrence(blocked.transition(OccurrenceState.BLOCKED, "Waiting"), 1)
        started = task.new_occurrence("started", 20, assignees=(member.member_id,))
        unit.tasks.save_occurrence(started, 0)
        unit.tasks.save_occurrence(started.transition(OccurrenceState.IN_PROGRESS), 1)
        other = task.new_occurrence("other-task", 20, assignees=("other",))
        unit.tasks.save_occurrence(other, 0)
        closed = task.new_occurrence("closed", 20, assignees=(member.member_id,))
        unit.tasks.save_occurrence(closed, 0)
        unit.tasks.save_occurrence(closed.transition(OccurrenceState.CANCELLED, "Done"), 1)

    response = api.client.get(OVERVIEW)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["assigned"] == {
        "total": 29,
        "items": [
            {"occurrence_id": f"assigned-{number:02}", "title": "Wipe table", "state": "assigned"}
            for number in range(25)
        ],
    }
    assert report["unclaimed"] == {
        "total": 27,
        "items": [
            {"occurrence_id": f"unclaimed-{number:02}", "title": "Wipe table", "state": "available"}
            for number in range(25)
        ],
    }
    assert api.client.get("/api/v1/tasks/occurrences/assigned-00").status_code == 200

    with api.store.write() as unit:
        for number in range(27):
            item = unit.tasks.occurrence("home", f"assigned-{number:02}")
            unit.tasks.save_occurrence(item.assign(("other",)), item.revision)
    refreshed = api.client.get(OVERVIEW).json()
    assert refreshed["assigned"] == {
        "total": 2,
        "items": [
            {"occurrence_id": "blocked", "title": "Wipe table", "state": "blocked"},
            {"occurrence_id": "started", "title": "Wipe table", "state": "in_progress"},
        ],
    }
    assert refreshed["unclaimed"] == report["unclaimed"]


def test_overview_requires_current_task_read_authority(api):
    assert api.client.get(OVERVIEW).status_code == 200
    with api.store.write() as unit:
        member = unit.members.list("home")[0]
        unit.members.save(
            replace(member, exceptions=(PermissionRule(Permission.TASKS_READ, False),), revision=2),
            1,
        )
    denied = api.client.get(OVERVIEW)
    assert denied.status_code == 403
    assert "assigned" not in denied.json() and "unclaimed" not in denied.json()
