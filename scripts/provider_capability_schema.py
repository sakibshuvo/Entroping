from __future__ import annotations

from pydantic import JsonValue, TypeAdapter

from .provider_capability_types import ProviderCapabilityRegistry

type JsonObject = dict[str, JsonValue]
JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)

PROVIDER_CAPABILITY_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
PROVIDER_CAPABILITY_SCHEMA_ID = (
    "https://sakibshuvo.github.io/Entroping/meta/provider-capability-registry.v1.schema.json"
)


def provider_capability_json_schema() -> JsonObject:
    schema = JSON_OBJECT_ADAPTER.validate_python(ProviderCapabilityRegistry.model_json_schema())
    schema["$schema"] = PROVIDER_CAPABILITY_SCHEMA_DRAFT
    schema["$id"] = PROVIDER_CAPABILITY_SCHEMA_ID
    schema["description"] = (
        "Authoring schema for Entroping's non-secret maintainer provider capability "
        "registry. Runtime Pydantic validation remains authoritative."
    )
    return schema
