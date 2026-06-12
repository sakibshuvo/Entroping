"""Tests for local software-factory role and metrics tooling."""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "factory_metrics.py"
ROLE_REGISTRY = REPO_ROOT / "docs" / "meta" / "AGENT_ROLE_REGISTRY.yaml"
PYTHON3_FACTORY_ENTRYPOINTS = (
    REPO_ROOT / "scripts" / "agent_context_probe.py",
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
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


def test_factory_metrics_role_set_matches_registry() -> None:
    registry = yaml.safe_load(ROLE_REGISTRY.read_text(encoding="utf-8"))
    module = _load_factory_metrics_module()

    assert set(registry["roles"]) == module.ROLES


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
            unsupported_by_script[script.relative_to(REPO_ROOT).as_posix()] = (
                unsupported_usages
            )

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
        "access_token=ghp_FAKE_NOT_A_SECRET_1234567890 "
        "aws_access_key_id=AKIAIOSFODNN7EXAMPLE",
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
