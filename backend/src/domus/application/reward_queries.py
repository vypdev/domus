"""Private Family reward projections bound to the current household member."""

from dataclasses import dataclass

from domus.application.authorization import HouseholdAccess
from domus.application.fixed_materialization import MaintenanceScope
from domus.application.ports import Transactions
from domus.application.reward_funding import reward_balance
from domus.application.task_ports import TaskCursors
from domus.domain.identity import HumanIdentity, Permission, allows, effective_role
from domus.domain.rewards import Redemption, RewardBalance, RewardOffer
from domus.domain.storage import JsonDocument


@dataclass(frozen=True, slots=True)
class CatalogReward:
    offer: RewardOffer
    eligible: bool


@dataclass(frozen=True, slots=True)
class RewardsView:
    enabled: bool
    revision: int
    may_manage: bool
    balance: RewardBalance
    catalog: tuple[CatalogReward, ...]
    requests: tuple[Redemption, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class RewardQueries:
    store: Transactions
    scope: MaintenanceScope
    human: HumanIdentity
    cursors: TaskCursors

    def report(self, *, limit: int, cursor: str | None) -> RewardsView:
        with self.store.read() as unit:
            home = self.scope.require(unit).household_id
            member = HouseholdAccess(self.human).require(unit, home, Permission.HOUSEHOLD_READ)
            policy = unit.policies.get(home)
            assert policy is not None
            role = effective_role(self.human, member, policy)
            assert role is not None
            binding = JsonDocument.from_value(
                {
                    "query": "family-rewards-v1",
                    "installation": self.scope.installation.instance_id,
                    "channel": self.scope.installation.channel,
                    "household": home,
                    "member": member.member_id,
                    "membership_revision": member.revision,
                    "policy_revision": policy.revision,
                    "role": role.value,
                    "limit": limit,
                }
            )
            after = None if cursor is None else self.cursors.decode(binding, cursor)
            setting = unit.rewards.setting(home)
            balance = reward_balance(
                unit, home, member.member_id, unit.points.member_balance(home, member.member_id)
            )
            requests = unit.rewards.requests(home, member.member_id, after=after, limit=limit + 1)
            next_cursor = (
                self.cursors.encode(binding, requests[limit - 1].redemption_id)
                if len(requests) > limit
                else None
            )
            return RewardsView(
                setting is not None and setting.enabled,
                0 if setting is None else setting.revision,
                allows(self.human, member, policy, Permission.POINTS_MANAGE, home),
                balance,
                tuple(
                    CatalogReward(offer, role in offer.eligible_roles)
                    for offer in unit.rewards.catalog(home)
                ),
                requests[:limit],
                next_cursor,
            )
