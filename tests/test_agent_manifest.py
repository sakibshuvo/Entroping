"""Tests for sanitized Architect agent run manifests."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

import entroping.core.agent_manifest as agent_manifest
from entroping.core.agent_manifest import (
    AGENT_RUN_MANIFEST_SCHEMA_VERSION,
    AgentRunCostEvidence,
    AgentRunManifestError,
    AgentRunManifestInput,
    AgentRunSourceEvidence,
    AgentRunSourceKind,
    AgentRunUsageEvidence,
    write_agent_run_manifest,
)
from entroping.core.safe_write import SafeWriteError


def test_write_agent_run_manifest_records_value_free_evidence(tmp_path: Path) -> None:
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir()
    persona_content = "Build checkout Hurl tests."
    persona_path.write_text(persona_content, encoding="utf-8")
    output_path = tmp_path / "tests" / "generated" / "checkout.hurl"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("GET {{base_url}}/checkout\nHTTP 200\n", encoding="utf-8")
    intent = "Generate checkout coverage using sk-live-secret"
    output_content = output_path.read_text(encoding="utf-8")

    result = write_agent_run_manifest(
        AgentRunManifestInput(
            project_root=tmp_path,
            command="architect build",
            mode="create",
            agent="builder",
            model="openai/gpt-4.1-mini",
            provider="openai",
            persona_source_path=persona_path,
            persona_content=persona_content,
            prompt_intent=intent,
            prompt_package_messages=(
                "system prompt with QAnstitution",
                "user prompt with private checkout detail",
            ),
            output_paths=(output_path,),
            source_evidence=(
                AgentRunSourceEvidence(
                    kind="explicit_prompt",
                    reference="prompt_intent",
                    sha256=hashlib.sha256(intent.encode("utf-8")).hexdigest(),
                ),
                AgentRunSourceEvidence(
                    kind="selected_hurl_target",
                    reference="tests/generated/checkout.hurl",
                    sha256=hashlib.sha256(output_content.encode("utf-8")).hexdigest(),
                ),
            ),
            tags=("ai", "smoke"),
            validation_status="passed",
            structured_output_validated=True,
            hurl_validated=True,
            latency_ms=42,
            cost=AgentRunCostEvidence(
                estimated_usd=0.000042,
                input_cost_per_1m_tokens_usd=0.25,
                output_cost_per_1m_tokens_usd=1.25,
            ),
            usage=AgentRunUsageEvidence(
                prompt_tokens=20,
                completion_tokens=30,
                total_tokens=50,
            ),
            generated_at=datetime(2026, 6, 4, 7, 30, tzinfo=UTC),
        )
    )

    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    raw_manifest = result.manifest_path.read_text(encoding="utf-8")
    assert result.manifest_path == (
        tmp_path
        / ".entroping"
        / "agent-runs"
        / "20260604T073000Z-architect-build-builder-422bbc5640e6.json"
    )
    assert payload == {
        "agent": "builder",
        "command": "architect build",
        "generated_at": "2026-06-04T07:30:00+00:00",
        "latency_ms": 42,
        "mode": "create",
        "model": "openai/gpt-4.1-mini",
        "output_paths": ["tests/generated/checkout.hurl"],
        "persona": {
            "sha256": hashlib.sha256(persona_content.encode("utf-8")).hexdigest(),
            "source_path": "agents/builder.md",
        },
        "provider": "openai",
        "prompt": {
            "intent_sha256": hashlib.sha256(intent.encode("utf-8")).hexdigest(),
            "package_sha256": hashlib.sha256(
                b"system prompt with QAnstitution\n\nuser prompt with private checkout detail"
            ).hexdigest(),
        },
        "schema_version": AGENT_RUN_MANIFEST_SCHEMA_VERSION,
        "source_evidence": [
            {
                "kind": "explicit_prompt",
                "reference": "prompt_intent",
                "sha256": hashlib.sha256(intent.encode("utf-8")).hexdigest(),
            },
            {
                "kind": "selected_hurl_target",
                "reference": "tests/generated/checkout.hurl",
                "sha256": hashlib.sha256(output_content.encode("utf-8")).hexdigest(),
            },
        ],
        "tags": ["ai", "smoke"],
        "cost": {
            "estimated_usd": 0.000042,
            "input_cost_per_1m_tokens_usd": 0.25,
            "output_cost_per_1m_tokens_usd": 1.25,
        },
        "usage": {
            "completion_tokens": 30,
            "prompt_tokens": 20,
            "total_tokens": 50,
        },
        "validation": {
            "hurl_validated": True,
            "status": "passed",
            "structured_output_validated": True,
        },
    }
    assert "sk-live-secret" not in raw_manifest
    assert "private checkout detail" not in raw_manifest
    assert "Build checkout Hurl tests." not in raw_manifest


def test_write_agent_run_manifest_rejects_invalid_cost_evidence(tmp_path: Path) -> None:
    with pytest.raises(AgentRunManifestError, match="estimated cost must be finite"):
        write_agent_run_manifest(
            replace(
                _base_manifest_input(tmp_path),
                cost=AgentRunCostEvidence(
                    estimated_usd=float("nan"),
                    input_cost_per_1m_tokens_usd=None,
                    output_cost_per_1m_tokens_usd=None,
                ),
            )
        )
    with pytest.raises(
        AgentRunManifestError,
        match="input cost per 1M tokens must be greater than or equal to 0",
    ):
        write_agent_run_manifest(
            replace(
                _base_manifest_input(tmp_path),
                cost=AgentRunCostEvidence(
                    estimated_usd=None,
                    input_cost_per_1m_tokens_usd=-0.01,
                    output_cost_per_1m_tokens_usd=None,
                ),
            )
        )


def test_write_agent_run_manifest_accepts_source_evidence_without_hash(
    tmp_path: Path,
) -> None:
    result = write_agent_run_manifest(
        replace(
            _base_manifest_input(tmp_path),
            source_evidence=(
                AgentRunSourceEvidence(
                    kind="failed_run",
                    reference="reports/run-latest.json",
                    sha256=None,
                ),
            ),
        )
    )

    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["source_evidence"] == [
        {
            "kind": "failed_run",
            "reference": "reports/run-latest.json",
            "sha256": None,
        }
    ]


def test_write_agent_run_manifest_rejects_invalid_source_hash(tmp_path: Path) -> None:
    with pytest.raises(AgentRunManifestError, match="source evidence sha256"):
        write_agent_run_manifest(
            replace(
                _base_manifest_input(tmp_path),
                source_evidence=(
                    AgentRunSourceEvidence(
                        kind="drift_report",
                        reference="reports/drift.json",
                        sha256="not-a-sha",
                    ),
                ),
            )
        )


def test_write_agent_run_manifest_rejects_invalid_source_kind(tmp_path: Path) -> None:
    with pytest.raises(AgentRunManifestError, match="source evidence kind"):
        write_agent_run_manifest(
            replace(
                _base_manifest_input(tmp_path),
                source_evidence=(
                    AgentRunSourceEvidence(
                        kind=cast(AgentRunSourceKind, "unknown"),
                        reference="reports/drift.json",
                    ),
                ),
            )
        )


def test_write_agent_run_manifest_rejects_paths_outside_project(tmp_path: Path) -> None:
    with pytest.raises(AgentRunManifestError, match="output path must stay inside"):
        write_agent_run_manifest(
            replace(
                _base_manifest_input(tmp_path),
                output_paths=(tmp_path.parent / "outside.hurl",),
            )
        )

    assert not (tmp_path / ".entroping" / "agent-runs").exists()


def test_write_agent_run_manifest_rejects_resolved_path_escape(tmp_path: Path) -> None:
    with pytest.raises(AgentRunManifestError, match="output path must stay inside"):
        write_agent_run_manifest(
            replace(
                _base_manifest_input(tmp_path),
                output_paths=(Path("../outside.hurl"),),
            )
        )


def test_write_agent_run_manifest_rejects_naive_timestamps(tmp_path: Path) -> None:
    with pytest.raises(AgentRunManifestError, match="generated_at"):
        write_agent_run_manifest(
            replace(
                _base_manifest_input(tmp_path),
                generated_at=datetime(2026, 6, 4, 7, 30),
            )
        )


def test_write_agent_run_manifest_rejects_symlinked_persona_path(tmp_path: Path) -> None:
    base_input = _base_manifest_input(tmp_path)
    symlink_path = tmp_path / "agents" / "builder-link.md"
    symlink_path.symlink_to(base_input.persona_source_path)

    with pytest.raises(AgentRunManifestError, match="persona source path must not use symlinks"):
        write_agent_run_manifest(replace(base_input, persona_source_path=symlink_path))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("agent", "", "agent"),
        ("model", "openai/gpt\n4", "model"),
        ("model", "openai/sk-live-secret", "model"),
        ("provider", "token=live-provider-secret", "provider"),
        ("tag", "token=live-tag-secret", "tag"),
    ],
)
def test_write_agent_run_manifest_rejects_unsafe_text_fields(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    with pytest.raises(AgentRunManifestError, match=message):
        base_input = _base_manifest_input(tmp_path)
        if field == "agent":
            updated = replace(base_input, agent=value)
        elif field == "provider":
            updated = replace(base_input, provider=value)
        elif field == "tag":
            updated = replace(base_input, tags=(value,))
        else:
            updated = replace(base_input, model=value)
        write_agent_run_manifest(updated)


def test_write_agent_run_manifest_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(agent_manifest, "safe_write_text", fail_safe_write)

    with pytest.raises(AgentRunManifestError, match="temporary write failed"):
        write_agent_run_manifest(_base_manifest_input(tmp_path))


def _base_manifest_input(tmp_path: Path) -> AgentRunManifestInput:
    persona_path = tmp_path / "agents" / "builder.md"
    persona_path.parent.mkdir(exist_ok=True)
    persona_path.write_text("Build tests.", encoding="utf-8")
    output_path = tmp_path / "tests" / "generated" / "checkout.hurl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("GET {{base_url}}/checkout\nHTTP 200\n", encoding="utf-8")
    return AgentRunManifestInput(
        project_root=tmp_path,
        command="architect build",
        mode="create",
        agent="builder",
        model="openai/gpt-4.1-mini",
        provider=None,
        persona_source_path=persona_path,
        persona_content="Build tests.",
        prompt_intent="Generate coverage.",
        prompt_package_messages=("system", "user"),
        output_paths=(output_path,),
        tags=(),
        validation_status="passed",
        structured_output_validated=True,
        hurl_validated=True,
        latency_ms=1,
        usage=AgentRunUsageEvidence(
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
        ),
        generated_at=datetime(2026, 6, 4, 7, 30, tzinfo=UTC),
    )
