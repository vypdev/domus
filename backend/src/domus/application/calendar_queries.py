"""Project protected calendar facts with an exact range, count and cursor binding."""

from dataclasses import dataclass, replace
from datetime import date, datetime, time

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions, UnitOfWork
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.relative_lifecycle import (
    recorded_invalidation,
    relative_invalidation_command,
)
from domus.application.relative_recurrence_commands import resolve_initial
from domus.application.reschedule_review import ScheduledWork, effective_deadline
from domus.application.task_authorization import TaskAccess, TaskActor
from domus.application.task_category_commands import require_active_category
from domus.application.task_ports import TaskCursors
from domus.domain.calendar_values import (
    CalendarCandidate,
    CalendarFilters,
    CalendarKind,
    CalendarPosition,
    CalendarRange,
    CalendarTiming,
)
from domus.domain.errors import (
    Conflict,
    Forbidden,
    IntegrationUnavailable,
    InvalidInput,
    StorageFailure,
)
from domus.domain.identity import HumanIdentity, Permission
from domus.domain.recurrence_rules import NominalDate
from domus.domain.recurrence_time import LocalInstant, NominalTime, TimePolicy
from domus.domain.relative_lifecycle import RelativeClosure
from domus.domain.relative_recurrence import RelativeSlot
from domus.domain.storage import Household, Installation, JsonDocument
from domus.domain.task_values import OccurrenceState, Priority, VerificationState


@dataclass(frozen=True, slots=True)
class CalendarEntry:
    entry_id: str
    kind: CalendarKind
    timing: CalendarTiming
    occurrence_id: str
    title: str
    state: OccurrenceState
    priority: Priority
    categories: tuple[str, ...]
    member_ids: tuple[str, ...]
    schedule_id: str | None
    slot_key: str | None
    local_date: date | None = None
    local_time: str | None = None
    instant_ms: int | None = None
    time_zone: str | None = None
    nominal_local: str | None = None
    resolved_local: str | None = None
    verification: VerificationState | None = None
    relative_review_required: bool = False
    category_id: str | None = None


@dataclass(frozen=True, slots=True)
class CalendarPage:
    period: CalendarRange
    time_zone: str
    entries: tuple[CalendarEntry, ...]
    count: int
    occurrence_count: int
    next_cursor: str | None
    pending: bool


@dataclass(frozen=True, slots=True)
class CalendarQueries:
    transactions: Transactions
    scope: MaintenanceScope
    human: HumanIdentity | Installation
    cursors: TaskCursors
    times: RecurrenceTimes

    def _read(self, unit: UnitOfWork) -> tuple[Household, TaskActor | None]:
        home = self.scope.household(unit)
        if home is None:
            raise Forbidden("permission_denied")
        if isinstance(self.human, Installation):
            if self.human != self.scope.installation:
                raise Forbidden("permission_denied")
            return home, None
        actor = TaskAccess(self.human).require(unit, self.scope.household_id, Permission.TASKS_READ)
        return home, actor

    def _boundary(self, day: date, policy: TimePolicy) -> int:
        value = resolve_initial(self.times, NominalTime(datetime.combine(day, time.min)), policy)
        assert value.resolved is not None
        return value.resolved.instant_ms

    def _binding(
        self,
        home: Household,
        actor: TaskActor | None,
        period: CalendarRange,
        filters: CalendarFilters,
        limit: int,
        kind: CalendarKind,
    ) -> JsonDocument:
        installation = self.scope.installation
        if isinstance(self.human, HumanIdentity):
            assert actor is not None
            subject = {
                "query": "calendar",
                "actor": self.human.ha_user_id,
                "membership_revision": actor.member.revision,
                "member_id": actor.member.member_id,
                "role": actor.role.value,
                "policy_revision": actor.identity_policy_revision,
            }
        else:
            subject = {"query": "ha-calendar"}
        return JsonDocument.from_value(
            {
                **subject,
                "version": 1,
                "instance": installation.instance_id,
                "channel": installation.channel,
                "household": home.household_id,
                "household_revision": home.revision,
                "limit": limit,
                "start": period.start.isoformat(),
                "end": period.end.isoformat(),
                "filters": filters.document().decode(),
                "position_kind": kind.value,
            }
        )

    def _slot(self, unit: UnitOfWork, candidate: CalendarCandidate) -> ScheduledWork | None:
        if candidate.slot_key is None:
            return None
        home = self.scope.household_id
        slot = (
            unit.recurrence.slot(home, candidate.slot_key)
            if candidate.timing is CalendarTiming.FIXED
            else unit.recurrence.relative_slot(home, candidate.slot_key)
        )
        if slot is None or slot.occurrence_id != candidate.occurrence_id:
            raise StorageFailure("invalid_calendar_projection")
        return slot

    def _relative_review_required(self, unit: UnitOfWork, slot: ScheduledWork | None) -> bool:
        if not isinstance(slot, RelativeSlot) or slot.source is None:
            return False
        key = RelativeClosure.cycle_key(slot.schedule, slot.source.cycle, slot.installation)
        receipt = unit.receipts.get(relative_invalidation_command(slot.schedule.household_id, key))
        return (
            receipt is not None
            and recorded_invalidation(receipt, key, slot.occurrence_id) == "review"
        )

    def _entry(self, unit: UnitOfWork, candidate: CalendarCandidate) -> CalendarEntry:
        home = self.scope.household_id
        work = unit.tasks.occurrence(home, candidate.occurrence_id)
        if work is None:
            raise StorageFailure("invalid_calendar_projection")
        position = candidate.position
        content = work.definition_snapshot.content
        label = work.definition_snapshot.category_label
        slot = self._slot(unit, candidate)
        entry = CalendarEntry(
            f"{position.kind.value}:{position.source_id}",
            position.kind,
            candidate.timing,
            work.occurrence_id,
            content.title,
            work.state,
            content.priority,
            () if label is None else (label,),
            work.assignee_ids,
            None if slot is None else slot.schedule.schedule_id,
            candidate.slot_key,
            relative_review_required=(
                isinstance(self.human, HumanIdentity) and self._relative_review_required(unit, slot)
            ),
            category_id=content.category_id,
        )
        if position.kind is CalendarKind.PLANNED:
            if slot is None:
                raise StorageFailure("invalid_calendar_projection")
            planned = slot.planned
            if isinstance(planned.nominal, NominalDate):
                return replace(entry, local_date=planned.nominal.local)
            assert planned.resolved is not None
            resolved = planned.resolved
            return replace(
                entry,
                local_date=planned.nominal.local.date(),
                local_time=resolved.resolved_local.time().isoformat(),
                instant_ms=resolved.instant_ms,
                time_zone=resolved.policy.zone,
                nominal_local=planned.nominal.local.isoformat(),
                resolved_local=resolved.resolved_local.isoformat(),
            )
        if position.kind is CalendarKind.DUE:
            if work.due_at is not None:
                return replace(entry, instant_ms=work.due_at)
            if slot is None:
                raise StorageFailure("invalid_calendar_projection")
            deadline = effective_deadline(unit, work, slot)
            if deadline.local_date is None:
                raise StorageFailure("invalid_calendar_projection")
            return replace(entry, local_date=deadline.local_date)
        cycle = unit.tasks.cycle(home, position.source_id)
        if cycle is None or cycle.occurrence_id != work.occurrence_id:
            raise StorageFailure("invalid_calendar_projection")
        if position.kind is CalendarKind.PERFORMED:
            return replace(
                entry,
                instant_ms=cycle.performed_at,
                member_ids=tuple(person.member_id for person in cycle.performers),
            )
        if cycle.verified_at is None or cycle.verified_by is None:
            raise StorageFailure("invalid_calendar_projection")
        return replace(
            entry,
            instant_ms=cycle.verified_at,
            member_ids=(cycle.verified_by.member_id,),
            verification=cycle.verification,
        )

    def _localize(self, item: CalendarEntry, policy: TimePolicy) -> CalendarEntry:
        if item.instant_ms is None or item.time_zone is not None:
            return item
        local = self.times.local_at(item.instant_ms, policy)
        if (
            not isinstance(local, LocalInstant)
            or local.instant_ms != item.instant_ms
            or local.policy != policy
        ):
            raise IntegrationUnavailable("recurrence_time_source_invalid")
        return replace(
            item,
            local_date=local.local.date(),
            local_time=local.local.time().isoformat(),
            time_zone=policy.zone,
        )

    def page(
        self,
        period: CalendarRange,
        filters: CalendarFilters,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> CalendarPage:
        if isinstance(self.human, Installation) and (
            filters.kind not in (CalendarKind.PLANNED, CalendarKind.DUE)
            or filters != CalendarFilters(filters.kind)
            or (period.end - period.start).days > 90
        ):
            raise Forbidden("permission_denied")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("invalid_page_size")
        with self.transactions.read() as unit:
            home, _ = self._read(unit)
        policy = TimePolicy(home.time_zone, self.times.data_identity)
        start, end = self._boundary(period.start, policy), self._boundary(period.end, policy)
        with self.transactions.read() as unit:
            current, actor = self._read(unit)
            if current != home:
                raise Conflict("calendar_context_changed")
            if (
                filters.member_id is not None
                and unit.members.get(home.household_id, filters.member_id) is None
            ):
                raise Forbidden("permission_denied")
            if filters.category is not None:
                require_active_category(unit, home.household_id, filters.category)
            after = None
            if cursor is not None:
                try:
                    label, token = cursor.split("~", 1)
                    kind = CalendarKind(label)
                except ValueError:
                    raise InvalidInput("invalid_calendar_cursor") from None
                binding = self._binding(home, actor, period, filters, limit, kind)
                after = CalendarPosition(kind, self.cursors.decode(binding, token))
            count, occurrence_count, candidates = unit.calendar.page(
                home.household_id,
                period,
                filters,
                start,
                end,
                limit + 1,
                after,
            )
            entries = tuple(self._entry(unit, candidate) for candidate in candidates[:limit])
            next_cursor = None
            if len(candidates) > limit:
                position = candidates[limit - 1].position
                binding = self._binding(home, actor, period, filters, limit, position.kind)
                next_cursor = (
                    f"{position.kind.value}~{self.cursors.encode(binding, position.source_id)}"
                )
            pending = (
                unit.calendar.rules_pending(home.household_id)
                or unit.recurrence.relative_sources_pending(home.household_id)
                or bool(
                    unit.tasks.lifecycle_sources(
                        home.household_id,
                        limit=1,
                        after=unit.recurrence.relative_inbox_after(home.household_id),
                    )
                )
            )
        return CalendarPage(
            period,
            policy.zone,
            tuple(self._localize(item, policy) for item in entries),
            count,
            occurrence_count,
            next_cursor,
            pending,
        )
