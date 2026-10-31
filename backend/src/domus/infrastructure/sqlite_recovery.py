"""Scoped recovery repository keeps immutable target bindings and optimistic transitions."""

import sqlite3
from dataclasses import dataclass, replace
from typing import cast

from domus.domain.errors import Conflict, DomusError, InvalidInput, StorageFailure
from domus.domain.identity import AdministratorMapping, MappingMode
from domus.domain.recovery import RecoveryRequest, RecoveryState, validate_recovery_time
from domus.domain.storage import Installation, JsonDocument

_COLUMNS = (
    "request_id",
    "household_id",
    "target_ha_user_id",
    "revision",
    "state",
    "created_at",
    "expires_at",
)


def _indexed(request: RecoveryRequest) -> tuple[object, ...]:
    return (
        request.request_id,
        request.household_id,
        request.target_ha_user_id,
        request.revision,
        request.state.value,
        request.created_at,
        request.expires_at,
    )


def _record(row: sqlite3.Row | None) -> RecoveryRequest | None:
    if row is None:
        return None
    try:
        document = JsonDocument(row["detail"])
        value = document.decode()
        request = RecoveryRequest(
            cast(str, value["request_id"]),
            cast(str, value["household_id"]),
            cast(str, value["target_ha_user_id"]),
            Installation(cast(str, value["instance_id"]), cast(str, value["channel"])),
            AdministratorMapping(
                MappingMode(cast(str, value["mapping_mode"])),
                cast(str | None, value["mapping_target"]),
            ),
            cast(int, value["policy_revision"]),
            cast(str | None, value["member_id"]),
            cast(int, value["member_revision"]),
            cast(int, value["created_at"]),
            cast(int, value["expires_at"]),
            RecoveryState(cast(str, value["state"])),
            cast(int, value["revision"]),
            cast(int | None, value["approved_at"]),
            cast(int | None, value["closed_at"]),
        )
        if request.document() != document or tuple(row[name] for name in _COLUMNS) != _indexed(
            request
        ):
            raise ValueError("inconsistent recovery record")
        return request
    except DomusError, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_recovery_record") from None


@dataclass
class SQLiteRecoveries:
    connection: sqlite3.Connection

    def get(self, household_id: str, request_id: str) -> RecoveryRequest | None:
        return _record(
            self.connection.execute(
                "SELECT * FROM recovery_requests WHERE household_id=? AND request_id=?",
                (household_id, request_id),
            ).fetchone()
        )

    def pending(
        self, household_id: str, now: int, *, limit: int = 257
    ) -> tuple[RecoveryRequest, ...]:
        validate_recovery_time(now)
        if type(limit) is not int or not 1 <= limit <= 257:
            raise InvalidInput("invalid_page_size")
        return tuple(
            cast(RecoveryRequest, _record(row))
            for row in self.connection.execute(
                "SELECT * FROM recovery_requests WHERE household_id=? "
                "AND state IN ('pending','approved') AND created_at<=? AND expires_at>? "
                "ORDER BY request_id LIMIT ?",
                (household_id, now, now, limit),
            )
        )

    def save(self, request: RecoveryRequest, expected_revision: int) -> None:
        if request.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        values = (*_indexed(request), request.document().encoded)
        if expected_revision == 0:
            try:
                self.connection.execute(
                    "INSERT INTO recovery_requests VALUES (?,?,?,?,?,?,?,?)", values
                )
            except sqlite3.IntegrityError:
                raise Conflict("recovery_exists") from None
        else:
            current = self.get(request.household_id, request.request_id)
            if current is None:
                raise Conflict("revision_conflict")
            if current.approved_at is not None and request.approved_at != current.approved_at:
                raise Conflict("recovery_binding_changed")
            if (
                replace(
                    current,
                    state=request.state,
                    revision=request.revision,
                    approved_at=request.approved_at,
                    expires_at=request.expires_at,
                    closed_at=request.closed_at,
                )
                != request
            ):
                raise Conflict("recovery_binding_changed")
            if (
                self.connection.execute(
                    "UPDATE recovery_requests SET revision=?,state=?,expires_at=?,detail=? "
                    "WHERE household_id=? AND request_id=? AND revision=?",
                    (
                        request.revision,
                        request.state.value,
                        request.expires_at,
                        request.document().encoded,
                        request.household_id,
                        request.request_id,
                        expected_revision,
                    ),
                ).rowcount
                != 1
            ):
                raise Conflict("revision_conflict")
