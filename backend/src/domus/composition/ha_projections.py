"""Wire opt-in Home Assistant reads over the shared installation boundary."""

from urllib.parse import urlsplit

from fastapi import FastAPI

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.task_queries import InstallationTaskDeadlines
from domus.composition.ha_calendar import calendar_route
from domus.domain.errors import InvalidInput
from domus.entrypoints.ha_calendar_http import CALENDAR_PATH
from domus.entrypoints.ha_deadline_http import DEADLINE_GRANT_PREFIX, DEADLINE_PATH, deadline_api
from domus.entrypoints.ha_projection_http import (
    HAProjectionBoundary,
    ProjectionGrant,
    ProjectionRoute,
    validate_digest,
)
from domus.infrastructure.application_runtime import SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteDatabase


def attach_ha_projections(
    app: FastAPI,
    store: SQLiteDatabase | None,
    calendar_digest: str | None,
    deadline_digest: str | None,
    *,
    public_origin: str | None = None,
) -> None:
    if calendar_digest is None and deadline_digest is None:
        return
    if store is None or (public_origin is not None and not public_origin.startswith("https://")):
        code = (
            "ha_calendar_requires_persistent_secure_origin"
            if calendar_digest is not None
            else "ha_deadlines_require_persistent_secure_origin"
        )
        raise InvalidInput(code)
    routes: dict[str, ProjectionRoute] = {}
    if calendar_digest is not None:
        routes[CALENDAR_PATH] = calendar_route(store, calendar_digest)
    if deadline_digest is not None:
        credential = ProjectionGrant(
            store.installation,
            validate_digest(deadline_digest, "invalid_ha_deadline_digest"),
            DEADLINE_GRANT_PREFIX,
        )
        query = InstallationTaskDeadlines(
            store,
            MaintenanceScope(store.installation, "home"),
            SystemClock(),
            PinnedRecurrenceTime(),
        )
        routes[DEADLINE_PATH] = ProjectionRoute(
            deadline_api(query), credential, "invalid_deadline_credential"
        )
    app.add_middleware(
        HAProjectionBoundary,
        routes=routes,
        standalone_host=None
        if public_origin is None
        else urlsplit(public_origin).netloc.encode("ascii"),
    )
