"""Allowlisted domain failure classification is shared by HTTP deployment adapters."""

from domus.domain.errors import (
    Conflict,
    DomusError,
    Forbidden,
    IdentityUnavailable,
    InvalidInput,
    NotFound,
    StorageBusy,
    Unauthenticated,
)

PUBLIC_CODES = frozenset(
    {
        "session_required",
        "session_expired",
        "session_changed",
        "identity_mismatch",
        "ha_unavailable",
        "ha_rejected",
        "invalid_ha_protocol",
        "ha_subject_rejected",
        "ha_directory_forbidden",
        "invalid_login_material",
        "invalid_login_attempt",
        "login_attempt_expired",
        "login_attempt_exists",
        "login_capacity",
        "invalid_login_result",
        "session_exists",
        "session_capacity",
        "invalid_auth_value",
        "invalid_session_lease",
        "invalid_identifier",
        "invalid_session_lifetime",
        "permission_denied",
        "revision_conflict",
        "idempotency_conflict",
        "invalid_request",
        "sign_in_declined",
        "request_forbidden",
        "invalid_household",
        "invalid_time_zone",
        "invalid_revision",
        "invalid_administrator_mapping",
        "invalid_policy",
        "invalid_permission_rule",
        "protected_permission",
        "invalid_profile_rule",
        "invalid_member",
        "invalid_permission_rules",
        "invalid_profile_rules",
        "invalid_idempotency_key",
        "household_exists",
        "member_exists",
        "member_missing",
        "member_capacity",
        "mapping_target_inactive",
        "setup_provenance_required",
        "setup_administrator_mismatch",
        "ha_administrator_required",
        "identity_state_changed",
        "last_administrator",
        "household_configuration_required",
        "operation_missing",
        "storage_busy",
        "invalid_ingress_subject",
    }
)


def classify(error: DomusError) -> tuple[int, str]:
    if error.code not in PUBLIC_CODES or type(error) is DomusError:
        return 500, "internal_error"
    for kind, status in (
        (Unauthenticated, 401),
        (Forbidden, 403),
        (InvalidInput, 422),
        (Conflict, 409),
        (IdentityUnavailable, 503),
        (StorageBusy, 503),
        (NotFound, 404),
    ):
        if isinstance(error, kind):
            return status, error.code
    return 500, "internal_error"
