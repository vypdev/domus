"""Real protected Ingress and standalone rewards share the Points ledger writer."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from test_recurrence_http import CONTEXT, USER
from test_task_runtime import api as api

from domus.application.points import PointsConsumer
from domus.application.task_commands import TaskCommands
from domus.application.task_requests import CompleteTask, CreateTask, ReopenTask
from domus.domain.identity import HumanIdentity, Member, MemberStatus, Role
from domus.domain.task_values import TaskContent, TaskOverrides
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock

REWARDS = "/api/v1/family/rewards"
MEMBER = "b" * 32
PEER = "c" * 32
ROLE_NAMES = [role.value for role in Role]


def member_context(subject):
    return {"X-Domus-Context": CONTEXT["X-Domus-Context"].replace(USER, subject)}


def response(api, subject, action, key, **payload):
    return api.client.post(
        REWARDS + "/commands",
        json={"action": f"reward.{action}", **payload},
        headers=api.headers(key) | member_context(subject),
    )


def command(api, subject, action, key, **payload):
    sent = response(api, subject, action, key, **payload)
    assert sent.status_code == 200, sent.text
    return sent.json()["result"]


def view(api, subject, **query):
    shown = api.client.get(REWARDS, headers=member_context(subject), params=query)
    assert shown.status_code == 200, shown.text
    return shown.json()


def catalog(api, *, cost=800):
    api.user(USER, True)
    command(api, USER, "configure", "enable", enabled=True, expected_revision=0)
    return command(
        api,
        USER,
        "offer",
        "offer",
        title="Movie night",
        cost_minor=cost,
        enabled=True,
        eligible_roles=ROLE_NAMES,
        expected_revision=0,
    )


def make_members(api):
    with api.store.write() as unit:
        for member_id, user in (("member", MEMBER), ("peer", PEER)):
            unit.members.save(
                Member(member_id, "home", user, Role.ADULT, MemberStatus.ACTIVE, 1), 0
            )


def work_api(api):
    actor = SimpleNamespace(current=lambda: HumanIdentity(USER, True, True, False))
    clock = SystemClock()
    tasks = TaskCommands(api.store, actor, clock, SecureIdentifiers())
    points = PointsConsumer(api.store, api.store.installation, clock)

    def award(key, amount):
        created = tasks.create(
            key, CreateTask(TaskContent(key), overrides=TaskOverrides(point_value_minor=amount))
        ).result.decode()
        occurrence_id = created["occurrence_id"]
        completed = tasks.complete(
            key, CompleteTask(occurrence_id, 1, ("member",), clock.now())
        ).result.decode()
        assert points.tick(lambda: True) == 1
        return occurrence_id, completed["revision"], completed["cycle"]["cycle_id"]

    def reverse(key, work):
        tasks.reopen(key, ReopenTask(*work, "Check the work"))
        assert points.tick(lambda: True) == 1

    return award, reverse


def test_reward_reservation_privacy_hold_delivery_and_negative_history(api):
    make_members(api)
    api.user(MEMBER)
    default = view(api, MEMBER)
    assert default["enabled"] is False and default["may_manage"] is False
    assert (
        response(
            api, MEMBER, "request", "disabled", offer_id="anything", expected_revision=1
        ).json()["code"]
        == "rewards_disabled"
    )
    offer = catalog(api)
    award, reverse = work_api(api)
    original = award("first", 1000)
    api.user(MEMBER)
    requested = command(
        api, MEMBER, "request", "reserve", offer_id=offer["offer_id"], expected_revision=1
    )
    rid = requested["redemption_id"]
    current = view(api, MEMBER)
    assert current["balance"] == {"posted_minor": 1000, "reserved_minor": 800}
    assert current["requests"][0]["cost_minor"] == 800
    assert (
        command(api, MEMBER, "request", "reserve", offer_id=offer["offer_id"], expected_revision=1)
        == requested
    )
    for action in ("approve", "deliver"):
        assert response(api, MEMBER, action, action, redemption_id=rid).status_code == 403
    assert (
        response(api, MEMBER, "configure", "forged", enabled=False, expected_revision=1).status_code
        == 403
    )
    assert (
        response(
            api, MEMBER, "request", "overdraw", offer_id=offer["offer_id"], expected_revision=1
        ).json()["code"]
        == "insufficient_reward_points"
    )

    api.user(PEER)
    assert view(api, PEER)["requests"] == []
    assert (
        api.client.get(
            REWARDS, headers=member_context(PEER), params={"member_id": "member"}
        ).status_code
        == 422
    )
    assert api.client.get(REWARDS, headers=member_context(MEMBER)).status_code == 403
    assert (
        response(
            api,
            PEER,
            "cancel",
            "others-cancel",
            redemption_id=rid,
            expected_revision=1,
            reason="Cancel",
        ).status_code
        == 403
    )
    api.user(USER, True)
    assert view(api, USER)["requests"] == []
    new = command(
        api,
        USER,
        "offer",
        "edit",
        offer_id=offer["offer_id"],
        title="Cinema",
        cost_minor=500,
        enabled=True,
        eligible_roles=ROLE_NAMES,
        expected_revision=1,
    )
    assert new["revision"] == 2
    accepted = command(api, USER, "approve", "approve", redemption_id=rid)
    assert accepted == {"redemption_id": rid, "stage": "approved", "revision": 2}
    assert command(api, USER, "approve", "approve", redemption_id=rid) == accepted
    reverse("reverse-original", original)
    api.user(MEMBER)
    held = view(api, MEMBER)
    record = held["requests"][0]
    assert record["stage"] == "funding_hold" and record["approval"] is not None
    assert record["title"] == "Movie night" and record["offer_revision"] == 1
    assert held["balance"] == {"posted_minor": 0, "reserved_minor": 800}
    api.user(USER, True)
    assert (
        response(api, USER, "deliver", "blocked", redemption_id=rid).json()["code"]
        == "reward_funding_hold"
    )
    replacement = award("replacement", 1000)
    api.user(MEMBER)
    funded = view(api, MEMBER)
    assert funded["requests"][0]["stage"] == "approved"
    assert funded["requests"][0]["approval"] == record["approval"]
    assert funded["balance"] == {"posted_minor": 1000, "reserved_minor": 800}
    api.user(USER, True)
    delivery = command(api, USER, "deliver", "deliver", redemption_id=rid)
    assert delivery["stage"] == "delivered"
    assert command(api, USER, "deliver", "deliver", redemption_id=rid) == delivery
    assert (
        response(api, USER, "deliver", "other-deliver", redemption_id=rid).json()["code"]
        == "redemption_not_approved"
    )
    original_receipt = api.client.get(REWARDS + "/requests/reward.deliver/deliver", headers=CONTEXT)
    assert original_receipt.status_code == 200 and original_receipt.json()["result"] == delivery
    reverse("reverse-replacement", replacement)
    api.user(MEMBER)
    assert view(api, MEMBER)["balance"] == {"posted_minor": -800, "reserved_minor": 0}
    assert view(api, MEMBER)["requests"][0]["stage"] == "delivered"
    assert (
        response(
            api, MEMBER, "request", "negative", offer_id=offer["offer_id"], expected_revision=2
        ).json()["code"]
        == "insufficient_reward_points"
    )
    day = datetime.now(UTC).date()
    report = api.client.get(
        "/api/v1/family",
        headers=member_context(MEMBER),
        params={"start": day - timedelta(days=1), "end": day + timedelta(days=1)},
    )
    assert report.status_code == 200, report.text
    family = report.json()
    assert family["posted_minor"] == family["available_minor"] == -800
    assert family["earned_minor"] == family["reserved_minor"] == 0
    assert family["spent_in_period_minor"] == 800 and family["spending_count"] == 1
    assert family["spending"][0]["redemption_id"] == rid
    assert len([entry for entry in family["history"] if entry["reverses"] is not None]) == 2


def test_own_cancellation_is_idempotent_and_reward_cursor_stays_member_scoped(api):
    make_members(api)
    offer = catalog(api, cost=200)
    award, _ = work_api(api)
    award("credit", 1000)
    api.user(MEMBER)
    ids = [
        command(
            api,
            MEMBER,
            "request",
            f"reserve-{index}",
            offer_id=offer["offer_id"],
            expected_revision=1,
        )["redemption_id"]
        for index in range(2)
    ]
    first = view(api, MEMBER, limit=1)
    assert [row["redemption_id"] for row in first["requests"]] == ids[1:]
    cursor = first["next_cursor"]
    assert [
        row["redemption_id"] for row in view(api, MEMBER, cursor=cursor, limit=1)["requests"]
    ] == ids[:1]
    cancel = {"redemption_id": ids[0], "expected_revision": 1, "reason": "Choose later"}
    current = command(api, MEMBER, "cancel", "cancel", **cancel)
    assert command(api, MEMBER, "cancel", "cancel", **cancel) == current
    assert current["stage"] == "cancelled"
    assert view(api, MEMBER)["balance"] == {"posted_minor": 1000, "reserved_minor": 200}
    api.user(PEER)
    other = api.client.get(
        REWARDS, params={"limit": 1, "cursor": cursor}, headers=member_context(PEER)
    )
    assert other.status_code == 422
    api.user(MEMBER)
    with api.store.write() as unit:
        member = unit.members.get("home", "member")
        unit.members.save(replace(member, status=MemberStatus.SUSPENDED, revision=2), 1)
    assert response(api, MEMBER, "cancel", "cancel", **cancel).status_code == 403
