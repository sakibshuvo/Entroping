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


def test_pr_body_check_allows_non_sensitive_changed_files_without_security_gate(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Docs-only cleanup.\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: docs-only validation fixture.\n",
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
        "## Summary\n"
        "Runner change.\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: script-only validation fixture.\n",
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
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
        "- [x] `scripts/feature_gate.sh --security` for dependency, subprocess, "
        "LLM, proxy, report, or filesystem-sensitive work.\n\n"
        "Commands run:\n\n"
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


def test_pr_body_check_accepts_sensitive_changed_files_with_bare_security_gate_line(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Worker preflight change.\n\n"
        "## Verification\n\n"
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


def test_pr_body_check_rejects_guardrail_changes_without_quality_audit(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body_path.write_text(
        "## Summary\n"
        "Quality gate change.\n\n"
        "## Verification\n\n"
        "scripts/regression.sh --security\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation fixture.\n",
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
        "## Summary\n"
        "Quality gate change.\n\n"
        "## Verification\n\n"
        "scripts/regression.sh --security\n"
        "scripts/audit_quality.sh\n\n"
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation fixture.\n",
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
        "- [x] Merge authority: Tier A only after local gates and GitHub CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A only after local gates, GitHub CI, "
        "PR declaration, and finish cleanup\n"
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
        "- [x] Merge authority: Tier A only after local gates and GitHub CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: \n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A only after local gates, GitHub CI, "
        "PR declaration, and finish cleanup\n"
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
        "- [x] Merge authority: Tier A only after local gates and GitHub CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek-pro\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A only after local gates, GitHub CI, "
        "PR declaration, and finish cleanup\n"
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
        "- Merge authority: Tier A only after local gates, GitHub CI, "
        "PR declaration, and finish cleanup\n"
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
        "- [x] Merge authority: Tier A only after local gates and GitHub CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A only after local gates, GitHub CI, "
        "PR declaration, and finish cleanup\n"
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
        "- [x] Merge authority: Tier A only after local gates and GitHub CI.\n\n"
        "## OpenCode Provider Lane Evidence\n\n"
        "- Provider lane: opencode/native-deepseek\n"
        "- Provider host: OpenCode native provider\n"
        "- Billing path: paid DeepSeek inside OpenCode\n"
        "- Model id: deepseek/deepseek-v4-pro\n"
        "- Autonomy tier: Tier A autonomous lane\n"
        "- Merge authority: Tier A only after local gates, GitHub CI, "
        "PR declaration, and finish cleanup\n"
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
