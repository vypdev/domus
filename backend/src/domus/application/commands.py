"""One authorized durable command commits business facts and replay evidence together."""

from collections.abc import Callable
from dataclasses import dataclass

from domus.application.ports import (
    Clock,
    CommandAuthorization,
    Identifiers,
    Transactions,
    UnitOfWork,
)
from domus.domain.errors import Conflict
from domus.domain.storage import AuditEntry, CommandKey, JsonDocument, OutboxEvent, Receipt


@dataclass(frozen=True, slots=True)
class Change:
    result: JsonDocument
    audit_detail: JsonDocument
    event_payload: JsonDocument


@dataclass
class AtomicCommands:
    transactions: Transactions
    authorization: CommandAuthorization
    clock: Clock
    identifiers: Identifiers

    def replay(self, command: CommandKey, payload: JsonDocument) -> Receipt | None:
        """Authorize a read-only retry before preparing any external proof.

        A new effect still enters execute(), which checks current authority and
        replay again in the writer transaction. No provider I/O holds its lock.
        """
        with self.transactions.read() as unit:
            self.authorization.require(command, unit)
            previous = unit.receipts.get(command)
            if previous is not None and previous.payload_fingerprint != payload.fingerprint:
                raise Conflict("idempotency_conflict")
            return previous

    def execute(
        self,
        command: CommandKey,
        payload: JsonDocument,
        apply: Callable[[UnitOfWork], Change],
    ) -> Receipt:
        with self.transactions.write() as unit:
            self.authorization.require(command, unit)
            previous = unit.receipts.get(command)
            if previous is not None:
                if previous.payload_fingerprint != payload.fingerprint:
                    raise Conflict("idempotency_conflict")
                return previous
            change = apply(unit)
            operation_id, created_at = self.identifiers.new(), self.clock.now()
            receipt = Receipt(command, payload.fingerprint, operation_id, change.result, created_at)
            unit.receipts.add(receipt)
            unit.audit.append(AuditEntry(operation_id, command, change.audit_detail, created_at))
            unit.outbox.append(
                OutboxEvent(
                    operation_id,
                    command.household_id,
                    command.action,
                    change.event_payload,
                    created_at,
                )
            )
            return receipt
