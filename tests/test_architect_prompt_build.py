"""Architect prompt-build orchestration tests."""

import json
from pathlib import Path

import pytest

from entroping.brain.architect_build import run_architect_prompt_build
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMCompletionResult
from entroping.brain.output_parser import ArchitectOutputParseError
from entroping.brain.prompt_builder import ArchitectPromptPackage
from entroping.core.config_loader import load_qanstitution
from entroping.core.hurl_validator import HurlValidationError


def _write_project(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "builder.md").write_text(
        "You generate reviewable Hurl tests.",
        encoding="utf-8",
    )
    (tmp_path / "qanstitution.yaml").write_text(
        """
project: checkout-api
sources:
  spec: openapi.yaml
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
    temperature: 0.2
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )


def test_run_architect_prompt_build_composes_boundaries_and_writes_edits(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")
    packages: list[ArchitectPromptPackage] = []
    validated: list[tuple[str, str]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "model": "openai/gpt-4.1-mini",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Generate checkout coverage",
                                "edits": [
                                    {
                                        "path": "tests/generated/checkout_ai.hurl",
                                        "content": "POST {{base_url}}/checkout\nHTTP 201\n",
                                    }
                                ],
                                "warnings": [],
                            },
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 11, "total_tokens": 18},
        }

    class CapturingClient(LiteLLMClient):
        def complete(self, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
            packages.append(package)
            return super().complete(package)

    result = run_architect_prompt_build(
        law=law,
        intent="Generate checkout coverage.",
        tags=("smoke", "ai"),
        project_root=tmp_path,
        config_path=tmp_path / "qanstitution.yaml",
        client=CapturingClient(completion_func=fake_completion),
        hurl_validator=lambda content, display_path: validated.append((content, display_path)),
    )

    assert result.summary == "Generate checkout coverage"
    assert result.model == "openai/gpt-4.1-mini"
    assert result.usage.total_tokens == 18
    assert result.written_paths == (tmp_path / "tests" / "generated" / "checkout_ai.hurl",)
    assert result.written_paths[0].read_text(encoding="utf-8").startswith(
        "# entroping: source=architect\n",
    )
    assert "# entroping: tags=ai,smoke" in result.written_paths[0].read_text(
        encoding="utf-8",
    )
    assert packages
    assert "You generate reviewable Hurl tests." in packages[0].messages[0].content
    assert "global_latency" in packages[0].messages[0].content
    assert "Requested Entroping tags: smoke, ai" in packages[0].messages[1].content
    assert validated == [
        (
            "# entroping: tags=ai,smoke\nPOST {{base_url}}/checkout\nHTTP 201\n",
            "tests/generated/checkout_ai.hurl",
        )
    ]


def test_run_architect_prompt_build_rejects_invalid_output_before_writing(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    with pytest.raises(ArchitectOutputParseError, match="List should have at least 1 item"):
        run_architect_prompt_build(
            law=law,
            intent="Generate checkout coverage.",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
            hurl_validator=lambda content, display_path: None,
        )

    assert not (tmp_path / "tests").exists()


def test_run_architect_prompt_build_validates_before_writing(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Generate invalid coverage",
                                "edits": [
                                    {
                                        "path": "tests/generated/bad.hurl",
                                        "content": "GET {{base_url}}/bad\nBAD\n",
                                    }
                                ],
                            },
                        )
                    }
                }
            ],
        }

    def fail_validation(content: str, display_path: str) -> None:
        _ = content
        raise HurlValidationError(f"Generated Hurl failed parser validation: {display_path}")

    with pytest.raises(HurlValidationError, match="tests/generated/bad.hurl"):
        run_architect_prompt_build(
            law=law,
            intent="Generate checkout coverage.",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
            hurl_validator=fail_validation,
        )

    assert not (tmp_path / "tests").exists()
