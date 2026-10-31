"""Parameterized identity repositories; policy decisions remain in the domain."""

import sqlite3
from dataclasses import dataclass
from typing import cast

from domus.domain.errors import Conflict, DomusError, StorageFailure
from domus.domain.identity import (
    AdministratorMapping,
    HouseholdPolicy,
    MappingMode,
    Member,
    MemberStatus,
    Permission,
    PermissionRule,
    ProfileRule,
    Role,
)
from domus.domain.storage import JsonDocument, JsonObject


def _rules(encoded: str) -> list[JsonObject]:
    rules = JsonDocument(encoded).decode()["rules"]
    if type(rules) is not list or any(type(rule) is not dict for rule in rules):
        raise ValueError("invalid stored rule shape")
    return cast(list[JsonObject], rules)


def _member(row: sqlite3.Row | None) -> Member | None:
    if row is None:
        return None
    try:
        return Member(
            row["member_id"],
            row["household_id"],
            row["ha_user_id"],
            Role(row["role"]),
            MemberStatus(row["status"]),
            row["revision"],
            tuple(
                PermissionRule(Permission(cast(str, rule["permission"])), cast(bool, rule["allow"]))
                for rule in _rules(row["exceptions"])
            ),
        )
    except DomusError, KeyError, TypeError, ValueError:
        raise StorageFailure("invalid_identity_record") from None


@dataclass
class SQLiteMembers:
    connection: sqlite3.Connection

    def get(self, household_id: str, member_id: str) -> Member | None:
        return _member(
            self.connection.execute(
                "SELECT * FROM members WHERE household_id=? AND member_id=?",
                (household_id, member_id),
            ).fetchone()
        )

    def by_user(self, household_id: str, ha_user_id: str) -> Member | None:
        return _member(
            self.connection.execute(
                "SELECT * FROM members WHERE household_id=? AND ha_user_id=?",
                (household_id, ha_user_id),
            ).fetchone()
        )

    def list(self, household_id: str) -> tuple[Member, ...]:
        rows = self.connection.execute(
            "SELECT * FROM members WHERE household_id=? ORDER BY member_id",
            (household_id,),
        )
        return tuple(cast(Member, _member(row)) for row in rows)

    def save(self, member: Member, expected_revision: int) -> None:
        if member.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        exceptions = JsonDocument.from_value(
            {
                "rules": [
                    {"permission": rule.permission.value, "allow": rule.allow}
                    for rule in member.exceptions
                ]
            }
        ).encoded
        values = (member.role.value, member.status.value, member.revision, exceptions)
        if expected_revision == 0:
            try:
                self.connection.execute(
                    "INSERT INTO members(role,status,revision,exceptions,member_id,"
                    "household_id,ha_user_id) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (*values, member.member_id, member.household_id, member.ha_user_id),
                )
            except sqlite3.IntegrityError:
                raise Conflict("member_exists") from None
        elif (
            self.connection.execute(
                "UPDATE members SET role=?,status=?,revision=?,exceptions=? "
                "WHERE member_id=? AND household_id=? AND ha_user_id=? AND revision=?",
                (
                    *values,
                    member.member_id,
                    member.household_id,
                    member.ha_user_id,
                    expected_revision,
                ),
            ).rowcount
            != 1
        ):
            raise Conflict("revision_conflict")


@dataclass
class SQLitePolicies:
    connection: sqlite3.Connection

    def get(self, household_id: str) -> HouseholdPolicy | None:
        row = self.connection.execute(
            "SELECT * FROM household_policy WHERE household_id=?",
            (household_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            return HouseholdPolicy(
                row["household_id"],
                AdministratorMapping(MappingMode(row["mapping_mode"]), row["target_ha_user_id"]),
                row["revision"],
                tuple(
                    ProfileRule(
                        Role(cast(str, rule["role"])),
                        Permission(cast(str, rule["permission"])),
                        cast(bool, rule["allow"]),
                    )
                    for rule in _rules(row["adjustments"])
                ),
            )
        except DomusError, KeyError, TypeError, ValueError:
            raise StorageFailure("invalid_identity_record") from None

    def save(self, policy: HouseholdPolicy, expected_revision: int) -> None:
        if policy.revision != expected_revision + 1:
            raise Conflict("revision_conflict")
        adjustments = JsonDocument.from_value(
            {
                "rules": [
                    {
                        "role": rule.role.value,
                        "permission": rule.permission.value,
                        "allow": rule.allow,
                    }
                    for rule in policy.adjustments
                ]
            }
        ).encoded
        values = (
            policy.mapping.mode.value,
            policy.mapping.target_ha_user_id,
            policy.revision,
            adjustments,
            policy.household_id,
        )
        if expected_revision == 0:
            try:
                self.connection.execute(
                    "INSERT INTO household_policy(mapping_mode,target_ha_user_id,"
                    "revision,adjustments,household_id) "
                    "VALUES (?,?,?,?,?)",
                    values,
                )
            except sqlite3.IntegrityError:
                raise Conflict("policy_exists") from None
        elif (
            self.connection.execute(
                "UPDATE household_policy SET mapping_mode=?,target_ha_user_id=?,"
                "revision=?,adjustments=? "
                "WHERE household_id=? AND revision=?",
                (*values, expected_revision),
            ).rowcount
            != 1
        ):
            raise Conflict("revision_conflict")
