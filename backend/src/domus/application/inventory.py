"""Own physical movements and task-linked commitments in the caller's transaction."""

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import cast

from domus.application.authorization import HouseholdAccess, MembershipAuthorization
from domus.application.commands import AtomicCommands, Change
from domus.application.identity_ports import CurrentHuman
from domus.application.inventory_ports import InventoryRecords
from domus.application.ports import Clock, Identifiers, Transactions, UnitOfWork
from domus.application.task_material_ports import InventoryMaterialResult, MaterialPostingRequest
from domus.domain.errors import Conflict, InvalidInput, NotFound, StorageFailure
from domus.domain.identity import HumanIdentity, Permission
from domus.domain.inventory import (
    MAX_STOCK_UNITS,
    BaseUnit,
    CatalogProduct,
    EffectKind,
    InventoryEffect,
    StockMovement,
    stock_units,
)
from domus.domain.storage import CommandKey, JsonDocument, Receipt
from domus.domain.task_material_values import (
    MaterialBinding,
    MaterialPendingReason,
    MaterialQuantity,
)
from domus.domain.task_materials import MaterialPosting
from domus.domain.task_values import validate_task_text


@dataclass(frozen=True, slots=True)
class InventorySettlement:
    records: InventoryRecords
    clock: Clock
    identifiers: Identifiers

    def resolve(
        self, household_id: str, actor_member_id: str, reference_id: str
    ) -> MaterialBinding | None:
        # TaskMaterialAccess has already proved actor and household inside this unit.
        return self.records.material(household_id, reference_id)

    def settle(self, request: MaterialPostingRequest) -> InventoryMaterialResult:
        intent = request.intent
        home, reference = intent.household_id, intent.line.binding.reference_id
        previous = self.records.movement(home, request.source_key)
        if previous is not None:
            return InventoryMaterialResult(posting=previous.posting)
        if self.records.material(home, reference) != intent.line.binding:
            return InventoryMaterialResult(pending_reason=MaterialPendingReason.BINDING_CHANGED)
        quantity = cast(MaterialQuantity, intent.quantity)
        used = stock_units(quantity)
        corrects = None
        if intent.posting is not None:
            corrects = intent.posting.movement_id
            original = self.records.movement_by_id(home, corrects)
            if original is None or original.posting != intent.posting:
                raise StorageFailure("invalid_inventory_posting_source")
            used -= stock_units(intent.posting.quantity)
        reservation = next(
            (
                item
                for item in self.records.effects(home, (intent.occurrence_id,))
                if item.kind is EffectKind.RESERVATION
                and item.reference_id == reference
                and item.line_id == intent.line.line_id
            ),
            None,
        )
        balance = self.records.balance(home, reference)
        available = balance - self.records.reserved(home, reference)
        usable = available + (0 if reservation is None else reservation.remaining)
        if used > usable or balance - used > MAX_STOCK_UNITS:
            return InventoryMaterialResult(pending_reason=MaterialPendingReason.STOCK_SHORTAGE)
        if reservation is not None and used > 0:
            self.records.update_effect(
                replace(
                    reservation,
                    remaining=max(0, reservation.remaining - used),
                    revision=reservation.revision + 1,
                ),
                reservation.revision,
            )
        posted = MaterialPosting(
            intent.intent_id,
            home,
            intent.occurrence_id,
            intent.cycle_id,
            intent.line.line_id,
            reference,
            intent.line.binding.revision,
            intent.revision,
            intent.effect_revision,
            quantity,
            self.identifiers.new(),
            self.identifiers.new(),
            self.clock.now(),
        )
        self.records.append(
            StockMovement(
                home,
                reference,
                posted.movement_id,
                request.source_key,
                request.actor_member_id,
                -used,
                posted.posted_at,
                intent.reason,
                posted,
                corrects,
            ),
            balance - used,
        )
        return InventoryMaterialResult(posting=posted)


class CatalogAction(StrEnum):
    REGISTER = "inventory.register-product"
    INTAKE = "inventory.intake"


@dataclass(frozen=True, slots=True)
class InventoryCommands:
    """Catalog and task integration use the same scoped physical ledger."""

    transactions: Transactions
    actor: CurrentHuman
    clock: Clock
    identifiers: Identifiers
    household_id: str = "home"

    def _execute(
        self,
        action: str,
        key: str,
        payload: JsonDocument,
        apply: Callable[[UnitOfWork, str, CommandKey], JsonDocument],
    ) -> Receipt:
        human = self.actor.current()
        command = CommandKey(self.household_id, human.ha_user_id, action, key)
        access = HouseholdAccess(human)
        authority = MembershipAuthorization(access, action, Permission.INVENTORY_MANAGE)

        def change(unit: UnitOfWork) -> Change:
            member = access.require(unit, self.household_id, Permission.INVENTORY_MANAGE)
            result = apply(unit, member.member_id, command)
            return Change(result, payload, JsonDocument.from_value({"version": 1, "kind": action}))

        return AtomicCommands(self.transactions, authority, self.clock, self.identifiers).execute(
            command, payload, change
        )

    def receive(self, key: str, binding: MaterialBinding, quantity: MaterialQuantity) -> Receipt:
        binding.require_quantity(quantity)
        if binding.household_id != self.household_id or binding.revision != 1 or quantity.is_zero:
            raise InvalidInput("invalid_inventory_receipt")
        payload = JsonDocument.from_value({"binding": asdict(binding), "quantity": quantity.value})

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            stock = unit.inventory
            home, reference = binding.household_id, binding.reference_id
            current = stock.material(home, reference)
            if current is None:
                stock.add_material(binding)
            elif current != binding:
                raise Conflict("inventory_binding_changed")
            movement = self._receive_stock(stock, binding, quantity, member, command)
            return JsonDocument.from_value({"movement_id": movement.movement_id})

        return self._execute("inventory.receive", key, payload, apply)

    def _receive_stock(
        self,
        stock: InventoryRecords,
        binding: MaterialBinding,
        quantity: MaterialQuantity,
        member: str,
        command: CommandKey,
    ) -> StockMovement:
        home, reference = binding.household_id, binding.reference_id
        received = stock_units(quantity)
        balance = stock.balance(home, reference) + received
        if balance > MAX_STOCK_UNITS:
            raise Conflict("inventory_stock_capacity")
        movement = StockMovement(
            home,
            reference,
            self.identifiers.new(),
            JsonDocument.from_value(asdict(command)).fingerprint,
            member,
            received,
            self.clock.now(),
            "receipt",
        )
        stock.append(movement, balance)
        return movement

    def register(self, key: str, name: str, base_unit: BaseUnit) -> Receipt:
        validate_task_text(name, 160, required=True)
        if not isinstance(base_unit, BaseUnit):
            raise InvalidInput("invalid_inventory_unit")
        payload = JsonDocument.from_value({"name": name, "base_unit": base_unit.value})

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            product = CatalogProduct(
                self.identifiers.new(), self.identifiers.new(), name, base_unit
            )
            unit.inventory.add_material(product.binding(self.household_id))
            unit.inventory.add_product(self.household_id, product)
            return JsonDocument.from_value({"product_id": product.product_id, **payload.decode()})

        return self._execute(CatalogAction.REGISTER.value, key, payload, apply)

    def intake(self, key: str, product_id: str, quantity: MaterialQuantity) -> Receipt:
        if quantity.is_zero:
            raise InvalidInput("invalid_inventory_receipt")
        payload = JsonDocument.from_value({"product_id": product_id, "quantity": quantity.value})

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            stock = unit.inventory
            product = stock.product(self.household_id, product_id)
            if product is None:
                raise NotFound("inventory_product_missing")
            binding = product.binding(self.household_id)
            binding.require_quantity(quantity)
            movement = self._receive_stock(stock, binding, quantity, member, command)
            return JsonDocument.from_value(
                {
                    "product_id": product.product_id,
                    "movement_id": movement.movement_id,
                    "base_unit": product.base_unit.value,
                    "quantity": quantity.value,
                }
            )

        return self._execute(CatalogAction.INTAKE.value, key, payload, apply)

    def original(self, action: CatalogAction, key: str, human: HumanIdentity) -> Receipt:
        with self.transactions.read() as unit:
            home = self.household_id
            HouseholdAccess(human).require(unit, home, Permission.INVENTORY_MANAGE)
            receipt = unit.receipts.get(CommandKey(home, human.ha_user_id, action.value, key))
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt

    def commit_effect(
        self,
        key: str,
        kind: EffectKind,
        reference_id: str,
        quantity: MaterialQuantity,
        *,
        occurrence_id: str | None = None,
    ) -> Receipt:
        if (
            not isinstance(kind, EffectKind)
            or quantity.is_zero
            or (occurrence_id is None and kind is EffectKind.RESERVATION)
        ):
            raise InvalidInput("invalid_inventory_effect")
        payload = JsonDocument.from_value(
            {
                "kind": kind.value,
                "reference_id": reference_id,
                "quantity": quantity.value,
                "occurrence_id": occurrence_id,
            }
        )

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            home, stock = self.household_id, unit.inventory
            binding = stock.material(home, reference_id)
            if binding is None:
                raise InvalidInput("invalid_material_reference")
            binding.require_quantity(quantity)
            line_id = None
            if occurrence_id is not None:
                work = unit.tasks.occurrence(home, occurrence_id)
                line = (
                    None
                    if work is None
                    else next(
                        (
                            item
                            for item in work.definition_snapshot.materials
                            if item.binding == binding
                        ),
                        None,
                    )
                )
                if line is None:
                    raise InvalidInput("invalid_material_reference")
                line_id = line.line_id
            amount = stock_units(quantity)
            if kind is EffectKind.RESERVATION and amount > stock.balance(
                home, reference_id
            ) - stock.reserved(home, reference_id):
                raise Conflict("inventory_insufficient_stock")
            value = InventoryEffect(
                home,
                self.identifiers.new(),
                kind,
                reference_id,
                occurrence_id,
                occurrence_id,
                line_id,
                amount,
            )
            stock.add_effect(value)
            return JsonDocument.from_value({"effect_id": value.effect_id})

        return self._execute("inventory.commit-effect", key, payload, apply)
