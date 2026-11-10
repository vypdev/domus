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
from domus.domain.identity import HumanIdentity, Permission, validate_revision
from domus.domain.inventory import (
    MAX_STOCK_UNITS,
    BaseUnit,
    CatalogProduct,
    EffectKind,
    InventoryEffect,
    MovementKind,
    ReplenishmentPolicy,
    StockMovement,
    stock_quantity,
    stock_units,
    validate_stock_reason,
)
from domus.domain.shopping import (
    MAX_SESSION_ITEMS,
    MIN_SESSION_ITEMS,
    Purchase,
    PurchaseReceipt,
    PurchaseSession,
    SessionSelection,
)
from domus.domain.shopping_needs import ShoppingExtra
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
                MovementKind.TASK_CONSUMPTION if corrects is None else MovementKind.TASK_CORRECTION,
                posted,
                corrects,
            ),
            balance - used,
        )
        return InventoryMaterialResult(posting=posted)


class CatalogAction(StrEnum):
    REGISTER = "inventory.register-product"
    INTAKE = "inventory.intake"
    ADJUST = "inventory.adjust"
    CORRECT_INTAKE = "inventory.correct-intake"
    CONFIGURE_REPLENISHMENT = "inventory.configure-replenishment"
    PURCHASE = "shopping.purchase"
    RECEIVE_PURCHASE = "shopping.receive"
    POST_RECEIPT = "shopping.post-receipt"
    ADD_EXTRA = "shopping.add-extra"
    CLEAR_EXTRA = "shopping.clear-extra"
    RECORD_SESSION = "shopping.record-session"


def _permission(action: str) -> Permission:
    if action == CatalogAction.ADD_EXTRA:
        return Permission.SHOPPING_REQUEST
    if action in (
        CatalogAction.PURCHASE,
        CatalogAction.RECEIVE_PURCHASE,
        CatalogAction.CLEAR_EXTRA,
        CatalogAction.RECORD_SESSION,
    ):
        return Permission.SHOPPING_MANAGE
    return Permission.INVENTORY_MANAGE


def _shopping_quantity(quantity: MaterialQuantity, unit: BaseUnit) -> int:
    if quantity.is_zero:
        raise InvalidInput("invalid_material_quantity")
    if quantity.precision > unit.precision:
        raise InvalidInput("invalid_material_precision")
    return stock_units(quantity)


def _shopping_item(
    product_id: str | None, name: str | None, quantity: MaterialQuantity
) -> JsonDocument:
    if (product_id is None) == (name is None):
        raise InvalidInput("invalid_shopping_item")
    if name is not None:
        validate_task_text(name, 160, required=True)
    return JsonDocument.from_value(
        {"product_id": product_id, "name": name, "quantity": quantity.value}
    )


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
        permission = _permission(action)
        authority = MembershipAuthorization(access, action, permission)

        def change(unit: UnitOfWork) -> Change:
            member = access.require(unit, self.household_id, permission)
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
        *,
        source_key: str | None = None,
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
            source_key or JsonDocument.from_value(asdict(command)).fingerprint,
            member,
            received,
            self.clock.now(),
            "receipt",
            MovementKind.INTAKE,
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
            product = self._product(stock, product_id)
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

    def adjust(self, key: str, product_id: str, quantity: str, reason: str) -> Receipt:
        validate_stock_reason(reason)
        magnitude = MaterialQuantity(quantity.removeprefix("-"))
        if magnitude.is_zero:
            raise InvalidInput("invalid_material_quantity")
        delta = stock_units(magnitude)
        if quantity.startswith("-"):
            delta = -delta
        payload = JsonDocument.from_value(
            {"product_id": product_id, "quantity": quantity, "reason": reason}
        )

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            stock = unit.inventory
            product = self._product(stock, product_id)
            product.binding(self.household_id).require_quantity(magnitude)
            return self._change_stock(
                stock, product, member, command, delta, reason, MovementKind.ADJUSTMENT
            )

        return self._execute(CatalogAction.ADJUST.value, key, payload, apply)

    def correct_intake(self, key: str, product_id: str, movement_id: str, reason: str) -> Receipt:
        validate_stock_reason(reason)
        payload = JsonDocument.from_value(
            {"product_id": product_id, "movement_id": movement_id, "reason": reason}
        )

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            home, stock = self.household_id, unit.inventory
            product = self._product(stock, product_id)
            original = stock.movement_by_id(home, movement_id)
            if original is None or original.reference_id != product.reference_id:
                raise NotFound("inventory_movement_missing")
            if original.kind is not MovementKind.INTAKE:
                raise InvalidInput("inventory_correction_requires_intake")
            if stock.correction_id(home, movement_id) is not None:
                raise Conflict("inventory_intake_corrected")
            return self._change_stock(
                stock,
                product,
                member,
                command,
                -original.delta,
                reason,
                MovementKind.INTAKE_CORRECTION,
                corrects=original.movement_id,
            )

        return self._execute(CatalogAction.CORRECT_INTAKE.value, key, payload, apply)

    def _product(self, stock: InventoryRecords, product_id: str) -> CatalogProduct:
        product = stock.product(self.household_id, product_id)
        if product is None:
            raise NotFound("inventory_product_missing")
        return product

    def configure_replenishment(
        self,
        key: str,
        product_id: str,
        minimum: MaterialQuantity,
        target: MaterialQuantity,
        expected_revision: int,
    ) -> Receipt:
        if expected_revision != 0:
            validate_revision(expected_revision)
        payload = JsonDocument.from_value(
            {
                "product_id": product_id,
                "minimum": minimum.value,
                "target": target.value,
                "expected_revision": str(expected_revision),
            }
        )

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            stock, home = unit.inventory, self.household_id
            binding = self._product(stock, product_id).binding(home)
            binding.require_quantity(minimum)
            binding.require_quantity(target)
            current = stock.replenishment(home, product_id)
            if current.revision != expected_revision:
                raise Conflict("revision_conflict")
            policy = ReplenishmentPolicy(
                stock_units(minimum), stock_units(target), current.revision + 1
            )
            stock.save_replenishment(home, product_id, policy)
            return JsonDocument.from_value(
                {
                    "product_id": product_id,
                    "minimum": minimum.value,
                    "target": target.value,
                    "revision": str(policy.revision),
                }
            )

        return self._execute(CatalogAction.CONFIGURE_REPLENISHMENT.value, key, payload, apply)

    def _change_stock(
        self,
        stock: InventoryRecords,
        product: CatalogProduct,
        member: str,
        command: CommandKey,
        delta: int,
        reason: str,
        kind: MovementKind,
        *,
        corrects: str | None = None,
    ) -> JsonDocument:
        home, reference = self.household_id, product.reference_id
        balance = stock.balance(home, reference) + delta
        if balance < stock.reserved(home, reference):
            raise Conflict("inventory_insufficient_stock")
        if balance > MAX_STOCK_UNITS:
            raise Conflict("inventory_stock_capacity")
        movement = StockMovement(
            home,
            reference,
            self.identifiers.new(),
            JsonDocument.from_value(asdict(command)).fingerprint,
            member,
            delta,
            self.clock.now(),
            reason,
            kind,
            corrects=corrects,
        )
        stock.append(movement, balance)
        return JsonDocument.from_value(
            {
                "product_id": product.product_id,
                "movement_id": movement.movement_id,
                "base_unit": product.base_unit.value,
                "quantity": stock_quantity(delta),
                "corrects": corrects,
            }
        )

    def original(self, action: CatalogAction, key: str, human: HumanIdentity) -> Receipt:
        with self.transactions.read() as unit:
            home = self.household_id
            HouseholdAccess(human).require(unit, home, _permission(action))
            receipt = unit.receipts.get(CommandKey(home, human.ha_user_id, action.value, key))
            if receipt is None:
                raise NotFound("operation_missing")
            return receipt

    def _record_purchase(
        self,
        unit: UnitOfWork,
        member: str,
        created_at: int,
        product_id: str | None,
        name: str | None,
        quantity: MaterialQuantity,
    ) -> str:
        home = self.household_id
        if product_id is not None:
            product = self._product(unit.inventory, product_id)
            label, base_unit = product.name, product.base_unit
            if unit.shopping.outstanding(home, product_id):
                raise Conflict("shopping_purchase_open")
        else:
            assert name is not None
            label, base_unit = name, BaseUnit.PIECE
        purchased = _shopping_quantity(quantity, base_unit)
        purchase_id = self.identifiers.new()
        unit.shopping.add_purchase(
            home,
            Purchase(
                purchase_id,
                product_id,
                label,
                base_unit,
                purchased,
                0,
                0,
                1,
                member,
                created_at,
            ),
        )
        return purchase_id

    def purchase(
        self, key: str, product_id: str | None, name: str | None, quantity: MaterialQuantity
    ) -> Receipt:
        payload = _shopping_item(product_id, name, quantity)

        def apply(unit: UnitOfWork, member: str, _command: CommandKey) -> JsonDocument:
            purchase_id = self._record_purchase(
                unit, member, self.clock.now(), product_id, name, quantity
            )
            return JsonDocument.from_value({"purchase_id": purchase_id})

        return self._execute(CatalogAction.PURCHASE.value, key, payload, apply)

    def record_purchase_session(self, key: str, items: tuple[SessionSelection, ...]) -> Receipt:
        selected = {(item.product_id, item.extra_id) for item in items}
        if not MIN_SESSION_ITEMS <= len(items) <= MAX_SESSION_ITEMS or len(selected) != len(items):
            raise InvalidInput("invalid_shopping_session")
        if any((product is None) == (extra is None) for product, extra in selected):
            raise InvalidInput("invalid_shopping_item")
        payload = JsonDocument.from_value(
            {
                "items": [
                    {
                        "product_id": item.product_id,
                        "extra_id": item.extra_id,
                        "quantity": item.quantity.value,
                    }
                    for item in items
                ]
            }
        )

        def apply(unit: UnitOfWork, member: str, _command: CommandKey) -> JsonDocument:
            home = self.household_id
            session = PurchaseSession(self.identifiers.new(), member, self.clock.now())
            purchase_ids = []
            for item in items:
                name = None
                if item.extra_id is not None:
                    extra = unit.shopping.extra(home, item.extra_id)
                    if extra is None or extra.product_id is not None:
                        raise NotFound("shopping_extra_missing")
                    if extra.cleared_at is not None:
                        raise Conflict("shopping_extra_cleared")
                    name = extra.name
                purchase_ids.append(
                    self._record_purchase(
                        unit, member, session.created_at, item.product_id, name, item.quantity
                    )
                )
            unit.shopping.add_session(home, session, tuple(purchase_ids))
            return JsonDocument.from_value(
                {"session_id": session.session_id, "purchase_ids": purchase_ids}
            )

        return self._execute(CatalogAction.RECORD_SESSION.value, key, payload, apply)

    def add_extra(
        self, key: str, product_id: str | None, name: str | None, quantity: MaterialQuantity
    ) -> Receipt:
        payload = _shopping_item(product_id, name, quantity)

        def apply(unit: UnitOfWork, member: str, _command: CommandKey) -> JsonDocument:
            if product_id is None:
                assert name is not None
                label, base_unit = name, BaseUnit.PIECE
            else:
                product = self._product(unit.inventory, product_id)
                label, base_unit = product.name, product.base_unit
            extra = ShoppingExtra(
                self.identifiers.new(),
                product_id,
                label,
                base_unit,
                _shopping_quantity(quantity, base_unit),
                member,
                self.clock.now(),
            )
            unit.shopping.add_extra(self.household_id, extra)
            return JsonDocument.from_value({"extra_id": extra.extra_id})

        return self._execute(CatalogAction.ADD_EXTRA.value, key, payload, apply)

    def clear_extra(self, key: str, extra_id: str) -> Receipt:
        payload = JsonDocument.from_value({"extra_id": extra_id})

        def apply(unit: UnitOfWork, member: str, _command: CommandKey) -> JsonDocument:
            home = self.household_id
            extra = unit.shopping.extra(home, extra_id)
            if extra is None:
                raise NotFound("shopping_extra_missing")
            if extra.cleared_at is not None:
                raise Conflict("shopping_extra_cleared")
            unit.shopping.clear_extra(home, extra_id, member, self.clock.now())
            return payload

        return self._execute(CatalogAction.CLEAR_EXTRA.value, key, payload, apply)

    def _purchase(self, unit: UnitOfWork, purchase_id: str) -> Purchase:
        purchase = unit.shopping.purchase(self.household_id, purchase_id)
        if purchase is None:
            raise NotFound("shopping_purchase_missing")
        return purchase

    def receive_purchase(
        self, key: str, purchase_id: str, quantity: MaterialQuantity, expected_revision: int
    ) -> Receipt:
        validate_revision(expected_revision)
        payload = JsonDocument.from_value(
            {
                "purchase_id": purchase_id,
                "quantity": quantity.value,
                "expected_revision": str(expected_revision),
            }
        )

        def apply(unit: UnitOfWork, member: str, _command: CommandKey) -> JsonDocument:
            purchase = self._purchase(unit, purchase_id)
            received = _shopping_quantity(quantity, purchase.base_unit)
            changed = purchase.receive(received, expected_revision)
            receipt_id = self.identifiers.new()
            home = self.household_id
            unit.shopping.add_receipt(
                home,
                PurchaseReceipt(receipt_id, purchase_id, received, member, self.clock.now(), None),
            )
            unit.shopping.update_purchase(home, changed)
            return JsonDocument.from_value({"purchase_id": purchase_id, "receipt_id": receipt_id})

        return self._execute(CatalogAction.RECEIVE_PURCHASE.value, key, payload, apply)

    def post_purchase_receipt(self, key: str, purchase_id: str, receipt_id: str) -> Receipt:
        payload = JsonDocument.from_value({"purchase_id": purchase_id, "receipt_id": receipt_id})

        def apply(unit: UnitOfWork, member: str, command: CommandKey) -> JsonDocument:
            home = self.household_id
            purchase = self._purchase(unit, purchase_id)
            receipt = unit.shopping.receipt(home, receipt_id)
            if receipt is None or receipt.purchase_id != purchase_id:
                raise NotFound("shopping_receipt_missing")
            if purchase.product_id is None:
                raise InvalidInput("shopping_receipt_untracked")
            if receipt.movement_id is not None:
                raise Conflict("shopping_receipt_posted")
            product = self._product(unit.inventory, purchase.product_id)
            movement = self._receive_stock(
                unit.inventory,
                product.binding(home),
                MaterialQuantity(stock_quantity(receipt.quantity)),
                member,
                command,
                source_key=receipt.stock_source,
            )
            unit.shopping.link_movement(home, receipt_id, movement.movement_id)
            unit.shopping.update_purchase(home, purchase.post(receipt.quantity))
            return JsonDocument.from_value(
                {**payload.decode(), "movement_id": movement.movement_id}
            )

        return self._execute(CatalogAction.POST_RECEIPT.value, key, payload, apply)

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
