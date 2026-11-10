"""Both actual CPU images preserve separate profiles in each owned deployment runtime."""

import json
import os
from pathlib import Path

import pytest
from test_app_image import data_volume as data_volume
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

assert SCHEMA_VERSION == 30
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
                    expected = rows
                    if table == 'households':
                        expected = [(*row, 60, "first_instant") for row in rows]
                    assert [tuple(row) for row in connection.execute(
                        'SELECT * FROM "' + table + '" ORDER BY rowid')] == expected
        with store.read() as unit:
            assert unit.households.current().materialization_horizon_days == 60
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
        assert checkpoint.schema_version == 30
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


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_current_image_composes_private_profile_http_without_a_second_login(image, mode):
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
import asyncio, sys
from pathlib import Path
from tempfile import TemporaryDirectory
import httpx
from domus.composition import ingress, server
from domus.domain.identity import HumanIdentity
from domus.domain.member_profiles import MemberLocale
from domus.infrastructure.ha_http import OAuthTokens

USER, OTHER = 'a' * 32, 'b' * 32
ORIGIN = 'https://fictional-domus.example'
class Source:
    actor = USER
    def __init__(self, endpoint):
        self.endpoint = endpoint
    def current_user(self, tokens):
        return self.directory_user('', self.actor)
    def directory_user(self, token, user_id):
        assert user_id in (USER, OTHER)
        return HumanIdentity(user_id, True, True, False)
    def directory_users(self, token, user_ids):
        return tuple(self.directory_user(token, user_id) for user_id in user_ids)
    def _request(self, token, operation):
        assert operation == 'config/auth/list'
        return [{'id': user, 'name': '<b>Same name</b>', 'is_active': True,
            'system_generated': False} for user in (USER, OTHER)]

class OAuth:
    def __init__(self, configuration):
        self.configuration = configuration
    def exchange(self, code, verifier):
        return OAuthTokens('fictional-access', 'fictional-refresh', 3600, 'homeassistant')
    def revoke(self, token):
        pass

mode = sys.argv[1]
assert mode in ('native', 'standalone')
ingress.HomeAssistantWebSocket = Source
server.HomeAssistantWebSocket = Source
server.HomeAssistantOAuth = OAuth

async def exercise(root):
    if mode == 'native':
        runtime = ingress.create_owned_runtime('fictional-supervisor', 'edge', root, (ORIGIN,))
        client_headers = {'X-Remote-User-Id': USER,
            'X-Ingress-Path': '/api/hassio_ingress/' + 'b' * 43,
            'Cookie': 'ingress_session=' + 'c' * 128}
    else:
        runtime = server.create_owned_runtime('http://fictional-ha.local', ORIGIN, 'edge', root)
        client_headers = {}
    try:
        transport = httpx.ASGITransport(app=runtime.app, client=('172.30.32.2', 12345))
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN,
                headers=client_headers) as client:
            def sign_in(user):
                Source.actor = user
                now = runtime.identity.clock.now()
                session = 'session-' + user
                runtime.identity.sign_in('fixture-code', 'v' * 43, session, now, now + 3600000)
                schemes = runtime.app.openapi()['components']['securitySchemes']
                cookie = schemes['DomusSession']['name']
                client.cookies.set(cookie, session)
            if mode == 'standalone':
                sign_in(USER)
            async def headers(key):
                response = await client.get('/api/v1/auth/csrf')
                assert response.status_code == 200, response.text
                return {'Origin': ORIGIN, 'X-CSRF-Token': response.json()['csrf_token'],
                    'Idempotency-Key': key}
            response = await client.post('/api/v1/household', json={
                'expected_revision': 0, 'name': 'API fixture', 'time_zone': 'UTC'},
                headers=await headers('setup'))
            assert response.status_code == 200, response.text
            base = '/api/v1/administration'
            capabilities = (await client.get(base + '/capabilities')).json()
            assert capabilities['contract_version'] == 2
            assert capabilities['household_id'] == 'home'
            assert capabilities['journal']['namespace'] == 'administration'
            original = (await client.get(base + '/preferences')).json()
            member = original['member_id']
            roster = await client.get(base + '/roster')
            assert roster.status_code == 200, roster.text
            assert roster.json()['directory_state'] == 'available'
            assert roster.json()['members'][0]['metadata'] == {
                'state': 'available', 'name': '<b>Same name</b>', 'avatar_state': 'unavailable'}
            directory = await client.get(base + '/directory')
            assert directory.status_code == 200, directory.text
            assert {row['ha_user_id'] for row in directory.json()['profiles']} == {USER, OTHER}
            saved = await client.put(base + '/preferences', json={
                'expected_revision': 1, 'locale': 'es', 'routine_participation_summaries': False},
                headers=await headers('private'))
            assert saved.status_code == 200, saved.text
            operation = saved.json()['operation_id']
            public = await client.put(base + '/members/' + member + '/presentation', json={
                'expected_revision': 1, 'alias': '<b>Literal</b>'}, headers=await headers('public'))
            assert public.status_code == 200, public.text
            before = runtime.storage.database.path.read_bytes()
            recovered = await client.get(base + '/requests/member.preferences.update/private')
            assert recovered.status_code == 200 and recovered.json()['operation_id'] == operation
            assert recovered.json()['notification_delivery'] == 'unavailable'
            assert runtime.storage.database.path.read_bytes() == before
            if mode == 'native':
                client.headers['X-Remote-User-Id'] = OTHER
                client.headers['Cookie'] = 'ingress_session=' + 'd' * 128
            else:
                sign_in(OTHER)
            joined = await client.post('/api/v1/members/enrollment', json={'expected_revision': 0},
                headers=await headers('join'))
            assert joined.status_code == 200 and joined.json()['result']['status'] == 'active'
            private_path = base + '/requests/member.preferences.update/private'
            assert (await client.get(private_path)).status_code == 404
            assert (await client.get('/api/v1/operations/' + operation)).status_code == 404
            own = (await client.get(base + '/preferences')).json()
            assert own['member_id'] != member and own['locale'] is None
            assert own['routine_participation_summaries'] is True
            roster = await client.get(base + '/roster')
            assert roster.status_code == 200 and len(roster.json()['members']) == 2
            assert all(set(row['metadata']) == {'state', 'name', 'avatar_state'}
                for row in roster.json()['members'])
            presentation = await client.get(base + '/members/' + member + '/presentation')
            assert presentation.json()['alias'] == '<b>Literal</b>'
            with runtime.storage.database.read() as unit:
                assert unit.preferences.get('home', member).locale is MemberLocale.SPANISH
                assert unit.preferences.get('home', member).revision == 2
                assert unit.presentations.get('home', member).revision == 2
    finally:
        runtime.close()

with TemporaryDirectory(prefix='domus-administration-api-image-') as directory:
    root = Path(directory) / 'owned'
    root.mkdir(mode=0o700)
    asyncio.run(exercise(root))
""",
        mode,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["native", "standalone"])
@pytest.mark.parametrize("delivery", ["pending", "acknowledged"])
def test_actual_compatible_application_data_and_generation_rollback(
    image, data_volume, mode, delivery
):
    source = Path(__file__).with_name("administration_rollback_fixture.py").read_text()
    previous = os.environ.get("DOMUS_SCHEMA9_IMAGE")
    assert previous, "Set DOMUS_SCHEMA9_IMAGE to the immutable compatible schema-9 image"
    inspected = []
    for reference, expected in (
        (previous, "87d726fa5a6a8cbcb56e0b911d15cc5b8a96a470"),
        (image, os.environ["DOMUS_TEST_SOURCE_COMMIT"]),
    ):
        result = docker("image", "inspect", reference)
        assert result.returncode == 0, result.stderr
        value = json.loads(result.stdout)[0]
        assert value["Config"]["Labels"]["org.opencontainers.image.revision"] == expected
        inspected.append(value)
    assert inspected[0]["Architecture"] == inspected[1]["Architecture"]
    assert (
        inspected[0]["Config"]["Labels"]["io.hass.arch"]
        == inspected[1]["Config"]["Labels"]["io.hass.arch"]
    )
    assert inspected[0]["Id"] != inspected[1]["Id"]
    previous_id, current_id = (value["Id"] for value in inspected)
    prepared = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        data_volume + ":/data",
        "--entrypoint",
        "/app/.venv/bin/python",
        current_id,
        "-c",
        "import os; from pathlib import Path; "
        "\nfor name in ('domus', 'snapshots'):"
        "\n p=Path('/data')/name; p.mkdir(mode=0o700); os.chown(p,65532,65532)",
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    observations = {}
    for phase, identifier in (
        ("initialize", previous_id),
        ("later", current_id),
        ("refuse", previous_id),
        ("restored", current_id),
        ("rollback", previous_id),
    ):
        result = docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "65532:65532",
            "--volume",
            data_volume + ":/data",
            "--entrypoint",
            "/app/.venv/bin/python",
            identifier,
            "-c",
            source,
            phase,
            mode,
            delivery,
        )
        assert result.returncode == 0, f"{phase}: {result.stdout}\n{result.stderr}"
        observations[phase] = json.loads(result.stdout)
    before, later, refusal, restored, rolled_back = (
        observations[name] for name in ("initialize", "later", "refuse", "restored", "rollback")
    )
    assert before["ui"] != later["ui"]
    assert restored["ui"] == later["ui"]
    assert restored["generation_id"] == later["selected_generation"]
    assert restored["state"] == before["state"]
    assert restored["schema"] == refusal["refused_schema"] == 30
    assert restored["original_operations_preserved"] is True
    assert rolled_back["ui"] == before["ui"]
    assert rolled_back["state"] == before["state"]
    assert rolled_back["schema"] == before["schema"] == 9


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_genuine_schema14_image_refuses_the_upgraded_category_database(image, data_volume, mode):
    previous = os.environ.get("DOMUS_SCHEMA14_IMAGE")
    assert previous, "Set DOMUS_SCHEMA14_IMAGE to the immutable pre-category image"
    inspected = []
    for reference, expected in (
        (previous, "449dc04c17a9c41d949d74cd341bf1e943a2fba9"),
        (image, os.environ["DOMUS_TEST_SOURCE_COMMIT"]),
    ):
        result = docker("image", "inspect", reference)
        assert result.returncode == 0, result.stderr
        value = json.loads(result.stdout)[0]
        assert value["Config"]["Labels"]["org.opencontainers.image.revision"] == expected
        inspected.append(value)
    assert inspected[0]["Architecture"] == inspected[1]["Architecture"]
    previous_id, current_id = (value["Id"] for value in inspected)

    prepared = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--volume",
        data_volume + ":/data",
        "--entrypoint",
        "/app/.venv/bin/python",
        current_id,
        "-c",
        "import os; from pathlib import Path; "
        "p=Path('/data/domus'); p.mkdir(mode=0o700); os.chown(p,65532,65532)",
    )
    assert prepared.returncode == 0, prepared.stderr
    script = """
import sys
from pathlib import Path
from domus.composition import ingress, server
from domus.domain.errors import DatabaseRejected
from domus.infrastructure.sqlite import SCHEMA_VERSION
phase, mode = sys.argv[1:]
root = Path('/data/domus')
path = root / 'domus.sqlite3'
def runtime():
    return (ingress.create_owned_runtime('fixture-supervisor', 'edge', root, ('http://ha.local:8123',))
            if mode == 'native' else
            server.create_owned_runtime('http://127.0.0.1:8123', 'http://127.0.0.1:8099',
                                        'edge', root, development_http=True))
if phase == 'refuse':
    assert SCHEMA_VERSION == 14
    original = path.read_bytes()
    try:
        runtime()
    except DatabaseRejected as exc:
        assert str(exc) == 'unsupported_schema'
    else:
        raise AssertionError('Old application accepted an unsupported schema')
    assert path.read_bytes() == original
else:
    assert SCHEMA_VERSION == (14 if phase == 'old' else 30)
    active = runtime()
    try:
        assert active.storage is not None
        with active.storage.database.read() as unit:
            if phase == 'new':
                assert unit.task_categories.active('home') == ()
    finally:
        active.close()
"""
    for phase, identifier in (("old", previous_id), ("new", current_id), ("refuse", previous_id)):
        result = docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "65532:65532",
            "--volume",
            data_volume + ":/data",
            "--entrypoint",
            "/app/.venv/bin/python",
            identifier,
            "-c",
            script,
            phase,
            mode,
        )
        assert result.returncode == 0, f"{phase}: {result.stdout}\n{result.stderr}"
