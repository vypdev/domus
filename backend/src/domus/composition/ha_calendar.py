"""Wire the opt-in installation query to the exact deployment boundary."""

from urllib.parse import urlsplit

from fastapi import FastAPI

from domus.application.calendar_queries import CalendarQueries
from domus.application.fixed_materialization import MaintenanceScope
from domus.domain.errors import InvalidInput
from domus.entrypoints.ha_calendar_http import CalendarBoundary, CalendarCredential, calendar_api
from domus.infrastructure.application_runtime import SystemClock
from domus.infrastructure.auth_runtime import SecureEntropy
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.task_cursor import TaskCursor


def attach_ha_calendar(
    app: FastAPI,
    store: SQLiteDatabase | None,
    digest: str | None,
    *,
    public_origin: str | None = None,
) -> None:
    if digest is None:
        return
    if store is None or (public_origin is not None and not public_origin.startswith("https://")):
        raise InvalidInput("ha_calendar_requires_persistent_secure_origin")
    installation = store.installation
    credential = CalendarCredential(installation, digest)
    cursors = TaskCursor(SystemClock(), SecureEntropy().new().encode("ascii"))
    query_service = CalendarQueries(
        store, MaintenanceScope(installation, "home"), installation, cursors, PinnedRecurrenceTime()
    )
    app.add_middleware(
        CalendarBoundary,
        api=calendar_api(query_service, installation),
        credential=credential,
        standalone_host=None
        if public_origin is None
        else urlsplit(public_origin).netloc.encode("ascii"),
    )
