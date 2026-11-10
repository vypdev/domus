"""Reconcile existing approvals in the same writer as each balance change."""

from domus.application.ports import UnitOfWork
from domus.domain.rewards import FundingChange, FundingSource, RewardBalance


def reward_balance(unit: UnitOfWork, home: str, member_id: str, task_posted: int) -> RewardBalance:
    reserved, _ = unit.rewards.reservations(home, member_id)
    return RewardBalance(task_posted - unit.rewards.spent(home, member_id), reserved)


def reconcile_reward_funding(
    unit: UnitOfWork,
    home: str,
    member_id: str,
    source: FundingSource,
    source_id: str,
    at: int,
) -> None:
    approvals = unit.rewards.approved(home, member_id)
    if not approvals:
        return
    balance = reward_balance(unit, home, member_id, unit.points.member_balance(home, member_id))
    for original in approvals:
        current = original.reconcile_funding(balance)
        if current is not original:
            unit.rewards.save_redemption(home, current)
            unit.rewards.funding(
                home,
                FundingChange(
                    current.redemption_id, current.revision, source, source_id, current.stage, at
                ),
            )
