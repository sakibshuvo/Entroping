"""Tests for local software-factory role and metrics tooling."""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "factory_metrics.py"
ROLE_REGISTRY = REPO_ROOT / "docs" / "meta" / "AGENT_ROLE_REGISTRY.yaml"
PYTHON3_FACTORY_ENTRYPOINTS = (
    REPO_ROOT / "scripts" / "ai_jobs.py",
    REPO_ROOT / "scripts" / "deepseek_worker.py",
    REPO_ROOT / "scripts" / "factory_metrics.py",
    REPO_ROOT / "scripts" / "opencode_worker.py",
)


def run_factory_metrics(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _load_factory_metrics_module() -> Any:
    spec = importlib.util.spec_from_file_location("factory_metrics", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _factory_event(
    *,
    issue: str,
    agent: str = "Codex",
    role: str = "integrator",
    event_type: str = "worker_job",
    estimated_tokens: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "entroping.factory-metrics.v1",
        "event_id": f"event-{issue}-{agent}",
        "recorded_at": "2026-06-14T00:00:00Z",
        "event_type": event_type,
        "role": role,
        "agent": agent,
        "issue": issue,
        "metrics": {"estimated_tokens": estimated_tokens},
        "outcome": "success",
        "decision": "accepted",
    }


def _required_context_tool_metrics(**overrides: int | float) -> dict[str, int | float]:
    metrics: dict[str, int | float] = {
        "grounded_file_hit_rate": 1.0,
        "nonexistent_reference_count": 0,
        "forbidden_scope_incidents": 0,
        "retrieval_precision": 0.5,
        "retrieval_recall": 0.5,
        "stale_claim_count": 0,
        "context_recovery_time_seconds": 120,
        "review_correction_count": 1,
        "human_steering_count": 1,
        "accepted_output_ratio": 0.5,
        "context_bytes": 4000,
        "estimated_tokens": 1000,
    }
    metrics.update(overrides)
    return metrics


def _context_tool_scorecard(
    *,
    tool_evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "entroping.context-tool-scorecard.v1",
        "scorecard_id": "issue-710-context-tools",
        "recorded_at": "2026-06-14T00:00:00Z",
        "baseline": {
            "name": "repo-native baseline",
            "components": [
                "rg",
                "scripts/context_pack.sh",
                "docs/meta/DECISION_REGISTRY.yaml",
                "curated Git-backed Markdown",
                "GitHub issues, PRs, and CI",
                "tests and gates",
            ],
        },
        "tool_evaluations": tool_evaluations,
    }


def _context_tool_evaluation(
    *,
    tool: str = "ContextMap",
    proof_status: str = "measured",
    recommended_status: str = "optional_manual",
    setup: dict[str, Any] | None = None,
    trials: list[dict[str, Any]] | None = None,
    evidence_sources: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    evaluation: dict[str, Any] = {
        "tool": tool,
        "tool_layer": "graph_context",
        "proof_status": proof_status,
        "status_before": "probation",
        "recommended_status": recommended_status,
        "evidence_sources": evidence_sources
        if evidence_sources is not None
        else [
            {
                "source_type": "github_issue",
                "reference": "#602",
                "summary": "Context-map pilot against report audit-chain issue.",
            },
            {
                "source_type": "curated_markdown",
                "reference": "docs/meta/CONTEXT_MANAGEMENT.md",
                "summary": "Canonical context-tool boundary.",
            },
        ],
        "trials": trials
        if trials is not None
        else [
            {
                "issue": "602",
                "packet_type": "source_test_impact",
                "workflow": "context_map_assisted",
                "baseline_workflow": "repo_native",
                "metrics": _required_context_tool_metrics(
                    retrieval_precision=0.75,
                    retrieval_recall=0.75,
                    context_recovery_time_seconds=90,
                    context_bytes=4500,
                    estimated_tokens=1125,
                ),
                "baseline_metrics": _required_context_tool_metrics(),
                "evidence_summary": (
                    "Context-map output helped only after exact symbol seeding; "
                    "baseline was better for initial orientation."
                ),
            }
        ],
    }
    if setup is not None:
        evaluation["setup"] = setup
    return evaluation


def _write_jsonl(path: Path, *events: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{json.dumps(event, sort_keys=True)}\n" for event in events),
        encoding="utf-8",
    )


def test_agent_role_registry_defines_portable_factory_roles() -> None:
    registry = yaml.safe_load(ROLE_REGISTRY.read_text(encoding="utf-8"))

    assert registry["schema_version"] == "entroping.agent-role-registry.v1"
    assert registry["portable"] is True
    assert registry["source_of_truth_order"][:3] == [
        "local_repo_files_and_tests",
        "github_issues_prs_ci",
        "adrs_and_canonical_docs",
    ]

    roles = registry["roles"]
    assert set(roles) >= {
        "product_manager",
        "architect",
        "dev_agent",
        "qa_agent",
        "code_review_agent",
        "security_agent",
        "monitoring_agent",
        "integrator",
    }

    for role_id, role in roles.items():
        assert role["display_name"]
        assert role["mission"]
        assert role["suggested_context_modes"]
        assert role["allowed_authority"]
        assert role["forbidden_decisions"]
        assert role["metrics_tags"]
        assert role["default_autonomy_tier"] in {"tier_a", "tier_b", "tier_c"}
        assert "source_of_truth_override" in role["forbidden_decisions"]
        assert role_id in role["metrics_tags"]


def test_agent_role_registry_defines_tier_a_cheap_worker_routing_defaults() -> None:
    registry = yaml.safe_load(ROLE_REGISTRY.read_text(encoding="utf-8"))
    routing = registry["worker_routing_defaults"]

    tier_a = routing["tier_a"]
    assert tier_a["default_engine"] == "opencode"
    assert tier_a["default_profile"] == "flash-free"
    assert tier_a["default_model"] == "opencode/deepseek-v4-flash-free"
    assert tier_a["default_provider_lane"] == "opencode/native-deepseek"
    assert tier_a["fallback_provider_lanes"] == [
        "deepseek-api/direct",
        "local/offline",
    ]
    assert tier_a["context_manifest_command"] == (
        "scripts/context_pack.sh --mode implementation --manifest"
    )
    assert "request only the needed files/snippets" in tier_a["context_rule"]
    assert tier_a["merge_authority"] == ("Tier A autonomous after gates and green CI")

    assert routing["tier_b"]["merge_authority"] == "Codex/human required"
    assert routing["tier_c"]["merge_authority"] == "Codex/human required"
    assert "security-sensitive" in routing["tier_c"]["stop_condition"]


def test_factory_metrics_role_set_matches_registry() -> None:
    registry = yaml.safe_load(ROLE_REGISTRY.read_text(encoding="utf-8"))
    module = _load_factory_metrics_module()

    assert set(registry["roles"]) == module.ROLES


def test_factory_metrics_entrypoint_is_thin_module_wrapper() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    top_level_functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    modules = {
        path.name for path in (REPO_ROOT / "scripts" / "factory_metrics_modules").glob("*.py")
    }

    assert top_level_functions == []
    assert {
        "__init__.py",
        "cli.py",
        "common.py",
        "context_scorecard.py",
        "events.py",
        "reporting.py",
        "schema.py",
    } <= modules


def test_factory_python3_entrypoints_avoid_evaluated_python310_plus_apis() -> None:
    unsupported_by_script: dict[str, list[str]] = {}

    for script in PYTHON3_FACTORY_ENTRYPOINTS:
        tree = ast.parse(script.read_text(encoding="utf-8"))
        unsupported_usages: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "datetime":
                for alias in node.names:
                    if alias.name == "UTC":
                        unsupported_usages.append("from datetime import UTC")
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "UTC"
                and isinstance(node.value, ast.Name)
                and node.value.id == "datetime"
            ):
                unsupported_usages.append("datetime.UTC")
            if isinstance(node, ast.Name) and node.id == "UTC":
                unsupported_usages.append("UTC")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "isinstance"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.BinOp)
                and isinstance(node.args[1].op, ast.BitOr)
            ):
                unsupported_usages.append("isinstance(..., type | type)")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "dataclass"
                and any(
                    keyword.arg == "slots"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                )
            ):
                unsupported_usages.append("dataclass(..., slots=True)")
        if unsupported_usages:
            unsupported_by_script[script.relative_to(REPO_ROOT).as_posix()] = unsupported_usages

    assert unsupported_by_script == {}


def test_factory_python3_entrypoints_smoke_under_host_python3() -> None:
    compile_result = subprocess.run(
        ["python3", "-m", "py_compile", *(str(script) for script in PYTHON3_FACTORY_ENTRYPOINTS)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert compile_result.returncode == 0, compile_result.stderr

    help_failures: dict[str, dict[str, object]] = {}
    for script in PYTHON3_FACTORY_ENTRYPOINTS:
        result = subprocess.run(
            ["python3", str(script), "--help"],
            check=False,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or "usage:" not in result.stdout.lower():
            help_failures[script.relative_to(REPO_ROOT).as_posix()] = {
                "returncode": result.returncode,
                "stdout": result.stdout[-1000:],
                "stderr": result.stderr[-1000:],
            }

    assert help_failures == {}


def test_factory_metrics_append_writes_local_jsonl_with_context_counts(
    tmp_path: Path,
) -> None:
    context_file = tmp_path / "context.md"
    context_file.write_text("abcd" * 25, encoding="utf-8")
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "context_pack",
        "--role",
        "architect",
        "--agent",
        "Codex",
        "--tool",
        "scripts/context_pack.sh",
        "--issue",
        "652",
        "--worktree",
        "/tmp/Entroping-issue-652",
        "--context-file",
        str(context_file),
        "--candidate-files",
        "4",
        "--files-read",
        "2",
        "--outcome",
        "success",
        "--decision",
        "accepted",
        "--note",
        "api_key=live-secret-token",
        "--ledger",
        str(ledger),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "recorded"
    assert Path(payload["ledger_path"]) == ledger

    [event] = _read_jsonl(ledger)
    assert event["schema_version"] == "entroping.factory-metrics.v1"
    assert event["event_type"] == "context_pack"
    assert event["role"] == "architect"
    assert event["agent"] == "Codex"
    assert event["issue"] == "652"
    assert event["metrics"]["context_bytes"] == 100
    assert event["metrics"]["estimated_tokens"] == 25
    assert event["metrics"]["candidate_files"] == 4
    assert event["metrics"]["files_read"] == 2
    assert event["outcome"] == "success"
    assert event["decision"] == "accepted"
    assert "live-secret-token" not in json.dumps(event)
    assert "api_key=<redacted>" in event["note"]


def test_factory_metrics_redacts_common_secret_shapes(tmp_path: Path) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "Codex",
        "--note",
        "access_token=ghp_FAKE_NOT_A_SECRET_1234567890 aws_access_key_id=AKIAIOSFODNN7EXAMPLE",
        "--ledger",
        str(ledger),
    )

    assert result.returncode == 0, result.stderr
    [event] = _read_jsonl(ledger)
    event_json = json.dumps(event)
    assert "ghp_FAKE_NOT_A_SECRET_1234567890" not in event_json
    assert "AKIAIOSFODNN7EXAMPLE" not in event_json
    assert "access_token=<redacted>" in event["note"]
    assert "aws_access_key_id=<redacted>" in event["note"]


def test_factory_metrics_rejects_append_over_active_aggregate_limit(
    tmp_path: Path,
) -> None:
    metrics_root = tmp_path / ".entroping" / "factory-metrics"
    metrics_root.mkdir(parents=True)
    filler = metrics_root / "bounded-filler.bin"
    with filler.open("wb") as handle:
        handle.truncate(67_108_864)
    ledger = metrics_root / "events.jsonl"

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "Codex",
        "--ledger",
        str(ledger),
    )

    assert result.returncode == 2
    assert "aggregate limit" in result.stderr
    assert not ledger.exists()


def test_factory_metrics_aggregate_excludes_finished_issue_archives(
    tmp_path: Path,
) -> None:
    metrics_root = tmp_path / ".entroping" / "factory-metrics"
    archive = metrics_root / "finished-issues" / "issue-1"
    archive.mkdir(parents=True)
    with (archive / "events.jsonl").open("wb") as handle:
        handle.truncate(67_108_864)
    ledger = metrics_root / "events.jsonl"

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "Codex",
        "--ledger",
        str(ledger),
    )

    assert result.returncode == 0, result.stderr
    assert ledger.exists()


def test_factory_metrics_rejects_raw_prompt_or_transcript_notes(tmp_path: Path) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "Codex",
        "--note",
        "raw prompt: inspect the provider transcript and stdout",
        "--ledger",
        str(ledger),
    )

    assert result.returncode == 2
    assert "note must not contain raw prompt or transcript material" in result.stderr
    assert not ledger.exists()


def test_factory_metrics_rejects_prompt_note_variants(tmp_path: Path) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    for note in ("raw-prompt: inspect this", '{"prompt": "inspect this"}'):
        result = run_factory_metrics(
            "--repo-root",
            str(tmp_path),
            "append",
            "--event-type",
            "worker_job",
            "--role",
            "dev_agent",
            "--agent",
            "Codex",
            "--note",
            note,
            "--ledger",
            str(ledger),
        )

        assert result.returncode == 2
        assert "note must not contain raw prompt or transcript material" in result.stderr
    assert not ledger.exists()


def test_factory_metrics_rejects_control_characters_in_text_fields(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "Codex\x1b[31m",
        "--ledger",
        str(ledger),
    )

    assert result.returncode == 2
    assert "agent must not contain control characters" in result.stderr
    assert not ledger.exists()


def test_factory_metrics_refuses_ledger_outside_factory_metrics_root(
    tmp_path: Path,
) -> None:
    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "OpenCode",
        "--ledger",
        str(tmp_path / "events.jsonl"),
    )

    assert result.returncode == 2
    assert "ledger path must be under .entroping/factory-metrics/" in result.stderr
    assert not (tmp_path / "events.jsonl").exists()


def test_factory_metrics_refuses_symlinked_ledger_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    outside_root = tmp_path / "outside"
    repo_root.mkdir()
    outside_root.mkdir()
    (repo_root / ".entroping").symlink_to(outside_root, target_is_directory=True)

    result = run_factory_metrics(
        "--repo-root",
        str(repo_root),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "Codex",
    )

    assert result.returncode == 2
    assert "ledger path must not use symlink components" in result.stderr
    assert not (outside_root / "factory-metrics" / "events.jsonl").exists()


def test_factory_metrics_refuses_context_file_outside_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside_context = tmp_path / "outside.md"
    outside_context.write_text("outside context\n", encoding="utf-8")

    result = run_factory_metrics(
        "--repo-root",
        str(repo_root),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "OpenCode",
        "--context-file",
        str(outside_context),
    )

    assert result.returncode == 2
    assert "context file must be under repo root" in result.stderr
    assert not (repo_root / ".entroping").exists()


def test_factory_metrics_rejects_negative_metric_values(tmp_path: Path) -> None:
    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "DeepSeek",
        "--cost-usd",
        "-0.01",
    )

    assert result.returncode == 2
    assert "--cost-usd must be greater than or equal to 0" in result.stderr


def test_factory_metrics_validate_rejects_invalid_events(tmp_path: Path) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    ledger.parent.mkdir(parents=True)
    invalid_outcome_event = {
        "schema_version": "entroping.factory-metrics.v1",
        "event_id": "event-1",
        "recorded_at": "2026-06-12T00:00:00Z",
        "event_type": "worker_job",
        "role": "architect",
        "agent": "Codex",
        "metrics": {},
        "outcome": "bogus",
        "decision": "maybe",
    }
    unexpected_field_event = {
        "schema_version": "entroping.factory-metrics.v1",
        "event_id": "event-2",
        "recorded_at": "2026-06-12T00:00:00Z",
        "event_type": "worker_job",
        "role": "dev_agent",
        "agent": "Codex",
        "metrics": {},
        "provider_transcript": "raw secret transcript",
    }
    unredacted_secret_event = {
        "schema_version": "entroping.factory-metrics.v1",
        "event_id": "event-3",
        "recorded_at": "2026-06-12T00:00:00Z",
        "event_type": "worker_job",
        "role": "dev_agent",
        "agent": "Codex",
        "metrics": {},
        "note": "access_token=ghp_FAKE_NOT_A_SECRET_1234567890",
    }
    ledger.write_text(
        '{"schema_version":"wrong","role":"architect"}\n'
        f"{json.dumps(invalid_outcome_event)}\n"
        f"{json.dumps(unexpected_field_event)}\n"
        f"{json.dumps(unredacted_secret_event)}\n",
        encoding="utf-8",
    )

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "validate",
        "--ledger",
        str(ledger),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert "line 1" in payload["errors"][0]
    assert "line 2: outcome is not supported" in payload["errors"]
    assert "line 2: decision is not supported" in payload["errors"]
    assert "line 3: unexpected field provider_transcript" in payload["errors"]
    assert "line 4: note contains unredacted secret-like value" in payload["errors"]


def test_factory_metrics_summary_aggregates_tokens_cost_and_outcomes(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    first = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "qa_agent",
        "--agent",
        "DeepSeek",
        "--provider",
        "deepseek",
        "--model",
        "deepseek-v4-flash",
        "--estimated-tokens",
        "1200",
        "--tests-run",
        "3",
        "--cost-usd",
        "0.02",
        "--outcome",
        "success",
        "--decision",
        "accepted",
        "--ledger",
        str(ledger),
    )
    second = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "code_review",
        "--role",
        "code_review_agent",
        "--agent",
        "Claude Code",
        "--estimated-tokens",
        "800",
        "--files-touched",
        "2",
        "--outcome",
        "failure",
        "--decision",
        "rejected",
        "--ledger",
        str(ledger),
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "summary",
        "--ledger",
        str(ledger),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["schema_version"] == "entroping.factory-metrics-summary.v1"
    assert summary["total_events"] == 2
    assert summary["totals"]["estimated_tokens"] == 2000
    assert summary["totals"]["tests_run"] == 3
    assert summary["totals"]["files_touched"] == 2
    assert summary["totals"]["cost_usd"] == 0.02
    assert summary["by_role"]["qa_agent"]["events"] == 1
    assert summary["by_role"]["code_review_agent"]["events"] == 1
    assert summary["by_agent"]["DeepSeek"]["events"] == 1
    assert summary["outcomes"] == {"failure": 1, "success": 1}
    assert summary["decisions"] == {"accepted": 1, "rejected": 1}


def test_factory_metrics_report_groups_cost_and_yield_by_issue(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    first = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "context_pack",
        "--role",
        "architect",
        "--agent",
        "Codex",
        "--tool",
        "scripts/context_pack.sh",
        "--issue",
        "667",
        "--context-bytes",
        "4096",
        "--estimated-tokens",
        "1024",
        "--candidate-files",
        "12",
        "--files-read",
        "5",
        "--duration-seconds",
        "1.5",
        "--outcome",
        "success",
        "--decision",
        "accepted",
        "--ledger",
        str(ledger),
    )
    second = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "code_review",
        "--role",
        "code_review_agent",
        "--agent",
        "DeepSeek",
        "--provider",
        "deepseek",
        "--model",
        "deepseek-v4-pro",
        "--issue",
        "667",
        "--estimated-tokens",
        "2048",
        "--files-touched",
        "2",
        "--tests-run",
        "3",
        "--gates-run",
        "1",
        "--duration-seconds",
        "9.5",
        "--cost-usd",
        "0.03",
        "--outcome",
        "failure",
        "--decision",
        "rejected",
        "--note",
        "provider response omitted",
        "--ledger",
        str(ledger),
    )
    third = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "qa_agent",
        "--agent",
        "OpenCode",
        "--provider",
        "opencode",
        "--model",
        "deepseek-v4-flash-free",
        "--estimated-tokens",
        "512",
        "--duration-seconds",
        "4",
        "--outcome",
        "success",
        "--decision",
        "needs_review",
        "--ledger",
        str(ledger),
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert third.returncode == 0, third.stderr

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == "entroping.factory-metrics-report.v1"
    assert report["total_events"] == 3
    assert report["totals"]["estimated_tokens"] == 3584
    assert report["totals"]["context_bytes"] == 4096
    assert report["totals"]["cost_usd"] == 0.03
    assert report["totals"]["duration_seconds"] == 15.0

    issues = {issue["issue"]: issue for issue in report["issues"]}
    assert list(issues) == ["667", "unassigned"]
    issue_667 = issues["667"]
    assert issue_667["events"] == 2
    assert issue_667["metrics"]["estimated_tokens"] == 3072
    assert issue_667["metrics"]["files_read"] == 5
    assert issue_667["metrics"]["files_touched"] == 2
    assert issue_667["metrics"]["tests_run"] == 3
    assert issue_667["metrics"]["gates_run"] == 1
    assert issue_667["roles"] == {"architect": 1, "code_review_agent": 1}
    assert issue_667["agents"] == {"Codex": 1, "DeepSeek": 1}
    assert issue_667["provider_models"] == {"deepseek/deepseek-v4-pro": 1}
    assert issue_667["outcomes"] == {"failure": 1, "success": 1}
    assert issue_667["decisions"] == {"accepted": 1, "rejected": 1}

    unassigned = issues["unassigned"]
    assert unassigned["events"] == 1
    assert unassigned["provider_models"] == {"opencode/deepseek-v4-flash-free": 1}
    assert unassigned["decisions"] == {"needs_review": 1}
    report_json = json.dumps(report)
    assert "provider response omitted" not in report_json
    assert "note" not in report_json


def test_factory_metrics_report_adds_model_comparison_view(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    direct_deepseek = _factory_event(
        issue="707",
        role="dev_agent",
        agent="DeepSeek",
    )
    direct_deepseek.update(
        {
            "provider": "deepseek-api/direct",
            "model": "deepseek-v4-pro",
            "metrics": {
                "estimated_tokens": 2400,
                "duration_seconds": 18.5,
                "cost_usd": 0.04,
                "files_touched": 2,
            },
            "decision": "accepted",
        }
    )
    kimi_review = _factory_event(
        issue="707",
        role="code_review_agent",
        agent="OpenCode",
    )
    kimi_review.update(
        {
            "provider": "opencode-go/kimi-k2.7-code",
            "model": "kimi-k2.7-code",
            "metrics": {
                "duration_seconds": 22.0,
                "files_read": 3,
            },
            "decision": "rejected",
        }
    )
    local_triage = _factory_event(
        issue="707",
        role="qa_agent",
        agent="Local",
    )
    local_triage["metrics"] = {"estimated_tokens": 600}
    local_triage["decision"] = "needs_review"
    _write_jsonl(ledger, direct_deepseek, kimi_review, local_triage)

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    rows = {
        (
            row["issue"],
            row["role"],
            row["provider_lane"],
            row["model_id"],
        ): row
        for row in report["model_comparison"]
    }

    direct = rows[("707", "dev_agent", "deepseek-api/direct", "deepseek-v4-pro")]
    assert direct["events"] == 1
    assert direct["metrics"]["estimated_tokens"] == 2400
    assert direct["metrics"]["cost_usd"] == 0.04
    assert direct["known_metric_counts"]["estimated_tokens"] == 1
    assert direct["unknown_metric_counts"]["estimated_tokens"] == 0
    assert direct["decisions"] == {"accepted": 1}
    assert direct["accepted_output_ratio"] == 1.0

    kimi = rows[
        (
            "707",
            "code_review_agent",
            "opencode-go/kimi-k2.7-code",
            "kimi-k2.7-code",
        )
    ]
    assert kimi["metrics"]["duration_seconds"] == 22.0
    assert kimi["known_metric_counts"]["cost_usd"] == 0
    assert kimi["unknown_metric_counts"]["cost_usd"] == 1
    assert kimi["unknown_metric_counts"]["estimated_tokens"] == 1
    assert kimi["decisions"] == {"rejected": 1}
    assert kimi["accepted_output_ratio"] == 0.0

    unknown = rows[("707", "qa_agent", "unknown", "unknown")]
    assert unknown["metrics"]["estimated_tokens"] == 600
    assert unknown["known_metric_counts"]["estimated_tokens"] == 1
    assert unknown["unknown_metric_counts"]["cost_usd"] == 1
    assert unknown["accepted_output_ratio"] is None

    issues = {issue["issue"]: issue for issue in report["issues"]}
    assert issues["707"]["model_comparison"] == report["model_comparison"]


def test_factory_metrics_report_can_include_finished_issue_archives(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    archive_root = tmp_path / ".entroping" / "factory-metrics" / "finished-issues"
    active = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "integrator",
        "--agent",
        "Codex",
        "--issue",
        "688",
        "--estimated-tokens",
        "100",
        "--ledger",
        str(ledger),
    )
    _write_jsonl(
        archive_root / "issue-686" / "events.jsonl",
        _factory_event(issue="686", agent="Codex", estimated_tokens=10),
    )
    _write_jsonl(
        archive_root / "issue-686" / "workers" / "deepseek" / "events.jsonl",
        _factory_event(
            issue="686",
            agent="DeepSeek",
            role="dev_agent",
            estimated_tokens=25,
        ),
    )
    assert active.returncode == 0, active.stderr

    default_result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )
    included_result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "json",
        "--include-finished-issues",
    )

    assert default_result.returncode == 0, default_result.stderr
    default_report = json.loads(default_result.stdout)
    assert default_report["total_events"] == 1
    assert [issue["issue"] for issue in default_report["issues"]] == ["688"]

    assert included_result.returncode == 0, included_result.stderr
    report = json.loads(included_result.stdout)
    assert report["total_events"] == 3
    assert report["totals"]["estimated_tokens"] == 135
    issues = {issue["issue"]: issue for issue in report["issues"]}
    assert list(issues) == ["686", "688"]
    assert issues["686"]["events"] == 2
    assert issues["686"]["metrics"]["estimated_tokens"] == 35
    assert issues["686"]["agents"] == {"Codex": 1, "DeepSeek": 1}
    assert issues["688"]["events"] == 1


def test_factory_metrics_report_attributes_archived_events_without_issue(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    archived_ledger = (
        tmp_path
        / ".entroping"
        / "factory-metrics"
        / "finished-issues"
        / "issue-708"
        / "issue-708"
        / "events.jsonl"
    )
    missing_issue_event = _factory_event(
        issue="placeholder",
        event_type="context_pack",
        estimated_tokens=100,
    )
    missing_issue_event.pop("issue")
    empty_issue_event = _factory_event(
        issue="",
        agent="Codex",
        event_type="gate_run",
        estimated_tokens=200,
    )
    explicit_issue_event = _factory_event(
        issue="709",
        agent="DeepSeek",
        estimated_tokens=300,
    )
    _write_jsonl(ledger, _factory_event(issue="688", estimated_tokens=50))
    _write_jsonl(
        archived_ledger,
        missing_issue_event,
        empty_issue_event,
        explicit_issue_event,
    )

    included_result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "json",
        "--include-finished-issues",
    )
    explicit_result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(archived_ledger),
        "--format",
        "json",
    )

    assert included_result.returncode == 0, included_result.stderr
    included_report = json.loads(included_result.stdout)
    included_issues = {issue["issue"]: issue for issue in included_report["issues"]}
    assert included_issues["708"]["events"] == 2
    assert included_issues["708"]["metrics"]["estimated_tokens"] == 300
    assert included_issues["709"]["events"] == 1
    assert "unassigned" not in included_issues

    assert explicit_result.returncode == 0, explicit_result.stderr
    explicit_report = json.loads(explicit_result.stdout)
    explicit_issues = {issue["issue"]: issue for issue in explicit_report["issues"]}
    assert explicit_issues["708"]["events"] == 2
    assert explicit_issues["709"]["events"] == 1
    assert "unassigned" not in explicit_issues


def test_factory_metrics_report_labels_malformed_finished_archives(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    archive_ledger = (
        tmp_path
        / ".entroping"
        / "factory-metrics"
        / "finished-issues"
        / "issue-686"
        / "events.jsonl"
    )
    _write_jsonl(ledger, _factory_event(issue="688", estimated_tokens=100))
    archive_ledger.parent.mkdir(parents=True)
    archive_ledger.write_text("{not-json}\n", encoding="utf-8")

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "json",
        "--include-finished-issues",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert payload["ledger_path"] == str(ledger)
    assert payload["events"] == 1
    assert payload["errors"] == [
        "finished-issues/issue-686/events.jsonl: line 1: invalid JSON: "
        "Expecting property name enclosed in double quotes"
    ]


def test_factory_metrics_report_does_not_follow_finished_archive_symlinks(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    archive_root = tmp_path / ".entroping" / "factory-metrics" / "finished-issues"
    outside = tmp_path / "outside"
    _write_jsonl(ledger, _factory_event(issue="688", estimated_tokens=100))
    _write_jsonl(
        archive_root / "issue-686" / "events.jsonl",
        _factory_event(issue="686", estimated_tokens=10),
    )
    _write_jsonl(
        outside / "linked-file-source.jsonl",
        _factory_event(issue="999", estimated_tokens=999),
    )
    _write_jsonl(
        outside / "linked-dir-source" / "events.jsonl",
        _factory_event(issue="998", estimated_tokens=998),
    )
    try:
        (archive_root / "issue-686" / "linked.jsonl").symlink_to(
            outside / "linked-file-source.jsonl"
        )
        (archive_root / "issue-linked").symlink_to(
            outside / "linked-dir-source",
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlinks are not available in this environment: {exc}")

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "json",
        "--include-finished-issues",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["total_events"] == 2
    assert report["totals"]["estimated_tokens"] == 110
    assert [issue["issue"] for issue in report["issues"]] == ["686", "688"]


def test_factory_metrics_report_does_not_double_count_selected_archive_ledger(
    tmp_path: Path,
) -> None:
    archived_ledger = (
        tmp_path
        / ".entroping"
        / "factory-metrics"
        / "finished-issues"
        / "issue-686"
        / "events.jsonl"
    )
    _write_jsonl(
        archived_ledger,
        _factory_event(issue="686", estimated_tokens=10),
    )

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(archived_ledger),
        "--format",
        "json",
        "--include-finished-issues",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["total_events"] == 1
    assert report["totals"]["estimated_tokens"] == 10
    assert [issue["issue"] for issue in report["issues"]] == ["686"]


def test_factory_metrics_report_writes_markdown_under_factory_metrics_root(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    output = tmp_path / ".entroping" / "factory-metrics" / "factory-report.md"

    append_result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "OpenCode",
        "--provider",
        "opencode",
        "--model",
        "deepseek-v4-flash-free",
        "--issue",
        "667",
        "--estimated-tokens",
        "1200",
        "--cost-usd",
        "0.02",
        "--duration-seconds",
        "30",
        "--outcome",
        "success",
        "--decision",
        "accepted",
        "--ledger",
        str(ledger),
    )
    assert append_result.returncode == 0, append_result.stderr

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "md",
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    assert "status: written" in result.stdout
    assert output.exists()
    markdown = output.read_text(encoding="utf-8")
    assert markdown.startswith("# Factory Metrics Report\n")
    assert "| 667 | 1 | 1200 | 0.02 | 30.00 |" in markdown
    assert "opencode/deepseek-v4-flash-free: 1" in markdown
    assert "OpenCode: 1" in markdown


def test_factory_metrics_report_markdown_escapes_labels(tmp_path: Path) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"

    append_result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "append",
        "--event-type",
        "worker_job",
        "--role",
        "dev_agent",
        "--agent",
        "OpenCode<script>`",
        "--provider",
        "opencode",
        "--model",
        "deepseek-v4-flash-free",
        "--issue",
        "667|<script>`",
        "--estimated-tokens",
        "12",
        "--ledger",
        str(ledger),
    )
    assert append_result.returncode == 0, append_result.stderr

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "md",
    )

    assert result.returncode == 0, result.stderr
    assert "<script>" not in result.stdout
    assert "667\\|&lt;script&gt;\\`" in result.stdout
    assert "OpenCode&lt;script&gt;\\`: 1" in result.stdout


def test_factory_metrics_report_refuses_output_outside_factory_metrics_root(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    outside_output = tmp_path / "factory-report.md"

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "report",
        "--ledger",
        str(ledger),
        "--format",
        "md",
        "--output",
        str(outside_output),
    )

    assert result.returncode == 2
    assert "report path must be under .entroping/factory-metrics/" in result.stderr
    assert not outside_output.exists()


def test_factory_metrics_report_builder_redacts_labels_defensively() -> None:
    module = _load_factory_metrics_module()
    event = {
        "schema_version": "entroping.factory-metrics.v1",
        "event_id": "event-1",
        "recorded_at": "2026-06-12T00:00:00Z",
        "event_type": "worker_job",
        "role": "code_review_agent",
        "agent": "DeepSeek api_key=live-secret-token",
        "provider": "deepseek",
        "model": "deepseek-v4-pro token=raw-secret-token",
        "issue": "667 access_token=ghp_FAKE_NOT_A_SECRET_1234567890",
        "metrics": {"estimated_tokens": 12},
        "outcome": "success",
        "decision": "needs_review",
    }

    report = module._report([event])

    serialized = json.dumps(report)
    assert "live-secret-token" not in serialized
    assert "raw-secret-token" not in serialized
    assert "ghp_FAKE_NOT_A_SECRET_1234567890" not in serialized
    assert "<redacted>" in serialized


def test_factory_metrics_readiness_passes_when_four_gate_evidence_is_present(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    context_event = _factory_event(
        issue="746",
        event_type="context_pack",
        role="integrator",
        agent="Codex",
        estimated_tokens=2500,
    )
    context_event["metrics"].update(
        {
            "context_bytes": 10000,
            "candidate_files": 8,
            "files_read": 4,
        }
    )
    quality_event = _factory_event(
        issue="746",
        event_type="gate_run",
        role="qa_agent",
        agent="Codex",
    )
    quality_event.update(
        {
            "metrics": {"tests_run": 32, "gates_run": 1},
            "gates": ["scripts/feature_gate.sh"],
            "checks": ["pytest tests/test_factory_metrics.py"],
        }
    )
    security_event = _factory_event(
        issue="746",
        event_type="gate_run",
        role="security_agent",
        agent="Codex",
    )
    security_event.update(
        {
            "metrics": {"gates_run": 1},
            "gates": ["scripts/regression.sh --security"],
            "checks": ["license policy OK", "no known vulnerabilities"],
        }
    )
    worker_event = _factory_event(
        issue="746",
        event_type="worker_job",
        role="code_review_agent",
        agent="DeepSeek",
        estimated_tokens=1200,
    )
    worker_event.update(
        {
            "provider": "deepseek-api/direct",
            "model": "deepseek-v4-flash",
            "metrics": {"estimated_tokens": 1200, "cost_usd": 0.01},
            "note": "provider response omitted",
        }
    )
    _write_jsonl(ledger, context_event, quality_event, security_event, worker_event)

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "readiness",
        "--issue",
        "746",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.factory-readiness.v1"
    assert payload["status"] == "pass"
    assert payload["issue"] == "746"
    assert payload["events_considered"] == 4
    assert payload["missing_gates"] == []
    assert set(payload["gates"]) == {
        "quality",
        "security",
        "context_preservation",
        "token_cost_efficiency",
    }
    assert all(gate["status"] == "pass" for gate in payload["gates"].values())
    assert "provider response omitted" not in result.stdout

    markdown = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "readiness",
        "--issue",
        "746",
        "--ledger",
        str(ledger),
        "--format",
        "md",
    )

    assert markdown.returncode == 0, markdown.stderr
    assert "# Factory Readiness Scorecard" in markdown.stdout
    assert "| quality | pass |" in markdown.stdout
    assert "scripts/regression.sh --security" in markdown.stdout
    assert "provider response omitted" not in markdown.stdout


def test_factory_metrics_readiness_fails_with_actionable_missing_gates(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    context_event = _factory_event(
        issue="746",
        event_type="context_pack",
        role="integrator",
        agent="Codex",
        estimated_tokens=1200,
    )
    context_event["metrics"].update({"context_bytes": 4800, "candidate_files": 4, "files_read": 2})
    _write_jsonl(ledger, context_event)

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "readiness",
        "--issue",
        "746",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["events_considered"] == 1
    assert payload["gates"]["context_preservation"]["status"] == "pass"
    assert payload["gates"]["quality"]["status"] == "fail"
    assert payload["gates"]["security"]["status"] == "fail"
    assert payload["gates"]["token_cost_efficiency"]["status"] == "fail"
    assert payload["missing_gates"] == [
        "quality",
        "security",
        "token_cost_efficiency",
    ]
    assert "quality evidence requires" in payload["gates"]["quality"]["missing"][0]
    assert "security evidence requires" in payload["gates"]["security"]["missing"][0]
    assert "token/cost evidence requires" in payload["gates"]["token_cost_efficiency"]["missing"][0]


def test_factory_metrics_readiness_accepts_explicit_not_applicable_evidence(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    context_event = _factory_event(
        issue="746",
        event_type="context_pack",
        role="integrator",
        agent="Codex",
        estimated_tokens=900,
    )
    context_event["metrics"].update({"context_bytes": 3600, "candidate_files": 3, "files_read": 2})
    quality_event = _factory_event(
        issue="746",
        event_type="gate_run",
        role="qa_agent",
        agent="Codex",
    )
    quality_event.update({"metrics": {"tests_run": 1}, "checks": ["docs guard test"]})
    security_event = _factory_event(
        issue="746",
        event_type="gate_run",
        role="security_agent",
        agent="Codex",
    )
    security_event.update(
        {
            "checks": ["security:not-applicable"],
            "metrics": {"gates_run": 1},
        }
    )
    no_provider_event = _factory_event(
        issue="746",
        event_type="outcome",
        role="integrator",
        agent="Codex",
    )
    no_provider_event.update(
        {
            "checks": ["provider:not-applicable", "llm-free"],
            "metrics": {"estimated_tokens": 0, "cost_usd": 0.0},
        }
    )
    _write_jsonl(ledger, context_event, quality_event, security_event, no_provider_event)

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "readiness",
        "--issue",
        "746",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert "security:not-applicable" in payload["gates"]["security"]["evidence"][0]["markers"]
    assert payload["gates"]["token_cost_efficiency"]["status"] == "pass"
    assert "provider:not-applicable" in json.dumps(payload["gates"]["token_cost_efficiency"])


def test_factory_metrics_readiness_rejects_zero_cost_without_provider_or_no_provider(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    context_event = _factory_event(
        issue="746",
        event_type="context_pack",
        role="integrator",
        agent="Codex",
        estimated_tokens=900,
    )
    context_event["metrics"].update({"context_bytes": 3600, "candidate_files": 3, "files_read": 2})
    quality_event = _factory_event(
        issue="746",
        event_type="gate_run",
        role="qa_agent",
        agent="Codex",
    )
    quality_event.update({"metrics": {"tests_run": 1}, "checks": ["docs guard test"]})
    security_event = _factory_event(
        issue="746",
        event_type="gate_run",
        role="security_agent",
        agent="Codex",
    )
    security_event.update({"checks": ["security:not-applicable"]})
    weak_cost_event = _factory_event(
        issue="746",
        event_type="outcome",
        role="integrator",
        agent="Codex",
    )
    weak_cost_event.update(
        {
            "checks": ["cost budget noted"],
            "metrics": {"estimated_tokens": 0, "cost_usd": 0.0},
        }
    )
    _write_jsonl(ledger, context_event, quality_event, security_event, weak_cost_event)

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "readiness",
        "--issue",
        "746",
        "--ledger",
        str(ledger),
        "--format",
        "json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["missing_gates"] == ["token_cost_efficiency"]
    assert payload["gates"]["token_cost_efficiency"]["evidence"] == []


def test_context_tool_scorecard_report_measures_tools_against_baseline(
    tmp_path: Path,
) -> None:
    scorecard_path = (
        tmp_path / ".entroping" / "factory-metrics" / "context-tools" / "scorecard.json"
    )
    scorecard_path.parent.mkdir(parents=True)
    scorecard = _context_tool_scorecard(
        tool_evaluations=[
            _context_tool_evaluation(),
            _context_tool_evaluation(
                tool="SymbolLens",
                proof_status="not_measured",
                recommended_status="probation",
                trials=[],
                evidence_sources=[
                    {
                        "source_type": "curated_markdown",
                        "reference": "docs/meta/CONTEXT_MANAGEMENT.md",
                        "summary": "SymbolLens remains unproven in this repo.",
                    }
                ],
            ),
        ]
    )
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "context-scorecard",
        "report",
        "--input",
        str(scorecard_path),
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == "entroping.context-tool-scorecard-report.v1"
    assert report["scorecard_id"] == "issue-710-context-tools"
    assert report["baseline_components"][:3] == [
        "rg",
        "scripts/context_pack.sh",
        "docs/meta/DECISION_REGISTRY.yaml",
    ]
    assert report["total_tools"] == 2
    assert report["total_trials"] == 1
    assert report["tools_by_recommendation"] == {
        "optional_manual": 1,
        "probation": 1,
    }

    tools = {tool["tool"]: tool for tool in report["tools"]}
    context_map = tools["ContextMap"]
    assert context_map["proof_status"] == "measured"
    assert context_map["recommended_status"] == "optional_manual"
    assert context_map["strongest_improvement_count"] == 3
    assert context_map["strongest_regression_count"] == 2
    assert context_map["trial_count"] == 1
    assert len(context_map["trials"]) == 1
    assert context_map["trials"][0]["workflow"] == "context_map_assisted"
    assert context_map["missing_required_metrics"] == []
    assert "retrieval_precision" in context_map["best_trial"]["improved_metrics"]
    assert "context_recovery_time_seconds" in context_map["best_trial"]["improved_metrics"]

    symbol_lens = tools["SymbolLens"]
    assert symbol_lens["proof_status"] == "not_measured"
    assert symbol_lens["trial_count"] == 0
    assert symbol_lens["strongest_improvement_count"] == 0
    assert symbol_lens["missing_required_metrics"] == []


def test_context_tool_scorecard_reports_setup_failure_evidence(
    tmp_path: Path,
) -> None:
    scorecard_path = (
        tmp_path / ".entroping" / "factory-metrics" / "context-tools" / "scorecard.json"
    )
    scorecard_path.parent.mkdir(parents=True)
    scorecard = _context_tool_scorecard(
        tool_evaluations=[
            _context_tool_evaluation(
                tool="Understand Anything",
                proof_status="not_measured",
                recommended_status="probation",
                setup={
                    "status": "blocked",
                    "duration_seconds": 42.5,
                    "command": "inspect installer without modifying Codex config",
                    "failure_reason": (
                        "Codex slash-command plugin install would mutate user-local "
                        "state and cannot become active in this running session."
                    ),
                },
                trials=[],
                evidence_sources=[
                    {
                        "source_type": "generated_understand_anything",
                        "reference": "understand-anything-out/setup-inspection.json",
                        "summary": "Installer was inspected but not activated.",
                    }
                ],
            )
        ]
    )
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "context-scorecard",
        "report",
        "--input",
        str(scorecard_path),
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    [tool] = json.loads(result.stdout)["tools"]
    assert tool["setup"] == {
        "status": "blocked",
        "duration_seconds": 42.5,
        "command": "inspect installer without modifying Codex config",
        "failure_reason": (
            "Codex slash-command plugin install would mutate user-local "
            "state and cannot become active in this running session."
        ),
    }


def test_context_tool_scorecard_rejects_invalid_setup_metadata(
    tmp_path: Path,
) -> None:
    scorecard_path = (
        tmp_path / ".entroping" / "factory-metrics" / "context-tools" / "scorecard.json"
    )
    scorecard_path.parent.mkdir(parents=True)
    scorecard = _context_tool_scorecard(
        tool_evaluations=[
            _context_tool_evaluation(
                setup={
                    "status": "imaginary",
                    "duration_seconds": -1,
                    "command": "raw prompt: leak this",
                    "failure_reason": "api_key=live-secret-token",
                }
            )
        ]
    )
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "context-scorecard",
        "validate",
        "--input",
        str(scorecard_path),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert "tool_evaluations[0].setup.status is not supported" in payload["errors"]
    assert (
        "tool_evaluations[0].setup.duration_seconds must be greater than or equal to 0"
        in payload["errors"]
    )
    assert (
        "tool_evaluations[0].setup.command must not contain raw prompt or transcript material"
        in payload["errors"]
    )
    assert (
        "tool_evaluations[0].setup.failure_reason contains unredacted secret-like value"
        in payload["errors"]
    )


def test_context_tool_scorecard_rejects_missing_evidence_as_active_proof(
    tmp_path: Path,
) -> None:
    scorecard_path = (
        tmp_path / ".entroping" / "factory-metrics" / "context-tools" / "scorecard.json"
    )
    scorecard_path.parent.mkdir(parents=True)
    scorecard = _context_tool_scorecard(
        tool_evaluations=[
            _context_tool_evaluation(
                proof_status="measured",
                recommended_status="active",
                evidence_sources=[],
                trials=[],
            )
        ]
    )
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "context-scorecard",
        "validate",
        "--input",
        str(scorecard_path),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert "tool_evaluations[0].evidence_sources must not be empty" in payload["errors"]
    assert (
        "tool_evaluations[0] cannot recommend active without measured trials" in payload["errors"]
    )


def test_context_tool_scorecard_rejects_non_authoritative_evidence(
    tmp_path: Path,
) -> None:
    scorecard_path = (
        tmp_path / ".entroping" / "factory-metrics" / "context-tools" / "scorecard.json"
    )
    scorecard_path.parent.mkdir(parents=True)
    scorecard = _context_tool_scorecard(
        tool_evaluations=[
            _context_tool_evaluation(
                evidence_sources=[
                    {
                        "source_type": "obsidian_workspace_state",
                        "reference": ".obsidian/workspace.json",
                        "summary": "UI graph state looked useful.",
                    },
                    {
                        "source_type": "provider_transcript",
                        "reference": "local-provider-output",
                        "summary": "Provider transcript said the tool helped.",
                    },
                ],
            )
        ]
    )
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")

    result = run_factory_metrics(
        "--repo-root",
        str(tmp_path),
        "context-scorecard",
        "validate",
        "--input",
        str(scorecard_path),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert (
        "tool_evaluations[0].evidence_sources[0].source_type "
        "obsidian_workspace_state is not accepted evidence"
    ) in payload["errors"]
    assert (
        "tool_evaluations[0].evidence_sources[1].source_type "
        "provider_transcript is not accepted evidence"
    ) in payload["errors"]
