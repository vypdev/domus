"""Run native calendar acceptance in disposable Home Assistant Core 2026.10.4."""

import asyncio
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from aiohttp import ClientConnectorCertificateError, web
from homeassistant import bootstrap, loader
from homeassistant.components.calendar import DATA_COMPONENT
from homeassistant.const import STATE_UNAVAILABLE, __version__
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get as entity_registry
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

DOMAIN = "domus_calendar"
NATIVE = "http://local-domus-edge:8100"
NATIVE_UUID = "79fe230b-ae32-4fee-9944-556c6c179fb2"
OTHER_UUID = "d265cddf-bcd4-4209-a365-4a8c547a0276"
FIRST = f"{NATIVE_UUID}.edge.{'a' * 64}"
ROTATED = f"{NATIVE_UUID}.edge.{'b' * 64}"
OTHER = f"{OTHER_UUID}.edge.{'c' * 64}"
PATH = "/api/v1/ha/calendar"
DEADLINES_PATH = "/api/v1/ha/task-deadlines"
DEADLINES_FIRST = f"{NATIVE_UUID}.edge.deadlines.{'a' * 64}"
DEADLINES_ROTATED = f"{NATIVE_UUID}.edge.deadlines.{'b' * 64}"
DEADLINES_OTHER = f"{OTHER_UUID}.edge.deadlines.{'c' * 64}"


@asynccontextmanager
async def core(config_directory=None):
    directory = (
        tempfile.TemporaryDirectory() if config_directory is None else nullcontext(config_directory)
    )
    with directory as config:
        components = Path(config, "custom_components")
        if not components.is_symlink():
            components.symlink_to("/config/custom_components", target_is_directory=True)
        hass = HomeAssistant(config)
        loader.async_setup(hass)
        result = await bootstrap.async_from_config_dict(
            {
                "homeassistant": {"name": "Disposable calendar test", "time_zone": "Europe/Madrid"},
                "calendar": {},
            },
            hass,
        )
        assert result is hass
        await hass.async_start()
        try:
            yield hass
        finally:
            await hass.async_stop()


async def configure(hass, url, token, entry=None, *, projection=None):
    context = (
        {"source": "user"}
        if entry is None
        else {"source": "reconfigure", "entry_id": entry.entry_id}
    )
    data = {"url": url, "token": token}
    if projection is not None:
        data["projection"] = projection
    return await hass.config_entries.flow.async_init(DOMAIN, context=context, data=data)


def entity_id(hass, entry):
    return entity_registry(hass).async_get_entity_id("calendar", DOMAIN, entry.unique_id)


def deadline_entities(hass, entry):
    registry = entity_registry(hass)
    return tuple(
        registry.async_get_entity_id("sensor", DOMAIN, f"{entry.unique_id}.{group}")
        for group in ("due_today", "overdue")
    )


def entity_states(hass, entities):
    return tuple(hass.states.get(entity).state for entity in entities)


async def native_events(hass, entity_id, start, end):
    entity = hass.data[DATA_COMPONENT].get_entity(entity_id)
    return [item.as_dict() for item in await entity.async_get_events(hass, start, end)]


async def events(hass, entity, start, end):
    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": start.isoformat(), "end_date_time": end.isoformat()},
        target={"entity_id": entity},
        blocking=True,
        return_response=True,
    )
    return result[entity]["events"]


def fixture_event(kind, uid, start, *, all_day=False):
    return {
        "kind": kind,
        "uid": f"{kind}:{uid}",
        "summary": f"Fixture {uid}",
        "start": start,
        "all_day": all_day,
        "task_state": "open",
    }


class Fixture:
    def __init__(self):
        self.mode = "normal"
        self.accepted = {FIRST, OTHER}
        self.tick = asyncio.Event()
        self.day = dt_util.now().date() + timedelta(days=1)
        self.deadline_grants = {DEADLINES_FIRST, DEADLINES_OTHER}
        self.deadline_body = b'{"due_today":0,"overdue":0}'
        self.deadline_status = 200
        self.deadline_requests = 0
        self.deadline_tick = asyncio.Event()

    async def respond_deadlines(self, request):
        self.deadline_requests += 1
        self.deadline_tick.set()
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if token not in self.deadline_grants:
            return web.Response(status=401)
        return web.Response(
            status=self.deadline_status, body=self.deadline_body, content_type="application/json"
        )

    async def respond(self, request):
        self.tick.set()
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if token not in self.accepted:
            return web.Response(status=401)
        instance, channel, _ = token.split(".")
        start, end, kind = (request.query[name] for name in ("start", "end", "kind"))
        cursor = None
        values = []
        pending = self.mode in {"known_pending", "empty_pending"}
        if self.mode in {"malformed", "oversize"}:
            raw = b'{"not_valid":' if self.mode == "malformed" else b" " * (128 * 1024 + 1)
            return web.Response(body=raw, content_type="application/json")
        if self.mode == "fail_due" and kind == "due":
            return web.Response(status=503)
        if self.mode == "redirect":
            raise web.HTTPFound("/unexpected")
        if self.mode != "empty_pending":
            all_day = self.day.isoformat()
            repeated = "2026-10-25"
            if kind == "planned" and start <= all_day < end:
                values.append(fixture_event(kind, "all-day", all_day, all_day=True))
            if kind == "due" and start <= repeated < end:
                values.extend(
                    fixture_event(kind, f"fold-{offset}", f"{repeated}T02:30:00{offset}")
                    for offset in ("+02:00", "+01:00")
                )
        count = len(values)
        if self.mode == "over_limit":
            count = 1001
        if self.mode in {"loop", "exhausted"}:
            offset = int(request.query.get("cursor", "0")) + 1
            count = 101
            cursor = "1" if self.mode == "loop" else str(offset)
            values = [fixture_event(kind, str(offset), self.day.isoformat(), all_day=True)]
        if kind == "planned" and self.mode in {"not_object", "bad_event", "bad_date", "naive"}:
            item = fixture_event(kind, "invalid", self.day.isoformat(), all_day=True)
            if self.mode == "bad_event":
                item["uid"] = ""
            if self.mode == "bad_date":
                item["start"] = self.day.strftime("%Y%m%d")
            if self.mode == "naive":
                item.update(all_day=False, start=f"{self.day.isoformat()}T10:00:00")
            values = [None if self.mode == "not_object" else item]
            count = 1
        if kind == "planned" and self.mode in {"changed", "duplicate", "paged", "truncated"}:
            second = "cursor" in request.query
            item = "second" if second and self.mode != "duplicate" else "first"
            values = [fixture_event(kind, item, self.day.isoformat(), all_day=True)]
            count = 3 if second and self.mode == "changed" else 2
            cursor = None if second or self.mode == "truncated" else "continue"
        if self.mode == "over_total":
            values = [fixture_event(kind, "at-bound", self.day.isoformat(), all_day=True)]
            count = 1 if kind == "planned" else 1000
        if self.mode == "wrong_identity":
            instance = "wrong"
        return web.json_response(
            {
                "instance_id": instance,
                "channel": channel,
                "projection": {
                    "period": {"start": start, "end": end},
                    "count": count,
                    "events": values,
                    "next_cursor": cursor,
                    "pending": pending,
                    "external_sync": "disabled",
                },
            }
        )


async def fixtures():
    """Exercise failure modes and lifecycle without touching any external installation."""
    fixture = Fixture()
    app = web.Application()
    app.router.add_get(PATH, fixture.respond)
    app.router.add_get(DEADLINES_PATH, fixture.respond_deadlines)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    config = tempfile.TemporaryDirectory()
    try:
        await web.TCPSite(runner, "0.0.0.0", 8100).start()
        async with core(config.name) as hass:
            form = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            assert form["type"] == "form" and form["step_id"] == "user"
            for url in (
                "http://localhost:8100",
                " https://domus.fixture",
                "https://user:password@domus.fixture",
                "https://domus.fixture:bad",
            ):
                assert (await configure(hass, url, FIRST))["errors"] == {"url": "invalid_endpoint"}
            nil = "00000000-0000-0000-0000-000000000000"
            for token in ("wrong-shape", f"{nil}.edge.{'a' * 64}", ROTATED):
                assert (await configure(hass, NATIVE, token))["errors"] == {"token": "invalid_auth"}
            fixture.mode = "wrong_identity"
            failed = await configure(hass, NATIVE, FIRST)
            assert failed["errors"] == {"base": "cannot_connect"}
            fixture.mode = "normal"
            first = await configure(hass, NATIVE, FIRST)
            assert first["type"] == "create_entry", first.get("errors")
            entry = first["result"]
            await hass.async_block_till_done()
            entity = entity_id(hass, entry)
            assert entity == "calendar.domus_schedule"
            assert hass.states.get(entity).attributes.get("supported_features", 0) == 0
            duplicate = await configure(hass, NATIVE, FIRST)
            assert duplicate["reason"] == "already_configured"
            wrong = await configure(hass, NATIVE, OTHER, entry)
            assert wrong["reason"] == "wrong_source"
            for language, expected in (("en", "Domus address"), ("es", "Dirección de Domus")):
                translations = await async_get_translations(hass, language, "config", [DOMAIN])
                assert translations[f"component.{DOMAIN}.config.step.user.data.url"] == expected

            zone = dt_util.DEFAULT_TIME_ZONE
            begin = datetime.combine(fixture.day, datetime.min.time(), zone)
            end = begin + timedelta(days=1)
            (service_item,) = await events(hass, entity, begin, end)
            assert service_item["summary"] == "Fixture all-day"
            (item,) = await native_events(hass, entity, begin, end)
            assert item["all_day"] and item["uid"] == "planned:all-day"
            assert (
                item["start"] == fixture.day.isoformat() and item["end"] == end.date().isoformat()
            )
            assert await events(hass, entity, end, end + timedelta(days=1)) == []
            assert await events(hass, entity, begin - timedelta(days=1), begin) == []
            repeated = datetime(2026, 10, 25, tzinfo=UTC)
            folds = await native_events(hass, entity, repeated, repeated + timedelta(hours=4))
            assert [item["uid"] for item in folds] == ["due:fold-+02:00", "due:fold-+01:00"]
            assert folds[1]["start"] == "2026-10-25T02:30:00+01:00"
            assert folds[1]["end"] == "2026-10-25T02:31:00+01:00"
            assert (
                await events(
                    hass,
                    entity,
                    datetime(2026, 10, 25, 1, 31, tzinfo=UTC),
                    repeated + timedelta(hours=4),
                )
                == []
            )
            maximum = await native_events(hass, entity, begin, begin + timedelta(days=90))
            assert any(event["uid"] == "planned:all-day" for event in maximum)

            fixture.mode = "paged"
            paged = await native_events(hass, entity, begin, end)
            assert [event["uid"] for event in paged] == ["planned:first", "planned:second"]
            for mode in (
                "malformed",
                "oversize",
                "wrong_identity",
                "fail_due",
                "loop",
                "exhausted",
                "over_limit",
                "over_total",
                "empty_pending",
                "redirect",
                "not_object",
                "bad_event",
                "bad_date",
                "naive",
                "changed",
                "duplicate",
                "truncated",
            ):
                fixture.mode = mode
                with suppress_expected_unavailable():
                    await events(hass, entity, begin, end)
            fixture.mode = "normal"
            with patch("custom_components.domus_calendar.client._READ_TIMEOUT", 0):
                with suppress_expected_unavailable():
                    await events(hass, entity, begin, end)
            fixture.mode = "known_pending"
            with suppress_expected_unavailable():
                await events(hass, entity, begin, begin + timedelta(days=91))
            _, coordinator = entry.runtime_data
            await coordinator.async_refresh()
            assert hass.states.get(entity).attributes["projection_pending"] is True
            fixture.mode = "fail_due"
            await coordinator.async_refresh()
            assert hass.states.get(entity).state == "unavailable"
            fixture.mode = "normal"
            await coordinator.async_refresh()
            assert hass.states.get(entity).state != "unavailable"

            fixture.accepted.remove(FIRST)
            fixture.accepted.add(ROTATED)
            assert (await configure(hass, NATIVE, FIRST, entry))["errors"] == {
                "token": "invalid_auth"
            }
            reconfigured = await configure(hass, NATIVE, ROTATED, entry)
            assert reconfigured["reason"] == "reconfigure_successful"
            await hass.async_block_till_done()
            assert entity_id(hass, entry) == entity and entry.data["token"] == ROTATED
            assert (await native_events(hass, entity, begin, end))[0]["uid"] == item["uid"]

            _, coordinator = entry.runtime_data
            assert coordinator.update_interval == timedelta(minutes=1)
            coordinator.update_interval = timedelta(seconds=1)
            await coordinator.async_refresh()
            fixture.tick.clear()
            await asyncio.wait_for(fixture.tick.wait(), timeout=3)
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            fixture.tick.clear()
            try:
                await asyncio.wait_for(fixture.tick.wait(), timeout=1.2)
            except TimeoutError:
                pass
            else:
                raise AssertionError("Calendar reads continued after config entry unload")
            state = hass.states.get(entity)
            assert state is None or state.state == "unavailable"
            entry_id, identity, sensors = await deadline_fixtures(hass, fixture)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            __file__,
            "restart-deadlines",
            config.name,
            entry_id,
            identity,
            *sensors,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        assert process.returncode == 0, output.decode()
    finally:
        await runner.cleanup()
        config.cleanup()


async def deadline_fixtures(hass, fixture):
    form = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "projection" in {str(field) for field in form["data_schema"].schema}
    rejected = await configure(hass, NATIVE, FIRST, projection="deadlines")
    assert rejected["errors"] == {"token": "invalid_auth"}
    unreachable = await configure(
        hass, "http://deadbeef-domus-edge:8100", DEADLINES_FIRST, projection="deadlines"
    )
    assert unreachable["errors"] == {"base": "cannot_connect"}
    first = await configure(hass, NATIVE, DEADLINES_FIRST, projection="deadlines")
    assert first["type"] == "create_entry", first.get("errors")
    entry = first["result"]
    await hass.async_block_till_done()
    sensors = deadline_entities(hass, entry)
    assert sensors == ("sensor.domus_tasks_due_today", "sensor.domus_overdue_tasks"), sensors
    assert entity_states(hass, sensors) == ("0", "0")
    duplicate = await configure(hass, NATIVE, DEADLINES_FIRST, projection="deadlines")
    assert duplicate["reason"] == "already_configured"
    wrong_source = await configure(hass, NATIVE, DEADLINES_OTHER, entry)
    assert wrong_source["reason"] == "wrong_source"

    for locale, expected in (("en", "Task deadline counts"), ("es", "Recuentos de vencimientos")):
        translations = await async_get_translations(hass, locale, "selector", [DOMAIN])
        assert translations[f"component.{DOMAIN}.selector.projection.options.deadlines"] == expected
    coordinator = entry.runtime_data
    assert coordinator.update_interval == timedelta(minutes=1)
    before = fixture.deadline_requests
    fixture.deadline_body = b'{"due_today":2,"overdue":3}'
    await coordinator.async_refresh()
    assert fixture.deadline_requests == before + 1
    assert entity_states(hass, sensors) == ("2", "3")

    for malformed in (
        b"not json",
        b"[]",
        b'{"due_today":1,"due_today":2}',
        b'{"due_today":true,"overdue":3}',
        b'{"due_today":2,"overdue":-1}',
        b'{"due_today":1,"overdue":9223372036854775808}',
        b" " * 129,
    ):
        fixture.deadline_body = malformed
        await coordinator.async_refresh()
        assert entity_states(hass, sensors) == (STATE_UNAVAILABLE, STATE_UNAVAILABLE)
    fixture.deadline_body = b'{"due_today":2,"overdue":3}'
    fixture.deadline_status = 503
    await coordinator.async_refresh()
    assert entity_states(hass, sensors) == (STATE_UNAVAILABLE, STATE_UNAVAILABLE)
    fixture.deadline_status = 200
    await coordinator.async_refresh()
    assert entity_states(hass, sensors) == ("2", "3")

    registry = entity_registry(hass)
    renamed = "sensor.renamed_domus_deadline"
    registry.async_update_entity(sensors[0], new_entity_id=renamed)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    sensors = (renamed, sensors[1])
    assert deadline_entities(hass, entry) == sensors
    assert entity_states(hass, sensors) == ("2", "3")

    fixture.deadline_grants.remove(DEADLINES_FIRST)
    fixture.deadline_grants.add(DEADLINES_ROTATED)
    await entry.runtime_data.async_refresh()
    assert entity_states(hass, sensors) == (STATE_UNAVAILABLE, STATE_UNAVAILABLE)
    rejected = await configure(hass, NATIVE, DEADLINES_FIRST, entry)
    assert rejected["errors"] == {"token": "invalid_auth"}
    rotated = await configure(hass, NATIVE, DEADLINES_ROTATED, entry)
    assert rotated["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert deadline_entities(hass, entry) == sensors
    assert entity_states(hass, sensors) == ("2", "3")

    coordinator = entry.runtime_data
    coordinator.update_interval = timedelta(seconds=1)
    await coordinator.async_refresh()
    fixture.deadline_tick.clear()
    await asyncio.wait_for(fixture.deadline_tick.wait(), timeout=3)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    before = fixture.deadline_requests
    await asyncio.sleep(1.2)
    assert fixture.deadline_requests == before
    assert all(
        hass.states.get(entity) is None or hass.states.get(entity).state == STATE_UNAVAILABLE
        for entity in sensors
    )
    return entry.entry_id, entry.unique_id, sensors


async def verify_deadline_restart(config, entry_id, identity, due, overdue):
    async with core(config) as restarted:
        await restarted.async_block_till_done()
        restored = restarted.config_entries.async_get_entry(entry_id)
        assert restored.unique_id == identity
        assert deadline_entities(restarted, restored) == (due, overdue)
        assert entity_states(restarted, (due, overdue)) == ("2", "3")


class suppress_expected_unavailable:
    def __enter__(self):
        return self

    def __exit__(self, kind, _value, _traceback):
        if kind is None:
            raise AssertionError("An incomplete read returned a calendar")
        return issubclass(kind, HomeAssistantError)


async def live():
    """Read materialized work through Core from isolated owned installations."""
    targets = json.loads(os.environ["DOMUS_CALENDAR_TARGETS"])
    assert {target["label"] for target in targets} == {
        "native edge",
        "native stable",
        "standalone edge",
        "standalone stable",
    }
    async with core() as hass:
        session = async_get_clientsession(hass)
        try:
            async with session.get("https://untrusted.domus.fixture:8443"):
                raise AssertionError("Core accepted a certificate for the wrong host")
        except ClientConnectorCertificateError:
            pass
        now = dt_util.now()
        entries, deadline_entries, identities = [], [], set()
        for target in targets:
            url, token, label = target["url"], target["token"], target["label"]
            other_channel = "stable" if label.endswith(" edge") else "edge"
            foreign = next(
                value["token"]
                for value in targets
                if value["label"] == f"{label.split()[0]} {other_channel}"
            )
            async with session.get(
                url + PATH, headers={"Authorization": f"Bearer {foreign}"}
            ) as denied:
                assert denied.status == 401
            result = await configure(hass, url, token)
            assert result["type"] == "create_entry", result.get("errors")
            entry = result["result"]
            entries.append(entry)
            assert entry.unique_id not in identities
            identities.add(entry.unique_id)
            await hass.async_block_till_done()
            entity = entity_id(hass, entry)
            async with session.get(
                url + DEADLINES_PATH, headers={"Authorization": f"Bearer {token}"}
            ) as denied:
                assert denied.status == 401
            deadlines = await configure(hass, url, target["deadline"], projection="deadlines")
            assert deadlines["type"] == "create_entry", deadlines.get("errors")
            deadline_entry = deadlines["result"]
            deadline_entries.append(deadline_entry)
            assert deadline_entry.unique_id not in identities
            identities.add(deadline_entry.unique_id)
            await hass.async_block_till_done()
            assert entity_states(hass, deadline_entities(hass, deadline_entry)) == ("0", "1")
            for _ in range(20):
                display = await events(hass, entity, now, now + timedelta(days=3))
                if any(item["summary"] == f"{label} plan" for item in display):
                    break
                await asyncio.sleep(0.1)
            else:
                raise AssertionError(f"{label} did not materialize the planned task")
            native = await native_events(hass, entity, now, now + timedelta(days=3))
            assert {item["summary"] for item in native} == {f"{label} deadline", f"{label} plan"}
            assert {item["summary"] for item in display} == {f"{label} deadline", f"{label} plan"}
            assert len(native) == len(display) == 3
            due = next(item for item in native if item["summary"].endswith(" deadline"))
            scheduled = [item for item in native if item["summary"].endswith(" plan")]
            assert {item["uid"].split(":")[0] for item in scheduled} == {"planned", "due"}
            assert all(item["all_day"] for item in scheduled)
            assert due["uid"].startswith("due:") and not due["all_day"]
            assert datetime.fromisoformat(due["end"]) - datetime.fromisoformat(
                due["start"]
            ) == timedelta(minutes=1)
        assert len({entity_id(hass, entry) for entry in entries}) == len(targets)
        assert (
            len({entity for entry in deadline_entries for entity in deadline_entities(hass, entry)})
            == 8
        )
        for entry in entries + deadline_entries:
            assert await hass.config_entries.async_unload(entry.entry_id)


if __name__ == "__main__":
    assert __version__ == "2026.10.4", __version__
    if len(sys.argv) > 1:
        assert sys.argv[1] == "restart-deadlines"
        asyncio.run(verify_deadline_restart(*sys.argv[2:]))
    else:
        asyncio.run(live() if "DOMUS_CALENDAR_TARGETS" in os.environ else fixtures())
    print("Home Assistant native calendar acceptance passed")
