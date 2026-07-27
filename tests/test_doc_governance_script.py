"""Tests for executable documentation governance."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_GOVERNANCE_SCRIPT = REPO_ROOT / "scripts" / "doc_governance_check.sh"
PR_BODY_SCRIPT = REPO_ROOT / "scripts" / "pr_body_check.py"


def run_pr_body_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PR_BODY_SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _body_with_lane(
    *,
    lane: str,
    commands: str,
    docs_line: str = "- [x] No docs update needed. Reason: checker fixture.\n",
) -> str:
    return (
        "## Summary\n"
        "Verification lane fixture.\n\n"
        "## Verification\n\n"
        f"- Verification lane: {lane}\n\n"
        "Commands run:\n\n"
        "```text\n"
        f"{commands}"
        "```\n\n"
        "## Documentation Impact Declaration\n\n"
        f"{docs_line}"
    )


def _dependabot_event(*, login: str = "dependabot[bot]") -> dict[str, object]:
    return {
        "pull_request": {
            "title": "build(deps): bump actions/checkout from 6 to 7",
            "body": "Bumps actions/checkout from 6 to 7.",
            "user": {"login": login, "type": "Bot"},
        }
    }


def test_doc_governance_help_documents_control_plane() -> None:
    result = subprocess.run(
        [str(DOC_GOVERNANCE_SCRIPT), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "documentation control plane" in result.stdout
    assert "ROADMAP.md" in result.stdout
    assert "Documentation Impact Declaration" in result.stdout


def test_doc_governance_passes_current_repo() -> None:
    result = subprocess.run(
        [str(DOC_GOVERNANCE_SCRIPT)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Documentation governance OK" in result.stdout


def test_doc_governance_rejects_missing_required_marker(tmp_path: Path) -> None:
    (tmp_path / "docs" / "meta").mkdir(parents=True)
    (tmp_path / ".github").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "README.md").write_text("README without roadmap link\n", encoding="utf-8")
    (tmp_path / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    (tmp_path / "docs/meta/VAULT_INDEX.md").write_text("# Index\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (tmp_path / ".github" / "pull_request_template.md").write_text(
        "## Summary\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "feature_gate.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (tmp_path / "docs" / "meta" / "FEATURE_DELIVERY_CHECKLIST.md").write_text(
        "# Checklist\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "meta" / "PROJECT_PROGRESS.md").write_text(
        "# Progress\n",
        encoding="utf-8",
    )
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "changelog.md").write_text("# Changelog\n", encoding="utf-8")

    result = subprocess.run(
        [str(DOC_GOVERNANCE_SCRIPT), "--root", str(tmp_path)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Documentation governance failed" in result.stderr
    assert "README.md" in result.stderr


def test_pr_body_check_accepts_documentation_impact_declaration(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": (
                        "## Summary\n"
                        "Change\n\n"
                        "## Documentation Impact Declaration\n\n"
                        "- [x] Roadmap/progress updated: ROADMAP.md and PROJECT_PROGRESS.md\n"
                        "- [ ] No docs update needed. Reason:\n"
                    )
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(str(event_path))

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_help_documents_local_body_file_mode() -> None:
    result = run_pr_body_check("--help")

    assert result.returncode == 0
    assert "--body-file" in result.stdout
    assert "--changed-file" in result.stdout
    assert "Verification lane" in result.stdout


def test_pr_body_check_accepts_local_body_file(tmp_path: Path) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Change\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: tool-only local validation mode.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check("--body-file", str(body_path))

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_accepts_normal_pr_body_without_opencode_evidence(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Reviewer notes mention OpenCode and DeepSeek, but this is a normal PR.\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: default validation only checks docs impact.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check("--body-file", str(body_path))

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_accepts_scoped_dependabot_pr_without_docs_declaration(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_dependabot_event()), encoding="utf-8")

    result = run_pr_body_check(
        str(event_path),
        "--changed-file",
        ".github/workflows/ci.yml",
        "--changed-file",
        ".github/workflows/pages.yml",
    )

    assert result.returncode == 0, result.stderr
    assert "dependency automation lane" in result.stdout


def test_pr_body_check_accepts_scoped_dependabot_npm_pr_without_docs_declaration(
    tmp_path: Path,
) -> None:
    event = _dependabot_event()
    pull_request = event["pull_request"]
    assert isinstance(pull_request, dict)
    pull_request["title"] = "build(deps): bump astro from 7.0.7 to 7.1.3"
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")

    result = run_pr_body_check(
        str(event_path),
        "--changed-file",
        "package.json",
        "--changed-file",
        "package-lock.json",
    )

    assert result.returncode == 0, result.stderr
    assert "dependency automation lane" in result.stdout


def test_pr_body_check_rejects_malformed_dependabot_title_without_docs_declaration(
    tmp_path: Path,
) -> None:
    event = _dependabot_event()
    pull_request = event["pull_request"]
    assert isinstance(pull_request, dict)
    pull_request["title"] = "build(deps::ci): bump actions/checkout from 6 to 7"
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")

    result = run_pr_body_check(
        str(event_path),
        "--changed-file",
        ".github/workflows/ci.yml",
    )

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_rejects_human_pr_without_docs_declaration_for_dependency_files(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(_dependabot_event(login="sakibshuvo")),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        str(event_path),
        "--changed-file",
        ".github/workflows/ci.yml",
    )

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_rejects_human_npm_pr_without_docs_declaration(
    tmp_path: Path,
) -> None:
    event = _dependabot_event(login="sakibshuvo")
    pull_request = event["pull_request"]
    assert isinstance(pull_request, dict)
    pull_request["title"] = "build(deps): bump astro from 7.0.7 to 7.1.3"
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")

    result = run_pr_body_check(
        str(event_path),
        "--changed-file",
        "package.json",
        "--changed-file",
        "package-lock.json",
    )

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_rejects_nonstandard_dependency_author_without_docs_declaration(
    tmp_path: Path,
) -> None:
    event = _dependabot_event()
    pull_request = event["pull_request"]
    assert isinstance(pull_request, dict)
    pull_request.pop("user")
    pull_request["author"] = {"login": "dependabot[bot]", "type": "Bot"}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")

    result = run_pr_body_check(
        str(event_path),
        "--changed-file",
        ".github/workflows/ci.yml",
    )

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_rejects_dependabot_pr_without_docs_declaration_for_source_files(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_dependabot_event()), encoding="utf-8")

    result = run_pr_body_check(
        str(event_path),
        "--changed-file",
        "src/entroping/core/run_workflow.py",
    )

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_rejects_changed_files_without_verification_lane(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Docs-only cleanup.\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "docs/meta/PROJECT_PROGRESS.md",
    )

    assert result.returncode == 1
    assert "Verification lane" in result.stderr


def test_pr_body_check_accepts_tiny_docs_lane_with_docs_governance(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="tiny-docs",
            commands="scripts/doc_governance_check.sh\n",
            docs_line="- [x] Roadmap/progress updated: docs/meta/PROJECT_PROGRESS.md\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "docs/meta/PROJECT_PROGRESS.md",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_rejects_tiny_docs_lane_for_prompt_guardrails(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="tiny-docs",
            commands="scripts/doc_governance_check.sh\n",
            docs_line="- [x] ADR/spec/context updated: prompt-library.\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "docs/meta/prompt-library/issue-worker.md",
    )

    assert result.returncode == 1
    assert "docs-guardrail" in result.stderr
    assert "tiny-docs" in result.stderr


def test_pr_body_check_accepts_docs_guardrail_lane_with_focused_doc_test(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="docs-guardrail",
            commands=(
                "uv run pytest tests/test_agent_workflow_docs.py -q\n"
                "scripts/doc_governance_check.sh\n"
            ),
            docs_line="- [x] ADR/spec/context updated: prompt-library.\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "docs/meta/prompt-library/issue-worker.md",
        "--changed-file",
        "tests/test_agent_workflow_docs.py",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_rejects_normal_code_lane_without_feature_gate(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="normal-code",
            commands="uv run pytest tests/test_models.py -q\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "src/entroping/models/doctor.py",
    )

    assert result.returncode == 1
    assert "normal-code" in result.stderr
    assert "scripts/feature_gate.sh" in result.stderr


def test_pr_body_check_allows_non_sensitive_changed_files_without_security_gate(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="tiny-docs",
            commands="scripts/doc_governance_check.sh\n",
            docs_line="- [x] No docs update needed. Reason: docs-only validation fixture.\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "docs/meta/PROJECT_PROGRESS.md",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_rejects_sensitive_changed_files_without_security_gate(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="security-runtime",
            commands="uv run pytest tests/test_hurl_runner.py -q\n",
            docs_line="- [x] No docs update needed. Reason: script-only validation fixture.\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "src/entroping/core/hurl_runner.py",
    )

    assert result.returncode == 1
    assert "Sensitive surface changes require documented security gate evidence" in result.stderr
    assert "src/entroping/core/hurl_runner.py" in result.stderr
    assert "hurl-runner" in result.stderr


def test_pr_body_check_accepts_sensitive_changed_files_with_security_gate(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="security-runtime",
            commands="scripts/regression.sh --security\n",
            docs_line="- [x] No docs update needed. Reason: script-only validation fixture.\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_accepts_sensitive_changed_files_with_checked_bare_security_gate(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n"
        "- [x] scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_accepts_sensitive_changed_files_with_commands_run_security_gate(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n"
        "Commands run:\n"
        "scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_accepts_commands_run_after_non_marker_not_run_text(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n"
        "- Note: the old check was not running before this fix.\n\n"
        "Commands run:\n"
        "scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_accepts_checked_command_inside_commands_run_section(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n"
        "Commands run:\n"
        "- [x] scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_rejects_security_gate_only_in_example_code_block(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n\n"
        "Example command:\n\n"
        "```text\n"
        "scripts/regression.sh --security\n"
        "```\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 1
    assert "security-runtime" in result.stderr
    assert "security gate evidence" in result.stderr


def test_pr_body_check_rejects_security_gate_only_in_blockquote(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n\n"
        "> - [x] scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 1
    assert "security-runtime" in result.stderr
    assert "security gate evidence" in result.stderr


def test_pr_body_check_rejects_security_gate_only_in_unchecked_item(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n"
        "- [ ] scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 1
    assert "security-runtime" in result.stderr
    assert "security gate evidence" in result.stderr


def test_pr_body_check_rejects_security_gate_only_in_not_run_section(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n\n"
        "Commands not run:\n"
        "scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 1
    assert "security-runtime" in result.stderr
    assert "security gate evidence" in result.stderr


def test_pr_body_check_rejects_security_gate_only_in_qualified_not_run_section(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n\n"
        "## Commands not run (already verified elsewhere)\n"
        "- [x] scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 1
    assert "security-runtime" in result.stderr
    assert "security gate evidence" in result.stderr


def test_pr_body_check_rejects_checked_security_gate_under_not_run_item(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- Verification lane: security-runtime\n\n"
        "- Commands not run:\n"
        "- [x] scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/deepseek_worker.py",
    )

    assert result.returncode == 1
    assert "security-runtime" in result.stderr
    assert "security gate evidence" in result.stderr


def test_pr_body_check_rejects_guardrail_changes_without_quality_audit(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="release-ci-architecture",
            commands="scripts/regression.sh --security\n",
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/audit_quality.sh",
    )

    assert result.returncode == 1
    assert "Quality/architecture guardrail changes require documented quality audit" in (
        result.stderr
    )
    assert "scripts/audit_quality.sh" in result.stderr


def test_pr_body_check_accepts_guardrail_changes_with_quality_audit(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="release-ci-architecture",
            commands=(
                "scripts/regression.sh --security\n"
                "scripts/audit_quality.sh\n"
            ),
        ),
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--changed-file",
        "scripts/audit_quality.sh",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_rejects_opencode_evidence_missing_provider_lane(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "OpenCode worker used DeepSeek V4 Pro.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A autonomous after gates and green CI\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "provider lane" in result.stderr


def test_pr_body_check_rejects_opencode_evidence_empty_provider_lane(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "OpenCode worker used DeepSeek V4 Pro.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: \n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A autonomous after gates and green CI\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "provider lane" in result.stderr


def test_pr_body_check_rejects_opencode_evidence_extended_provider_lane(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "OpenCode worker used a custom DeepSeek lane.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek-pro\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A autonomous after gates and green CI\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "provider lane must be one of" in result.stderr


def test_pr_body_check_rejects_unchecked_opencode_evidence_fields(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Tier A OpenCode worker guard update.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- [ ] Provider lane: opencode/native-deepseek\n"
        "- [x] Provider host: OpenCode native provider\n"
        "- [x] Billing path: paid DeepSeek inside OpenCode\n"
        "- [x] Model id: deepseek/deepseek-v4-pro\n"
        "- [x] Autonomy tier: Tier A autonomous lane\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI\n"
        "- [x] Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "provider lane" in result.stderr


def test_pr_body_check_rejects_invalid_opencode_autonomy_tier(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Tier A OpenCode worker guard update.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A but basically safe\n"
        "- Merge authority: Tier A autonomous after gates and green CI\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "autonomy tier must be one of" in result.stderr


def test_pr_body_check_rejects_invalid_opencode_merge_authority(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Tier A OpenCode worker guard update.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: merge whenever it looks green\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "merge authority must be one of" in result.stderr


def test_pr_body_check_requires_issue_for_opencode_evidence(tmp_path: Path) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Tier A OpenCode worker guard update.\n\n"
        "Closes #706\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
    )

    assert result.returncode == 2
    assert "--issue is required" in result.stderr


def test_pr_body_check_rejects_checked_empty_autonomy_detail(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Tier A OpenCode worker guard update.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Merge authority:\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A autonomous after gates and green CI\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "Checked agent autonomy declaration needs detail" in result.stderr


def test_pr_body_check_rejects_ambiguous_opencode_wording_without_lane(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Implemented by OpenCode with DeepSeek V4 Pro.\n\n"
        "Closes #706\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "concrete provider lane" in result.stderr


def test_pr_body_check_rejects_opencode_evidence_missing_closing_keyword(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Tier A OpenCode worker guard update.\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A autonomous after gates and green CI\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 1
    assert "Closes #706" in result.stderr


def test_pr_body_check_accepts_tier_a_opencode_provider_lane_evidence(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Tier A OpenCode worker guard update.\n\n"
        "Closes #706\n\n"
        "## Agent Autonomy Declaration\n\n"
        "- [x] Tier A autonomous lane: low-risk docs/tests/guard/script work only.\n"
        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A autonomous after gates and green CI\n"
        "- Commands run: uv run pytest tests/test_doc_governance_script.py -q\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_accepts_codex_spark_provider_lane_evidence(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="docs-guardrail",
            commands=(
                "scripts/doc_governance_check.sh\n"
                "uv run pytest tests/test_doc_governance_script.py -q\n"
            ),
            docs_line="- [x] No docs update needed. Reason: checker-only validation.\n",
        )
        + "\n"
        + "Closes #706\n\n"
        + "## Agent Autonomy Declaration\n\n"
        + "- [x] Tier B assisted lane: implementation may be agent-generated,"
        + " but merge requires human or Codex review.\n"
        + "- [x] Merge authority: Codex/human required.\n\n"
        + "## OpenCode Provider Lane Evidence\n\n"
        + "- Provider lane: codex-spark\n"
        + "- Provider host: Codex Spark\n"
        + "- Billing path: Codex quota\n"
        + "- Model id: Spark\n"
        + "- Autonomy tier: Tier B assisted lane\n"
        + "- Merge authority: Codex/human required\n"
        + "- Commands run: scripts/pr_body_check.py --body-file <path>\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
        "--changed-file",
        "README.md",
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_rejects_invalid_codex_spark_lane(tmp_path: Path) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        _body_with_lane(
            lane="docs-guardrail",
            commands=(
                "scripts/doc_governance_check.sh\n"
                "uv run pytest tests/test_doc_governance_script.py -q\n"
            ),
            docs_line="- [x] No docs update needed. Reason: checker-only validation.\n",
        )
        + "\n"
        + "Closes #706\n\n"
        + "## Agent Autonomy Declaration\n\n"
        + "- [x] Tier B assisted lane: implementation may be agent-generated,"
        + " but merge requires human or Codex review.\n"
        + "- [x] Merge authority: Codex/human required.\n\n"
        + "## OpenCode Provider Lane Evidence\n\n"
        + "- Provider lane: codex-sparkx\n"
        + "- Provider host: Codex Spark\n"
        + "- Billing path: Codex quota\n"
        + "- Model id: Spark\n"
        + "- Autonomy tier: Tier B assisted lane\n"
        + "- Merge authority: Codex/human required\n"
        + "- Commands run: scripts/pr_body_check.py --body-file <path>\n",
        encoding="utf-8",
    )

    result = run_pr_body_check(
        "--body-file",
        str(body_path),
        "--require-opencode-evidence",
        "--issue",
        "706",
        "--changed-file",
        "README.md",
    )

    assert result.returncode == 1, result.stderr
    assert "provider lane must be one of" in result.stderr


def test_pr_body_check_rejects_local_body_file_missing_declaration(tmp_path: Path) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text("## Summary\nOnly summary\n", encoding="utf-8")

    result = run_pr_body_check("--body-file", str(body_path))

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_rejects_local_body_file_unchecked_declaration(tmp_path: Path) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Change\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [ ] No docs update needed. Reason: unchecked is not enough.\n",
        encoding="utf-8",
    )

    result = run_pr_body_check("--body-file", str(body_path))

    assert result.returncode == 1
    assert "must check at least one" in result.stderr


def test_pr_body_check_rejects_missing_declaration(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": {"body": "## Summary\nOnly summary"}}))

    result = run_pr_body_check(str(event_path))

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_skips_non_pr_events(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"ref": "refs/heads/main"}), encoding="utf-8")

    result = run_pr_body_check(str(event_path))

    assert result.returncode == 0
    assert "No pull request payload" in result.stdout
