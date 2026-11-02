"""Current authority, private originals and independent revisions at the real SQLite boundary."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from threading import Barrier

import pytest
from test_member_commands import configured

from domus.application.household_administration_queries import HouseholdAdministrationQueries
from domus.application.household_queries import HouseholdQueries
from domus.application.member_commands import UpdateMember
from domus.application.member_profile_access import (
    ALIAS_ACTION,
    PREFERENCES_ACTION,
    ProfileAuthorization,
    require_profile_original,
)
from domus.application.member_profile_commands import (
    AliasUpdate,
    MemberProfileCommands,
    PreferencesUpdate,
)
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IdentityUnavailable,
    InvalidInput,
    NotFound,
    StorageFailure,
)
from domus.domain.identity import HumanIdentity, MemberStatus, Permission, PermissionRule, Role
from domus.domain.member_profiles import MemberLocale, MemberPreferences, MemberPresentation
from domus.domain.storage import CommandKey, JsonDocument


def fixture(tmp_path, *, role=Role.RESTRICTED, active=True):
    membership, store, actor, _, target = configured(tmp_path)
    if active:
        membership.update("activate", UpdateMember(target, 1, role, MemberStatus.ACTIVE))
    service = MemberProfileCommands(store, actor, membership.clock, membership.identifiers)
    return service, store, actor, target


def owner(actor):
    actor.human = HumanIdentity("ha_joiner", False, True, False)
    return actor.human


def evidence(store):
    with store._connection() as connection:
        return tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("receipts", "audit", "outbox")
        )


@pytest.mark.parametrize("role", list(Role))
def test_every_active_profile_can_change_its_own_alias_and_preferences_by_default(tmp_path, role):
    service, store, actor, target = fixture(tmp_path, role=role)
    human = owner(actor)
    public = service.update_alias("alias", AliasUpdate(target, 1, "  <b>Literal</b>  "))
    private = service.update_preferences(
        "preferences", PreferencesUpdate(1, MemberLocale.SPANISH, False)
    )
    assert public.command.action == ALIAS_ACTION and private.command.action == PREFERENCES_ACTION
    assert public.command.actor_id == private.command.actor_id == "ha_joiner"
    queries = HouseholdAdministrationQueries(store, human)
    assert queries.presentation(target) == MemberPresentation(target, "home", "<b>Literal</b>", 2)
    assert queries.preferences() == MemberPreferences(
        target, "home", MemberLocale.SPANISH, False, 2
    )
    assert private.result.decode()["notification_delivery"] == "unavailable"


def test_administrator_alias_edit_of_pending_member_preserves_membership_and_private_state(
    tmp_path,
):
    service, store, actor, target = fixture(tmp_path, active=False)
    with store.read() as unit:
        original = unit.members.get("home", target)
        preferences = unit.preferences.get("home", target)
    service.update_alias("pending-alias", AliasUpdate(target, 1, "Pending alias"))
    with store.read() as unit:
        assert unit.members.get("home", target) == original
        assert unit.preferences.get("home", target) == preferences
    assert original.status is MemberStatus.PENDING
    assert HouseholdAdministrationQueries(store, actor.human).preferences().member_id != target


@pytest.mark.parametrize("kind", ["alias", "preferences"])
def test_replay_retains_original_result_after_another_authorized_change(tmp_path, kind):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    first = (
        AliasUpdate(target, 1, "First") if kind == "alias" else PreferencesUpdate(1, None, False)
    )
    second = (
        AliasUpdate(target, 2, "Later")
        if kind == "alias"
        else PreferencesUpdate(2, MemberLocale.ENGLISH, True)
    )
    method = service.update_alias if kind == "alias" else service.update_preferences
    saved = method("original", first)
    method("later", second)
    before = evidence(store)
    assert method("original", first) == saved
    original = HouseholdQueries(store, human).operation(saved.operation_id).receipt
    assert original.result == saved.result and evidence(store) == before
    with pytest.raises(Conflict, match="idempotency_conflict"):
        method("original", second)
    assert evidence(store) == before


@pytest.mark.parametrize("locale", [None, MemberLocale.ENGLISH, MemberLocale.SPANISH])
@pytest.mark.parametrize("summaries", [True, False])
def test_private_values_and_inferable_fingerprints_never_reach_shared_audit_or_events(
    tmp_path, locale, summaries
):
    service, store, actor, _ = fixture(tmp_path)
    owner(actor)
    receipt = service.update_preferences("private", PreferencesUpdate(1, locale, summaries))
    result = receipt.result.decode()
    assert result["locale"] == (locale.value if locale is not None else None)
    assert result["routine_participation_summaries"] is summaries
    forbidden = {
        "locale",
        "routine_participation_summaries",
        "preferences",
        "request",
        "result",
        "payload_fingerprint",
        "result_fingerprint",
    }
    with store.read() as unit:
        entries = [
            entry.detail for entry in unit.audit.entries("home") if entry.command == receipt.command
        ]
        events = [
            event.payload
            for event in unit.outbox.pending()
            if event.event_id == receipt.operation_id
        ]
    for document in (*entries, *events):
        assert forbidden.isdisjoint(document.decode())
        assert receipt.payload_fingerprint not in document.encoded
        assert receipt.result.fingerprint not in document.encoded
        assert "member_id" in document.decode() and "revision" in document.decode()


def test_another_administrator_cannot_recover_owner_private_original_even_with_operation_id(
    tmp_path,
):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    saved = service.update_preferences("private", PreferencesUpdate(1, MemberLocale.SPANISH, False))
    assert HouseholdQueries(store, human).operation(saved.operation_id).receipt == saved
    administrator = HumanIdentity("ha_admin", True, True, False)
    with pytest.raises(NotFound, match="operation_missing"):
        HouseholdQueries(store, administrator).operation(saved.operation_id)
    assert HouseholdAdministrationQueries(store, administrator).preferences().member_id != target
    assert "member_id" not in asdict(PreferencesUpdate(1, None, True))
    assert "household_id" not in asdict(PreferencesUpdate(1, None, True))


@pytest.mark.parametrize("kind", ["alias", "preferences"])
def test_current_owner_permission_precedes_original_replay_and_lookup(tmp_path, kind):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    request = (
        AliasUpdate(target, 1, "Alias") if kind == "alias" else PreferencesUpdate(1, None, False)
    )
    method = service.update_alias if kind == "alias" else service.update_preferences
    receipt = method("original", request)
    with store.write() as unit:
        current = unit.members.get("home", target)
        unit.members.save(
            replace(
                current,
                revision=current.revision + 1,
                exceptions=(PermissionRule(Permission.PREFERENCES_WRITE, False),),
            ),
            current.revision,
        )
    before = evidence(store)
    for action in (
        lambda: method("original", request),
        lambda: HouseholdQueries(store, human).operation(receipt.operation_id),
    ):
        with pytest.raises(Forbidden, match="permission_denied"):
            action()
    assert evidence(store) == before


@pytest.mark.parametrize(
    "status", [MemberStatus.PENDING, MemberStatus.SUSPENDED, MemberStatus.ARCHIVED]
)
def test_inactive_owners_cannot_read_or_mutate_profiles(tmp_path, status):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    with store.write() as unit:
        current = unit.members.get("home", target)
        unit.members.save(
            replace(current, status=status, revision=current.revision + 1), current.revision
        )
    queries = HouseholdAdministrationQueries(store, human)
    before = evidence(store)
    for action in (
        lambda: queries.preferences(),
        lambda: queries.presentation(target),
        lambda: service.update_alias("alias", AliasUpdate(target, 1, "Alias")),
        lambda: service.update_preferences("prefs", PreferencesUpdate(1, None, False)),
    ):
        with pytest.raises(Forbidden):
            action()
    assert evidence(store) == before


def test_ordinary_owner_cannot_change_another_members_alias_or_cross_household_scope(tmp_path):
    service, store, actor, _ = fixture(tmp_path)
    human = owner(actor)
    with store.read() as unit:
        administrator = unit.members.by_user("home", "ha_admin")
    for action in (
        lambda: service.update_alias("other", AliasUpdate(administrator.member_id, 1, "Forged")),
        lambda: replace(service, household_id="other").update_preferences(
            "other", PreferencesUpdate(1, None, False)
        ),
        lambda: HouseholdAdministrationQueries(store, human, "other").preferences(),
    ):
        with pytest.raises(Forbidden):
            action()


def test_source_outage_blocks_changes_while_an_authorized_local_query_is_read_only(tmp_path):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    actor.error = IdentityUnavailable("ha_unavailable")
    before = store.path.read_bytes()
    assert HouseholdAdministrationQueries(store, human).preferences() == MemberPreferences(
        target, "home"
    )
    with pytest.raises(IdentityUnavailable):
        service.update_preferences("prefs", PreferencesUpdate(1, None, False))
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("kind", ["alias", "preferences"])
def test_late_actual_outbox_failure_rolls_back_profile_receipt_and_audit_together(tmp_path, kind):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)

    class FailingTransactions:
        def read(self):
            return store.read()

        @contextmanager
        def write(self):
            with store.write() as unit:
                unit.members.connection.execute(
                    "CREATE TRIGGER fail_event BEFORE INSERT ON outbox "
                    "BEGIN SELECT RAISE(ABORT,'sensitive private fixture'); END"
                )
                yield unit

    service = replace(service, transactions=FailingTransactions())
    before = evidence(store)
    with pytest.raises(StorageFailure, match="^storage_failure$"):
        if kind == "alias":
            service.update_alias("alias", AliasUpdate(target, 1, "Alias"))
        else:
            service.update_preferences("private", PreferencesUpdate(1, MemberLocale.SPANISH, False))
    queries = HouseholdAdministrationQueries(store, human)
    assert queries.preferences() == MemberPreferences(target, "home")
    assert queries.presentation(target) == MemberPresentation(target, "home")
    assert evidence(store) == before


@pytest.mark.parametrize("kind", ["alias", "preferences"])
def test_real_independent_writers_have_one_revision_winner_and_one_original_receipt(tmp_path, kind):
    service, store, actor, target = fixture(tmp_path)
    owner(actor)
    barrier = Barrier(2, timeout=5)
    before = evidence(store)

    def attempt(number):
        request = (
            AliasUpdate(target, 1, str(number))
            if kind == "alias"
            else PreferencesUpdate(1, None, bool(number))
        )
        barrier.wait()
        try:
            method = service.update_alias if kind == "alias" else service.update_preferences
            return method(f"race-{number}", request)
        except Conflict as error:
            assert error.code == "revision_conflict"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))
    assert sum(result is not None for result in results) == 1
    assert evidence(store) == tuple(count + 1 for count in before)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_revision", True),
        ("expected_revision", 0),
        ("expected_revision", 1.0),
        ("expected_revision", 2**63),
        ("alias", ""),
        ("alias", "x\n"),
        ("alias", "x" * 81),
        ("alias", "\ud800"),
        ("member_id", "../other"),
    ],
)
def test_alias_request_reuses_closed_domain_bounds(field, value):
    values = {"member_id": "member", "expected_revision": 1, "alias": "Alias", field: value}
    with pytest.raises(InvalidInput):
        AliasUpdate(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_revision", False),
        ("expected_revision", -1),
        ("expected_revision", 1.0),
        ("expected_revision", 2**63),
        ("locale", "es"),
        ("locale", "future"),
        ("routine_participation_summaries", 0),
        ("routine_participation_summaries", "false"),
    ],
)
def test_preferences_request_rejects_ambiguous_values(field, value):
    values = {
        "expected_revision": 1,
        "locale": None,
        "routine_participation_summaries": True,
        field: value,
    }
    with pytest.raises(InvalidInput):
        PreferencesUpdate(**values)


@pytest.mark.parametrize("change", ["actor", "action", "unknown", "private_subject"])
def test_profile_command_authorization_binds_exact_proven_actor_and_registered_action(
    tmp_path, change
):
    _, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    action = "unknown" if change == "unknown" else PREFERENCES_ACTION
    subject = target if change == "private_subject" else None
    authorization = ProfileAuthorization(human, action, subject)
    command = CommandKey(
        "home",
        "forged" if change == "actor" else human.ha_user_id,
        ALIAS_ACTION if change == "action" else action,
        "key",
    )
    with pytest.raises(Forbidden):
        with store.read() as unit:
            authorization.require(command, unit)


def test_missing_public_subject_and_revoked_private_read_fail_without_initializing_records(
    tmp_path,
):
    _, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    queries = HouseholdAdministrationQueries(store, human)
    before = store.path.read_bytes()
    with pytest.raises(NotFound, match="member_missing"):
        queries.presentation("missing")
    assert store.path.read_bytes() == before
    with store.write() as unit:
        current = unit.members.get("home", target)
        unit.members.save(
            replace(
                current,
                revision=current.revision + 1,
                exceptions=(PermissionRule(Permission.PREFERENCES_READ, False),),
            ),
            current.revision,
        )
    with pytest.raises(Forbidden):
        queries.preferences()


@pytest.mark.parametrize("kind", ["alias", "preferences"])
def test_wrong_original_subject_is_not_disclosed_by_profile_operation_lookup(tmp_path, kind):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    saved = (
        service.update_alias("save", AliasUpdate(target, 1, "Alias"))
        if kind == "alias"
        else service.update_preferences("save", PreferencesUpdate(1, None, False))
    )
    with store._connection() as connection:
        result = saved.result.decode()
        result["member_id"] = "other-member"
        connection.execute(
            "UPDATE receipts SET result=? WHERE operation_id=?",
            (JsonDocument.from_value(result).encoded, saved.operation_id),
        )
    with pytest.raises(Forbidden):
        HouseholdQueries(store, human).operation(saved.operation_id)


def test_explicit_null_clears_public_alias_without_changing_private_preferences(tmp_path):
    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    service.update_alias("set", AliasUpdate(target, 1, "Before"))
    service.update_alias("clear", AliasUpdate(target, 2, None))
    queries = HouseholdAdministrationQueries(store, human)
    assert queries.presentation(target) == MemberPresentation(target, "home", None, 3)
    assert queries.preferences() == MemberPreferences(target, "home")


def test_acknowledged_technical_event_is_not_notification_delivery(tmp_path):
    service, store, actor, _ = fixture(tmp_path)
    human = owner(actor)
    saved = service.update_preferences("save", PreferencesUpdate(1, None, True))
    with store.write() as unit:
        assert unit.outbox.acknowledge(saved.operation_id)
    view = HouseholdQueries(store, human).operation(saved.operation_id)
    assert view.delivered and view.receipt.result.decode()["notification_delivery"] == "unavailable"


def test_authorized_admin_missing_alias_subject_produces_no_partial_command(tmp_path):
    service, store, _, _ = fixture(tmp_path)
    before = evidence(store)
    with pytest.raises(Conflict, match="member_missing"):
        service.update_alias("missing", AliasUpdate("missing", 1, "Alias"))
    assert evidence(store) == before


@pytest.mark.parametrize("kind", ["alias", "preferences"])
def test_permission_loss_after_fresh_source_proof_is_rechecked_in_the_writer(tmp_path, kind):
    service, store, actor, target = fixture(tmp_path)
    owner(actor)

    class RevokingTransactions:
        def read(self):
            return store.read()

        @contextmanager
        def write(self):
            # Controlled independent writer: the grant changes after source proof.
            with store.write() as unit:
                current = unit.members.get("home", target)
                unit.members.save(
                    replace(
                        current,
                        revision=current.revision + 1,
                        exceptions=(PermissionRule(Permission.PREFERENCES_WRITE, False),),
                    ),
                    current.revision,
                )
            with store.write() as unit:
                yield unit

    service = replace(service, transactions=RevokingTransactions())
    before = evidence(store)
    with pytest.raises(Forbidden):
        if kind == "alias":
            service.update_alias("alias", AliasUpdate(target, 1, "Denied"))
        else:
            service.update_preferences("preferences", PreferencesUpdate(1, None, False))
    assert evidence(store) == before
    with store.read() as unit:
        assert unit.presentations.get("home", target) == MemberPresentation(target, "home")
        assert unit.preferences.get("home", target) == MemberPreferences(target, "home")


@pytest.mark.parametrize("has_policy", [True, False])
def test_unlinked_or_unconfigured_identity_cannot_gain_profile_authority(tmp_path, has_policy):
    service, store, actor, target = fixture(tmp_path)
    if has_policy:
        actor.human = HumanIdentity("unlinked_ha_admin", True, True, False)
    else:
        with store._connection() as connection:
            connection.execute("DELETE FROM household_policy")
    before = evidence(store)
    for action in (
        lambda: service.update_alias("alias", AliasUpdate(target, 1, "Denied")),
        lambda: HouseholdAdministrationQueries(store, actor.human).preferences(),
    ):
        with pytest.raises(Forbidden):
            action()
    assert evidence(store) == before


@pytest.mark.parametrize("subject", [None, False, "../unsafe", ""])
def test_malformed_original_profile_subject_fails_without_disclosing_result(tmp_path, subject):
    service, store, actor, _ = fixture(tmp_path)
    human = owner(actor)
    receipt = service.update_preferences("save", PreferencesUpdate(1, MemberLocale.SPANISH, False))
    with store._connection() as connection:
        result = receipt.result.decode()
        result["member_id"] = subject
        connection.execute(
            "UPDATE receipts SET result=? WHERE operation_id=?",
            (JsonDocument.from_value(result).encoded, receipt.operation_id),
        )
    with pytest.raises(StorageFailure, match="^invalid_operation_record$"):
        HouseholdQueries(store, human).operation(receipt.operation_id)


@pytest.mark.parametrize("field,value", [("household_id", "other"), ("actor_id", "other")])
def test_original_profile_guard_rejects_another_command_namespace(tmp_path, field, value):
    service, store, actor, _ = fixture(tmp_path)
    human = owner(actor)
    receipt = service.update_preferences("save", PreferencesUpdate(1, None, False))
    wrong = replace(receipt, command=replace(receipt.command, **{field: value}))
    with pytest.raises(Forbidden):
        with store.read() as unit:
            require_profile_original(unit, human, "home", wrong)


def test_missing_preference_repository_result_cannot_initialize_or_disclose_defaults(
    tmp_path, monkeypatch
):
    from domus.infrastructure.sqlite_member_profiles import SQLitePreferences

    service, store, actor, _ = fixture(tmp_path)
    human = owner(actor)
    monkeypatch.setattr(SQLitePreferences, "get", lambda *_: None)
    before = evidence(store)
    for action in (
        lambda: service.update_preferences("save", PreferencesUpdate(1, None, False)),
        lambda: HouseholdAdministrationQueries(store, human).preferences(),
    ):
        with pytest.raises(StorageFailure, match="invalid_member_profile_record"):
            action()
    assert evidence(store) == before


def test_admin_alias_authority_never_overrides_revoked_private_preference_authority(tmp_path):
    service, store, actor, target = fixture(tmp_path, role=Role.ADMINISTRATOR)
    owner(actor)
    with store.write() as unit:
        current = unit.members.get("home", target)
        unit.members.save(
            replace(
                current,
                revision=current.revision + 1,
                exceptions=(PermissionRule(Permission.PREFERENCES_WRITE, False),),
            ),
            current.revision,
        )
    service.update_alias("public", AliasUpdate(target, 1, "Administrator alias"))
    with pytest.raises(Forbidden):
        service.update_preferences("private", PreferencesUpdate(1, None, False))


@pytest.mark.parametrize("kind", ["alias", "preferences"])
def test_actual_restoration_retains_private_original_without_recreating_absent_profile_effect(
    tmp_path, kind
):
    from contextlib import closing

    from test_activation_compatibility import identity_at
    from test_sqlite_snapshots import Clock

    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations
    from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

    service, store, actor, target = fixture(tmp_path)
    human = owner(actor)
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    (root / "domus.sqlite3").write_bytes(store.path.read_bytes())
    (root / "domus.sqlite3").chmod(0o600)
    identity_at(root, store.installation)
    with closing(open_storage(root, "edge")) as storage:
        service = replace(service, transactions=storage.database)
        archive = tmp_path / "snapshot"
        checkpoint = SQLiteSnapshots(
            storage.database, archive, storage.installation, Clock()
        ).create("before")
        request = (
            AliasUpdate(target, 1, "After")
            if kind == "alias"
            else PreferencesUpdate(1, MemberLocale.SPANISH, False)
        )
        method = service.update_alias if kind == "alias" else service.update_preferences
        saved = method("original", request)
        prepared = tmp_path / "prepared"
        SQLiteRestorations(
            storage.database, archive, prepared, storage.installation, Clock(), checkpoint
        ).prepare("restore-profile")
    result = SQLiteActivation(root, store.installation, Clock(), prepared).activate()
    assert result.state == "active"
    with closing(open_storage(root, "edge")) as selected:
        service = replace(service, transactions=selected.database)
        method = service.update_alias if kind == "alias" else service.update_preferences
        before = evidence(selected.database)
        replay = method("original", request)
        assert replay.historical and replay.result == saved.result
        lookup = HouseholdQueries(selected.database, human).operation(saved.operation_id)
        assert lookup.receipt.historical and lookup.receipt.result == saved.result
        # The real restored receipt retains historical/absent wording at the wire boundary.
        from domus.entrypoints.administration_http import _profile_receipt

        response = _profile_receipt(lookup.receipt)
        assert response.state == "historical"
        assert "absent" in response.message and response.notification_delivery == "unavailable"
        queries = HouseholdAdministrationQueries(selected.database, human)
        assert queries.preferences() == MemberPreferences(target, "home")
        assert queries.presentation(target) == MemberPresentation(target, "home")
        assert evidence(selected.database) == before
        with pytest.raises(NotFound):
            HouseholdQueries(
                selected.database, HumanIdentity("ha_admin", True, True, False)
            ).operation(saved.operation_id)


def test_original_key_lookup_recovers_a_lost_operation_id_without_sending_a_mutation(tmp_path):
    service, store, actor, _ = fixture(tmp_path)
    human = owner(actor)
    saved = service.update_preferences("original-key", PreferencesUpdate(1, None, False))
    before = evidence(store)
    queries = HouseholdQueries(store, human)
    assert queries.administration_request(PREFERENCES_ACTION, "original-key").receipt == saved
    with pytest.raises(NotFound, match="operation_missing"):
        queries.administration_request(PREFERENCES_ACTION, "unreceived-key")
    assert evidence(store) == before


@pytest.mark.parametrize(
    "action", ["household.setup", "member.enroll", "recovery.request", "unknown"]
)
def test_administration_key_lookup_cannot_widen_the_entry_recovery_contract(tmp_path, action):
    _, store, actor, _ = fixture(tmp_path)
    before = evidence(store)
    with pytest.raises(Forbidden):
        HouseholdQueries(store, actor.human).administration_request(action, "key")
    assert evidence(store) == before


def test_identical_private_keys_remain_scoped_to_the_verified_actor(tmp_path):
    service, store, actor, _ = fixture(tmp_path)
    human = owner(actor)
    first = service.update_preferences(
        "same-key", PreferencesUpdate(1, MemberLocale.SPANISH, False)
    )
    administrator = HumanIdentity("ha_admin", True, True, False)
    actor.human = administrator
    second = service.update_preferences(
        "same-key", PreferencesUpdate(1, MemberLocale.ENGLISH, True)
    )
    assert (
        HouseholdQueries(store, human)
        .administration_request(PREFERENCES_ACTION, "same-key")
        .receipt
        == first
    )
    assert (
        HouseholdQueries(store, administrator)
        .administration_request(PREFERENCES_ACTION, "same-key")
        .receipt
        == second
    )
