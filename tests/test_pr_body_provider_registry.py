from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PR_BODY_CHECK = REPO_ROOT / "scripts" / "pr_body_check.py"


def _tier_a_body() -> str:
    return "\n".join(
        [
            "## Summary",
            "Provider authority guard.",
            "Verification lane: security-runtime",
            "",
            "Closes #1558",
            "",
            "## Agent Autonomy Declaration",
            "",
            "- [x] Tier A autonomous lane: bounded implementation.",
            "- [x] Merge authority: Tier A autonomous after gates and green CI.",
            "",
            "## OpenCode Provider Lane Evidence",
            "",
            "- Provider lane: opencode/native-deepseek",
            "- Provider host: OpenCode",
            "- Billing path: OpenCode free-model lane",
            "- Model id: opencode/deepseek-v4-flash-free",
            "- Autonomy tier: Tier A autonomous lane",
            "- Merge authority: Tier A autonomous after gates and green CI",
            "- Commands run: scripts/regression.sh --security",
            "",
            "## Documentation Impact Declaration",
            "",
            "- [x] No docs update needed. Reason: checker-only validation.",
        ]
    ) + "\n"


def _write_tier_a_issue(
    path: Path,
    *,
    body: str = "## Autonomy\n\nTier A autonomous lane.",
) -> None:
    _ = path.write_text(
        json.dumps(
            {
                "number": 1558,
                "state": "open",
                "body": body,
                "labels": [{"name": "autonomy:tier-a"}],
                "pull_request": None,
            }
        ),
        encoding="utf-8",
    )


def _run_pr_body_check(
    body_path: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PR_BODY_CHECK),
            "--body-file",
            str(body_path),
            "--require-opencode-evidence",
            "--issue",
            "1558",
            *extra_args,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_pr_body_help_describes_label_owned_issue_authority() -> None:
    result = subprocess.run(
        [sys.executable, str(PR_BODY_CHECK), "--help"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    normalized_help = " ".join(result.stdout.split())
    assert "number, state, labels, and pull_request" in normalized_help
    assert "number, state, body, and pull_request" not in normalized_help


def test_pr_body_rejects_unknown_paid_provider_model_combination(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    command = "uv run pytest tests/test_pr_body_provider_registry.py -q"
    body = "\n".join(
        [
            "## Summary",
            "Provider registry guard.",
            "",
            "Closes #1558",
            "",
            "## Agent Autonomy Declaration",
            "",
            "- [x] Tier C restricted lane: Codex owns implementation.",
            "- [x] Merge authority: Codex/human required.",
            "",
            "## OpenCode Provider Lane Evidence",
            "",
            "- Provider lane: deepseek-api/direct",
            "- Provider host: repo-local DeepSeek worker",
            "- Billing path: paid direct DeepSeek API",
            "- Model id: deepseek-v9-unregistered",
            "- Autonomy tier: Tier C restricted lane",
            "- Merge authority: Codex/human required",
            f"- Commands run: {command}",
            "",
            "## Documentation Impact Declaration",
            "",
            "- [x] Documentation updated.",
            "",
        ]
    )
    _ = body_path.write_text(
        body,
        encoding="utf-8",
    )

    result = _run_pr_body_check(body_path)

    assert result.returncode == 1
    assert "unknown paid provider/model combination" in result.stderr


def test_pr_body_rejects_paid_alias_for_free_model(tmp_path: Path) -> None:
    body_path = tmp_path / "pr-body.md"
    body = "\n".join(
        [
            "## Summary",
            "Provider registry guard.",
            "",
            "Closes #1558",
            "",
            "## Agent Autonomy Declaration",
            "",
            "- [x] Tier A autonomous lane: bounded implementation.",
            "- [x] Merge authority: Tier A autonomous after gates and green CI.",
            "",
            "## OpenCode Provider Lane Evidence",
            "",
            "- Provider lane: opencode/native-deepseek",
            "- Provider host: OpenCode",
            "- Billing path: paid DeepSeek inside OpenCode",
            "- Model id: opencode/deepseek-v4-flash-free",
            "- Autonomy tier: Tier A autonomous lane",
            "- Merge authority: Tier A autonomous after gates and green CI",
            "- Commands run: uv run pytest tests/test_pr_body_provider_registry.py -q",
            "",
            "## Documentation Impact Declaration",
            "",
            "- [x] Documentation updated.",
        ]
    )
    _ = body_path.write_text(body + "\n", encoding="utf-8")

    result = _run_pr_body_check(body_path)

    assert result.returncode == 1
    assert "billing path does not match" in result.stderr


def test_pr_body_rejects_autonomous_merge_authority_for_restricted_lane(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body = "\n".join(
        [
            "## Summary",
            "Provider authority guard.",
            "",
            "Closes #1558",
            "",
            "## Agent Autonomy Declaration",
            "",
            "- [x] Tier C restricted lane: Codex owns implementation.",
            "- [x] Merge authority: Tier A autonomous after gates and green CI.",
            "",
            "## OpenCode Provider Lane Evidence",
            "",
            "- Provider lane: deepseek-api/direct",
            "- Provider host: repo-local DeepSeek worker",
            "- Billing path: paid direct DeepSeek API",
            "- Model id: deepseek-v4-pro",
            "- Autonomy tier: Tier C restricted lane",
            "- Merge authority: Tier A autonomous after gates and green CI",
            "- Commands run: uv run pytest tests/test_pr_body_provider_registry.py -q",
            "",
            "## Documentation Impact Declaration",
            "",
            "- [x] No docs update needed. Reason: checker-only validation.",
        ]
    )
    _ = body_path.write_text(body + "\n", encoding="utf-8")

    result = _run_pr_body_check(body_path)

    assert result.returncode == 1
    assert "cannot use merge authority" in result.stderr


def test_pr_body_rejects_structured_autonomy_that_differs_from_declaration(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    body = "\n".join(
        [
            "## Summary",
            "Provider authority guard.",
            "",
            "Closes #1558",
            "",
            "## Agent Autonomy Declaration",
            "",
            "- [x] Tier C restricted lane: Codex owns implementation.",
            "- [x] Merge authority: Codex/human required.",
            "",
            "## OpenCode Provider Lane Evidence",
            "",
            "- Provider lane: deepseek-api/direct",
            "- Provider host: repo-local DeepSeek worker",
            "- Billing path: paid direct DeepSeek API",
            "- Model id: deepseek-v4-pro",
            "- Autonomy tier: Tier B assisted lane",
            "- Merge authority: Codex/human required",
            "- Commands run: uv run pytest tests/test_pr_body_provider_registry.py -q",
            "",
            "## Documentation Impact Declaration",
            "",
            "- [x] No docs update needed. Reason: checker-only validation.",
        ]
    )
    _ = body_path.write_text(body + "\n", encoding="utf-8")

    result = _run_pr_body_check(body_path)

    assert result.returncode == 1
    assert "does not match the checked Agent Autonomy Declaration" in result.stderr


def test_pr_body_rejects_tier_a_self_promotion_against_trusted_issue(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    issue_path = tmp_path / "issue.json"
    body = "\n".join(
        [
            "## Summary",
            "Provider authority guard.",
            "",
            "Closes #1558",
            "",
            "## Agent Autonomy Declaration",
            "",
            "- [x] Tier A autonomous lane: bounded implementation.",
            "- [x] Merge authority: Tier A autonomous after gates and green CI.",
            "",
            "## OpenCode Provider Lane Evidence",
            "",
            "- Provider lane: opencode/native-deepseek",
            "- Provider host: OpenCode",
            "- Billing path: OpenCode free-model lane",
            "- Model id: opencode/deepseek-v4-flash-free",
            "- Autonomy tier: Tier A autonomous lane",
            "- Merge authority: Tier A autonomous after gates and green CI",
            "- Commands run: uv run pytest tests/test_pr_body_provider_registry.py -q",
            "",
            "## Documentation Impact Declaration",
            "",
            "- [x] No docs update needed. Reason: checker-only validation.",
        ]
    )
    _ = body_path.write_text(body + "\n", encoding="utf-8")
    _ = issue_path.write_text(
        json.dumps(
            {
                "number": 1558,
                "state": "open",
                "body": "## Autonomy\n\nTier C restricted architecture lane.",
                "labels": [{"name": "autonomy:tier-c"}],
                "pull_request": None,
            }
        ),
        encoding="utf-8",
    )

    result = _run_pr_body_check(
        body_path,
        "--issue-metadata-file",
        str(issue_path),
        "--changed-file",
        "scripts/pr_body_check.py",
    )

    assert result.returncode == 1
    assert "does not match trusted issue autonomy tier" in result.stderr

    _ = issue_path.write_text(
        json.dumps(
            {
                "number": 1558,
                "state": "open",
                "body": "## Autonomy\n\nTier A autonomous lane.",
                "labels": [{"name": "autonomy:tier-a"}],
                "pull_request": None,
            }
        ),
        encoding="utf-8",
    )
    sensitive_result = _run_pr_body_check(
        body_path,
        "--issue-metadata-file",
        str(issue_path),
        "--changed-file",
        "scripts/pr_body_check.py",
    )

    assert sensitive_result.returncode == 1
    assert "forbidden for sensitive or release/quality guardrail changes" in (
        sensitive_result.stderr
    )


@pytest.mark.parametrize(
    "changed_file",
    [
        "docs/meta/provider-capability-registry.json",
        "docs/meta/provider-capability-registry.v1.schema.json",
        "scripts/provider_capability_types.py",
        "scripts/provider_capability_io.py",
        "scripts/provider_capability_registry.py",
        "scripts/provider_capability_schema.py",
        "scripts/update_provider_capability_schema.py",
        "scripts/ai_job_quarantine_modules/evidence.py",
        "scripts/ai_job_quarantine_modules/quarantine.py",
        "scripts/ai_job_quarantine_modules/requeue.py",
        "scripts/ai_job_quarantine.py",
        "scripts/opencode_readiness.py",
        "docs/meta/AGENT_CONTROL_PLANE.md",
        "docs/meta/AGENT_ROLE_REGISTRY.yaml",
        "docs/meta/DECISION_REGISTRY.yaml",
        "docs/meta/FACTORY_OPERATIONS.md",
        "docs/meta/prompt-library/model-comparison-trial.md",
        "docs/meta/prompt-library/model-output-acceptance-gate.md",
        "docs/meta/prompt-library/multi-agent-marathon.md",
        "docs/meta/prompt-library/opencode-codex-review-request.md",
        "docs/meta/prompt-library/opencode-desktop-handoff.md",
        "docs/meta/prompt-library/opencode-desktop-one-shot.md",
        "docs/technical/TDS.md",
        ".github/pull_request_template.md",
        "decisions/ADR-0024-provider-capability-registry.md",
        "tests/test_ai_job_quarantine.py",
        "tests/test_ci_workflow.py",
        "tests/test_doc_governance_script.py",
        "tests/test_provider_capability_registry_authorization.py",
        "tests/test_pr_body_provider_registry.py",
    ],
)
def test_pr_body_rejects_tier_a_changes_to_provider_authority_surface(
    tmp_path: Path,
    changed_file: str,
) -> None:
    body_path = tmp_path / "pr-body.md"
    issue_path = tmp_path / "issue.json"
    _ = body_path.write_text(_tier_a_body(), encoding="utf-8")
    _write_tier_a_issue(issue_path)

    result = _run_pr_body_check(
        body_path,
        "--issue-metadata-file",
        str(issue_path),
        "--changed-file",
        changed_file,
    )

    assert result.returncode == 1
    assert "forbidden for sensitive or release/quality guardrail changes" in result.stderr


@pytest.mark.parametrize("label", ["Autonomy tier", "Merge authority"])
def test_pr_body_rejects_duplicate_structured_authority_fields(
    tmp_path: Path,
    label: str,
) -> None:
    body_path = tmp_path / "pr-body.md"
    issue_path = tmp_path / "issue.json"
    duplicate = (
        "Tier C restricted lane"
        if label == "Autonomy tier"
        else "Codex/human required"
    )
    body = _tier_a_body().replace(
        "## Documentation Impact Declaration",
        f"- {label}: {duplicate}\n\n## Documentation Impact Declaration",
    )
    _ = body_path.write_text(body, encoding="utf-8")
    _write_tier_a_issue(issue_path)

    result = _run_pr_body_check(
        body_path,
        "--issue-metadata-file",
        str(issue_path),
    )

    assert result.returncode == 1
    assert f"exactly one {label.lower()}" in result.stderr


@pytest.mark.parametrize(
    "wrapper",
    [
        "comment",
        "fence",
        "quote",
        "indented",
        "short-fence-close",
        "wrong-fence-close",
    ],
)
def test_pr_body_ignores_non_authoritative_provider_evidence(
    tmp_path: Path,
    wrapper: str,
) -> None:
    event_path = tmp_path / "event.json"
    body = _tier_a_body()
    if wrapper == "comment":
        hidden_body = f"<!--\n{body}-->\n"
    elif wrapper == "fence":
        hidden_body = f"```markdown\n{body}```\n"
    elif wrapper == "quote":
        hidden_body = "\n".join(f"> {line}" for line in body.splitlines()) + "\n"
    elif wrapper == "indented":
        hidden_body = "\n".join(f"    {line}" for line in body.splitlines()) + "\n"
    elif wrapper == "short-fence-close":
        hidden_body = f"````markdown\n```\n{body}````\n"
    else:
        hidden_body = f"```markdown\n~~~\n{body}```\n"
    _ = event_path.write_text(
        json.dumps({"pull_request": {"body": hidden_body}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PR_BODY_CHECK),
            str(event_path),
            "--print-provider-evidence-issue",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_pr_body_detects_visible_evidence_after_inline_comment_literal(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    body = "Inline comment example: `<!--`\n\n" + _tier_a_body()
    _ = event_path.write_text(
        json.dumps({"pull_request": {"body": body}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PR_BODY_CHECK),
            str(event_path),
            "--print-provider-evidence-issue",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1558"


def test_pr_body_detects_visible_evidence_after_escaped_backtick(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    body = "\\` escaped literal\n" + _tier_a_body() + "\n` unmatched literal\n"
    _ = event_path.write_text(
        json.dumps({"pull_request": {"body": body}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PR_BODY_CHECK),
            str(event_path),
            "--print-provider-evidence-issue",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1558"


def test_pr_body_detects_authority_headings_that_end_lazy_blockquote(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    body = _tier_a_body().replace(
        "## Agent Autonomy Declaration",
        "> quoted paragraph\n## Agent Autonomy Declaration",
    ).replace(
        "## OpenCode Provider Lane Evidence",
        "> quoted paragraph\n## OpenCode Provider Lane Evidence",
    )
    _ = event_path.write_text(
        json.dumps({"pull_request": {"body": body}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PR_BODY_CHECK),
            str(event_path),
            "--print-provider-evidence-issue",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1558"


def test_pr_body_ignores_closing_issue_in_lazy_blockquote_continuation(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "event.json"
    body = _tier_a_body().replace(
        "Closes #1558",
        "> quoted paragraph\nCloses #1558",
    )
    _ = event_path.write_text(
        json.dumps({"pull_request": {"body": body}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PR_BODY_CHECK),
            str(event_path),
            "--print-provider-evidence-issue",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "must close exactly one GitHub issue" in result.stderr


@pytest.mark.parametrize(
    "issue_body",
    [
        "<!--\n## Autonomy\n\nTier A autonomous lane.\n-->",
        "    ## Autonomy\n\n    Tier A autonomous lane.",
        "````markdown\n```\n## Autonomy\n\nTier A autonomous lane.\n````",
    ],
)
def test_pr_body_ignores_prompt_like_issue_body_when_label_grants_tier_a(
    tmp_path: Path,
    issue_body: str,
) -> None:
    body_path = tmp_path / "pr-body.md"
    issue_path = tmp_path / "issue.json"
    _ = body_path.write_text(_tier_a_body(), encoding="utf-8")
    _write_tier_a_issue(
        issue_path,
        body=issue_body,
    )

    result = _run_pr_body_check(
        body_path,
        "--issue-metadata-file",
        str(issue_path),
    )

    assert result.returncode == 0, result.stderr


def test_pr_body_accepts_trusted_issue_heading_after_blockquote(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "pr-body.md"
    issue_path = tmp_path / "issue.json"
    _ = body_path.write_text(_tier_a_body(), encoding="utf-8")
    _write_tier_a_issue(
        issue_path,
        body="> quoted paragraph\n## Autonomy\n\nTier A autonomous lane.",
    )

    result = _run_pr_body_check(
        body_path,
        "--issue-metadata-file",
        str(issue_path),
    )

    assert result.returncode == 0, result.stderr


def test_pr_body_rejects_symlinked_trusted_issue_metadata(tmp_path: Path) -> None:
    body_path = tmp_path / "pr-body.md"
    issue_target = tmp_path / "issue-target.json"
    issue_link = tmp_path / "issue.json"
    _ = body_path.write_text(
        "## Documentation Impact Declaration\n\n"
        "- [x] No docs update needed. Reason: checker-only validation.\n",
        encoding="utf-8",
    )
    _ = issue_target.write_text(
        json.dumps(
            {
                "number": 1558,
                "state": "open",
                "body": "## Autonomy\n\nTier C restricted lane.",
                "pull_request": None,
            }
        ),
        encoding="utf-8",
    )
    issue_link.symlink_to(issue_target)

    result = _run_pr_body_check(
        body_path,
        "--issue-metadata-file",
        str(issue_link),
    )

    assert result.returncode == 1
    assert "could not safely open trusted issue metadata" in result.stderr


def test_pr_body_reports_declared_provider_evidence_issue_for_ci(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    _ = event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": (
                        "Closes #1558\n\n"
                        "## Agent Autonomy Declaration\n\n"
                        "- [x] Tier C restricted lane: no autonomous merge.\n"
                        "- [x] Merge authority: Tier A autonomous after gates and green CI.\n"
                    )
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PR_BODY_CHECK),
            str(event_path),
            "--print-provider-evidence-issue",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1558"
