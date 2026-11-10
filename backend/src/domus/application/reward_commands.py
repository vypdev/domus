"""Current-authority reward mutations serialized with the existing Points writer."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum

from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.reward_funding import reconcile_reward_funding, reward_balance
from domus.domain.errors import Conflict, Forbidden, InvalidInput, NotFound
from domus.domain.identity import HumanIdentity, Member, Permission, Role, effective_role
from domus.domain.rewards import (
    FundingSource,
    Redemption,
    RewardBalance,
    RewardDecision,
    RewardOffer,
    RewardSetting,
    RewardSpend,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt, validate_identifier

CATALOG_LIMIT = 64
OPEN_REDEMPTION_LIMIT = 32


class RewardAction(StrEnum):
    CONFIGURE = "reward.configure"
    OFFER = "reward.offer"
    REQUEST = "reward.request"
    APPROVE = "reward.approve"
    DELIVER = "reward.deliver"
    CANCEL = "reward.cancel"

    @property
    def permission(self) -> Permission:
        if self in {RewardAction.REQUEST, RewardAction.CANCEL}:
            return Permission.HOUSEHOLD_READ
        return Permission.POINTS_MANAGE


def _document(value: object) -> JsonDocument:
    return JsonDocument(json.dumps(value))


def _expected(actual: int, expected: int) -> None:
    if type(expected) is not int or not 0 <= expected <= 2**63 - 1:
        raise InvalidInput("invalid_revision")
    if actual != expected:
        raise Conflict("revision_conflict")


def _scope_original(action: RewardAction, member: Member, receipt: Receipt) -> Receipt:
    if action.permission is Permission.HOUSEHOLD_READ:
        if receipt.result.decode().get("requester_member_id") != member.member_id:
            raise Forbidden("permission_denied")
    return receipt


def _change(result: dict[str, object], detail: object) -> Change:
    document = _document(result)
    return Change(document, _document(detail), document)


def _redemption_change(redemption: Redemption, *, own: bool) -> Change:
    result: dict[str, object] = {
        "redemption_id": redemption.redemption_id,
        "stage": redemption.stage,
        "revision": redemption.revision,
    }
    if own:
        result["requester_member_id"] = redemption.member_id
    return _change(result, asdict(redemption))


def _role(unit: UnitOfWork, home: str, human: HumanIdentity, member: Member) -> Role:
    policy = unit.policies.get(home)
    assert policy is not None
    role = effective_role(human, member, policy)
    assert role is not None
    return role


@dataclass(frozen=True, slots=True)
class RewardCommands:
    store: Transactions
    actor: CurrentHuman
    clock: Clock
    identifiers: Identifiers
    home: str = "home"

    def _execute(
        self,
        action: RewardAction,
        key: str,
        request: object,
        apply: Callable[[UnitOfWork, HumanIdentity, Member], Change],
    ) -> Receipt:
        human = self.actor.current()
        access = HouseholdAccess(human)
        auth = MembershipAuthorization(access, action.value, action.permission)
        command = CommandKey(self.home, human.ha_user_id, action.value, key)
        commands = AtomicCommands(self.store, auth, self.clock, self.identifiers)
        with self.store.write() as unit:
            member = access.require(unit, self.home, action.permission)
            receipt = commands.in_unit(
                unit, command, _document(request), lambda writer: apply(writer, human, member)
            )
            return _scope_original(action, member, receipt)

    def configure(self, key: str, enabled: bool, expected_revision: int) -> Receipt:
        def apply(unit: UnitOfWork, _human: HumanIdentity, _member: Member) -> Change:
            current = unit.rewards.setting(self.home)
            _expected(0 if current is None else current.revision, expected_revision)
            setting = RewardSetting(enabled, expected_revision + 1)
            unit.rewards.save_setting(self.home, setting)
            return _change(asdict(setting), asdict(setting))

        return self._execute(
            RewardAction.CONFIGURE,
            key,
            {"enabled": enabled, "expected_revision": expected_revision},
            apply,
        )

    def offer(
        self,
        key: str,
        offer_id: str | None,
        title: str,
        cost_minor: int,
        enabled: bool,
        eligible_roles: tuple[Role, ...],
        expected_revision: int,
    ) -> Receipt:
        if offer_id is not None:
            validate_identifier(offer_id)
        request = {
            "offer_id": offer_id,
            "title": title,
            "cost_minor": cost_minor,
            "enabled": enabled,
            "eligible_roles": eligible_roles,
            "expected_revision": expected_revision,
        }

        def apply(unit: UnitOfWork, _human: HumanIdentity, _member: Member) -> Change:
            if offer_id is None:
                _expected(0, expected_revision)
                if len(unit.rewards.catalog(self.home)) >= CATALOG_LIMIT:
                    raise Conflict("reward_catalog_capacity")
                identity = self.identifiers.new()
            else:
                current = unit.rewards.offer(self.home, offer_id)
                if current is None:
                    raise Forbidden("permission_denied")
                _expected(current.revision, expected_revision)
                identity = current.offer_id
            offer = RewardOffer(
                identity, title, cost_minor, enabled, eligible_roles, expected_revision + 1
            )
            unit.rewards.save_offer(self.home, offer)
            return _change(asdict(offer), asdict(offer))

        return self._execute(RewardAction.OFFER, key, request, apply)

    def request(self, key: str, offer_id: str, expected_revision: int) -> Receipt:
        validate_identifier(offer_id)

        def apply(unit: UnitOfWork, human: HumanIdentity, member: Member) -> Change:
            settings = unit.rewards.setting(self.home)
            if settings is None or not settings.enabled:
                raise Conflict("rewards_disabled")
            offer = unit.rewards.offer(self.home, offer_id)
            if offer is None or not offer.permits(_role(unit, self.home, human, member)):
                raise Forbidden("reward_unavailable")
            _expected(offer.revision, expected_revision)
            reserved, active = unit.rewards.reservations(self.home, member.member_id)
            if active >= OPEN_REDEMPTION_LIMIT:
                raise Conflict("reward_request_capacity")
            posted = unit.points.member_balance(self.home, member.member_id) - unit.rewards.spent(
                self.home, member.member_id
            )
            RewardBalance(posted, reserved).reserve(offer.cost_minor)
            redemption = Redemption.request(
                self.identifiers.new(), member.member_id, offer, self.clock.now()
            )
            unit.rewards.save_redemption(self.home, redemption)
            return _redemption_change(redemption, own=True)

        return self._execute(
            RewardAction.REQUEST,
            key,
            {"offer_id": offer_id, "expected_revision": expected_revision},
            apply,
        )

    def _transition(
        self,
        action: RewardAction,
        key: str,
        redemption_id: str,
        apply: Callable[[UnitOfWork, Member, Redemption], Change],
        payload: dict[str, object],
    ) -> Receipt:
        validate_identifier(redemption_id)

        def act(unit: UnitOfWork, _human: HumanIdentity, member: Member) -> Change:
            redemption = unit.rewards.redemption(self.home, redemption_id)
            if redemption is None or (
                action is RewardAction.CANCEL and redemption.member_id != member.member_id
            ):
                raise Forbidden("permission_denied")
            return apply(unit, member, redemption)

        return self._execute(action, key, {"redemption_id": redemption_id, **payload}, act)

    def approve(self, key: str, redemption_id: str) -> Receipt:
        def apply(unit: UnitOfWork, member: Member, before: Redemption) -> Change:
            balance = reward_balance(
                unit,
                self.home,
                before.member_id,
                unit.points.member_balance(self.home, before.member_id),
            )
            current = before.approve(RewardDecision(member.member_id, self.clock.now()), balance)
            unit.rewards.save_redemption(self.home, current)
            return _redemption_change(current, own=False)

        return self._transition(RewardAction.APPROVE, key, redemption_id, apply, {})

    def deliver(self, key: str, redemption_id: str) -> Receipt:
        def apply(unit: UnitOfWork, member: Member, before: Redemption) -> Change:
            balance = reward_balance(
                unit,
                self.home,
                before.member_id,
                unit.points.member_balance(self.home, before.member_id),
            )
            at = self.clock.now()
            delivered = before.deliver(RewardDecision(member.member_id, at), balance)
            unit.rewards.save_redemption(self.home, delivered)
            unit.rewards.post_spend(
                self.home,
                delivered.member_id,
                RewardSpend(delivered.redemption_id, delivered.title, delivered.cost_minor, at),
            )
            return _redemption_change(delivered, own=False)

        return self._transition(RewardAction.DELIVER, key, redemption_id, apply, {})

    def cancel(self, key: str, redemption_id: str, expected_revision: int, reason: str) -> Receipt:
        def apply(unit: UnitOfWork, member: Member, before: Redemption) -> Change:
            _expected(before.revision, expected_revision)
            at = self.clock.now()
            cancelled = before.cancel(RewardDecision(member.member_id, at), reason)
            unit.rewards.save_redemption(self.home, cancelled)
            reconcile_reward_funding(
                unit,
                self.home,
                before.member_id,
                FundingSource.CANCELLATION,
                redemption_id,
                at,
            )
            return _redemption_change(cancelled, own=True)

        return self._transition(
            RewardAction.CANCEL,
            key,
            redemption_id,
            apply,
            {"expected_revision": expected_revision, "reason": reason},
        )

    def original(self, action: RewardAction, key: str, human: HumanIdentity) -> Receipt:
        with self.store.read() as unit:
            member = HouseholdAccess(human).require(unit, self.home, action.permission)
            receipt = unit.receipts.get(CommandKey(self.home, human.ha_user_id, action.value, key))
            if receipt is None:
                raise NotFound("operation_missing")
            return _scope_original(action, member, receipt)
