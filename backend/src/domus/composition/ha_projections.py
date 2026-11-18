"""Wire opt-in Home Assistant reads over the shared installation boundary."""

from urllib.parse import urlsplit

from fastapi import FastAPI

from domus.application.fixed_materialization import MaintenanceScope
from domus.application.inventory_queries import InstallationLowStock
from domus.application.shopping_list import InstallationShoppingList
from domus.application.task_queries import InstallationOpenTasks, InstallationTaskDeadlines
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
from domus.entrypoints.ha_shopping_http import SHOPPING_GRANT_PREFIX, SHOPPING_PATH, shopping_api
from domus.entrypoints.ha_stock_http import STOCK_GRANT_PREFIX, STOCK_PATH, stock_api
from domus.entrypoints.ha_tasks_http import TASKS_GRANT_PREFIX, TASKS_PATH, tasks_api
from domus.infrastructure.application_runtime import SystemClock
from domus.infrastructure.recurrence_time import PinnedRecurrenceTime
from domus.infrastructure.sqlite import SQLiteDatabase


def attach_ha_projections(
    app: FastAPI,
    store: SQLiteDatabase | None,
    calendar_digest: str | None,
    deadline_digest: str | None,
    stock_digest: str | None,
    shopping_digest: str | None,
    tasks_digest: str | None = None,
    *,
    public_origin: str | None = None,
) -> None:
    if all(
        digest is None
        for digest in (
            calendar_digest,
            deadline_digest,
            stock_digest,
            shopping_digest,
            tasks_digest,
        )
    ):
        return
    if store is None or (public_origin is not None and not public_origin.startswith("https://")):
        if calendar_digest is not None:
            raise InvalidInput("ha_calendar_requires_persistent_secure_origin")
        if deadline_digest is not None:
            raise InvalidInput("ha_deadlines_require_persistent_secure_origin")
        if stock_digest is not None:
            raise InvalidInput("ha_stock_requires_persistent_secure_origin")
        if shopping_digest is not None:
            raise InvalidInput("ha_shopping_requires_persistent_secure_origin")
        raise InvalidInput("ha_tasks_requires_persistent_secure_origin")
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
    if stock_digest is not None:
        credential = ProjectionGrant(
            store.installation,
            validate_digest(stock_digest, "invalid_ha_stock_digest"),
            STOCK_GRANT_PREFIX,
        )
        stock_query = InstallationLowStock(store, MaintenanceScope(store.installation, "home"))
        routes[STOCK_PATH] = ProjectionRoute(
            stock_api(stock_query), credential, "invalid_stock_credential"
        )
    if shopping_digest is not None:
        credential = ProjectionGrant(
            store.installation,
            validate_digest(shopping_digest, "invalid_ha_shopping_digest"),
            SHOPPING_GRANT_PREFIX,
        )
        shopping = InstallationShoppingList(store, MaintenanceScope(store.installation, "home"))
        routes[SHOPPING_PATH] = ProjectionRoute(
            shopping_api(shopping), credential, "invalid_shopping_credential"
        )
    if tasks_digest is not None:
        credential = ProjectionGrant(
            store.installation,
            validate_digest(tasks_digest, "invalid_ha_tasks_digest"),
            TASKS_GRANT_PREFIX,
        )
        tasks = InstallationOpenTasks(store, MaintenanceScope(store.installation, "home"))
        routes[TASKS_PATH] = ProjectionRoute(
            tasks_api(tasks), credential, "invalid_tasks_credential"
        )
    app.add_middleware(
        HAProjectionBoundary,
        routes=routes,
        standalone_host=None
        if public_origin is None
        else urlsplit(public_origin).netloc.encode("ascii"),
    )
