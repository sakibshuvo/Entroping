"""JSON Schema export for the QAnstitution authoring contract."""

from typing import cast

from entroping.models.qanstitution import GateGroupReference, Qanstitution

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]

QANSTITUTION_SCHEMA_ID = (
    "https://sakibshuvo.github.io/Entroping/technical/qanstitution.schema.json"
)
QANSTITUTION_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def qanstitution_json_schema() -> JsonObject:
    """Return the generated JSON Schema for ``qanstitution.yaml`` authoring."""

    schema = cast(JsonObject, Qanstitution.model_json_schema())
    definitions = cast(JsonObject, schema.setdefault("$defs", {}))
    gate_group_reference_schema = cast(JsonObject, GateGroupReference.model_json_schema())
    definitions["GateGroupReference"] = _without_defs(gate_group_reference_schema)

    properties = cast(JsonObject, schema["properties"])
    gates_schema = cast(JsonObject, properties["gates"])
    gates_schema["items"] = {
        "anyOf": [
            {"$ref": "#/$defs/GateRule"},
            {"$ref": "#/$defs/GateGroupReference"},
        ]
    }
    schema["$schema"] = QANSTITUTION_SCHEMA_DRAFT
    schema["$id"] = QANSTITUTION_SCHEMA_ID
    schema["description"] = (
        "Authoring schema for Entroping qanstitution.yaml files. Runtime "
        "Pydantic validation remains authoritative."
    )
    return schema


def _without_defs(schema: JsonObject) -> JsonObject:
    return {key: value for key, value in schema.items() if key != "$defs"}
