"""Annotations are opt-in reads; original Shopping clients keep their exact wire shape."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from test_inventory_catalog_http import INVENTORY, OUTSIDER, get, post, register
from test_recurrence_http import USER
from test_rewards_http import member_context
from test_shared_shopping import REQUESTER
from test_shopping_http import command, original
from test_task_runtime import api as api

from domus.domain.errors import InvalidInput
from domus.domain.identity import Member, MemberStatus, Permission, PermissionRule, Role
from domus.domain.member_profiles import MemberPresentation
from domus.entrypoints.inventory_http import AddExtraBody


def test_published_note_schema_admits_the_same_unicode_as_the_command_validator():
    note = AddExtraBody.model_json_schema()["properties"]["note"]
    assert "pattern" in note
    for name in ("household-api.openapi.json", "native-household-api.openapi.json"):
        document = json.loads((Path(__file__).parents[2] / "docs/contracts" / name).read_text())
        assert document["components"]["schemas"]["AddExtraBody"]["properties"]["note"] == note
    pattern = re.compile(note["pattern"])
    required = {
        "action": "shopping.add-extra",
        "product_id": None,
        "name": "Schema qualification",
        "quantity": "1",
    }
    for value in (
        "",
        "Line\nTab\tCarriage\rReturn",
        "😀" * 1000,
        "~\u00a0 text",
        "<b>literal</b>",
        "\ud7ff\ue000\uffff\U00010000\U0010ffff",
    ):
        assert pattern.fullmatch(value) and len(value) <= note["maxLength"]
        assert AddExtraBody.model_validate({**required, "note": value}).note == value
    for codepoint in (*range(0x20), *range(0x7F, 0xA0), *range(0xD800, 0xE000)):
        if codepoint in (9, 10, 13):
            continue
        value = "Prefix" + chr(codepoint) + "suffix"
        assert pattern.fullmatch(value) is None
        with pytest.raises(InvalidInput) as invalid:
            AddExtraBody.model_validate({**required, "note": value})
        assert invalid.value.code == "invalid_shopping_note"


def test_escaped_json_rejects_lone_surrogates_and_recovers_with_supplementary_notes(api):
    api.user(USER, True)
    tables = ("shopping_extras", "receipts", "audit", "outbox", "inventory_movements")
    with closing(sqlite3.connect(api.store.path)) as db:
        before = {
            table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables
        }
    for index, invalid_note in enumerate(("\ud800", "\udfff", "\udc00\ud800", "\ud83dx\ude00")):
        key = f"escaped-unicode-{index}"
        payload = {
            "action": "shopping.add-extra",
            "product_id": None,
            "name": "Escaped Unicode",
            "quantity": "1",
            "note": invalid_note,
        }
        # Exercise real JSON decoding, not an HTTP client's UTF-8 encoder failure.
        headers = api.headers(key) | member_context(USER) | {"Content-Type": "application/json"}
        response = api.client.post(
            INVENTORY + "/commands", content=json.dumps(payload, ensure_ascii=True), headers=headers
        )
        assert response.status_code == 422, response.text
        # The existing HTTP boundary rejects malformed Unicode before the named
        # command validator; preserve its public error and the unused key.
        assert response.json()["code"] == "invalid_request"
        assert response.json()["action_required"]
        with closing(sqlite3.connect(api.store.path)) as db:
            assert {
                table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in tables
            } == {
                table: count + (index if table != "inventory_movements" else 0)
                for table, count in before.items()
            }
        # The same key remains available. Escaped UTF-16 pairs decode to Unicode
        # scalars, including both supplementary boundaries and 1,000 emoji.
        corrected = ("😀" * 1000, "\U00010000", "\U0010ffff", "Literal\nTab\tReturn\r😀")[index]
        body = json.dumps(payload | {"note": corrected}, ensure_ascii=True)
        assert json.loads(body)["note"] == corrected
        saved = api.client.post(INVENTORY + "/commands", content=body, headers=headers)
        assert saved.status_code == 200, saved.text
        assert (
            api.client.post(INVENTORY + "/commands", content=body, headers=headers).json()
            == saved.json()
        )
        assert original(api, key, "add-extra").json() == saved.json()
    with closing(sqlite3.connect(api.store.path)) as db:
        assert {
            table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables
        } == {
            table: count + (4 if table != "inventory_movements" else 0)
            for table, count in before.items()
        }


def annotated(api, product=None, user=USER, **params):
    suffix = "/annotated" if product is None else f"/{product}/sources/annotated"
    return api.client.get(
        INVENTORY + "/shopping-list" + suffix, headers=member_context(user), params=params
    )


def test_new_annotations_preserve_independent_sources_and_the_legacy_read_contract(api):
    api.user(USER, True)
    product = register(api, "catalog", "Tea", "piece")
    legacy = command(api, "legacy", "add-extra", product_id=product, name=None, quantity="1")
    assert legacy.status_code == 200
    first = command(
        api,
        "annotated",
        "add-extra",
        product_id=product,
        name=None,
        quantity="2",
        note="Decaffeinated\nKeep the original whitespace. 😀",
        priority="high",
    )
    assert first.status_code == 200, first.text
    assert original(api, "annotated", "add-extra").json() == first.json()
    free = command(
        api,
        "fruit",
        "add-extra",
        product_id=None,
        name="Fruit",
        quantity="3",
        note="<img src=x onerror=alert(1)>\nUntrusted text",
        priority="urgent",
    )
    assert free.status_code == 200
    legacy_list = api.client.get(INVENTORY + "/shopping-list", headers=member_context(USER))
    assert legacy_list.status_code == 200
    assert set(legacy_list.json()) == {"items", "next_cursor"}
    assert all("annotation" not in row for row in legacy_list.json()["items"])
    result = annotated(api)
    assert result.status_code == 200, result.text
    assert [row["item"] for row in result.json()["items"]] == legacy_list.json()["items"]
    assert result.json()["items"][0]["annotation"] is None
    assert result.json()["items"][1]["annotation"] == {
        "note": "<img src=x onerror=alert(1)>\nUntrusted text",
        "priority": "urgent",
    }
    sources = annotated(api, product)
    assert sources.status_code == 200, sources.text
    annotations = {
        row["source"]["origin_id"]: row["annotation"] for row in sources.json()["sources"]
    }
    assert annotations[legacy.json()["result"]["extra_id"]] == {"note": "", "priority": "normal"}
    assert annotations[first.json()["result"]["extra_id"]] == {
        "note": "Decaffeinated\nKeep the original whitespace. 😀",
        "priority": "high",
    }
    assert sources.json()["item"]["manual"] == "3"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("note", "x" * 1001, "invalid_shopping_note"),
        ("note", "unsafe\x00text", "invalid_shopping_note"),
        ("note", 123, "invalid_shopping_note"),
        ("priority", "fast", "invalid_shopping_priority"),
        ("priority", True, "invalid_shopping_priority"),
        *[
            pytest.param(
                "note", "unsafe" + chr(code) + "text", "invalid_shopping_note", id=f"C1-{code:04x}"
            )
            for code in range(0x80, 0xA0)
        ],
    ],
)
def test_invalid_annotation_identifies_the_field_and_creates_no_receipt(api, field, value, code):
    api.user(USER, True)
    with closing(sqlite3.connect(api.store.path)) as db:
        before = {
            table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("shopping_extras", "receipts", "audit", "outbox", "inventory_movements")
        }
    response = command(
        api, "invalid", "add-extra", product_id=None, name="Fruit", quantity="1", **{field: value}
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code
    assert field in response.json()["action_required"].lower()
    with closing(sqlite3.connect(api.store.path)) as db:
        assert {
            table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in before
        } == before
    corrected = "Corrected\t\r\n note 😀"
    retry = command(
        api,
        "invalid",
        "add-extra",
        product_id=None,
        name="Fruit",
        quantity="1",
        note=corrected,
        priority="normal",
    )
    assert retry.status_code == 200, retry.text
    assert original(api, "invalid", "add-extra").json() == retry.json()
    assert annotated(api).json()["items"][0]["annotation"] == {
        "note": corrected,
        "priority": "normal",
    }
    with closing(sqlite3.connect(api.store.path)) as db:
        assert {
            table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in before
        } == {table: count + int(table != "inventory_movements") for table, count in before.items()}


def test_annotation_reads_keep_current_authority_task_redaction_and_bound_cursors(api):
    with api.store.write() as unit:
        unit.members.save(
            Member(
                "requester",
                "home",
                REQUESTER,
                Role.VIEWER,
                MemberStatus.ACTIVE,
                1,
                (
                    PermissionRule(Permission.SHOPPING_REQUEST, True),
                    PermissionRule(Permission.TASKS_READ, False),
                ),
            ),
            0,
        )
        unit.presentations.save(MemberPresentation("requester", "home", "Requester", 2), 1)
    api.user(USER, True)
    product = register(api, "catalog", "Tea", "piece")
    reference = get(api).json()["products"][0]["reference_id"]
    assert (
        post(
            api,
            "pantry",
            "configure-replenishment",
            product_id=product,
            minimum="1",
            target="3",
            expected_revision="0",
        ).status_code
        == 200
    )
    task = api.client.post(
        "/api/v1/tasks/definitions",
        headers=api.headers("plan") | member_context(USER),
        json={
            "title": "Private task title",
            "expected_revision": 0,
            "materials": [{"reference_id": reference, "planned_quantity": "2"}],
        },
    )
    assert task.status_code == 200, task.text
    for key in ("first", "second"):
        assert (
            command(
                api,
                key,
                "add-extra",
                product_id=product,
                name=None,
                quantity="1",
                note=key,
                priority="low",
            ).status_code
            == 200
        )
    assert (
        command(
            api,
            "free",
            "add-extra",
            product_id=None,
            name="Fruit",
            quantity="1",
            note="😀" * 1000,
            priority="normal",
        ).status_code
        == 200
    )
    complete = annotated(api, product).json()
    assert {row["source"]["kind"] for row in complete["sources"]} == {"extra", "pantry", "task"}
    assert all(
        row["annotation"] is None for row in complete["sources"] if row["source"]["kind"] != "extra"
    )
    api.user(REQUESTER)
    redacted = annotated(api, product, REQUESTER)
    assert redacted.status_code == 200, redacted.text
    assert redacted.json()["item"]["tasks"] == "0"
    assert {row["source"]["kind"] for row in redacted.json()["sources"]} == {"extra", "pantry"}
    assert "Private task title" not in redacted.text
    assert annotated(api, "foreign", REQUESTER).status_code == 404
    for path in ("", f"/{product}/sources"):
        endpoint = INVENTORY + "/shopping-list" + path
        headers = member_context(REQUESTER)
        old = api.client.get(endpoint, headers=headers, params={"limit": 1})
        new = api.client.get(endpoint + "/annotated", headers=headers, params={"limit": 1})
        old_cursor, new_cursor = old.json()["next_cursor"], new.json()["next_cursor"]
        assert old_cursor and new_cursor
        for suffix, cursor in (("", new_cursor), ("/annotated", old_cursor)):
            rejected = api.client.get(
                endpoint + suffix, headers=headers, params={"limit": 1, "cursor": cursor}
            )
            assert rejected.status_code == 422 and rejected.json()["code"] == "invalid_task_cursor"
        continued = api.client.get(
            endpoint + "/annotated", headers=headers, params={"limit": 1, "cursor": new_cursor}
        )
        assert continued.status_code == 200
    with api.store.write() as unit:
        member = unit.members.by_user("home", REQUESTER)
        unit.members.save(
            replace(
                member,
                revision=2,
                exceptions=(
                    PermissionRule(Permission.HOUSEHOLD_READ, False),
                    PermissionRule(Permission.SHOPPING_REQUEST, False),
                ),
            ),
            1,
        )
    for user in (REQUESTER, OUTSIDER):
        api.user(user)
        for product_id in (None, product):
            denied = annotated(api, product_id, user)
            assert denied.status_code == 403
            assert not {"items", "item", "sources"} & denied.json().keys()
        assert (
            command(
                api,
                "denied",
                "add-extra",
                user=user,
                product_id=None,
                name="Fruit",
                quantity="1",
                note="Must not persist",
                priority="urgent",
            ).status_code
            == 403
        )
