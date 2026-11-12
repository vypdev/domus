"""Wire the opt-in installation query to the exact deployment boundary."""

from domus.application.calendar_queries import CalendarQueries
from domus.application.fixed_materialization import MaintenanceScope
from domus.entrypoints.ha_calendar_http import calendar_api
from domus.entrypoints.ha_projection_http import ProjectionGrant, ProjectionRoute, validate_digest
from domus.infrastructure.application_runtime import SystemClock
from domus.infrastructure.auth_runtime import SecureEntropy
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteDatabase
from domus.infrastructure.task_cursor import TaskCursor


def calendar_route(store: SQLiteDatabase, digest: str) -> ProjectionRoute:
    installation = store.installation
    credential = ProjectionGrant(
        installation, validate_digest(digest, "invalid_ha_calendar_digest"), ""
    )
    cursors = TaskCursor(SystemClock(), SecureEntropy().new().encode("ascii"))
    query_service = CalendarQueries(
        store, MaintenanceScope(installation, "home"), installation, cursors, PinnedRecurrenceTime()
    )
    return ProjectionRoute(
        calendar_api(query_service, installation), credential, "invalid_calendar_credential"
    )
