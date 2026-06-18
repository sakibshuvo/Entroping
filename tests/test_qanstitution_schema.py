"""Contract tests for the committed QAnstitution authoring schema."""

import json
import re
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from entroping.models.conditions import CONDITION_JSON_SCHEMA_PATTERN
from entroping.models.qanstitution import (
    SUPPORTED_QANSTITUTION_VERSIONS,
    GateGroupReference,
    Qanstitution,
    expand_qanstitution_gate_entries,
)
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
    agent_config = _object(definitions["AgentConfig"])
    gate_group = _object(definitions["GateGroup"])
    gate_group_reference = _object(definitions["GateGroupReference"])
    agent_properties = _object(agent_config["properties"])
    gate_properties = _object(gate_rule["properties"])
    gate_group_properties = _object(gate_group["properties"])
    condition_schema = _object(gate_properties["condition"])
    version_schema = _object(properties["version"])
    agents_schema = _object(properties["agents"])
    agent_names = _object(agents_schema["propertyNames"])
    gates_schema = _object(properties["gates"])
    runtime_settings = _object(definitions["RuntimeSettings"])
    settings_properties = _object(runtime_settings["properties"])

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
    assert _object(gate_group_reference["properties"])["group"] == {
        "title": "Group",
        "type": "string",
    }
    assert "gate_groups" in properties
    assert "groups" in gate_group_properties
    assert "anyOf" in _object(gates_schema["items"])
    assert "protected_environments" in settings_properties
    assert condition_schema["pattern"] == CONDITION_JSON_SCHEMA_PATTERN
    assert version_schema["enum"] == [*SUPPORTED_QANSTITUTION_VERSIONS, None]
    assert "schema compatibility marker" in str(version_schema["description"])
    assert "local loopback" in str(
        _object(agent_properties["api_base"])["description"]
    )

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
            "protected_environments": ["prod", "production", "protected"],
        },
    }

    law = Qanstitution.model_validate(valid_policy)

    assert law.project == "checkout-api"
    assert law.settings.protected_environments == ["prod", "production", "protected"]
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


def test_qanstitution_settings_normalize_and_validate_protected_environments() -> None:
    law = Qanstitution.model_validate(
        {
            "project": "checkout-api",
            "settings": {"protected_environments": [" Prod ", "prod", "PROTECTED"]},
            "gates": [
                {
                    "id": "global_latency",
                    "condition": "true",
                    "gate": "duration < 2000",
                    "enforcement": "block",
                }
            ],
        }
    )

    assert law.settings.protected_environments == ["prod", "protected"]

    for value, message in [
        (" ", "must not be empty"),
        ("pro\x1fd", "must not contain control characters"),
    ]:
        with pytest.raises(ValidationError, match=message):
            Qanstitution.model_validate(
                {
                    "project": "checkout-api",
                    "settings": {"protected_environments": [value]},
                    "gates": [
                        {
                            "id": "global_latency",
                            "condition": "true",
                            "gate": "duration < 2000",
                            "enforcement": "block",
                        }
                    ],
                }
            )


@pytest.mark.parametrize(
    "version",
    [
        "4.1",
    ],
)
def test_qanstitution_model_accepts_supported_version_markers(version: str) -> None:
    policy: dict[str, object] = {
        "project": "checkout-api",
        "version": version,
        "gates": [
            {
                "id": "versioned",
                "condition": "true",
                "gate": "duration < 500",
                "enforcement": "block",
            }
        ],
    }

    law = Qanstitution.model_validate(policy)

    assert law.version == version


def test_qanstitution_model_accepts_missing_version_marker_for_legacy_policy() -> None:
    law = Qanstitution.model_validate(
        {
            "project": "checkout-api",
            "gates": [
                {
                    "id": "legacy",
                    "condition": "true",
                    "gate": "duration < 500",
                    "enforcement": "block",
                }
            ],
        }
    )

    assert law.version is None


def test_qanstitution_model_expands_gate_group_references() -> None:
    law = Qanstitution.model_validate(
        {
            "project": "checkout-api",
            "gate_groups": {
                "latency": {
                    "gates": [
                        {
                            "id": "smoke_latency",
                            "condition": "tags contains 'smoke'",
                            "gate": "duration < 500",
                            "enforcement": "block",
                        }
                    ]
                }
            },
            "gates": [{"group": "latency"}],
        }
    )

    assert [gate.id for gate in law.gates] == ["smoke_latency"]


@pytest.mark.parametrize(
    ("version", "message"),
    [
        ("", "must not be empty"),
        (" 4.1 ", "must not contain leading or trailing whitespace"),
        ("4.0", "Unsupported QAnstitution version"),
        ("4.2", "Unsupported QAnstitution version"),
        ("5.0", "Unsupported QAnstitution version"),
    ],
)
def test_qanstitution_model_rejects_invalid_version_markers(version: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message) as exc_info:
        Qanstitution.model_validate(
            {
                "project": "checkout-api",
                "version": version,
                "gates": [
                    {
                        "id": "versioned",
                        "condition": "true",
                        "gate": "duration < 500",
                        "enforcement": "block",
                    }
                ],
            }
        )
    assert "QANSTITUTION_REFERENCE.md#qanstitution-schema-compatibility" in str(exc_info.value)


def test_qanstitution_model_rejects_malformed_known_failure_expiry() -> None:
    for expires in ("tomorrow", "20260610", "2026-02-31"):
        with pytest.raises(ValidationError, match="expires must use YYYY-MM-DD"):
            Qanstitution.model_validate(
                {
                    "project": "checkout-api",
                    "ignore_failures": [
                        {
                            "test": "tests/checkout.hurl",
                            "rule_id": "global_latency",
                            "issue_id": "GH-491",
                            "expires": expires,
                            "reason": "Malformed expiry must not pass policy loading.",
                        }
                    ],
                }
            )


def test_qanstitution_model_rejects_non_mapping_config() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid dictionary"):
        Qanstitution.model_validate("project: checkout-api")


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (
            {
                "project": "checkout-api",
                "gates": [{"group": "missing"}],
            },
            "Unknown gate group 'missing'",
        ),
        (
            {
                "project": "checkout-api",
                "gate_groups": {
                    "a": {"groups": ["b"]},
                    "b": {"groups": ["a"]},
                },
                "gates": [{"group": "a"}],
            },
            "Gate group cycle detected",
        ),
        (
            {
                "project": "checkout-api",
                "gate_groups": None,
            },
            "gate_groups must be a mapping",
        ),
        (
            {
                "project": "checkout-api",
                "gate_groups": [],
            },
            "gate_groups must be a mapping",
        ),
        (
            {
                "project": "checkout-api",
                "gate_groups": {1: {}},
            },
            "gate group names must be strings",
        ),
        (
            {
                "project": "checkout-api",
                "gate_groups": {" ": {}},
            },
            "gate group name must not be empty",
        ),
        (
            {
                "project": "checkout-api",
                "gates": None,
            },
            "gates must be a list",
        ),
        (
            {
                "project": "checkout-api",
                "gates": "latency",
            },
            "gates must be a list",
        ),
        (
            {
                "project": "checkout-api",
                "gates": [{"group": "bad\nname"}],
            },
            "gate group name must not contain control characters",
        ),
        (
            {
                "project": "checkout-api",
                "gate_groups": {"latency": {}},
                "gates": [{"group": "latency", "id": "ambiguous"}],
            },
            "Extra inputs are not permitted",
        ),
        (
            {
                "project": "checkout-api",
                "gates": [42],
            },
            "Input should be a valid dictionary",
        ),
    ],
)
def test_qanstitution_model_rejects_invalid_gate_group_references(
    policy: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Qanstitution.model_validate(policy)


def test_qanstitution_model_rejects_explosive_gate_group_expansion() -> None:
    gate_groups: dict[str, object] = {
        "leaf": {
            "gates": [
                {
                    "id": "leaf_gate",
                    "condition": "true",
                    "gate": "duration < 500",
                    "enforcement": "block",
                }
            ],
        }
    }
    previous = "leaf"
    for index in range(15):
        group_name = f"diamond_{index}"
        gate_groups[group_name] = {"groups": [previous, previous]}
        previous = group_name

    with pytest.raises(ValidationError, match="gate group expansion exceeds"):
        Qanstitution.model_validate(
            {
                "project": "checkout-api",
                "gate_groups": gate_groups,
                "gates": [{"group": previous}],
            }
        )


def test_qanstitution_model_rejects_excessive_gate_group_depth() -> None:
    gate_groups: dict[str, object] = {
        "leaf": {
            "gates": [
                {
                    "id": "leaf_gate",
                    "condition": "true",
                    "gate": "duration < 500",
                    "enforcement": "block",
                }
            ],
        }
    }
    previous = "leaf"
    for index in range(70):
        group_name = f"nested_{index}"
        gate_groups[group_name] = {"groups": [previous]}
        previous = group_name

    with pytest.raises(ValidationError, match="gate group expansion depth exceeds"):
        Qanstitution.model_validate(
            {
                "project": "checkout-api",
                "gate_groups": gate_groups,
                "gates": [{"group": previous}],
            }
        )


def test_expand_qanstitution_gate_entries_accepts_typed_gate_group_reference() -> None:
    expanded = expand_qanstitution_gate_entries(
        {
            "project": "checkout-api",
            "gate_groups": {
                "latency": {
                    "gates": [
                        {
                            "id": "smoke_latency",
                            "condition": "tags contains 'smoke'",
                            "gate": "duration < 500",
                            "enforcement": "block",
                        }
                    ]
                }
            },
            "gates": [GateGroupReference(group="latency")],
        }
    )

    assert [(entry.rule.id, entry.group) for entry in expanded] == [("smoke_latency", "latency")]


def test_qanstitution_schema_authoring_guidance_is_public_and_editor_ready() -> None:
    vscode_settings = json.loads(
        (REPO_ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8")
    )
    schema_mapping = vscode_settings["yaml.schemas"]["./docs/technical/qanstitution.schema.json"]
    reference = (REPO_ROOT / "docs" / "technical" / "QANSTITUTION_REFERENCE.md").read_text(
        encoding="utf-8"
    )
    first_hour = (REPO_ROOT / "docs" / "user" / "QANSTITUTION_FIRST_HOUR.md").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    mkdocs = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")

    assert "qanstitution.yaml" in schema_mapping
    assert "**/qanstitution.yaml" in schema_mapping
    assert "qanstitution.schema.json" in reference
    assert ".vscode/settings.json" in reference
    assert "VS Code and JetBrains" in reference
    assert "A dedicated IDE extension" in reference
    assert "runtime validation remains authoritative" in reference
    assert 'Supported explicit marker for the v4.1 policy shape is `version: "4.1"`' in reference
    assert "Migration helpers, if they are needed" in reference
    assert "must never run implicitly from" in reference
    assert "qanstitution.schema.json" in first_hour
    assert "For JetBrains users" in first_hour
    assert "no plugin or custom Entroping service" in first_hour
    assert 'Use `version: "4.1"` for new QAnstitution files.' in first_hour
    assert "docs/technical/qanstitution.schema.json" in readme
    assert "QANSTITUTION_FIRST_HOUR.md" in readme
    assert "QANSTITUTION_REFERENCE.md" in readme
    assert "`entroping doctor` remains the authoritative runtime validation" in readme
    assert "technical/qanstitution.schema.json" in docs_index
    assert "QAnstitution Reference: technical/QANSTITUTION_REFERENCE.md" in mkdocs
