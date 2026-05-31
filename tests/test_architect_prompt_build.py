"""Architect prompt-build orchestration tests."""

import json
import os
from pathlib import Path

import pytest

import entroping.brain.architect_build as architect_build
from entroping.brain.architect_build import run_architect_prompt_build
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMCompletionResult
from entroping.brain.output_parser import ArchitectOutputParseError
from entroping.brain.prompt_builder import ArchitectPromptPackage
from entroping.core.config_loader import load_qanstitution
from entroping.core.hurl_validator import HurlValidationError
from entroping.models import ArchitectEdit, ArchitectEditSet


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


def test_run_architect_prompt_build_merge_preserves_manual_blocks(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "manual" / "checkout.hurl"
    target.parent.mkdir(parents=True)
    target.write_text(
        (
            "# manual setup stays\n"
            "GET {{base_url}}/health\n"
            "HTTP 200\n"
            "\n"
            "# entroping: managed-begin checkout-auth\n"
            "GET {{base_url}}/checkout\n"
            "HTTP 200\n"
            "# entroping: managed-end checkout-auth\n"
            "\n"
            "# manual footer stays\n"
        ),
        encoding="utf-8",
    )
    law = load_qanstitution(tmp_path / "qanstitution.yaml")
    packages: list[ArchitectPromptPackage] = []
    validated: list[tuple[str, str]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Merged checkout coverage",
                                "edits": [
                                    {
                                        "path": "tests/manual/checkout.hurl",
                                        "content": (
                                            "# entroping: managed-begin checkout-auth\n"
                                            "GET {{base_url}}/checkout\n"
                                            "Authorization: Bearer {{token}}\n"
                                            "HTTP 200\n"
                                            "# entroping: managed-end checkout-auth\n"
                                        ),
                                    }
                                ],
                            },
                        )
                    }
                }
            ],
        }

    class CapturingClient(LiteLLMClient):
        def complete(self, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
            packages.append(package)
            return super().complete(package)

    result = run_architect_prompt_build(
        law=law,
        intent="Merge Authorization into checkout coverage.",
        strategy="merge",
        project_root=tmp_path,
        config_path=tmp_path / "qanstitution.yaml",
        client=CapturingClient(completion_func=fake_completion),
        hurl_validator=lambda content, display_path: validated.append((content, display_path)),
    )

    expected = (
        "# manual setup stays\n"
        "GET {{base_url}}/health\n"
        "HTTP 200\n"
        "\n"
        "# entroping: managed-begin checkout-auth\n"
        "GET {{base_url}}/checkout\n"
        "Authorization: Bearer {{token}}\n"
        "HTTP 200\n"
        "# entroping: managed-end checkout-auth\n"
        "\n"
        "# manual footer stays\n"
    )
    assert result.summary == "Merged checkout coverage"
    assert result.written_paths == (target,)
    assert target.read_text(encoding="utf-8") == expected
    assert validated == [(expected, "tests/manual/checkout.hurl")]
    assert packages
    assert "Merge strategy" in packages[0].messages[1].content
    assert "# entroping: source=architect" not in target.read_text(encoding="utf-8")


def test_run_architect_prompt_build_merge_updates_architect_owned_target(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "generated" / "checkout.hurl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "# entroping: source=architect\nGET {{base_url}}/old\nHTTP 200\n",
        encoding="utf-8",
    )
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Updated Architect-owned target",
                                "edits": [
                                    {
                                        "path": "tests/generated/checkout.hurl",
                                        "content": "GET {{base_url}}/new\nHTTP 200\n",
                                    }
                                ],
                            },
                        )
                    }
                }
            ],
        }

    result = run_architect_prompt_build(
        law=law,
        intent="Merge checkout coverage.",
        strategy="merge",
        project_root=tmp_path,
        config_path=tmp_path / "qanstitution.yaml",
        client=LiteLLMClient(completion_func=fake_completion),
        hurl_validator=lambda content, display_path: None,
    )

    assert result.written_paths == (target,)
    assert target.read_text(encoding="utf-8").startswith("# entroping: source=architect\n")
    assert "GET {{base_url}}/new" in target.read_text(encoding="utf-8")


def test_run_architect_prompt_build_merge_rejects_missing_targets_without_writing(
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
                                "summary": "Missing merge target",
                                "edits": [
                                    {
                                        "path": "tests/manual/missing.hurl",
                                        "content": "GET {{base_url}}/missing\nHTTP 200\n",
                                    }
                                ],
                            },
                        )
                    }
                }
            ],
        }

    with pytest.raises(ValueError, match="Merge target does not exist"):
        run_architect_prompt_build(
            law=law,
            intent="Merge checkout coverage.",
            strategy="merge",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
            hurl_validator=lambda content, display_path: None,
        )

    assert not (tmp_path / "tests").exists()


@pytest.mark.parametrize(
    ("existing", "generated", "message"),
    [
        (
            "# manual\nGET {{base_url}}/health\nHTTP 200\n",
            "GET {{base_url}}/health\nHTTP 200\n",
            "Architect-owned or contain managed blocks",
        ),
        (
            "# entroping: managed-begin checkout-auth\nGET {{base_url}}/checkout\n",
            "# entroping: managed-begin checkout-auth\nGET {{base_url}}/checkout\n",
            "Invalid managed blocks",
        ),
        (
            "# entroping: managed-begin checkout-auth\n"
            "GET {{base_url}}/checkout\n"
            "# entroping: managed-end checkout-auth\n",
            "# entroping: managed-begin refund-auth\n"
            "GET {{base_url}}/refunds\n"
            "# entroping: managed-end refund-auth\n",
            "Could not merge managed blocks",
        ),
    ],
)
def test_run_architect_prompt_build_merge_rejects_invalid_manual_targets(
    tmp_path: Path,
    existing: str,
    generated: str,
    message: str,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "manual" / "checkout.hurl"
    target.parent.mkdir(parents=True)
    target.write_text(existing, encoding="utf-8")
    original = target.read_text(encoding="utf-8")
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Invalid manual merge",
                                "edits": [
                                    {
                                        "path": "tests/manual/checkout.hurl",
                                        "content": generated,
                                    }
                                ],
                            },
                        )
                    }
                }
            ],
        }

    with pytest.raises(ValueError, match=message):
        run_architect_prompt_build(
            law=law,
            intent="Merge checkout coverage.",
            strategy="merge",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
            hurl_validator=lambda content, display_path: None,
        )

    assert target.read_text(encoding="utf-8") == original


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


def test_requested_tags_replace_existing_tag_metadata() -> None:
    edit_set = ArchitectEditSet(
        summary="Tagged",
        edits=[
            ArchitectEdit(
                path="tests/generated/tagged.hurl",
                content="# entroping: tags=old\nGET {{base_url}}/checkout\nHTTP 200\n",
            )
        ],
    )

    tagged = architect_build._apply_requested_tags(edit_set, tags=("smoke", "ai"))

    assert tagged.edits[0].content.startswith("# entroping: tags=ai,old,smoke\n")


def test_architect_build_tag_and_header_helpers_cover_empty_and_non_metadata_lines() -> None:
    assert not architect_build._has_architect_header("")
    assert architect_build._has_architect_header("\n# entroping: source=architect\n")
    assert not architect_build._has_architect_header("\n# manual\n")
    assert not architect_build._is_tags_metadata_line("# entroping:")
    assert not architect_build._is_tags_metadata_line("# entroping: owner=qa")
    assert not architect_build._is_tags_metadata_line("# plain comment")
    assert architect_build._content_with_requested_tags("", ("smoke",)) == "# entroping: tags=smoke"
    assert architect_build._content_with_requested_tags(
        "\nGET {{base_url}}/checkout\nHTTP 200\n",
        ("smoke",),
    ).startswith("\n# entroping: tags=smoke\n")
    assert architect_build._content_with_requested_tags(
        "# entroping: source=architect\nGET {{base_url}}/checkout\nHTTP 200\n",
        ("smoke",),
    ).startswith("# entroping: source=architect\n# entroping: tags=smoke\n")


def test_read_merge_target_rejects_unsafe_or_unreadable_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "tests" / "manual.hurl"
    target.parent.mkdir()
    target.write_text("# manual\nGET /health\nHTTP 200\n", encoding="utf-8")
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside.hurl"
    outside.write_text("# manual\nGET /outside\nHTTP 200\n", encoding="utf-8")
    symlink = tmp_path / "tests" / "linked.hurl"
    symlink.symlink_to(target)

    with pytest.raises(ValueError, match="must not use symlinks"):
        architect_build._read_merge_target("tests/linked.hurl", root=tmp_path)

    directory = tmp_path / "tests" / "directory.hurl"
    directory.mkdir()
    with pytest.raises(ValueError, match="must be a file"):
        architect_build._read_merge_target("tests/directory.hurl", root=tmp_path)

    large = tmp_path / "tests" / "large.hurl"
    large.write_text("x" * 256_001, encoding="utf-8")
    with pytest.raises(ValueError, match="too large"):
        architect_build._read_merge_target("tests/large.hurl", root=tmp_path)

    bad_utf8 = tmp_path / "tests" / "bad.hurl"
    bad_utf8.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        architect_build._read_merge_target("tests/bad.hurl", root=tmp_path)

    escape = tmp_path / "tests" / "escape.hurl"
    escape.symlink_to(outside)

    def allow_symlink_path(candidate: Path, *, root: Path) -> None:
        _ = candidate, root

    original_reject_symlink_path = architect_build._reject_symlink_path
    monkeypatch.setattr(architect_build, "_reject_symlink_path", allow_symlink_path)
    with pytest.raises(ValueError, match="must stay under project root"):
        architect_build._read_merge_target("tests/escape.hurl", root=tmp_path)

    monkeypatch.setattr(architect_build, "_reject_symlink_path", original_reject_symlink_path)
    original_exists = Path.exists
    original_is_file = Path.is_file
    original_stat = Path.stat
    target_resolved = target.resolve()

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == target_resolved and follow_symlinks:
            raise OSError("stat failed")
        return original_stat(self, follow_symlinks=follow_symlinks)

    def target_exists(self: Path) -> bool:
        if self == target_resolved:
            return True
        return original_exists(self)

    def target_is_file(self: Path) -> bool:
        if self == target_resolved:
            return True
        return original_is_file(self)

    monkeypatch.setattr(Path, "exists", target_exists)
    monkeypatch.setattr(Path, "is_file", target_is_file)
    monkeypatch.setattr(Path, "stat", fail_stat)
    with pytest.raises(ValueError, match="Could not inspect"):
        architect_build._read_merge_target("tests/manual.hurl", root=tmp_path)

    monkeypatch.setattr(Path, "exists", original_exists)
    monkeypatch.setattr(Path, "is_file", original_is_file)
    monkeypatch.setattr(Path, "stat", original_stat)
    original_read_text = Path.read_text

    def fail_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == target_resolved:
            raise OSError("read failed")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    with pytest.raises(ValueError, match="Could not read"):
        architect_build._read_merge_target("tests/manual.hurl", root=tmp_path)


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
