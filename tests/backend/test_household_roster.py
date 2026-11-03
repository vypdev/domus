"""Current proof and local grants fence provider I/O before any public roster disclosure."""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_member_commands import configured

from domus.application.household_roster import HouseholdRosterQueries
from domus.application.member_commands import UpdateMember
from domus.domain.errors import Conflict, Forbidden, IdentityRejected, StorageFailure
from domus.domain.identity import (
    HumanIdentity,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    Role,
)
from domus.domain.member_profiles import MemberPresentation
from domus.domain.member_sources import (
    HAProfile,
    MemberSourceSnapshot,
    ProfileDirectory,
    ProfileResult,
    SourceState,
)


class Source:
    def __init__(self, subject):
        profiles = (
            HAProfile("ha_admin", "Same", True),
            HAProfile("ha_joiner", "Same", True),
            HAProfile("unjoined", "<b>Literal</b>", True),
            HAProfile("inactive", "Old", False),
        )
        directory = ProfileDirectory(SourceState.AVAILABLE, profiles)
        self.value = MemberSourceSnapshot(subject, directory, directory.profile(subject))
        self.callback = lambda: None
        self.calls = 0

    def read(self):
        self.calls += 1
        self.callback()
        return self.value


def fixture(tmp_path, *, administrator=True):
    commands, store, actor, _, target = configured(tmp_path)
    commands.update("activate", UpdateMember(target, 1, Role.RESTRICTED, MemberStatus.ACTIVE))
    if not administrator:
        actor.human = HumanIdentity("ha_joiner", False, True, False)
    source = Source(actor.human.ha_user_id)
    reader = SimpleNamespace(read=lambda: actor.human)
    return HouseholdRosterQueries(store, reader, source), store, actor, source, target


def test_roster_keeps_distinct_accounts_public_aliases_and_existing_privileged_masking(tmp_path):
    query, store, _, source, target = fixture(tmp_path)
    with store.write() as unit:
        unit.presentations.save(MemberPresentation(target, "home", "Literal alias", 2), 1)
    before = store.path.read_bytes()
    result = query.roster()
    assert len(result.members) == 2 and source.calls == 1
    assert len({item.member.member_id for item in result.members}) == 2
    assert {item.metadata.name for item in result.members} == {"Same"}
    row = next(item for item in result.members if item.member.member_id == target)
    assert row.presentation.alias == "Literal alias" and row.presentation.revision == 2
    assert row.member.ha_user_id == "ha_joiner" and row.member.exceptions == ()
    assert not hasattr(row, "preferences")
    assert store.path.read_bytes() == before


def test_ordinary_roster_never_exposes_other_account_links_or_unjoined_directory(tmp_path):
    query, _, _, _, target = fixture(tmp_path, administrator=False)
    result = query.roster()
    for row in result.members:
        assert row.member.ha_user_id == ("ha_joiner" if row.member.member_id == target else None)
        assert row.member.exceptions == (() if row.member.member_id == target else None)
    with pytest.raises(Forbidden):
        query.directory()


def test_ordinary_roster_projection_also_masks_linkage_inside_metadata(tmp_path):
    from dataclasses import asdict

    query, _, _, _, target = fixture(tmp_path, administrator=False)
    row = next(item for item in query.roster().members if item.member.member_id != target)
    metadata = asdict(row)["metadata"]
    assert set(metadata) == {"state", "name"}
    assert metadata["name"] == "Same"


def test_known_accounts_without_names_keep_complete_directory_but_unavailable_labels(tmp_path):
    query, _, actor, source, _ = fixture(tmp_path)
    directory = ProfileDirectory(
        SourceState.AVAILABLE,
        tuple(replace(profile, name=None) for profile in source.value.directory.profiles),
    )
    source.value = MemberSourceSnapshot(
        actor.human.ha_user_id, directory, directory.profile(actor.human.ha_user_id)
    )
    assert all(
        row.metadata.state is SourceState.UNAVAILABLE and row.metadata.name is None
        for row in query.roster().members
    )
    assert query.directory().state is SourceState.AVAILABLE


def test_only_current_policy_authority_reads_complete_eligible_directory_facts(tmp_path):
    query, _, _, source, _ = fixture(tmp_path)
    result = query.directory()
    assert result.state is SourceState.AVAILABLE
    assert {item.ha_user_id for item in result.profiles} == {"ha_admin", "ha_joiner", "unjoined"}
    assert (
        next(item for item in result.profiles if item.ha_user_id == "unjoined").name
        == "<b>Literal</b>"
    )
    assert source.calls == 1


@pytest.mark.parametrize("state", [SourceState.DENIED, SourceState.UNAVAILABLE])
def test_unavailable_source_retains_real_roster_and_explicit_state_without_fake_choices(
    tmp_path, state
):
    query, store, actor, source, target = fixture(tmp_path)
    with store.read() as unit:
        expected_members = tuple(unit.members.list("home"))
    assert len(expected_members) == 2
    assert {item.ha_user_id for item in expected_members} == {"ha_admin", "ha_joiner"}
    assert target in {item.member_id for item in expected_members}
    source.value = MemberSourceSnapshot(
        actor.human.ha_user_id, ProfileDirectory(state), ProfileResult(state)
    )
    before = store.path.read_bytes()
    roster = query.roster()
    assert {item.member.member_id: item.member.ha_user_id for item in roster.members} == {
        item.member_id: item.ha_user_id for item in expected_members
    }
    assert len(roster.members) == len(expected_members)
    assert all(item.metadata.state is state for item in roster.members)
    assert all(item.metadata.name is None for item in roster.members)
    directory = query.directory()
    assert directory.state is state and directory.profiles == ()
    assert store.path.read_bytes() == before


def test_metadata_callback_runs_outside_sql_and_current_alias_is_read_after_it(tmp_path):
    query, store, _, source, target = fixture(tmp_path)

    def update_alias():
        with store.write() as unit:
            unit.presentations.save(MemberPresentation(target, "home", "Concurrent alias", 2), 1)

    source.callback = update_alias
    row = next(item for item in query.roster().members if item.member.member_id == target)
    assert row.presentation.alias == "Concurrent alias"


@pytest.mark.parametrize("kind", ["roster", "directory"])
def test_local_grants_are_rechecked_after_source_io_before_disclosure(tmp_path, kind):
    query, store, actor, source, target = fixture(tmp_path)

    def suspend():
        with store.write() as unit:
            member = unit.members.by_user("home", actor.human.ha_user_id)
            unit.members.save(
                replace(member, status=MemberStatus.SUSPENDED, revision=member.revision + 1),
                member.revision,
            )

    source.callback = suspend
    with pytest.raises(Forbidden):
        getattr(query, kind)()
    assert source.calls == 1


@pytest.mark.parametrize("kind", ["roster", "directory"])
def test_provider_cannot_switch_the_verified_actor_during_io(tmp_path, kind):
    query, _, actor, source, _ = fixture(tmp_path)
    source.callback = lambda: setattr(
        actor, "human", HumanIdentity("ha_joiner", False, True, False)
    )
    with pytest.raises(IdentityRejected, match="identity_mismatch"):
        getattr(query, kind)()


def test_lost_inherited_ha_administration_removes_privileged_roster_fields(tmp_path):
    query, _, actor, source, target = fixture(tmp_path, administrator=False)
    actor.human = replace(actor.human, is_administrator=True)
    source.callback = lambda: setattr(actor, "human", replace(actor.human, is_administrator=False))
    result = query.roster()
    other = next(item for item in result.members if item.member.member_id != target)
    assert other.member.ha_user_id is None and other.member.exceptions is None


def test_lost_inherited_ha_administration_blocks_directory_disclosure(tmp_path):
    query, _, actor, source, _ = fixture(tmp_path, administrator=False)
    actor.human = replace(actor.human, is_administrator=True)
    source.callback = lambda: setattr(actor, "human", replace(actor.human, is_administrator=False))
    with pytest.raises(Forbidden):
        query.directory()


@pytest.mark.parametrize("change", ["member", "policy"])
def test_changed_identity_snapshot_requires_a_fresh_view_instead_of_rebasing(tmp_path, change):
    query, store, _, source, target = fixture(tmp_path)

    def update():
        with store.write() as unit:
            if change == "member":
                member = unit.members.get("home", target)
                unit.members.save(replace(member, revision=member.revision + 1), member.revision)
            else:
                policy = unit.policies.get("home")
                unit.policies.save(replace(policy, revision=policy.revision + 1), policy.revision)

    source.callback = update
    with pytest.raises(Conflict, match="identity_state_changed"):
        query.roster()


@pytest.mark.parametrize("corrupt", ["wrong_subject", "invalid_result"])
def test_source_contract_mismatch_fails_closed_without_records_or_grants(tmp_path, corrupt):
    query, store, _, source, _ = fixture(tmp_path)
    source.value = Source("ha_joiner").value if corrupt == "wrong_subject" else None
    before = store.path.read_bytes()
    with pytest.raises((IdentityRejected, StorageFailure)):
        query.roster()
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "status", [MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_inactive_members_cannot_trigger_a_directory_provider_read(tmp_path, status):
    query, store, _, source, target = fixture(tmp_path, administrator=False)
    with store.write() as unit:
        member = unit.members.get("home", target)
        unit.members.save(
            replace(member, status=status, revision=member.revision + 1), member.revision
        )
    with pytest.raises(Forbidden):
        query.roster()
    assert source.calls == 0


def test_missing_profile_port_record_is_not_an_initializer(tmp_path):
    query, store, _, _, _ = fixture(tmp_path)

    class Broken:
        @contextmanager
        def read(self):
            with store.read() as unit:
                yield SimpleNamespace(
                    members=unit.members,
                    policies=unit.policies,
                    presentations=SimpleNamespace(get=lambda *_: None),
                )

    query = replace(query, transactions=Broken())
    before = store.path.read_bytes()
    with pytest.raises(StorageFailure, match="invalid_member_profile_record"):
        query.roster()
    assert store.path.read_bytes() == before


def test_an_oversized_actual_local_roster_is_not_sent_to_a_provider_or_truncated(tmp_path):
    query, store, _, source, _ = fixture(tmp_path)
    with store.write() as unit:
        for index in range(255):
            unit.members.save(
                Member(
                    f"extra-{index}",
                    "home",
                    f"source-{index}",
                    Role.VIEWER,
                    MemberStatus.ARCHIVED,
                    1,
                ),
                0,
            )
    with pytest.raises(StorageFailure, match="invalid_identity_record"):
        query.roster()
    assert source.calls == 0


def test_revoked_ordinary_read_permission_precedes_snapshot_conflict_and_disclosure(tmp_path):
    query, store, _, source, target = fixture(tmp_path, administrator=False)

    def revoke():
        with store.write() as unit:
            member = unit.members.get("home", target)
            unit.members.save(
                replace(
                    member,
                    revision=member.revision + 1,
                    exceptions=(PermissionRule(Permission.MEMBERS_READ, False),),
                ),
                member.revision,
            )

    source.callback = revoke
    with pytest.raises(Forbidden):
        query.roster()
