"""Expose the aggregate stock count for the Home Assistant sensor."""

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope

from domus.application.inventory_queries import InstallationLowStock, LowStockCount
from domus.domain.errors import DomusError, InvalidInput
from domus.entrypoints.bounded_http import BoundedHTTP
from domus.entrypoints.ha_projection_http import NO_STORE, projection_error

STOCK_PATH = "/api/v1/ha/low-stock-products"
STOCK_DIGEST_ENV = "DOMUS_HA_STOCK_DIGEST"
STOCK_GRANT_PREFIX = "stock."


def _validate(scope: Scope) -> None:
    if scope["query_string"] or len(scope["headers"]) > 32:
        raise InvalidInput("invalid_stock_request")


def stock_api(query: InstallationLowStock) -> ASGIApp:
    api = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)

    @api.get(STOCK_PATH, response_model=LowStockCount)
    def read() -> LowStockCount | JSONResponse:
        try:
            return query.read()
        except DomusError:
            return projection_error(503, "low_stock_unavailable")

    return BoundedHTTP(api, _validate, lambda: "", projection_error, NO_STORE)
