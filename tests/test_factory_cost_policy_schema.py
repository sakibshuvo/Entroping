from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.v1.schema.json"
EXAMPLE_PATH = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.example.json"


def _runtime_schema() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.factory_cost_policy", "schema"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return cast(dict[str, Any], json.loads(result.stdout))


def test_committed_schema_matches_runtime_export() -> None:
    committed = cast(
        dict[str, Any],
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
    )
    assert committed == _runtime_schema()
    assert json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))["schema_version"] == (
        "entroping.factory-cost-policy.v1"
    )


def test_schema_is_closed_and_contains_no_secret_fields() -> None:
    schema = _runtime_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith("/meta/factory-cost-policy.v1.schema.json")
    assert schema["additionalProperties"] is False
    assert all(
        definition.get("additionalProperties") is False
        for definition in schema["$defs"].values()
        if definition.get("type") == "object"
    )
    serialized = json.dumps(schema).lower()
    assert "api_key" not in serialized
    assert "access_token" not in serialized
    assert "password" not in serialized
