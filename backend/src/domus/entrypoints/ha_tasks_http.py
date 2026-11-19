"""Expose a bounded open-task snapshot to the native Home Assistant list."""

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope

from domus.application.task_queries import InstallationOpenTasks, OpenTaskSnapshot
from domus.domain.errors import DomusError, InvalidInput
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.ha_projection_http import NO_STORE, projection_error

TASKS_PATH = "/api/v1/ha/tasks"
TASKS_DIGEST_ENV = "DOMUS_HA_TASKS_DIGEST"
TASKS_GRANT_PREFIX = "tasks."


def _validate(scope: Scope) -> None:
    if scope["query_string"] or len(scope["headers"]) > 32:
        raise InvalidInput("invalid_tasks_request")


def tasks_api(query: InstallationOpenTasks) -> ASGIApp:
    api = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)

    @api.get(TASKS_PATH, response_model=OpenTaskSnapshot)
    def read() -> OpenTaskSnapshot | JSONResponse:
        try:
            return query.read()
        except DomusError:
            return projection_error(503, "task_list_unavailable")

    return BoundedHTTP(api, _validate, lambda: "", projection_error, NO_STORE)
