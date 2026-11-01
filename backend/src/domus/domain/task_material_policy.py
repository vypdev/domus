"""Material source integrity is identical for live reads and checkpoint validation."""

from domus.domain.errors import InvalidInput
from domus.domain.task_materials import MaterialIntent
from domus.domain.tasks import TaskCycle, TaskOccurrence


def cycle_materials(
    work: TaskOccurrence, cycle: TaskCycle, values: tuple[MaterialIntent, ...]
) -> tuple[MaterialIntent, ...]:
    """Return the exact frozen line order; neither an omitted nor extra source is safe."""
    if (
        cycle.household_id != work.household_id
        or cycle.occurrence_id != work.occurrence_id
        or cycle.definition_revision != work.definition_snapshot.revision
        or type(values) is not tuple
        or len(values) > 32
        or any(not isinstance(value, MaterialIntent) for value in values)
    ):
        raise InvalidInput("invalid_material_references")
    lines = work.definition_snapshot.materials
    by_line = {value.line.line_id: value for value in values}
    if (
        len(by_line) != len(values)
        or len({value.intent_id for value in values}) != len(values)
        or set(by_line) != {line.line_id for line in lines}
    ):
        raise InvalidInput("invalid_material_references")
    for line in lines:
        value = by_line[line.line_id]
        if (
            value.household_id != work.household_id
            or value.occurrence_id != work.occurrence_id
            or value.cycle_id != cycle.cycle_id
            or value.line != line
            or value.recorded_by != cycle.recorded_by
            or value.performed_at != cycle.performed_at
            or value.created_at != cycle.recorded_at
            or value.recording_mode is not cycle.rules.material_recording
        ):
            raise InvalidInput("invalid_material_references")
    return tuple(by_line[line.line_id] for line in lines)
