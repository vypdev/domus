"""Complete requested CLI termination through the existing runtime cleanup."""

import signal
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import FrameType


class _TerminationRequested(BaseException):
    """Unwind the CLI into its owned-resource finally blocks."""


@contextmanager
def graceful_termination() -> Iterator[Callable[[], None]]:
    """Yield a callback that defers further SIGTERM requests during cleanup."""
    stopping = False

    def begin_cleanup() -> None:
        nonlocal stopping
        stopping = True

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        if not stopping:
            begin_cleanup()
            raise _TerminationRequested

    previous = signal.signal(signal.SIGTERM, request_stop)
    try:
        try:
            yield begin_cleanup
        except _TerminationRequested:
            pass
    finally:
        signal.signal(signal.SIGTERM, previous)
