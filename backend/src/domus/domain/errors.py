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


class Forbidden(DomusError):
    """Current authority does not permit the requested action."""


class StorageBusy(DomusError):
    """A bounded writer slot was not obtained; identical retry is possible."""


class StorageFailure(DomusError):
    """Persistence failed without exposing driver or filesystem details."""


class DatabaseRejected(DomusError):
    """Schema or installation identity cannot be safely opened for mutation."""
