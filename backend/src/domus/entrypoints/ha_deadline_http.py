"""Expose the fixed, read-only projection for the two Home Assistant sensors."""

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope

from domus.application.task_queries import InstallationTaskDeadlines, TaskDeadlineCounts
from domus.domain.errors import DomusError, InvalidInput
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.ha_projection_http import NO_STORE, projection_error

DEADLINE_PATH = "/api/v1/ha/task-deadlines"
DEADLINE_DIGEST_ENV = "DOMUS_HA_DEADLINE_DIGEST"
DEADLINE_GRANT_PREFIX = "deadlines."


def _validate(scope: Scope) -> None:
    if scope["query_string"] or len(scope["headers"]) > 32:
        raise InvalidInput("invalid_deadline_request")


def deadline_api(query: InstallationTaskDeadlines) -> ASGIApp:
    api = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)

    @api.get(DEADLINE_PATH, response_model=TaskDeadlineCounts)
    def read() -> TaskDeadlineCounts | JSONResponse:
        try:
            return query.read()
        except DomusError:
            return projection_error(503, "task_deadlines_unavailable")

    return BoundedHTTP(api, _validate, lambda: "", projection_error, NO_STORE)
