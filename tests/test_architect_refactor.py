"""Architect refactor orchestration tests."""

import json
import os
from pathlib import Path

import pytest

import entroping.brain.architect_refactor as architect_refactor
from entroping.brain.architect_refactor import (
    ArchitectRefactorError,
    discover_refactor_targets,
    run_architect_refactor,
)
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMCompletionResult
from entroping.brain.prompt_builder import ArchitectPromptPackage
from entroping.core.config_loader import load_qanstitution
from entroping.core.hurl_validator import HurlValidationError


def _write_project(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "builder.md").write_text(
        "Refactor Hurl tests with minimal diffs.",
        encoding="utf-8",
    )
    (tmp_path / "qanstitution.yaml").write_text(
        """
project: checkout-api
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


def _write_architect_hurl(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# entroping: source=architect\n{content}", encoding="utf-8")


def _write_manual_hurl(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_run_architect_refactor_loads_targets_and_writes_validated_edits(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "generated" / "checkout.hurl"
    _write_architect_hurl(target, "GET {{base_url}}/checkout\nHTTP 200\n")
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
                                "summary": "Added auth header",
                                "edits": [
                                    {
                                        "path": "tests/generated/checkout.hurl",
                                        "content": (
                                            "# entroping: source=architect\n"
                                            "GET {{base_url}}/checkout\n"
                                            "Authorization: Bearer {{token}}\n"
                                            "HTTP 200\n"
                                        ),
                                    }
                                ],
                                "warnings": ["Review token fixture."],
                            },
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 17, "completion_tokens": 13, "total_tokens": 30},
        }

    class CapturingClient(LiteLLMClient):
        def complete(self, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
            packages.append(package)
            return super().complete(package)

    result = run_architect_refactor(
        law=law,
        target_glob="tests/generated/*.hurl",
        prompt="Add Authorization header.",
        project_root=tmp_path,
        config_path=tmp_path / "qanstitution.yaml",
        client=CapturingClient(completion_func=fake_completion),
        hurl_validator=lambda content, display_path: validated.append((content, display_path)),
    )

    assert result.summary == "Added auth header"
    assert result.warnings == ("Review token fixture.",)
    assert result.written_paths == (target,)
    assert "Authorization: Bearer {{token}}" in target.read_text(encoding="utf-8")
    assert packages
    assert packages[0].role == "builder"
    assert "Refactor Hurl tests with minimal diffs." in packages[0].messages[0].content
    assert "global_latency" in packages[0].messages[0].content
    assert "Add Authorization header." in packages[0].messages[1].content
    assert "## tests/generated/checkout.hurl" in packages[0].messages[1].content
    assert "GET {{base_url}}/checkout" in packages[0].messages[1].content
    assert validated == [
        (
            (
                "# entroping: source=architect\n"
                "GET {{base_url}}/checkout\n"
                "Authorization: Bearer {{token}}\n"
                "HTTP 200\n"
            ),
            "tests/generated/checkout.hurl",
        )
    ]


def test_run_architect_refactor_merges_managed_blocks_into_manual_target(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "manual" / "checkout.hurl"
    _write_manual_hurl(
        target,
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
                                "summary": "Updated managed checkout block",
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

    result = run_architect_refactor(
        law=law,
        target_glob="tests/manual/*.hurl",
        prompt="Add Authorization header to the checkout block.",
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
    assert result.summary == "Updated managed checkout block"
    assert result.written_paths == (target,)
    assert target.read_text(encoding="utf-8") == expected
    assert validated == [(expected, "tests/manual/checkout.hurl")]
    assert packages
    assert "Managed-block manual target" in packages[0].messages[1].content
    assert "checkout-auth" in packages[0].messages[1].content
    assert "# entroping: source=architect" not in target.read_text(encoding="utf-8")


def test_run_architect_refactor_rejects_missing_targets_before_provider_call(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")
    provider_called = False

    class FailingClient(LiteLLMClient):
        def complete(self, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
            nonlocal provider_called
            provider_called = True
            return super().complete(package)

    with pytest.raises(ArchitectRefactorError, match="No Hurl targets matched"):
        run_architect_refactor(
            law=law,
            target_glob="tests/generated/*.hurl",
            prompt="Add Authorization header.",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=FailingClient(),
            hurl_validator=lambda content, display_path: None,
        )

    assert provider_called is False


@pytest.mark.parametrize(
    ("target_glob", "message"),
    [
        ("../*.hurl", "must stay under project root"),
        ("/tmp/*.hurl", "must stay under project root"),
        ("tests\\*.hurl", "must use POSIX separators"),
        ("tests/\u0000*.hurl", "must not contain control characters"),
    ],
)
def test_discover_refactor_targets_rejects_unsafe_globs(
    tmp_path: Path,
    target_glob: str,
    message: str,
) -> None:
    with pytest.raises(ArchitectRefactorError, match=message):
        discover_refactor_targets(target_glob, project_root=tmp_path)


def test_discover_refactor_targets_rejects_empty_glob(tmp_path: Path) -> None:
    with pytest.raises(ArchitectRefactorError, match="must not be empty"):
        discover_refactor_targets("   ", project_root=tmp_path)


def test_discover_refactor_targets_rejects_non_hurl_matches(tmp_path: Path) -> None:
    target = tmp_path / "tests" / "generated" / "notes.txt"
    target.parent.mkdir(parents=True)
    target.write_text("# entroping: source=architect\nnot hurl\n", encoding="utf-8")

    with pytest.raises(ArchitectRefactorError, match="must be a Hurl file"):
        discover_refactor_targets("tests/generated/*", project_root=tmp_path)


def test_discover_refactor_targets_rejects_symlink_targets(tmp_path: Path) -> None:
    target = tmp_path / "target.hurl"
    target.write_text("# entroping: source=architect\nGET /target\nHTTP 200\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "linked.hurl").symlink_to(target)

    with pytest.raises(ArchitectRefactorError, match="must not use symlinks"):
        discover_refactor_targets("tests/linked.hurl", project_root=tmp_path)


def test_discover_refactor_targets_rejects_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside.hurl"
    outside.write_text("# entroping: source=architect\nGET /outside\nHTTP 200\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    linked = tests_dir / "linked.hurl"
    linked.symlink_to(outside)

    def allow_symlink_path(candidate: Path, *, root: Path) -> None:
        _ = candidate, root

    monkeypatch.setattr(architect_refactor, "_reject_symlink_path", allow_symlink_path)

    with pytest.raises(ArchitectRefactorError, match="must stay under project root"):
        discover_refactor_targets("tests/linked.hurl", project_root=tmp_path)


def test_discover_refactor_targets_rejects_directory_target(tmp_path: Path) -> None:
    target = tmp_path / "tests" / "generated" / "directory.hurl"
    target.mkdir(parents=True)

    with pytest.raises(ArchitectRefactorError, match="must be a file"):
        discover_refactor_targets("tests/generated/directory.hurl", project_root=tmp_path)


def test_run_architect_refactor_rejects_manual_targets_without_managed_blocks_before_provider_call(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "manual.hurl"
    _write_manual_hurl(target, "# manual\nGET {{base_url}}/checkout\nHTTP 200\n")
    law = load_qanstitution(tmp_path / "qanstitution.yaml")
    provider_called = False

    class FailingClient(LiteLLMClient):
        def complete(self, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
            nonlocal provider_called
            provider_called = True
            return super().complete(package)

    with pytest.raises(
        ArchitectRefactorError,
        match="Refactor target must be Architect-owned or contain managed blocks",
    ):
        run_architect_refactor(
            law=law,
            target_glob="tests/manual.hurl",
            prompt="Add Authorization header.",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=FailingClient(),
            hurl_validator=lambda content, display_path: None,
        )

    assert provider_called is False


def test_discover_refactor_targets_rejects_invalid_managed_blocks(tmp_path: Path) -> None:
    target = tmp_path / "tests" / "manual.hurl"
    _write_manual_hurl(
        target,
        "# entroping: managed-begin checkout-auth\nGET {{base_url}}/checkout\n",
    )

    with pytest.raises(ArchitectRefactorError, match="Invalid managed blocks"):
        discover_refactor_targets("tests/manual.hurl", project_root=tmp_path)


def test_run_architect_refactor_rejects_unknown_managed_blocks_without_writing(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "manual" / "checkout.hurl"
    original = (
        "# manual setup stays\n"
        "# entroping: managed-begin checkout-auth\n"
        "GET {{base_url}}/checkout\n"
        "HTTP 200\n"
        "# entroping: managed-end checkout-auth\n"
    )
    _write_manual_hurl(target, original)
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Bad managed block",
                                "edits": [
                                    {
                                        "path": "tests/manual/checkout.hurl",
                                        "content": (
                                            "# entroping: managed-begin refund-auth\n"
                                            "GET {{base_url}}/refunds\n"
                                            "# entroping: managed-end refund-auth\n"
                                        ),
                                    }
                                ],
                            },
                        )
                    }
                }
            ],
        }

    with pytest.raises(ArchitectRefactorError, match="generated block is not present"):
        run_architect_refactor(
            law=law,
            target_glob="tests/manual/*.hurl",
            prompt="Add Authorization header.",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
            hurl_validator=lambda content, display_path: None,
        )

    assert target.read_text(encoding="utf-8") == original


def test_run_architect_refactor_rejects_edits_outside_selected_targets(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "generated" / "checkout.hurl"
    _write_architect_hurl(target, "GET {{base_url}}/checkout\nHTTP 200\n")
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Bad refactor",
                                "edits": [
                                    {
                                        "path": "tests/generated/other.hurl",
                                        "content": "GET {{base_url}}/other\nHTTP 200\n",
                                    }
                                ],
                            },
                        )
                    }
                }
            ],
        }

    with pytest.raises(ArchitectRefactorError, match="may only modify selected targets"):
        run_architect_refactor(
            law=law,
            target_glob="tests/generated/checkout.hurl",
            prompt="Add Authorization header.",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
            hurl_validator=lambda content, display_path: None,
        )

    assert "GET {{base_url}}/checkout" in target.read_text(encoding="utf-8")


def test_refactor_target_reader_rejects_unreadable_or_empty_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "tests" / "generated" / "checkout.hurl"
    _write_architect_hurl(target, "GET {{base_url}}/checkout\nHTTP 200\n")
    display_path = "tests/generated/checkout.hurl"

    original_stat = Path.stat

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == target:
            raise OSError("stat failed")
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fail_stat)
    with pytest.raises(ArchitectRefactorError, match="Could not inspect"):
        architect_refactor._read_refactor_target(target, display_path=display_path)

    monkeypatch.setattr(Path, "stat", original_stat)
    target.write_text("x" * 256_001, encoding="utf-8")
    with pytest.raises(ArchitectRefactorError, match="too large"):
        architect_refactor._read_refactor_target(target, display_path=display_path)

    target.write_bytes(b"\xff")
    with pytest.raises(ArchitectRefactorError, match="UTF-8"):
        architect_refactor._read_refactor_target(target, display_path=display_path)

    target.write_text("", encoding="utf-8")
    with pytest.raises(ArchitectRefactorError, match="must not be empty"):
        architect_refactor._read_refactor_target(target, display_path=display_path)

    target.write_text("# entroping: source=architect\nGET /checkout\nHTTP 200\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == target:
            raise OSError("read failed")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    with pytest.raises(ArchitectRefactorError, match="Could not read"):
        architect_refactor._read_refactor_target(target, display_path=display_path)


def test_architect_refactor_header_helper_handles_blank_and_manual_content() -> None:
    assert not architect_refactor._has_architect_header("")
    assert architect_refactor._has_architect_header("\n# entroping: source=architect\n")
    assert not architect_refactor._has_architect_header("\n# manual\n")


def test_run_architect_refactor_validates_all_edits_before_writing(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    target = tmp_path / "tests" / "generated" / "checkout.hurl"
    _write_architect_hurl(target, "GET {{base_url}}/checkout\nHTTP 200\n")
    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Invalid refactor",
                                "edits": [
                                    {
                                        "path": "tests/generated/checkout.hurl",
                                        "content": "GET {{base_url}}/checkout\nBAD\n",
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

    with pytest.raises(HurlValidationError, match="tests/generated/checkout.hurl"):
        run_architect_refactor(
            law=law,
            target_glob="tests/generated/checkout.hurl",
            prompt="Add Authorization header.",
            project_root=tmp_path,
            config_path=tmp_path / "qanstitution.yaml",
            client=LiteLLMClient(completion_func=fake_completion),
            hurl_validator=fail_validation,
        )

    assert "GET {{base_url}}/checkout" in target.read_text(encoding="utf-8")
