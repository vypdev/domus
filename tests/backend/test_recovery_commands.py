"""Recovery requires current HA proof, an exact console decision and atomic consumption."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from test_household_commands import fixture

from domus.application.household_commands import SetupHousehold
from domus.application.recovery_commands import RecoveryCommands, RecoveryConsole, RecoveryQueries
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IdentityUnavailable,
    InvalidInput,
    NotFound,
    StorageFailure,
)
from domus.domain.identity import HumanIdentity, MappingMode, Member, MemberStatus, Role
from domus.domain.storage import Installation
from domus.infrastructure.sqlite import SQLiteOutbox


class Clock:
    time = 1000

    def now(self) -> int:
        return self.time


class Console:
    accepted = True
    before = None

    def __init__(self):
        self.reviews = []

    def confirm(self, request, member):
        self.reviews.append((request, member))
        if self.before:
            self.before()
        return self.accepted


def configured(tmp_path: Path, mode: MappingMode = MappingMode.SETUP) -> tuple:
    household, store, actor, _, identifiers = fixture(tmp_path / "database")
    target = "ha_selected" if mode is MappingMode.SELECTED else None
    household.setup("setup", SetupHousehold("Home", "UTC", mode, target))
    actor.human = HumanIdentity("ha_new", True, True, False)
    clock, console = Clock(), Console()
    commands = RecoveryCommands(store, actor, store.installation, clock, identifiers)
    approval = RecoveryConsole(store, store.installation, clock, identifiers, console)
    return commands, approval, store, actor, clock, console


def start(commands) -> str:
    return commands.start("start").result.decode()["request_id"]


@pytest.mark.parametrize("mode", [MappingMode.SETUP, MappingMode.SELECTED])
def test_recovery_grants_only_explicit_administration_after_console_and_fresh_proof(
    tmp_path: Path, mode: MappingMode
) -> None:
    commands, approval, store, actor, clock, console = configured(tmp_path, mode)
    request_id = start(commands)
    with store.read() as unit:
        original_policy = unit.policies.get("home")
        assert unit.members.by_user("home", "ha_new") is None
    with pytest.raises(Conflict, match="recovery_not_approved"):
        commands.complete("complete", request_id, 1)
    approved = approval.approve(request_id)
    assert len(console.reviews) == 1
    assert console.reviews[0][0].target_ha_user_id == "ha_new"
    assert approval.approve(request_id) == approved and len(console.reviews) == 1
    finished = commands.complete("complete", request_id, 2)
    result = finished.result.decode()
    assert result["state"] == "recovered" and result["role"] == "administrator"
    with store.read() as unit:
        member = unit.members.by_user("home", "ha_new")
        assert member.role is Role.ADMINISTRATOR and member.status is MemberStatus.ACTIVE
        assert unit.policies.get("home") == original_policy
        assert unit.recoveries.get("home", request_id).state.value == "consumed"
        assert unit.receipts.get(finished.command) == finished
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 4
    clock.time = 900000
    assert commands.complete("complete", request_id, 2) == finished
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.complete("another-key", request_id, 2)
    assert (
        RecoveryQueries(store, actor.human, store.installation, clock)
        .get(request_id)
        .decode()["state"]
        == "consumed"
    )


@pytest.mark.parametrize("status", list(MemberStatus))
def test_existing_link_is_explicitly_restored_without_relinking_or_duplicate_member(
    tmp_path: Path, status: MemberStatus
) -> None:
    commands, approval, store, _, _, _ = configured(tmp_path)
    with store.write() as unit:
        unit.members.save(Member("existing", "home", "ha_new", Role.RESTRICTED, status, 1), 0)
    request_id = start(commands)
    approval.approve(request_id)
    receipt = commands.complete("complete", request_id, 2)
    with store.read() as unit:
        person = unit.members.by_user("home", "ha_new")
        assert person.member_id == "existing" and person.revision == 2
        assert person.role is Role.ADMINISTRATOR and person.status is MemberStatus.ACTIVE
        assert len([m for m in unit.members.list("home") if m.ha_user_id == "ha_new"]) == 1
    assert receipt.result.decode()["member_id"] == "existing"


@pytest.mark.parametrize("failure", ["not_ha_admin", "all_mapping", "outage"])
def test_request_requires_selected_or_setup_mode_and_current_ha_administrator(
    tmp_path: Path, failure: str
) -> None:
    commands, _, store, actor, _, _ = configured(
        tmp_path, MappingMode.ALL if failure == "all_mapping" else MappingMode.SETUP
    )
    if failure == "not_ha_admin":
        actor.human = replace(actor.human, is_administrator=False)
    if failure == "outage":
        actor.error = IdentityUnavailable("ha_unavailable")
    with pytest.raises((Forbidden, IdentityUnavailable)):
        commands.start("start")
    with store.read() as unit:
        assert unit.recoveries.pending("home", 1000) == ()
        assert len(unit.audit.entries("home")) == 1


def test_denied_console_confirmation_never_creates_approval_or_grant(tmp_path: Path) -> None:
    commands, approval, store, _, _, console = configured(tmp_path)
    request_id = start(commands)
    console.accepted = False
    with pytest.raises(Forbidden, match="console_confirmation_required"):
        approval.approve(request_id)
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "pending"
        assert len(unit.audit.entries("home")) == 2


@pytest.mark.parametrize("stage", ["approval", "completion"])
def test_expiration_does_not_extend_on_approval_and_grants_nothing(
    tmp_path: Path, stage: str
) -> None:
    commands, approval, store, _, clock, _ = configured(tmp_path)
    request_id = start(commands)
    if stage == "completion":
        approval.approve(request_id)
    clock.time = 601000
    with pytest.raises(Conflict, match="recovery_expired"):
        approval.approve(request_id) if stage == "approval" else commands.complete(
            "finish", request_id, 2
        )
    with store.read() as unit:
        assert unit.members.by_user("home", "ha_new") is None
    assert commands.status(request_id).decode()["state"] == "expired"


@pytest.mark.parametrize("change", ["policy", "member", "installation", "ha_admin", "actor"])
def test_approval_cannot_be_retargeted_or_used_after_source_or_binding_change(
    tmp_path: Path, change: str
) -> None:
    commands, approval, store, actor, _, _ = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    if change == "policy":
        with store.write() as unit:
            policy = unit.policies.get("home")
            unit.policies.save(replace(policy, revision=2), 1)
    elif change == "member":
        with store.write() as unit:
            unit.members.save(
                Member("new", "home", "ha_new", Role.VIEWER, MemberStatus.PENDING, 1), 0
            )
    elif change == "installation":
        commands.installation = Installation(store.installation.instance_id, "stable")
    elif change == "ha_admin":
        actor.human = replace(actor.human, is_administrator=False)
    else:
        actor.human = HumanIdentity("other", True, True, False)
    with pytest.raises((Conflict, Forbidden, NotFound)):
        commands.complete("finish", request_id, 2)
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "approved"


def test_policy_change_during_terminal_confirmation_is_detected_before_approval(
    tmp_path: Path,
) -> None:
    commands, approval, store, _, _, console = configured(tmp_path)
    request_id = start(commands)

    def change():
        with store.write() as unit:
            policy = unit.policies.get("home")
            unit.policies.save(replace(policy, revision=2), 1)

    console.before = change
    with pytest.raises(Conflict, match="recovery_binding_changed"):
        approval.approve(request_id)
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "pending"


def test_late_outbox_failure_rolls_back_consumption_grant_and_all_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, approval, store, _, _, _ = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    original = SQLiteOutbox.append

    def fail(self, event):
        original(self, event)
        if event.event_type == "recovery.complete":
            raise StorageFailure("injected_outbox_failure")

    monkeypatch.setattr(SQLiteOutbox, "append", fail)
    with pytest.raises(StorageFailure):
        commands.complete("finish", request_id, 2)
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "approved"
        assert unit.members.by_user("home", "ha_new") is None
        assert len(unit.audit.entries("home")) == len(unit.outbox.pending()) == 3
    monkeypatch.setattr(SQLiteOutbox, "append", original)
    commands.complete("finish", request_id, 2)


def test_only_request_owner_can_read_or_cancel_and_cancellation_prevents_grant(
    tmp_path: Path,
) -> None:
    commands, approval, store, actor, _, _ = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    actor.human = HumanIdentity("other", True, True, False)
    with pytest.raises(NotFound):
        commands.status(request_id)
    with pytest.raises(NotFound):
        commands.cancel("cancel", request_id, 2)
    actor.human = HumanIdentity("ha_new", False, True, False)
    canceled = commands.cancel("cancel", request_id, 2)
    assert commands.cancel("cancel", request_id, 2) == canceled
    actor.human = replace(actor.human, is_administrator=True)
    with pytest.raises(Conflict):
        commands.complete("finish", request_id, 3)
    with store.read() as unit:
        assert unit.members.by_user("home", "ha_new") is None


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_completion_has_one_grant_and_one_consumed_request(
    tmp_path: Path, same_key: bool
) -> None:
    commands, approval, store, actor, _, _ = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    barrier = Barrier(2)
    original = actor.current

    def current():
        human = original()
        barrier.wait(timeout=5)
        return human

    actor.current = current

    def finish(key):
        try:
            return commands.complete(key, request_id, 2)
        except Conflict as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(finish, ["finish", "finish" if same_key else "other-key"]))
    if same_key:
        assert values[0] == values[1]
    else:
        assert sum(not isinstance(v, str) for v in values) == 1
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "consumed"
        assert len(unit.audit.entries("home")) == 4


def test_request_replay_is_stable_and_other_keys_cannot_flood_pending_requests(
    tmp_path: Path,
) -> None:
    commands, _, _, _, _, _ = configured(tmp_path)
    first = commands.start("start")
    assert commands.start("start") == first
    with pytest.raises(Conflict, match="recovery_pending"):
        commands.start("other-key")
    with pytest.raises(InvalidInput) as rejected:
        commands.start("bad", True)
    assert rejected.value.code == "invalid_revision"


def test_missing_household_or_request_never_acquires_recovery_authority(tmp_path: Path) -> None:
    household, store, actor, _, identifiers = fixture(tmp_path / "empty")
    commands = RecoveryCommands(store, actor, store.installation, Clock(), identifiers)
    with pytest.raises(Forbidden, match="recovery_unavailable"):
        commands.start("start")
    commands, approval, _, _, _, _ = configured(tmp_path)
    with pytest.raises(NotFound, match="recovery_missing"):
        commands.status("missing")
    with pytest.raises(NotFound, match="recovery_missing"):
        approval.approve("missing")


def test_active_request_capacity_is_bounded_per_household(tmp_path: Path) -> None:
    from domus.domain.recovery import RecoveryRequest

    commands, _, store, _, _, _ = configured(tmp_path)
    with store.write() as unit:
        policy = unit.policies.get("home")
        for i in range(256):
            unit.recoveries.save(
                RecoveryRequest(
                    f"request-{i}",
                    "home",
                    f"ha_other{i}",
                    store.installation,
                    policy.mapping,
                    1,
                    None,
                    0,
                    1000,
                    601000,
                ),
                0,
            )
    with pytest.raises(Conflict, match="recovery_capacity"):
        commands.start("start")


def test_member_capacity_and_cancellation_revision_conflict_preserve_request(
    tmp_path: Path,
) -> None:
    commands, approval, store, _, _, _ = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    with store.write() as unit:
        for i in range(255):
            unit.members.save(
                Member(f"member-{i}", "home", f"ha_other{i}", Role.VIEWER, MemberStatus.ACTIVE, 1),
                0,
            )
    with pytest.raises(Conflict, match="member_capacity"):
        commands.complete("finish", request_id, 2)
    with pytest.raises(Conflict, match="revision_conflict"):
        commands.cancel("cancel", request_id, 1)
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "approved"


def test_canceled_request_cannot_receive_console_approval(tmp_path: Path) -> None:
    commands, approval, _, _, _, _ = configured(tmp_path)
    request_id = start(commands)
    commands.cancel("cancel", request_id, 1)
    with pytest.raises(Conflict, match="recovery_closed"):
        approval.approve(request_id)


@pytest.mark.parametrize("actor,action", [("other", "recovery.request"), ("ha_new", "unexpected")])
def test_human_recovery_authority_cannot_authorize_a_forged_actor_or_action(
    tmp_path: Path, actor: str, action: str
) -> None:
    from domus.application.recovery_commands import _HumanAuthority
    from domus.domain.storage import CommandKey

    _, _, store, human, _, _ = configured(tmp_path)
    authority = _HumanAuthority(human.human, store.installation, "recovery.request")
    with pytest.raises(Forbidden):
        with store.read() as unit:
            authority.require(CommandKey("home", actor, action, "key"), unit)
    unknown = _HumanAuthority(human.human, store.installation, "unexpected")
    with pytest.raises(Forbidden):
        with store.read() as unit:
            unknown.require(CommandKey("home", "ha_new", "unexpected", "key"), unit)


@pytest.mark.parametrize(
    "actor,action,key",
    [
        ("other", "recovery.approve", "request"),
        ("installation-console", "unexpected", "request"),
        ("installation-console", "recovery.approve", "other"),
    ],
)
def test_console_authority_requires_its_exact_operation_identity(
    tmp_path: Path, actor: str, action: str, key: str
) -> None:
    from domus.application.recovery_commands import _ConsoleAuthority
    from domus.domain.storage import CommandKey

    _, _, store, _, clock, _ = configured(tmp_path)
    authority = _ConsoleAuthority(store.installation, clock, "request")
    with pytest.raises(Forbidden):
        with store.read() as unit:
            authority.require(CommandKey("home", actor, action, key), unit)


def test_expiry_while_operator_reviews_the_terminal_never_commits_approval(tmp_path: Path) -> None:
    commands, approval, store, _, clock, console = configured(tmp_path)
    request_id = start(commands)
    console.before = lambda: setattr(clock, "time", 601000)
    with pytest.raises(Conflict, match="recovery_expired"):
        approval.approve(request_id)
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).state.value == "pending"
        assert len(unit.audit.entries("home")) == 2


def test_completed_recovery_receipt_is_denied_after_current_local_administration_is_removed(
    tmp_path: Path,
) -> None:
    commands, approval, store, _, _, _ = configured(tmp_path)
    request_id = start(commands)
    approval.approve(request_id)
    completed = commands.complete("finish", request_id, 2)
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_new")
        unit.members.save(
            replace(member, role=Role.VIEWER, revision=member.revision + 1), member.revision
        )
    with pytest.raises(Forbidden, match="permission_denied"):
        commands.complete("finish", request_id, 2)
    with store.read() as unit:
        assert unit.receipts.get(completed.command) == completed
        assert unit.recoveries.get("home", request_id).state.value == "consumed"
        assert len(unit.audit.entries("home")) == 4


def test_approval_has_ten_full_minutes_from_confirmation_and_replay_never_extends_it(
    tmp_path: Path,
) -> None:
    commands, approval, store, _, clock, _ = configured(tmp_path)
    request_id = start(commands)
    clock.time = 500000
    receipt = approval.approve(request_id)
    assert receipt.result.decode()["expires_at"] == 1100000
    clock.time = 601000
    assert approval.approve(request_id) == receipt
    assert commands.complete("finish", request_id, 2).result.decode()["state"] == "recovered"
    with store.read() as unit:
        assert unit.recoveries.get("home", request_id).expires_at == 1100000
