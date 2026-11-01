"""Cycle-scoped material CAS; the enclosing task transaction owns every commit and effect."""

import sqlite3
from dataclasses import dataclass
from typing import cast

from domus.application.task_material_ports import TaskMaterialRepository
from domus.domain.errors import Conflict
from domus.domain.task_materials import MaterialIntent
from domus.infrastructure.sqlite_task_material_records import material_document, read_material
from domus.infrastructure.sqlite_tasks import SQLiteTasks, _immutable, _model, _page


def _headers(value: MaterialIntent) -> dict[str, object]:
    return {
        "intent_id": value.intent_id,
        "household_id": value.household_id,
        "occurrence_id": value.occurrence_id,
        "cycle_id": value.cycle_id,
        "line_id": value.line.line_id,
        "recorded_by": value.recorded_by,
        "revision": value.revision,
        "state": value.state.value,
    }


@dataclass
class SQLiteTaskMaterials(TaskMaterialRepository):
    connection: sqlite3.Connection

    def get(self, household_id: str, intent_id: str) -> MaterialIntent | None:
        _page(household_id, 1, intent_id, "intent_id")
        return _model(
            self.connection.execute(
                "SELECT * FROM task_material_intents WHERE household_id=? AND intent_id=?",
                (household_id, intent_id),
            ).fetchone(),
            read_material,
            _headers,
        )

    def list(
        self, household_id: str, cycle_id: str, *, limit: int = 25, after: str | None = None
    ) -> tuple[MaterialIntent, ...]:
        where, parameters = _page(household_id, limit, after, "intent_id")
        _page(household_id, 1, cycle_id, "cycle_id")
        where.append("cycle_id=?")
        parameters.append(cycle_id)
        rows = self.connection.execute(
            "SELECT * FROM task_material_intents WHERE "
            + " AND ".join(where)
            + " ORDER BY intent_id LIMIT ?",
            (*parameters, limit),
        )
        return tuple(cast(MaterialIntent, _model(row, read_material, _headers)) for row in rows)

    def save(self, value: MaterialIntent, expected_revision: int) -> None:
        previous = self.get(value.household_id, value.intent_id)
        _immutable(
            previous,
            value,
            (
                "occurrence_id",
                "cycle_id",
                "line",
                "submitted_quantity",
                "recorded_by",
                "performed_at",
                "created_at",
                "recording_mode",
                "authorized_at_recording",
            ),
        )
        if previous is not None:
            if (
                value.updated_at < previous.updated_at
                or value.effect_revision
                not in (previous.effect_revision, previous.effect_revision + 1)
                or (
                    value.effect_revision == previous.effect_revision
                    and value.quantity != previous.quantity
                )
                or (previous.posting is not None and value.posting is None)
                or (
                    previous.posting != value.posting
                    and value.posting is not None
                    and previous.posting is not None
                    and (
                        value.posting.posted_at < previous.posting.posted_at
                        or value.posting.effect_revision <= previous.posting.effect_revision
                        or value.posting.movement_id == previous.posting.movement_id
                        or value.posting.inventory_operation_id
                        == previous.posting.inventory_operation_id
                    )
                )
            ):
                raise Conflict("material_effect_conflict")
        SQLiteTasks(self.connection)._write(
            "task_material_intents",
            {"household_id": value.household_id, "intent_id": value.intent_id},
            _headers(value),
            material_document(value).encoded,
            value.revision,
            expected_revision,
        )
