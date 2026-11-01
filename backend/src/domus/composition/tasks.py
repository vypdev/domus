"""One task service factory binds production session adapters to shared application use cases."""

from collections.abc import Callable
from typing import Protocol

from domus.application.ports import Transactions
from domus.application.task_commands import TaskCommands
from domus.application.task_events import TaskEventFeed, TaskEventSource
from domus.application.task_queries import TaskQueries
from domus.domain.identity import HumanIdentity
from domus.domain.storage import Installation
from domus.entrypoints.task_http import TaskHTTPContext
from domus.infrastructure.application_runtime import SecureIdentifiers, SystemClock
from domus.infrastructure.auth_runtime import SecureEntropy
from domus.infrastructure.task_cursor import TaskCursor


class TaskSession(Protocol):
    def read(self) -> HumanIdentity: ...
    def current(self) -> HumanIdentity: ...


def task_event_source(store: Transactions, installation: Installation) -> TaskEventSource:
    return TaskEventFeed(store, installation)


def task_contexts(
    store: Transactions, installation: Installation
) -> Callable[[TaskSession], TaskHTTPContext]:
    clock, identifiers = SystemClock(), SecureIdentifiers()
    cursors = TaskCursor(clock, SecureEntropy().new().encode("ascii"))

    def context(actor: TaskSession) -> TaskHTTPContext:
        return TaskHTTPContext(
            lambda: TaskQueries(store, actor.read(), cursors, installation),
            TaskCommands(store, actor, clock, identifiers),
        )

    return context
