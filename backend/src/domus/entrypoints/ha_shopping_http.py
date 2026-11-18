"""Expose the bounded shopping snapshot to the native Home Assistant list."""

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope

from domus.application.shopping_list import InstallationShoppingList, ShoppingSnapshot
from domus.domain.errors import DomusError, InvalidInput
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.ha_projection_http import NO_STORE, projection_error

SHOPPING_PATH = "/api/v1/ha/shopping-list"
SHOPPING_DIGEST_ENV = "DOMUS_HA_SHOPPING_DIGEST"
SHOPPING_GRANT_PREFIX = "shopping."


def _validate(scope: Scope) -> None:
    if scope["query_string"] or len(scope["headers"]) > 32:
        raise InvalidInput("invalid_shopping_request")


def shopping_api(query: InstallationShoppingList) -> ASGIApp:
    api = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)

    @api.get(SHOPPING_PATH, response_model=ShoppingSnapshot)
    def read() -> ShoppingSnapshot | JSONResponse:
        try:
            return query.read()
        except DomusError:
            return projection_error(503, "shopping_list_unavailable")

    return BoundedHTTP(api, _validate, lambda: "", projection_error, NO_STORE)
