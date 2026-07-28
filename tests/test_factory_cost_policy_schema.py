from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pydantic import TypeAdapter

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.v1.schema.json"
EXAMPLE_PATH = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.example.json"
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, JsonValue])


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _runtime_schema() -> dict[str, JsonValue]:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.factory_cost_policy", "schema"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return JSON_OBJECT_ADAPTER.validate_json(result.stdout)


def test_committed_schema_matches_runtime_export() -> None:
    committed = JSON_OBJECT_ADAPTER.validate_json(SCHEMA_PATH.read_bytes())
    assert committed == _runtime_schema()
    example = JSON_OBJECT_ADAPTER.validate_json(EXAMPLE_PATH.read_bytes())
    assert example["schema_version"] == (
        "entroping.factory-cost-policy.v1"
    )


def test_schema_is_closed_and_contains_no_secret_fields() -> None:
    schema = _runtime_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    schema_id = schema["$id"]
    assert isinstance(schema_id, str)
    assert schema_id.endswith("/meta/factory-cost-policy.v1.schema.json")
    assert schema["additionalProperties"] is False
    definitions = _object(schema["$defs"])
    assert all(
        _object(definition).get("additionalProperties") is False
        for definition in definitions.values()
        if _object(definition).get("type") == "object"
    )
    serialized = json.dumps(schema).lower()
    assert "api_key" not in serialized
    assert "access_token" not in serialized
    assert "password" not in serialized
