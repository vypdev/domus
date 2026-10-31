"""Current local authorization controls every read and discloses no unrelated private linkage."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_household_commands import fixture
from test_member_commands import configured

from domus.application.household_queries import HouseholdQueries
from domus.domain.errors import Conflict, Forbidden, NotFound
from domus.domain.identity import HumanIdentity, MemberStatus, Permission, PermissionRule, Role


def test_unconfigured_access_never_initializes_or_enrolls_anyone(tmp_path: Path) -> None:
    _, store, actor, _, _ = fixture(tmp_path / "database")
    result = HouseholdQueries(store, actor.human).access()
    assert result.state == "unconfigured" and result.setup_allowed
    assert not result.enrollment_allowed and result.member is None
    ordinary = HumanIdentity("ordinary", False, True, False)
    assert not HouseholdQueries(store, ordinary).access().setup_allowed
    with store.read() as unit:
        assert unit.households.current() is None
        assert unit.audit.entries("home") == unit.outbox.pending() == ()


def test_pending_and_unlinked_people_can_read_only_their_own_access_state(tmp_path: Path) -> None:
    _, store, _, directory, member_id = configured(tmp_path)
    pending = HouseholdQueries(store, directory.people["ha_joiner"])
    result = pending.access()
    assert result.state == "pending" and not result.enrollment_allowed
    assert result.member.member_id == member_id
    assert result.permissions == ()
    unlinked = HouseholdQueries(store, HumanIdentity("unlinked", False, True, False)).access()
    assert unlinked.state == "not_enrolled" and unlinked.enrollment_allowed
    assert unlinked.member is None and unlinked.policy_revision is None
    for read in (pending.household, pending.members, pending.policy):
        with pytest.raises(Forbidden):
            read()


def test_admin_can_read_household_member_linkage_and_policy(tmp_path: Path) -> None:
    _, store, actor, _, member_id = configured(tmp_path)
    queries = HouseholdQueries(store, actor.human)
    assert queries.household().name == "Home"
    assert queries.policy().revision == 1
    result = queries.access()
    assert result.state == "active" and not result.setup_allowed
    assert result.member.role is Role.VIEWER and result.effective_role is Role.ADMINISTRATOR
    assert Permission.MEMBERS_MANAGE in result.permissions
    assert Permission.OPERATIONS_READ in result.permissions
    assert (
        Permission.TASKS_COMPLETE not in result.permissions
    )  # This view is the M1 administration scope.
    assert (
        next(member for member in queries.members() if member.member_id == member_id).ha_user_id
        == "ha_joiner"
    )


def test_viewer_roster_hides_others_ha_linkage_and_exceptions(tmp_path: Path) -> None:
    commands, store, _, directory, member_id = configured(tmp_path)
    with store.write() as unit:
        pending = unit.members.get("home", member_id)
        unit.members.save(replace(pending, status=MemberStatus.ACTIVE, revision=2), 1)
        admin = unit.members.by_user("home", "ha_admin")
        unit.members.save(
            replace(
                admin, exceptions=(PermissionRule(Permission.SHOPPING_REQUEST, False),), revision=2
            ),
            1,
        )
    queries = HouseholdQueries(store, directory.people["ha_joiner"])
    roster = queries.members()
    own = next(member for member in roster if member.member_id == member_id)
    other = next(member for member in roster if member.member_id != member_id)
    assert own.ha_user_id == "ha_joiner" and own.exceptions == ()
    assert other.ha_user_id is None and other.exceptions is None
    assert queries.household().household_id == "home"
    with pytest.raises(Forbidden):
        queries.policy()
    assert commands.household_id == "home"


def test_suspension_and_permission_revocation_apply_without_rebuilding_query_service(
    tmp_path: Path,
) -> None:
    _, store, actor, _, _ = configured(tmp_path)
    queries = HouseholdQueries(store, actor.human)
    assert queries.household().name == "Home"
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_admin")
        unit.members.save(
            replace(
                member, exceptions=(PermissionRule(Permission.HOUSEHOLD_READ, False),), revision=2
            ),
            1,
        )
    with pytest.raises(Forbidden):
        queries.household()
    with store.write() as unit:
        member = unit.members.by_user("home", "ha_admin")
        unit.members.save(replace(member, status=MemberStatus.SUSPENDED, revision=3), 2)
    assert queries.access().state == "suspended"
    with pytest.raises(Forbidden):
        queries.members()


def test_operation_query_requires_current_original_permission_and_own_actor(tmp_path: Path) -> None:
    _, store, actor, _, member_id = configured(tmp_path)
    queries = HouseholdQueries(store, actor.human)
    with store.read() as unit:
        setup = unit.audit.entries("home")[0]
    receipt = queries.operation(setup.operation_id)
    assert receipt.receipt.command.action == "household.setup" and not receipt.delivered
    with store.write() as unit:
        unit.outbox.acknowledge(setup.operation_id)
    assert queries.operation(setup.operation_id).delivered
    ordinary = HouseholdQueries(store, HumanIdentity("ha_joiner", False, True, False))
    with pytest.raises(Forbidden):
        ordinary.operation(setup.operation_id)
    with store.write() as unit:
        member = unit.members.get("home", member_id)
        unit.members.save(replace(member, status=MemberStatus.ACTIVE, revision=2), 1)
    with pytest.raises(NotFound):
        ordinary.operation(setup.operation_id)
    actor.human = replace(actor.human, is_administrator=False)
    with pytest.raises(Forbidden):
        HouseholdQueries(store, actor.human).operation(setup.operation_id)


def test_configured_household_without_policy_fails_closed(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    _, store, actor, _, _ = configured(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("DELETE FROM household_policy")
    with pytest.raises(Conflict, match="household_configuration_required"):
        HouseholdQueries(store, actor.human).access()


def test_own_enrollment_result_remains_original_after_activation(tmp_path: Path) -> None:
    _, store, _, directory, member_id = configured(tmp_path)
    with store.read() as unit:
        enrollment = unit.audit.entries("home")[1]
    with store.write() as unit:
        member = unit.members.get("home", member_id)
        unit.members.save(replace(member, status=MemberStatus.ACTIVE, revision=2), 1)
    queries = HouseholdQueries(store, directory.people["ha_joiner"])
    result = queries.operation(enrollment.operation_id)
    assert result.receipt.result.decode()["status"] == "pending"
    assert queries.access().state == "active"


def test_cross_household_access_fails_without_disclosing_state(tmp_path: Path) -> None:
    _, store, actor, _, _ = configured(tmp_path)
    with pytest.raises(Forbidden):
        HouseholdQueries(store, actor.human, "other").access()


def test_corrupt_overflow_roster_never_leaks_a_partial_list(tmp_path: Path) -> None:
    from domus.domain.errors import StorageFailure

    _, store, actor, _, member_id = configured(tmp_path)
    with store.write() as unit:
        member = unit.members.get("home", member_id)
        for number in range(255):
            unit.members.save(
                replace(member, member_id=f"overflow{number}", ha_user_id=f"ha_{number}"), 0
            )
    with pytest.raises(StorageFailure):
        HouseholdQueries(store, actor.human).members()


def test_operation_query_does_not_authorize_unregistered_command_actions(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    _, store, actor, _, _ = configured(tmp_path)
    with store.read() as unit:
        operation = unit.audit.entries("home")[0].operation_id
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute(
            "UPDATE receipts SET action='unknown.command' WHERE operation_id=?", (operation,)
        )
    with pytest.raises(Forbidden):
        HouseholdQueries(store, actor.human).operation(operation)


@pytest.mark.parametrize("damage", ["missing-event", "invalid-delivery", "missing-household"])
def test_missing_or_corrupt_atomic_records_are_not_reported_as_success(
    tmp_path: Path, damage: str
) -> None:
    import sqlite3
    from contextlib import closing

    from domus.domain.errors import StorageFailure

    _, store, actor, _, _ = configured(tmp_path)
    with store.read() as unit:
        operation = unit.audit.entries("home")[0].operation_id
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        if damage == "missing-event":
            connection.execute("DELETE FROM outbox WHERE event_id=?", (operation,))
        elif damage == "invalid-delivery":
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute(
                "UPDATE outbox SET delivered='invalid' WHERE event_id=?", (operation,)
            )
        else:
            connection.execute("DELETE FROM households")
    queries = HouseholdQueries(store, actor.human)
    with pytest.raises(StorageFailure):
        if damage == "missing-household":
            queries.household()
        else:
            queries.operation(operation)


def test_an_unlinked_human_cannot_probe_operation_existence(tmp_path: Path) -> None:
    _, store, _, _, _ = configured(tmp_path)
    queries = HouseholdQueries(store, HumanIdentity("unlinked", False, True, False))
    with pytest.raises(Forbidden):
        queries.operation("unknown-operation")
