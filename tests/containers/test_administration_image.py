"""Both actual CPU images preserve separate profiles in each owned deployment runtime."""

from pathlib import Path

import pytest
from test_app_image import docker
from test_app_image import image as image


@pytest.mark.parametrize("mode", ["native", "standalone"])
@pytest.mark.parametrize("starting_schema", [0, 8])
def test_current_image_persists_independent_profiles_in_owned_runtime(image, mode, starting_schema):
    historical = (
        (Path(__file__).parents[1] / "fixtures/sqlite/v8.sql").read_text()
        if starting_schema == 8
        else ""
    )
    result = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "65532:65532",
        "--entrypoint",
        "/app/.venv/bin/python",
        image,
        "-c",
        """
import sys, json, sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from domus.application.household_commands import HouseholdCommands, SetupHousehold
from domus.composition import ingress, server
from domus.domain.identity import HumanIdentity
from domus.domain.member_profiles import MemberLocale, MemberPresentation, MemberPreferences
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock, TimeZoneCatalog
from domus.infrastructure.sqlite import SQLiteDatabase, SCHEMA_VERSION
from domus.infrastructure.sqlite_snapshots import SQLiteSnapshots

assert SCHEMA_VERSION == 9
class Human:
    user_id = 'fictional_profile_ha_user'
    def current(self):
        return HumanIdentity(self.user_id, True, True, False)
    def get(self, user_id):
        raise AssertionError('No external directory subject is selected')

mode = sys.argv[1]
assert mode in ('native', 'standalone')
with TemporaryDirectory(prefix='domus-profile-image-') as directory:
    root = Path(directory) / 'owned'
    root.mkdir(mode=0o700)
    original = {}
    if sys.argv[2]:
        database = root / 'domus.sqlite3'
        with closing(sqlite3.connect(database, autocommit=True)) as connection:
            connection.executescript(sys.argv[2])
            assert connection.execute('PRAGMA user_version').fetchone()[0] == 8
            installation = connection.execute(
                'SELECT instance_id,channel FROM installation').fetchone()
            original = {
                row[0]: connection.execute('SELECT * FROM "' + row[0] + '" ORDER BY rowid')
                    .fetchall()
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            Human.user_id = original['members'][0][2]
        database.chmod(0o600)
        marker = root / 'installation.json'
        marker.write_text(json.dumps({'schema_version': 1, 'instance_id': installation[0],
            'channel': installation[1], 'state': 'ready'}))
        marker.chmod(0o600)
    def factory():
        if mode == 'native':
            return ingress.create_owned_runtime('fictional-token', 'edge', root,
                ('http://fictional-ha.local',))
        return server.create_owned_runtime('http://fictional-ha.local',
            'https://fictional-domus.example', 'edge', root)
    runtime = factory()
    try:
        storage = runtime.storage
        store = storage.database
        human, clock, ids = Human(), SystemClock(), SecureIdentifiers()
        if not original:
            HouseholdCommands(store, human, human, TimeZoneCatalog(), clock, ids).setup(
                'setup', SetupHousehold('Profile fixture', 'UTC'))
        else:
            with store._connection() as connection:
                for table, rows in original.items():
                    assert [tuple(row) for row in connection.execute(
                        'SELECT * FROM "' + table + '" ORDER BY rowid')] == rows
        with store.read() as unit:
            member = unit.members.by_user('home', human.current().ha_user_id)
            assert unit.presentations.get('home', member.member_id) == MemberPresentation(
                member.member_id, 'home')
            assert unit.preferences.get('home', member.member_id) == MemberPreferences(
                member.member_id, 'home')
        public = MemberPresentation(member.member_id, 'home', '<script>literal</script>', 2)
        private = MemberPreferences(member.member_id, 'home', MemberLocale.SPANISH, False, 2)
        with store.write() as unit:
            unit.presentations.save(public, 1)
            unit.preferences.save(private, 1)
        checkpoint = SQLiteSnapshots(store, Path(directory) / 'snapshot', storage.installation,
            clock).create('profile-checkpoint')
        assert checkpoint.schema_version == 9
        assert len(tuple((Path(directory) / 'snapshot').iterdir())) == 3
    finally:
        runtime.close()
    reopened = factory()
    try:
        with reopened.storage.database.read() as unit:
            assert unit.members.by_user('home', human.current().ha_user_id) == member
            assert unit.presentations.get('home', member.member_id) == public
            assert unit.preferences.get('home', member.member_id) == private
            assert len(unit.audit.entries('home')) == len(unit.outbox.pending()) == (
                len(original['receipts']) if original else 1)
        with SQLiteDatabase(Path(directory) / 'snapshot/domus.sqlite3',
            reopened.storage.installation).read() as unit:
            assert unit.presentations.get('home', member.member_id) == public
            assert unit.preferences.get('home', member.member_id) == private
    finally:
        reopened.close()
""",
        mode,
        historical,
    )
    assert result.returncode == 0, result.stdout + result.stderr
