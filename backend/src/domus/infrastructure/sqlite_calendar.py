"""SQLite range selection shares its authorized predicates between rows and counts."""

import sqlite3
from dataclasses import dataclass

from domus.domain.calendar_values import (
    CalendarCandidate,
    CalendarFilters,
    CalendarKind,
    CalendarPosition,
    CalendarRange,
    CalendarTiming,
)
from domus.domain.errors import InvalidInput, StorageFailure

_SCOPE = """
WITH slots AS (
    SELECT occurrence_id, slot_key, timing_kind, nominal_kind, nominal_value
    FROM recurrence_slots WHERE household_id=:home
    UNION ALL
    SELECT occurrence_id, slot_key, timing_kind,
           json_extract(document,'$.planned.nominal.kind'),
           json_extract(document,'$.planned.nominal.local')
    FROM recurrence_relative_slots WHERE household_id=:home
),
moved AS (
    SELECT json_extract(o.payload,'$.occurrence_id') AS occurrence_id,
           json_extract(r.result,'$.recurrence_reschedule.destination.nominal.local')
               AS nominal_value,
           row_number() OVER (
               PARTITION BY json_extract(o.payload,'$.occurrence_id') ORDER BY o.position DESC
           ) AS rank
    FROM receipts r JOIN outbox o ON o.event_id=r.operation_id
    WHERE r.household_id=:home AND r.action='task.recurrence.reschedule'
),
facts AS (
    SELECT 'planned' AS kind, s.occurrence_id AS source_id, s.occurrence_id,
           NULL AS participants, NULL AS verifier
    FROM slots s WHERE substr(s.nominal_value,1,10)>=:start AND substr(s.nominal_value,1,10)<:end
    UNION ALL
    SELECT 'due', w.occurrence_id, w.occurrence_id, NULL, NULL
    FROM task_occurrences w
    WHERE w.household_id=:home AND json_extract(w.document,'$.due_at')>=:from_ms
        AND json_extract(w.document,'$.due_at')<:until_ms
    UNION ALL
    SELECT 'due', s.occurrence_id, s.occurrence_id, NULL, NULL
    FROM slots s LEFT JOIN moved m ON m.occurrence_id=s.occurrence_id AND m.rank=1
    WHERE s.nominal_kind='date' AND coalesce(m.nominal_value,s.nominal_value)>=:start
        AND coalesce(m.nominal_value,s.nominal_value)<:end
    UNION ALL
    SELECT 'performed', c.cycle_id, c.occurrence_id, json_extract(c.document,'$.performers'), NULL
    FROM task_cycles c
    WHERE c.household_id=:home AND json_extract(c.document,'$.performed_at')>=:from_ms
        AND json_extract(c.document,'$.performed_at')<:until_ms
    UNION ALL
    SELECT 'approval', c.cycle_id, c.occurrence_id, NULL, c.verified_by
    FROM task_cycles c
    WHERE c.household_id=:home AND json_extract(c.document,'$.verified_at')>=:from_ms
        AND json_extract(c.document,'$.verified_at')<:until_ms
),
visible AS (
    SELECT f.kind,f.source_id,f.occurrence_id,s.slot_key,
           coalesce(s.timing_kind,'manual') AS timing
    FROM facts f
    JOIN task_occurrences w ON w.household_id=:home AND w.occurrence_id=f.occurrence_id
    LEFT JOIN slots s ON s.occurrence_id=f.occurrence_id
    WHERE (:kind IS NULL OR f.kind=:kind)
      AND (:timing IS NULL OR coalesce(s.timing_kind,'manual')=:timing)
      AND (:state IS NULL OR w.state=:state)
      AND (:priority IS NULL
           OR json_extract(w.document,'$.definition_snapshot.content.priority')=:priority)
      AND (:category IS NULL OR EXISTS (
          SELECT 1 FROM json_each(w.document,'$.definition_snapshot.content.tags') t
          WHERE t.value=:category
      ))
      AND (:member_id IS NULL OR
          (f.kind='approval' AND f.verifier=:member_id) OR
          (f.kind='performed' AND EXISTS (
              SELECT 1 FROM json_each(f.participants) p
              WHERE json_extract(p.value,'$.member_id')=:member_id
          )) OR
          (f.kind IN ('due','planned') AND EXISTS (
              SELECT 1 FROM json_each(w.document,'$.assignee_ids') a WHERE a.value=:member_id
          ))
      )
)
"""


@dataclass
class SQLiteCalendar:
    connection: sqlite3.Connection

    def page(
        self,
        household_id: str,
        period: CalendarRange,
        filters: CalendarFilters,
        from_ms: int,
        until_ms: int,
        limit: int,
        after: CalendarPosition | None,
    ) -> tuple[int, tuple[CalendarCandidate, ...]]:
        parameters = {
            "home": household_id,
            "start": period.start.isoformat(),
            "end": period.end.isoformat(),
            "from_ms": from_ms,
            "until_ms": until_ms,
            "limit": limit,
            "after_kind": None if after is None else after.kind.value,
            "after_id": None if after is None else after.source_id,
            **filters.document().decode(),
        }
        count = self.connection.execute(
            _SCOPE + "SELECT count(*) FROM visible", parameters
        ).fetchone()[0]
        rows = self.connection.execute(
            _SCOPE + "SELECT * FROM visible WHERE :after_kind IS NULL "
            "OR (kind,source_id)>(:after_kind,:after_id) ORDER BY kind,source_id LIMIT :limit",
            parameters,
        )
        try:
            candidates = tuple(
                CalendarCandidate(
                    CalendarPosition(CalendarKind(row["kind"]), row["source_id"]),
                    row["occurrence_id"],
                    CalendarTiming(row["timing"]),
                    row["slot_key"],
                )
                for row in rows
            )
        except ValueError, InvalidInput:
            raise StorageFailure("invalid_calendar_projection") from None
        if len({item.position for item in candidates}) != len(candidates):
            raise StorageFailure("invalid_calendar_projection")
        return count, candidates

    def rules_pending(self, household_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM recurrence_rules r LEFT JOIN recurrence_progress p "
                "ON p.household_id=r.household_id AND p.schedule_id=r.schedule_id "
                "WHERE r.household_id=? AND r.state='active' AND (p.schedule_id IS NULL "
                "OR (r.timing_kind='fixed_calendar' "
                "AND json_extract(p.document,'$.cursor.closed') IS NOT 1) "
                "OR (r.timing_kind='completion_relative' "
                "AND json_extract(p.document,'$.current_slot_key') IS NULL)) LIMIT 1",
                (household_id,),
            ).fetchone()
            is not None
        )
