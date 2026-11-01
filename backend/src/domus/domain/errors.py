"""Safe application failures carry codes rather than provider exception text."""


class DomusError(Exception):
    """A stable, nonsecret failure that entrypoints can map to their own schemas."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class InvalidInput(DomusError):
    """An input cannot establish a valid domain value."""


class Conflict(DomusError):
    """Current durable state conflicts with the requested transition."""


class NotFound(DomusError):
    """An authorized scoped lookup has no matching record."""


class Forbidden(DomusError):
    """Current authority does not permit the requested action."""


class Unauthenticated(DomusError):
    """No current eligible identity/session can establish access."""


class IdentityRejected(Unauthenticated):
    """An explicit upstream rejection invalidates local session authority."""


class IdentityUnavailable(DomusError):
    """A bounded provider availability failure; never a mutation grant."""


class IntegrationUnavailable(DomusError):
    """A required domain integration cannot currently establish its own facts."""


class StorageBusy(DomusError):
    """A bounded writer slot was not obtained; identical retry is possible."""


class StorageFailure(DomusError):
    """Persistence failed without exposing driver or filesystem details."""


class DatabaseRejected(DomusError):
    """Schema or installation identity cannot be safely opened for mutation."""
