"""Project private ledger and work facts from one authorized read transaction."""

from dataclasses import dataclass

from domus.application.authorization import HouseholdAccess
from domus.application.calendar_queries import calendar_boundary
from domus.application.family_ports import FamilyLedgerEntry
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions
from domus.application.recurrence_ports import RecurrenceTimes
from domus.application.task_authorization import TaskAccess
from domus.application.task_ports import TaskCursors
from domus.domain.calendar_values import CalendarRange
from domus.domain.identity import HumanIdentity, Permission
from domus.domain.points import conserved_shares
from domus.domain.recurrence_time import TimePolicy
from domus.domain.storage import JsonDocument
from domus.domain.task_values import VerificationState


@dataclass(frozen=True, slots=True)
class FamilyReport:
    period: CalendarRange
    time_zone: str
    posted_minor: int
    available_minor: int
    earned_minor: int
    pending_verification_minor: int
    pending_posting_minor: int
    completed_count: int
    tracked_count: int
    elapsed_ms: int
    history: tuple[FamilyLedgerEntry, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class FamilyQueries:
    transactions: Transactions
    scope: MaintenanceScope
    human: HumanIdentity
    cursors: TaskCursors
    times: RecurrenceTimes

    def report(self, period: CalendarRange, *, limit: int, cursor: str | None) -> FamilyReport:
        with self.transactions.read() as unit:
            home = self.scope.require(unit)
            household_id = home.household_id
            HouseholdAccess(self.human).require(unit, household_id, Permission.HOUSEHOLD_READ)
            actor = TaskAccess(self.human).require(unit, household_id, Permission.TASKS_READ)
            member_id = actor.member.member_id
            policy = TimePolicy(home.time_zone, self.times.data_identity)
            start = calendar_boundary(period.start, self.times, policy)
            end = calendar_boundary(period.end, self.times, policy)
            binding = JsonDocument.from_value(
                {
                    "query": "family-history-v1",
                    "installation": self.scope.installation.instance_id,
                    "channel": self.scope.installation.channel,
                    "household": household_id,
                    "household_revision": home.revision,
                    "member": member_id,
                    "membership_revision": actor.member.revision,
                    "policy_revision": actor.identity_policy_revision,
                    "role": actor.role.value,
                    "start": period.start.isoformat(),
                    "end": period.end.isoformat(),
                    "limit": limit,
                }
            )
            after = None if cursor is None else self.cursors.decode(binding, cursor)
            posted, earned = unit.points.member_totals(household_id, member_id, start, end)
            history = unit.points.member_history(household_id, member_id, after, limit + 1)
            next_cursor = (
                self.cursors.encode(binding, history[limit - 1].event_id)
                if len(history) > limit
                else None
            )
            verification = posting = count = tracked = elapsed = 0
            for work in unit.points.member_work(household_id, member_id, start, end):
                cycle = work.cycle
                count += 1
                if work.started_at is not None:
                    tracked += 1
                    elapsed += cycle.performed_at - work.started_at
                if work.awaiting_credit:
                    rotation = unit.points.next_recipient(household_id, work.definition_id)
                    shares, _, _ = conserved_shares(cycle, rotation)
                    amount = dict(shares)[member_id]
                    if cycle.verification is VerificationState.PENDING:
                        verification += amount
                    else:
                        posting += amount
            return FamilyReport(
                period,
                home.time_zone,
                posted,
                posted,
                earned,
                verification,
                posting,
                count,
                tracked,
                elapsed,
                history[:limit],
                next_cursor,
            )
