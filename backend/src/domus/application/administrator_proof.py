"""Prepare eligible administrator facts through ports before entering a writer transaction."""

from domus.application.identity_ports import HumanDirectory
from domus.domain.errors import Forbidden
from domus.domain.identity import (
    HouseholdPolicy,
    HumanIdentity,
    MappingMode,
    Member,
    MemberStatus,
    Role,
    effective_role,
)


def exact_human(human: HumanIdentity, user_id: str) -> HumanIdentity:
    if not isinstance(human, HumanIdentity) or human.ha_user_id != user_id:
        raise Forbidden("identity_mismatch")
    return human


def remaining_humans(
    policy: HouseholdPolicy,
    members: tuple[Member, ...],
    known: tuple[HumanIdentity, ...],
    directory: HumanDirectory,
) -> tuple[tuple[HumanIdentity, ...], bool]:
    """An omitted eligible candidate is a negative fact, never a transport fallback.

    Return whether external proof was needed so callers reprove their actor.
    The transition must still check these facts and local inventory atomically.
    """
    humans = {human.ha_user_id: human for human in known}
    if any(
        member.ha_user_id in humans
        and effective_role(humans[member.ha_user_id], member, policy) is Role.ADMINISTRATOR
        for member in members
    ):
        return known, False
    candidates = tuple(
        member.ha_user_id
        for member in members
        if member.status is MemberStatus.ACTIVE
        and member.ha_user_id not in humans
        and (
            member.role is Role.ADMINISTRATOR
            or policy.mapping.mode is MappingMode.ALL
            or policy.mapping.target_ha_user_id == member.ha_user_id
        )
    )
    if not candidates:
        return known, False
    resolved = directory.eligible(candidates)
    if type(resolved) is not tuple or len(resolved) > len(candidates):
        raise Forbidden("identity_mismatch")
    for candidate in resolved:
        if (
            not isinstance(candidate, HumanIdentity)
            or candidate.ha_user_id not in candidates
            or candidate.ha_user_id in humans
        ):
            raise Forbidden("identity_mismatch")
        humans[candidate.ha_user_id] = candidate
    return tuple(humans.values()), True
