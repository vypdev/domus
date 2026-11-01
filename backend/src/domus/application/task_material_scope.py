"""Server-recorded material selectors are source evidence, never a snapshot of authority."""

from dataclasses import dataclass, fields
from typing import cast

from domus.domain.errors import InvalidInput
from domus.domain.identity import Role, validate_revision
from domus.domain.storage import JsonObject, validate_identifier
from domus.domain.task_materials import MaterialIntent
from domus.domain.task_values import validate_task_ids
from domus.domain.tasks import TaskCycle, TaskOccurrence


@dataclass(frozen=True, slots=True)
class MaterialScope:
    household_id: str
    occurrence_id: str
    cycle_id: str
    intent_id: str
    line_id: str
    definition_revision: int
    performer_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in (
            self.household_id,
            self.occurrence_id,
            self.cycle_id,
            self.intent_id,
            self.line_id,
        ):
            validate_identifier(value)
        validate_revision(self.definition_revision)
        validate_task_ids(self.performer_ids)
        if not self.performer_ids:
            raise InvalidInput("invalid_material_scope")

    def require_work(self, work: TaskOccurrence) -> None:
        if (
            self.household_id != work.household_id
            or self.occurrence_id != work.occurrence_id
            or self.definition_revision != work.definition_snapshot.revision
            or self.line_id not in {line.line_id for line in work.definition_snapshot.materials}
        ):
            raise InvalidInput("invalid_material_scope")

    @classmethod
    def source(
        cls, work: TaskOccurrence, cycle: TaskCycle, intent: MaterialIntent
    ) -> MaterialScope:
        return cls(
            work.household_id,
            work.occurrence_id,
            cycle.cycle_id,
            intent.intent_id,
            intent.line.line_id,
            work.definition_snapshot.revision,
            tuple(value.member_id for value in cycle.performers),
        )

    def document(self) -> JsonObject:
        return {
            "household_id": self.household_id,
            "occurrence_id": self.occurrence_id,
            "cycle_id": self.cycle_id,
            "intent_id": self.intent_id,
            "line_id": self.line_id,
            "definition_revision": self.definition_revision,
            "performer_ids": list(self.performer_ids),
        }


def material_scope(result: JsonObject) -> MaterialScope:
    raw = result.get("material_source")
    if (
        not isinstance(raw, dict)
        or set(raw) != {value.name for value in fields(MaterialScope)}
        or not isinstance(raw["performer_ids"], list)
    ):
        raise InvalidInput("invalid_material_scope")
    scope = MaterialScope(
        cast(str, raw["household_id"]),
        cast(str, raw["occurrence_id"]),
        cast(str, raw["cycle_id"]),
        cast(str, raw["intent_id"]),
        cast(str, raw["line_id"]),
        cast(int, raw["definition_revision"]),
        tuple(cast(list[str], raw["performer_ids"])),
    )
    cycle, material = result.get("cycle"), result.get("material")
    if (
        not isinstance(cycle, dict)
        or not isinstance(material, dict)
        or result.get("occurrence_id") != scope.occurrence_id
        or type(result.get("definition_revision")) is not int
        or result.get("definition_revision") != scope.definition_revision
        or any(
            type(cycle.get(name)) is not type(getattr(scope, name))
            or cycle.get(name) != getattr(scope, name)
            for name in ("household_id", "occurrence_id", "cycle_id", "definition_revision")
        )
        or any(
            material.get(name) != getattr(scope, name)
            for name in ("intent_id", "cycle_id", "line_id")
        )
    ):
        raise InvalidInput("invalid_material_scope")
    performers = cycle.get("performers")
    if not isinstance(performers, list) or any(
        not isinstance(row, dict) or set(row) != {"member_id", "role"} for row in performers
    ):
        raise InvalidInput("invalid_material_scope")
    rows = cast(list[JsonObject], performers)
    for row in rows:
        Role(cast(str, row["role"]))
    if tuple(row["member_id"] for row in rows) != scope.performer_ids:
        raise InvalidInput("invalid_material_scope")
    return scope
