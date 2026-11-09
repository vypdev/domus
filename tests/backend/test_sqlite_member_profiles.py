"""Real member profile records, genuine historical migrations and independent inspection."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from test_sqlite_identity import member, store_at
from test_sqlite_snapshots import Clock

from domus.domain.errors import Conflict, DatabaseRejected, InvalidInput, StorageFailure
from domus.domain.identity import MemberStatus
from domus.domain.member_profiles import MemberLocale, MemberPreferences, MemberPresentation
from domus.domain.storage import Installation
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

FIXTURES = Path(__file__).parents[1] / "fixtures/sqlite"


def prepared(tmp_path):
    store = store_at(tmp_path / "database")
    with store.write() as unit:
        unit.members.save(member(), 0)
    return store


def frozen(tmp_path, version=8):
    path = tmp_path / "database"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.executescript((FIXTURES / f"v{version}.sql").read_text())
        identity = connection.execute("SELECT instance_id,channel FROM installation").fetchone()
    return SQLiteDatabase(path, Installation(*identity))


def facts(path, tables):
    with closing(sqlite3.connect(path)) as connection:
        originals = {"households": "household_id,singleton,name,time_zone,revision"}
        return {
            table: connection.execute(
                f'SELECT {originals.get(table, "*")} FROM "{table}" ORDER BY rowid'
            ).fetchall()
            for table in tables
        }


def test_created_member_has_persisted_independent_public_and_private_defaults(tmp_path):
    store = prepared(tmp_path)
    restarted = SQLiteDatabase(store.path, store.installation)
    restarted.initialize(require_existing=True)
    with restarted.read() as unit:
        assert unit.presentations.get("home", "member_1") == MemberPresentation("member_1", "home")
        assert unit.preferences.get("home", "member_1") == MemberPreferences("member_1", "home")
        for repository in (unit.presentations, unit.preferences):
            assert repository.get("other", "member_1") is None
            assert repository.get("home", "missing") is None
    with closing(sqlite3.connect(store.path)) as connection:
        public = connection.execute("SELECT * FROM member_presentations").fetchone()
        private = connection.execute("SELECT * FROM member_preferences").fetchone()
        assert public == ("member_1", "home", None, 1)
        assert private == ("member_1", "home", None, 1, 1)


@pytest.mark.parametrize("alias", [None, "🧹" * 80, "e\u0301", "<script>literal</script>"])
def test_alias_round_trip_retains_literal_text_and_cannot_relink_identity(tmp_path, alias):
    store = prepared(tmp_path)
    value = MemberPresentation("member_1", "home", alias, 2)
    with store.write() as unit:
        unit.presentations.save(value, 1)
    with SQLiteDatabase(store.path, store.installation).read() as unit:
        assert unit.presentations.get("home", "member_1") == value
        assert unit.members.get("home", "member_1") == member()
        assert unit.preferences.get("home", "member_1") == MemberPreferences("member_1", "home")


@pytest.mark.parametrize("locale", [None, MemberLocale.ENGLISH, MemberLocale.SPANISH])
@pytest.mark.parametrize("summaries", [False, True])
def test_owner_private_preferences_round_trip_without_creating_shared_evidence(
    tmp_path, locale, summaries
):
    store = prepared(tmp_path)
    value = MemberPreferences("member_1", "home", locale, summaries, 2)
    with store.write() as unit:
        unit.preferences.save(value, 1)
    with SQLiteDatabase(store.path, store.installation).read() as unit:
        assert unit.preferences.get("home", "member_1") == value
        assert unit.presentations.get("home", "member_1") == MemberPresentation("member_1", "home")
        assert unit.members.get("home", "member_1") == member()
        assert unit.audit.entries("home") == unit.outbox.pending() == ()


@pytest.mark.parametrize("kind", ["presentations", "preferences"])
def test_profile_compare_and_swap_is_independent_scoped_and_has_one_winner(tmp_path, kind):
    store = prepared(tmp_path)
    other = SQLiteDatabase(store.path, store.installation)
    with store.read() as unit:
        original = getattr(unit, kind).get("home", "member_1")
    changed = replace(original, revision=2)
    with store.write() as unit:
        getattr(unit, kind).save(changed, 1)
    for value, expected in [
        (original, 1),
        (changed, 1),
        (replace(changed, revision=4), 2),
        (replace(changed, household_id="other", revision=3), 2),
        (replace(changed, member_id="missing", revision=3), 2),
    ]:
        with pytest.raises(Conflict, match="revision_conflict"):
            with other.write() as unit:
                getattr(unit, kind).save(value, expected)
    with other.write() as unit:
        unit.members.save(replace(member(), status=MemberStatus.ARCHIVED, revision=2), 1)
    with other.read() as unit:
        assert getattr(unit, kind).get("home", "member_1") == changed


@pytest.mark.parametrize("kind", ["presentations", "preferences"])
@pytest.mark.parametrize("revision", [True, 0, -1, 1.0, None, 2**63])
def test_profile_repositories_reject_invalid_expected_revision_before_sql(tmp_path, kind, revision):
    store = prepared(tmp_path)
    with pytest.raises(InvalidInput, match="invalid_revision"):
        with store.write() as unit:
            value = getattr(unit, kind).get("home", "member_1")
            getattr(unit, kind).save(replace(value, revision=2), revision)


def test_profile_and_member_creation_roll_back_after_late_command_failure(tmp_path):
    store = store_at(tmp_path / "database")
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute(
            "CREATE TRIGGER fail_private BEFORE INSERT ON member_preferences "
            "BEGIN SELECT RAISE(ABORT,'injected private insert failure'); END"
        )
    # Normal inspection rejects an unrelated trigger before entering a writer.
    with pytest.raises(DatabaseRejected):
        with store.write():
            pytest.fail("An extra trigger must not authorize a current transaction")
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("DROP TRIGGER fail_private")
    with pytest.raises(RuntimeError, match="injected"):
        with store.write() as unit:
            unit.members.save(member(), 0)
            unit.presentations.save(MemberPresentation("member_1", "home", "Alias", 2), 1)
            unit.preferences.save(
                MemberPreferences("member_1", "home", MemberLocale.SPANISH, False, 2), 1
            )
            raise RuntimeError("injected after all profile writes")
    with store.read() as unit:
        assert unit.members.list("home") == ()
        assert unit.presentations.get("home", "member_1") is None
        assert unit.preferences.get("home", "member_1") is None


def test_actual_private_insert_failure_rolls_back_member_and_public_insert_together(tmp_path):
    store = store_at(tmp_path / "database")
    with pytest.raises(StorageFailure, match="storage_failure"):
        with store.write() as unit:
            unit.members.connection.execute(
                "CREATE TRIGGER fail_private BEFORE INSERT ON member_preferences "
                "BEGIN SELECT RAISE(ABORT,'private fault must not escape'); END"
            )
            unit.members.save(member(), 0)
    with store.read() as unit:
        assert unit.members.list("home") == ()
        assert unit.presentations.get("home", "member_1") is None
        assert unit.preferences.get("home", "member_1") is None


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("member_presentations", "alias", " "),
        ("member_presentations", "alias", " untrimmed"),
        ("member_presentations", "alias", "x\n"),
        ("member_presentations", "alias", "x" * 81),
        ("member_presentations", "alias", b"not text"),
        ("member_presentations", "revision", 0),
        ("member_presentations", "revision", 1.5),
        ("member_preferences", "locale", "fr"),
        ("member_preferences", "locale", b"en"),
        ("member_preferences", "routine_participation_summaries", 2),
        ("member_preferences", "routine_participation_summaries", -1),
        ("member_preferences", "routine_participation_summaries", "true"),
        ("member_preferences", "routine_participation_summaries", 0.5),
        ("member_preferences", "revision", 0),
        ("member_preferences", "revision", "not a revision"),
    ],
)
def test_corrupt_profile_is_rejected_on_use_and_independent_checkpoint_inspection(
    tmp_path, table, column, value
):
    store = prepared(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(f"UPDATE {table} SET {column}=?", (value,))
    kind = "presentations" if table == "member_presentations" else "preferences"
    with pytest.raises(StorageFailure, match="invalid_member_profile_record"):
        with store.read() as unit:
            getattr(unit, kind).get("home", "member_1")
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock()).create("invalid")
    assert not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize(
    "kind,table", [("presentations", "member_presentations"), ("preferences", "member_preferences")]
)
def test_missing_profile_cannot_be_silently_recreated_as_a_default(tmp_path, kind, table):
    store = prepared(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute(f"DELETE FROM {table}")
    with pytest.raises(StorageFailure, match="invalid_member_profile_record"):
        with store.read() as unit:
            getattr(unit, kind).get("home", "member_1")
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_records"):
        SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock()).create("invalid")


@pytest.mark.parametrize(
    "kind,table", [("presentations", "member_presentations"), ("preferences", "member_preferences")]
)
def test_existing_orphan_profile_is_not_disclosed_repaired_or_accepted_as_a_snapshot(
    tmp_path, kind, table
):
    store = prepared(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(f"UPDATE {table} SET member_id='orphan'")
        assert connection.execute("PRAGMA foreign_key_check").fetchall()
    before = store.path.read_bytes()
    with store.read() as unit:
        assert getattr(unit, kind).get("home", "orphan") is None
    with pytest.raises(StorageFailure, match="invalid_member_profile_record"):
        with store.read() as unit:
            getattr(unit, kind).get("home", "member_1")
    with pytest.raises(DatabaseRejected, match="invalid_snapshot_database"):
        SQLiteSnapshots(store, tmp_path / "snapshot", store.installation, Clock()).create("invalid")
    assert not (tmp_path / "snapshot").exists()
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("version", range(1, 9))
def test_real_historical_input_upgrade_preserves_every_original_table_and_adds_defaults(
    tmp_path, version
):
    store = frozen(tmp_path, version)
    with store._connection() as connection:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
    original = facts(store.path, tables)
    before = store.path.read_bytes()
    for transaction in (store.read, store.write):
        with pytest.raises(DatabaseRejected, match="unsupported_schema"):
            with transaction():
                pytest.fail("Old schema must be migrated explicitly")
    assert store.path.read_bytes() == before
    store.initialize(require_existing=True)
    store.initialize(require_existing=True)
    actual = facts(store.path, tables)
    if version == 5:
        # The already-supported schema6 transition adds empty material snapshots.
        # All other fields and all original operation/history bytes must be unchanged.
        for table in ("task_definitions", "task_occurrences"):
            old_rows, new_rows = original.pop(table), actual.pop(table)
            assert len(old_rows) == len(new_rows)
            for old, new in zip(old_rows, new_rows, strict=True):
                assert old[:-1] == new[:-1]
                expected = json.loads(old[-1])
                assert expected["version"] == 1
                expected["version"] = 2
                if table == "task_definitions":
                    expected["materials"] = []
                else:
                    assert expected["definition_snapshot"]["version"] == 1
                    expected["definition_snapshot"].update(version=2, materials=[])
                assert json.loads(new[-1]) == expected
    assert actual == original
    if version < 8:
        recurrence_tables = (
            "recurrence_rules",
            "recurrence_progress",
            "recurrence_slots",
            "recurrence_frontiers",
            "recurrence_progress_evidence",
            "recurrence_relative_slots",
        )
        assert facts(store.path, recurrence_tables) == {table: [] for table in recurrence_tables}
    with store.read() as unit:
        for household in original["households"]:
            for current in unit.members.list(household[0]):
                assert unit.presentations.get(
                    current.household_id, current.member_id
                ) == MemberPresentation(current.member_id, current.household_id)
                assert unit.preferences.get(
                    current.household_id, current.member_id
                ) == MemberPreferences(current.member_id, current.household_id)
    with store._connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_schema8_fixture_is_the_exact_original_published_source_dump():
    assert hashlib.sha256((FIXTURES / "v8.sql").read_bytes()).hexdigest() == (
        "041615f0253c0537ac6c713e10a8984fb5043b1f6df29a6a2c7193824ebc6ed5"
    )


@pytest.mark.parametrize("version", range(1, 9))
def test_late_profile_migration_failure_restores_exact_original_bytes(
    tmp_path, monkeypatch, version
):
    from domus.infrastructure import sqlite as adapter

    store = frozen(tmp_path, version)
    before = store.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "PROFILE_STATEMENTS", (*adapter.PROFILE_STATEMENTS, "INVALID SQL"))
        with pytest.raises(StorageFailure, match="storage_failure"):
            store.initialize(require_existing=True)
    assert store.path.read_bytes() == before
    store.initialize(require_existing=True)


def test_schema9_version_on_unmigrated_schema8_does_not_authorize_profile_use(tmp_path):
    store = frozen(tmp_path)
    with store._connection() as connection:
        connection.execute("PRAGMA user_version=9")
    before = store.path.read_bytes()
    for transaction in (store.read, store.write):
        with pytest.raises(DatabaseRejected, match="unsupported_schema"):
            with transaction():
                pytest.fail("A changed version number is not a schema upgrade")
    assert store.path.read_bytes() == before


def test_snapshot_independently_preserves_both_profiles_without_changing_member_history(tmp_path):
    store = prepared(tmp_path)
    public = MemberPresentation("member_1", "home", "Alias", 2)
    private = MemberPreferences("member_1", "home", MemberLocale.SPANISH, False, 2)
    with store.write() as unit:
        unit.presentations.save(public, 1)
        unit.preferences.save(private, 1)
    archive = tmp_path / "snapshot"
    snapshots = SQLiteSnapshots(store, archive, store.installation, Clock())
    checkpoint = snapshots.create("original")
    assert checkpoint.schema_version == 14 and snapshots.inspect() == checkpoint
    with SQLiteDatabase(archive / "domus.sqlite3", store.installation).read() as unit:
        assert unit.presentations.get("home", "member_1") == public
        assert unit.preferences.get("home", "member_1") == private
        assert unit.members.get("home", "member_1") == member()


@pytest.mark.parametrize("kind", ["presentations", "preferences"])
def test_concurrent_independent_writers_cannot_overwrite_the_same_profile_revision(tmp_path, kind):
    store = prepared(tmp_path)
    gate = Barrier(2, timeout=5)

    def attempt(number):
        writer = SQLiteDatabase(store.path, store.installation)
        with writer.read() as unit:
            before = getattr(unit, kind).get("home", "member_1")
        change = (
            replace(before, alias=f"Choice {number}", revision=2)
            if kind == "presentations"
            else replace(before, routine_participation_summaries=bool(number), revision=2)
        )
        gate.wait()
        try:
            with writer.write() as unit:
                getattr(unit, kind).save(change, before.revision)
            return change
        except Conflict as error:
            assert error.code == "revision_conflict"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    with store.read() as unit:
        assert getattr(unit, kind).get("home", "member_1") == winners[0]


@pytest.mark.parametrize("status", list(MemberStatus))
def test_all_membership_statuses_receive_explicit_defaults_without_changing_authority(
    tmp_path, status
):
    store = store_at(tmp_path / "database")
    original = replace(member(), status=status)
    with store.write() as unit:
        unit.members.save(original, 0)
    with store.read() as unit:
        assert unit.members.get("home", "member_1") == original
        assert unit.presentations.get("home", "member_1") == MemberPresentation("member_1", "home")
        assert unit.preferences.get("home", "member_1") == MemberPreferences("member_1", "home")


@pytest.mark.parametrize("table", ["member_presentations", "member_preferences"])
def test_profile_cannot_link_outside_the_canonical_member_household(tmp_path, table):
    store = prepared(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"UPDATE {table} SET household_id='another-household'")
    with store.read() as unit:
        assert unit.presentations.get("home", "member_1") == MemberPresentation("member_1", "home")
        assert unit.preferences.get("home", "member_1") == MemberPreferences("member_1", "home")


@pytest.mark.parametrize("table", ["member_presentations", "member_preferences"])
def test_sql_constraints_cannot_hide_an_unowned_profile_with_null_primary_key(tmp_path, table):
    store = prepared(tmp_path)
    with closing(sqlite3.connect(store.path, autocommit=True)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        placeholders = "?,?,?,?" if table == "member_presentations" else "?,?,?,?,?"
        values = (
            (None, "home", None, 1)
            if table == "member_presentations"
            else (None, "home", None, 1, 1)
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


def test_actual_generation_restore_keeps_checkpoint_profiles_and_the_unmodified_source(tmp_path):
    from test_household_commands import fixture as command_fixture

    from domus.application.household_commands import SetupHousehold
    from domus.infrastructure.owned_storage import open_storage
    from domus.infrastructure.sqlite_activation import SQLiteActivation
    from domus.infrastructure.sqlite_restoration import SQLiteRestorations

    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    storage = open_storage(root, "edge")
    commands, _, actor, _, _ = command_fixture(tmp_path / "unused")
    commands = replace(commands, transactions=storage.database)
    commands.setup("setup", SetupHousehold("Home", "UTC"))
    with storage.database.read() as unit:
        owner = unit.members.by_user("home", actor.current().ha_user_id)
    public = MemberPresentation(owner.member_id, "home", "Checkpoint alias", 2)
    private = MemberPreferences(owner.member_id, "home", MemberLocale.SPANISH, False, 2)
    with storage.database.write() as unit:
        unit.presentations.save(public, 1)
        unit.preferences.save(private, 1)
    archive = tmp_path / "snapshot"
    snapshot = SQLiteSnapshots(storage.database, archive, storage.installation, Clock()).create(
        "old"
    )
    with storage.database.write() as unit:
        unit.presentations.save(replace(public, alias="Later alias", revision=3), 2)
        unit.preferences.save(replace(private, locale=MemberLocale.ENGLISH, revision=3), 2)
    original = storage.database.path.read_bytes()
    target, installation = tmp_path / "prepared", storage.installation
    prepared_restore = SQLiteRestorations(
        storage.database, archive, target, installation, Clock(), snapshot
    ).prepare("restore-profiles")
    storage.close()
    result = SQLiteActivation(root, installation, Clock(), target).activate()
    assert result.state == "active" and result.record.prepared == prepared_restore
    with closing(open_storage(root, "edge")) as selected:
        assert selected.generation_id == "restore-profiles"
        with selected.database.read() as unit:
            assert unit.presentations.get("home", owner.member_id) == public
            assert unit.preferences.get("home", owner.member_id) == private
            assert unit.members.get("home", owner.member_id) == owner
    assert (root / "domus.sqlite3").read_bytes() == original
