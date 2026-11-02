"""Preserve explicit int64 bounds after the framework's float-valued schema projection."""

from typing import Any

from fastapi import FastAPI

_INT64_MAXIMUM = 2**63 - 1


def _exact_int64(value: object) -> None:
    if isinstance(value, dict):
        if (
            value.get("type") == "integer"
            and value.get("format") == "int64"
            and value.get("maximum") == float(_INT64_MAXIMUM)
        ):
            value["maximum"] = _INT64_MAXIMUM
        for nested in value.values():
            _exact_int64(nested)
    elif isinstance(value, list):
        for nested in value:
            _exact_int64(nested)


class DomusAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        schema = super().openapi()
        _exact_int64(schema)
        return schema
