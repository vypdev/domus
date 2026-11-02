"""The actual OpenAPI projection retains exact declared int64 bounds without widening others."""

from fastapi import FastAPI
from pydantic import Field

from domus.entrypoints.http_contract import NonnegativeRevision, PositiveRevision, StrictModel
from domus.entrypoints.openapi import DomusAPI


class Values(StrictModel):
    revision: PositiveRevision
    policy_revision: NonnegativeRevision
    optional: PositiveRevision | None
    bounded: int = Field(ge=1, le=100, json_schema_extra={"format": "int64"})
    unmarked: int = Field(ge=1, le=2**63 - 1)
    approximate: float = Field(le=2**63 - 1, json_schema_extra={"format": "int64"})


def configured(app):
    @app.get("/values", response_model=Values)
    def values():
        raise AssertionError("Schema inspection does not execute the endpoint")

    return app


def test_explicit_int64_bounds_survive_actual_framework_projection_and_cached_reuse():
    app = configured(DomusAPI())
    schema = app.openapi()
    values = schema["components"]["schemas"]["Values"]["properties"]
    for item in (values["revision"], values["policy_revision"], values["optional"]["anyOf"][0]):
        assert type(item["maximum"]) is int and item["maximum"] == 2**63 - 1
    assert values["bounded"]["maximum"] == 100
    assert type(values["unmarked"]["maximum"]) is float
    assert type(values["approximate"]["maximum"]) is float
    assert app.openapi() is schema


def test_original_framework_control_reproduces_numeric_bound_coercion():
    values = configured(FastAPI()).openapi()["components"]["schemas"]["Values"]["properties"]
    assert type(values["revision"]["maximum"]) is float
    assert values["revision"]["maximum"] > 2**63 - 1
    assert type(Values.model_json_schema()["properties"]["revision"]["maximum"]) is int
