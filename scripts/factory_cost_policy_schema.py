from __future__ import annotations

from pydantic import JsonValue, TypeAdapter

from .factory_cost_policy_models import FactoryCostPolicy

type JsonObject = dict[str, JsonValue]
JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)

FACTORY_COST_POLICY_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
FACTORY_COST_POLICY_SCHEMA_ID = (
    "https://sakibshuvo.github.io/Entroping/meta/factory-cost-policy.v1.schema.json"
)


def factory_cost_policy_json_schema() -> JsonObject:
    schema = JSON_OBJECT_ADAPTER.validate_python(FactoryCostPolicy.model_json_schema())
    schema["$schema"] = FACTORY_COST_POLICY_SCHEMA_DRAFT
    schema["$id"] = FACTORY_COST_POLICY_SCHEMA_ID
    schema["description"] = (
        "Authoring schema for the local Entroping factory cost policy. "
        "Runtime Pydantic validation remains authoritative."
    )
    return schema
