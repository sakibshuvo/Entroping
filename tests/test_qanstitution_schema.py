"""Contract tests for the committed QAnstitution authoring schema."""

import json
import re
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from entroping.models.conditions import CONDITION_JSON_SCHEMA_PATTERN
from entroping.models.qanstitution import Qanstitution
from entroping.models.qanstitution_schema import (
    QANSTITUTION_SCHEMA_DRAFT,
    QANSTITUTION_SCHEMA_ID,
    JsonObject,
    JsonValue,
    qanstitution_json_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs" / "technical" / "qanstitution.schema.json"


def _load_schema() -> JsonObject:
    return cast(JsonObject, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def test_qanstitution_schema_file_matches_runtime_model_export() -> None:
    assert _load_schema() == qanstitution_json_schema()


def test_qanstitution_schema_contract_covers_current_runtime_shape() -> None:
    schema = _load_schema()
    definitions = _object(schema["$defs"])
    properties = _object(schema["properties"])
    gate_rule = _object(definitions["GateRule"])
    gate_properties = _object(gate_rule["properties"])
    condition_schema = _object(gate_properties["condition"])
    agents_schema = _object(properties["agents"])
    agent_names = _object(agents_schema["propertyNames"])

    assert schema["$schema"] == QANSTITUTION_SCHEMA_DRAFT
    assert schema["$id"] == QANSTITUTION_SCHEMA_ID
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["project"]
    assert agent_names["enum"] == ["builder", "auditor", "breaker"]
    assert _object(gate_properties["enforcement"])["enum"] == [
        "block",
        "warn",
        "audit_only",
    ]
    assert condition_schema["pattern"] == CONDITION_JSON_SCHEMA_PATTERN

    condition_pattern = re.compile(str(condition_schema["pattern"]))
    valid_policy = {
        "project": "checkout-api",
        "agents": {
            "builder": {
                "source": "agents/builder.md",
                "model": "openai/test-model",
                "api_base": "http://127.0.0.1:8000/v1",
                "api_key_env": "ENTROPING_TEST_KEY",
            }
        },
        "gates": [
            {
                "id": "smoke_latency",
                "condition": "tags contains 'smoke'",
                "gate": "duration < 500",
                "enforcement": "block",
            }
        ],
        "settings": {
            "timeout": 30_000,
            "parallel_workers": 2,
            "follow_redirects": True,
            "retry": 0,
        },
    }

    law = Qanstitution.model_validate(valid_policy)

    assert law.project == "checkout-api"
    assert condition_pattern.fullmatch("tags contains 'smoke'") is not None
    assert condition_pattern.fullmatch("tags has 'smoke'") is None
    with pytest.raises(ValidationError, match="Unsupported QAnstitution condition syntax"):
        Qanstitution.model_validate(
            {
                **valid_policy,
                "gates": [
                    {
                        "id": "bad_condition",
                        "condition": "tags has 'smoke'",
                        "gate": "duration < 500",
                        "enforcement": "block",
                    }
                ],
            }
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Qanstitution.model_validate({**valid_policy, "redaction": {"headers": []}})


def test_qanstitution_schema_authoring_guidance_is_public_and_editor_ready() -> None:
    vscode_settings = json.loads(
        (REPO_ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8")
    )
    schema_mapping = vscode_settings["yaml.schemas"][
        "./docs/technical/qanstitution.schema.json"
    ]
    reference = (REPO_ROOT / "docs" / "technical" / "QANSTITUTION_REFERENCE.md").read_text(
        encoding="utf-8"
    )
    first_hour = (REPO_ROOT / "docs" / "user" / "QANSTITUTION_FIRST_HOUR.md").read_text(
        encoding="utf-8"
    )
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    mkdocs = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")

    assert "qanstitution.yaml" in schema_mapping
    assert "**/qanstitution.yaml" in schema_mapping
    assert "qanstitution.schema.json" in reference
    assert ".vscode/settings.json" in reference
    assert "runtime validation remains authoritative" in reference
    assert "qanstitution.schema.json" in first_hour
    assert "technical/qanstitution.schema.json" in docs_index
    assert "QAnstitution Reference: technical/QANSTITUTION_REFERENCE.md" in mkdocs
