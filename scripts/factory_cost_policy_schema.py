from __future__ import annotations

from typing import cast

from .factory_cost_policy_models import FactoryCostPolicy

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]

FACTORY_COST_POLICY_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
FACTORY_COST_POLICY_SCHEMA_ID = (
    "https://sakibshuvo.github.io/Entroping/meta/factory-cost-policy.v1.schema.json"
)


def factory_cost_policy_json_schema() -> JsonObject:
    schema = cast(JsonObject, FactoryCostPolicy.model_json_schema())
    schema["$schema"] = FACTORY_COST_POLICY_SCHEMA_DRAFT
    schema["$id"] = FACTORY_COST_POLICY_SCHEMA_ID
    schema["description"] = (
        "Authoring schema for the local Entroping factory cost policy. "
        "Runtime Pydantic validation remains authoritative."
    )
    return schema
