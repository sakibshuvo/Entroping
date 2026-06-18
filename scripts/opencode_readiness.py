#!/usr/bin/env python3
"""Preflight OpenCode independent-session readiness for Entroping."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as datetime_timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "entroping.opencode-readiness.v1"
UTC_TZ = datetime_timezone.utc  # noqa: UP017 - workflow scripts support py3.9.
DEFAULT_STALE_REPO_PATH = Path.home() / "Documents" / "Entroping"
DEFAULT_EXPECTED_REPO_ROOT_PREFIX = Path.home() / "projects"
OUTPUT_LIMIT = 4000

REQUIRED_WORKFLOW_FILES = (
    "AGENTS.md",
    "docs/meta/AGENT_CONTROL_PLANE.md",
    "docs/meta/DOCS_GOVERNANCE.md",
    "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
    "docs/meta/prompt-library/opencode-desktop-handoff.md",
    "docs/meta/prompt-library/codex-outage-daily-operations.md",
    "docs/meta/prompt-library/issue-worker.md",
    "scripts/start_issue.sh",
    "scripts/finish_issue.sh",
    "scripts/context_pack.sh",
    "scripts/agent_toolchain.py",
    "scripts/opencode_worker.py",
    "scripts/deepseek_worker.py",
    "scripts/ai_jobs.py",
    "scripts/pr_body_check.py",
    "scripts/factory_metrics.py",
)

PROMPT_GUARDRAIL_TERMS = {
    "docs/meta/prompt-library/opencode-desktop-handoff.md": (
        "Provider lane:",
        "opencode/native-deepseek",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "Codex-native tools are not automatically available inside OpenCode",
        "OpenCode MCP servers are not Codex MCP state",
        "Start with narrow read-only MCP access",
        "Do not commit local OpenCode config",
        "MCP credentials",
        "provider keys",
        "scripts/opencode_worker.py --record-factory-metrics",
        "scripts/deepseek_worker.py --record-factory-metrics",
        "scripts/pr_body_check.py --body-file <body.md> --require-opencode-evidence",
        "scripts/finish_issue.sh <issue-number>",
        "Tier B/Tier C requires Codex or human review before merge",
    ),
    "docs/meta/AGENT_CONTROL_PLANE.md": (
        "No helper agent is a source of truth",
        "OpenCode Go is the Kimi/Qwen/model-variety lane",
        "OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek lane",
        "Autonomous OpenCode Shipping Lanes",
        "Tier A autonomous lane",
        "Tier B assisted lane",
        "Tier C restricted lane",
        "One write agent per issue-scoped worktree",
        "scripts/context_pack.sh --mode implementation --record-factory-metrics",
        "scripts/factory_metrics.py readiness --issue <issue> --format json",
        "scripts/agent_toolchain.py --mode implementation --format json",
        "entroping.agent-toolchain.v1",
        "PATH lookup only",
        "safe_default",
        "guarded_local_only",
        "manual_explicit",
        "Do not run automatically",
        "not scan home directories",
        "provider config",
        "local secret stores",
        "act",
        "trufflehog",
        "semgrep",
        "trivy",
        "syft",
        "grype",
    ),
}

COMMAND_HELP_CHECKS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("scripts/context_pack.sh", "--help"),
        ("--manifest", "--strict-budget", "--record-factory-metrics"),
    ),
    (
        (sys.executable, "scripts/opencode_worker.py", "--help"),
        ("--mode", "review", "patch", "--record-factory-metrics", "--factory-metrics-ledger"),
    ),
    (
        (sys.executable, "scripts/deepseek_worker.py", "--help"),
        ("--thinking", "enabled", "disabled", "--record-factory-metrics", "--api-key-env"),
    ),
    (
        (sys.executable, "scripts/ai_jobs.py", "run-next", "--help"),
        ("--worker-dry-run", "--record-factory-metrics", "--deepseek-thinking"),
    ),
    (
        (sys.executable, "scripts/pr_body_check.py", "--help"),
        ("--require-opencode-evidence", "--changed-file", "--issue"),
    ),
    (
        (sys.executable, "scripts/agent_toolchain.py", "--help"),
        (
            "--mode",
            "implementation",
            "security",
            "--require-recommended",
            "--format",
        ),
    ),
)

IGNORE_PROBES = (
    ".entroping/ai-reviews/readiness-probe",
    ".entroping/factory-metrics/readiness-probe.jsonl",
    "reports/opencode-readiness-probe.json",
    ".opencode/readiness-probe.json",
    ".codex/readiness-probe.json",
)

LOCAL_ARTIFACT_PREFIXES = (
    ".entroping/",
    ".opencode/",
    ".codex/",
    ".obsidian/",
    "reports/",
    "llm-wiki-out/",
    ".understand-anything/",
    "understand-anything-out/",
    "agent-context-out/",
)


@dataclass(frozen=True)
class CheckResult:
    """One readiness check."""

    name: str
    status: str
    message: str
    details: dict[str, Any]


@dataclass(frozen=True)
class CommandResult:
    """Bounded subprocess result."""

    returncode: int | None
    stdout: str
    stderr: str
    error: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight an Entroping OpenCode independent session. The check "
            "verifies repo workflow guardrails and OpenCode availability, but "
            "does not read provider keys, MCP credentials, or local config values."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root to check. Default: current Git root or this script's repo.",
    )
    parser.add_argument(
        "--opencode-bin",
        type=Path,
        default=None,
        help="OpenCode executable to probe. Default: first opencode on PATH.",
    )
    parser.add_argument(
        "--stale-repo-path",
        type=Path,
        action="append",
        default=None,
        help=(
            "Known stale Entroping checkout path to reject. Repeatable. "
            "Default: ENTROPING_STALE_REPO_PATHS or "
            f"{DEFAULT_STALE_REPO_PATH}."
        ),
    )
    parser.add_argument(
        "--expected-repo-prefix",
        type=Path,
        default=None,
        help=(
            "Expected parent directory for active Entroping checkouts. "
            "Default: ENTROPING_EXPECTED_REPO_PREFIX or "
            f"{DEFAULT_EXPECTED_REPO_ROOT_PREFIX}."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("implementation", "verification", "monitoring"),
        default="implementation",
        help="Session mode. Implementation mode fails on direct main-branch work.",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Fail when git status is not clean instead of reporting a warning.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args(argv)

    repo_root = _resolve_repo_root(args.repo_root)
    opencode_bin = _resolve_opencode_bin(args.opencode_bin)
    stale_repo_paths = _resolve_stale_repo_paths(args.stale_repo_path)
    expected_repo_prefix = _resolve_expected_repo_prefix(args.expected_repo_prefix)

    checks = _run_checks(
        repo_root=repo_root,
        opencode_bin=opencode_bin,
        stale_repo_paths=stale_repo_paths,
        expected_repo_prefix=expected_repo_prefix,
        mode=args.mode,
        require_clean=args.require_clean,
    )
    overall_status = _overall_status(checks)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC_TZ).replace(microsecond=0).isoformat(),
        "repo_root": str(repo_root),
        "mode": args.mode,
        "overall_status": overall_status,
        "checks": [_check_to_json(check) for check in checks],
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(payload)

    return 1 if overall_status == "fail" else 0


def _run_checks(
    *,
    repo_root: Path,
    opencode_bin: Path | None,
    stale_repo_paths: tuple[Path, ...],
    expected_repo_prefix: Path,
    mode: str,
    require_clean: bool,
) -> list[CheckResult]:
    checks = [
        _check_active_repo_path(
            repo_root,
            stale_repo_paths=stale_repo_paths,
            expected_repo_prefix=expected_repo_prefix,
        ),
        _check_git_repository(repo_root),
        _check_branch(repo_root, mode=mode),
        _check_worktree_status(repo_root, require_clean=require_clean),
        _check_required_files(repo_root),
        _check_prompt_guardrails(repo_root),
        _check_command_help_surfaces(repo_root),
        _check_agent_toolchain_policy(repo_root, mode=mode),
        _check_opencode_binary(repo_root, opencode_bin),
        _check_local_opencode_config(),
        _check_local_artifact_ignore_rules(repo_root),
        _check_tracked_local_artifacts(repo_root),
    ]
    return checks


def _resolve_repo_root(repo_root: Path | None) -> Path:
    if repo_root is not None:
        return repo_root.expanduser().resolve()

    git_root = _run(["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd(), timeout=5)
    if git_root.returncode == 0 and git_root.stdout.strip():
        return Path(git_root.stdout.strip()).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _resolve_opencode_bin(opencode_bin: Path | None) -> Path | None:
    if opencode_bin is not None:
        return opencode_bin.expanduser().resolve()
    found = shutil.which("opencode")
    if found is None:
        return None
    return Path(found).resolve()


def _resolve_stale_repo_paths(explicit_paths: list[Path] | None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if explicit_paths:
        candidates.extend(explicit_paths)
    else:
        env_value = os.environ.get("ENTROPING_STALE_REPO_PATHS", "").strip()
        if env_value:
            candidates.extend(Path(part) for part in env_value.split(os.pathsep) if part)
        else:
            candidates.append(DEFAULT_STALE_REPO_PATH)
    return tuple(_dedupe_paths([path.expanduser().resolve() for path in candidates]))


def _resolve_expected_repo_prefix(explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()
    env_value = os.environ.get("ENTROPING_EXPECTED_REPO_PREFIX", "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return DEFAULT_EXPECTED_REPO_ROOT_PREFIX


def _check_active_repo_path(
    repo_root: Path,
    *,
    stale_repo_paths: tuple[Path, ...],
    expected_repo_prefix: Path,
) -> CheckResult:
    matched_stale_path = next(
        (stale_path for stale_path in stale_repo_paths if _is_within(repo_root, stale_path)),
        None,
    )
    if matched_stale_path is not None:
        return CheckResult(
            name="active_repo_path",
            status="fail",
            message=f"repo root points at stale Documents/Entroping path: {repo_root}",
            details={"repo_root": str(repo_root), "stale_path": str(matched_stale_path)},
        )

    if _is_within(repo_root, expected_repo_prefix):
        return CheckResult(
            name="active_repo_path",
            status="pass",
            message=f"repo root is under active projects path: {repo_root}",
            details={
                "repo_root": str(repo_root),
                "expected_prefix": str(expected_repo_prefix),
                "stale_paths": [str(path) for path in stale_repo_paths],
            },
        )

    return CheckResult(
        name="active_repo_path",
        status="warn",
        message=(
            "repo root is not the known stale path, but is outside the expected "
            f"projects directory: {repo_root}"
        ),
        details={
            "repo_root": str(repo_root),
            "expected_prefix": str(expected_repo_prefix),
            "stale_paths": [str(path) for path in stale_repo_paths],
        },
    )


def _check_git_repository(repo_root: Path) -> CheckResult:
    result = _run(["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return CheckResult(
            name="git_repository",
            status="fail",
            message="repo root is not a readable Git worktree",
            details={"stderr": result.stderr, "error": result.error},
        )

    actual_root = Path(result.stdout.strip()).resolve()
    if actual_root != repo_root:
        return CheckResult(
            name="git_repository",
            status="fail",
            message=f"git top-level does not match requested repo root: {actual_root}",
            details={"requested": str(repo_root), "actual": str(actual_root)},
        )

    return CheckResult(
        name="git_repository",
        status="pass",
        message=f"git top-level matches repo root: {actual_root}",
        details={"git_root": str(actual_root)},
    )


def _check_branch(repo_root: Path, *, mode: str) -> CheckResult:
    result = _run(["git", "-C", str(repo_root), "branch", "--show-current"])
    branch = result.stdout.strip()
    if result.returncode != 0:
        return CheckResult(
            name="git_branch",
            status="fail",
            message="could not read current branch",
            details={"stderr": result.stderr, "error": result.error},
        )

    if mode == "implementation" and branch in {"main", "master"}:
        return CheckResult(
            name="git_branch",
            status="fail",
            message=(
                "implementation sessions must start from scripts/start_issue.sh, "
                f"not direct edits on {branch}"
            ),
            details={"branch": branch, "mode": mode},
        )

    status = "warn" if branch in {"main", "master"} else "pass"
    message = (
        f"current branch is {branch}"
        if status == "pass"
        else f"current branch is {branch}; keep this mode read-only"
    )
    return CheckResult(
        name="git_branch",
        status=status,
        message=message,
        details={"branch": branch, "mode": mode},
    )


def _check_worktree_status(repo_root: Path, *, require_clean: bool) -> CheckResult:
    result = _run(["git", "-C", str(repo_root), "status", "--short"])
    if result.returncode != 0:
        return CheckResult(
            name="git_status",
            status="fail",
            message="could not read git status",
            details={"stderr": result.stderr, "error": result.error},
        )

    entries = [line for line in result.stdout.splitlines() if line.strip()]
    if not entries:
        return CheckResult(
            name="git_status",
            status="pass",
            message="worktree is clean",
            details={"changed_entry_count": 0},
        )

    status = "fail" if require_clean else "warn"
    return CheckResult(
        name="git_status",
        status=status,
        message=f"worktree has {len(entries)} changed entries",
        details={
            "changed_entry_count": len(entries),
            "require_clean": require_clean,
            "sample": entries[:10],
        },
    )


def _check_required_files(repo_root: Path) -> CheckResult:
    missing = [path for path in REQUIRED_WORKFLOW_FILES if not (repo_root / path).exists()]
    if missing:
        return CheckResult(
            name="required_workflow_files",
            status="fail",
            message=f"missing required workflow files: {', '.join(missing)}",
            details={"missing": missing},
        )
    return CheckResult(
        name="required_workflow_files",
        status="pass",
        message=f"{len(REQUIRED_WORKFLOW_FILES)} required workflow files are present",
        details={"files": list(REQUIRED_WORKFLOW_FILES)},
    )


def _check_prompt_guardrails(repo_root: Path) -> CheckResult:
    missing: dict[str, list[str]] = {}
    for relative_path, terms in PROMPT_GUARDRAIL_TERMS.items():
        path = repo_root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            missing[relative_path] = list(terms)
            continue
        missing_terms = [term for term in terms if not _contains_term(text, term)]
        if missing_terms:
            missing[relative_path] = missing_terms

    if missing:
        return CheckResult(
            name="prompt_library_guardrails",
            status="fail",
            message="prompt-library guardrail terms are missing",
            details={"missing": missing},
        )

    return CheckResult(
        name="prompt_library_guardrails",
        status="pass",
        message="OpenCode prompt and control-plane guardrails are present",
        details={"checked_files": sorted(PROMPT_GUARDRAIL_TERMS)},
    )


def _check_command_help_surfaces(repo_root: Path) -> CheckResult:
    missing: dict[str, list[str]] = {}
    failures: dict[str, dict[str, str | int | None]] = {}
    for command, terms in COMMAND_HELP_CHECKS:
        result = _run(command, cwd=repo_root, timeout=15, output_limit=20000)
        command_name = " ".join(command)
        if result.returncode != 0:
            failures[command_name] = {
                "returncode": result.returncode,
                "stderr": result.stderr,
                "error": result.error,
            }
            continue
        output = f"{result.stdout}\n{result.stderr}"
        missing_terms = [term for term in terms if term not in output]
        if missing_terms:
            missing[command_name] = missing_terms

    if failures or missing:
        return CheckResult(
            name="command_help_surfaces",
            status="fail",
            message="required workflow command help surfaces are incomplete",
            details={"failures": failures, "missing_terms": missing},
        )

    return CheckResult(
        name="command_help_surfaces",
        status="pass",
        message=f"{len(COMMAND_HELP_CHECKS)} workflow command help surfaces verified",
        details={"commands": [" ".join(command) for command, _terms in COMMAND_HELP_CHECKS]},
    )


def _check_agent_toolchain_policy(repo_root: Path, *, mode: str) -> CheckResult:
    toolchain_mode = {
        "implementation": "implementation",
        "verification": "review",
        "monitoring": "maintenance",
    }[mode]
    result = _run(
        [
            sys.executable,
            "scripts/agent_toolchain.py",
            "--mode",
            toolchain_mode,
            "--format",
            "json",
        ],
        cwd=repo_root,
        timeout=15,
        output_limit=30000,
    )
    if result.returncode != 0:
        return CheckResult(
            name="agent_toolchain_policy",
            status="fail",
            message="agent toolchain policy preflight failed",
            details={
                "returncode": result.returncode,
                "stderr": result.stderr,
                "error": result.error,
            },
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return CheckResult(
            name="agent_toolchain_policy",
            status="fail",
            message="agent toolchain preflight did not emit valid JSON",
            details={"error": str(exc)},
        )

    if payload.get("schema_version") != "entroping.agent-toolchain.v1":
        return CheckResult(
            name="agent_toolchain_policy",
            status="fail",
            message="agent toolchain preflight schema is not recognized",
            details={"schema_version": payload.get("schema_version")},
        )

    if payload.get("probe_mode") != "path_lookup_only":
        return CheckResult(
            name="agent_toolchain_policy",
            status="fail",
            message="agent toolchain preflight must remain PATH lookup only",
            details={"probe_mode": payload.get("probe_mode")},
        )

    unsafe_flags = {
        key: payload.get(key)
        for key in (
            "scanner_execution",
            "network_execution",
            "local_config_read",
            "provider_config_read",
        )
        if payload.get(key) is not False
    }
    if unsafe_flags:
        return CheckResult(
            name="agent_toolchain_policy",
            status="fail",
            message="agent toolchain preflight reported unsafe probing behavior",
            details={"unsafe_flags": unsafe_flags},
        )

    missing_recommended = payload.get("missing_recommended", [])
    if not isinstance(missing_recommended, list):
        return CheckResult(
            name="agent_toolchain_policy",
            status="fail",
            message="agent toolchain preflight missing_recommended shape is invalid",
            details={"missing_recommended": missing_recommended},
        )

    status = "warn" if missing_recommended else "pass"
    message = (
        "agent toolchain policy verified; all recommended tools are available"
        if status == "pass"
        else "agent toolchain policy verified with missing recommended tools"
    )
    return CheckResult(
        name="agent_toolchain_policy",
        status=status,
        message=message,
        details={
            "schema_version": payload["schema_version"],
            "toolchain_mode": toolchain_mode,
            "tool_count": payload.get("tool_count"),
            "available_count": payload.get("available_count"),
            "policy_counts": payload.get("policy_counts"),
            "available_policy_counts": payload.get("available_policy_counts"),
            "missing_recommended": missing_recommended,
            "probe_mode": payload["probe_mode"],
            "scanner_execution": payload["scanner_execution"],
            "network_execution": payload["network_execution"],
            "local_config_read": payload["local_config_read"],
            "provider_config_read": payload["provider_config_read"],
        },
    )


def _check_opencode_binary(repo_root: Path, opencode_bin: Path | None) -> CheckResult:
    if opencode_bin is None:
        return CheckResult(
            name="opencode_binary",
            status="fail",
            message="opencode executable was not found on PATH",
            details={"path": None},
        )
    if not opencode_bin.exists():
        return CheckResult(
            name="opencode_binary",
            status="fail",
            message=f"configured opencode executable does not exist: {opencode_bin}",
            details={"path": str(opencode_bin)},
        )

    result = _run([str(opencode_bin), "--version"], cwd=repo_root, timeout=10)
    if result.returncode != 0:
        return CheckResult(
            name="opencode_binary",
            status="fail",
            message=f"opencode --version failed for {opencode_bin}",
            details={
                "path": str(opencode_bin),
                "returncode": result.returncode,
                "stderr": result.stderr,
                "error": result.error,
            },
        )
    version = (result.stdout or result.stderr).strip().splitlines()[0:1]
    version_text = version[0] if version else "version output empty"
    return CheckResult(
        name="opencode_binary",
        status="pass",
        message=f"OpenCode binary is available: {version_text}",
        details={"path": str(opencode_bin), "version": version_text},
    )


def _check_local_opencode_config() -> CheckResult:
    config_candidates = _opencode_config_candidates()
    present = [str(path) for path in config_candidates if path.exists()]
    if present:
        return CheckResult(
            name="local_opencode_config",
            status="warn",
            message=(
                "local OpenCode config path exists but content was not inspected; "
                "verify providers, MCP, hooks, and skills in OpenCode: "
                + ", ".join(present)
            ),
            details={"present_paths": present, "values_read": False, "content_inspected": False},
        )

    return CheckResult(
        name="local_opencode_config",
        status="warn",
        message=(
            "no local OpenCode config path found; configure providers, MCP, hooks, "
            "and skills in OpenCode before independent sessions"
        ),
        details={"checked_paths": [str(path) for path in config_candidates], "values_read": False},
    )


def _opencode_config_candidates() -> tuple[Path, ...]:
    home = Path(os.environ.get("HOME", "~")).expanduser()
    candidates: list[Path] = []
    xdg_config_env = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg_config_env:
        candidates.append(Path(xdg_config_env).expanduser() / "opencode" / "opencode.json")
    candidates.extend(
        (
            home / ".config" / "opencode" / "opencode.json",
            home / ".opencode",
        )
    )
    return _dedupe_paths(candidates)


def _check_local_artifact_ignore_rules(repo_root: Path) -> CheckResult:
    not_ignored: list[str] = []
    for probe in IGNORE_PROBES:
        result = _run(["git", "-C", str(repo_root), "check-ignore", "-q", probe])
        if result.returncode != 0:
            not_ignored.append(probe)

    if not_ignored:
        return CheckResult(
            name="local_artifact_ignore_rules",
            status="fail",
            message="local OpenCode/Codex/AI artifact paths are not all ignored",
            details={"not_ignored": not_ignored},
        )

    return CheckResult(
        name="local_artifact_ignore_rules",
        status="pass",
        message=f"{len(IGNORE_PROBES)} local artifact ignore probes passed",
        details={"ignored_probes": list(IGNORE_PROBES)},
    )


def _check_tracked_local_artifacts(repo_root: Path) -> CheckResult:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return CheckResult(
            name="tracked_local_artifacts",
            status="fail",
            message="could not list tracked files",
            details={"error": str(exc)},
        )
    if result.returncode != 0:
        return CheckResult(
            name="tracked_local_artifacts",
            status="fail",
            message="could not list tracked files",
            details={"stderr": _decode_output(result.stderr), "returncode": result.returncode},
        )

    tracked_files = [
        raw.decode("utf-8", errors="replace")
        for raw in result.stdout.split(b"\0")
        if raw
    ]
    forbidden = [
        path
        for path in tracked_files
        if any(
            path == prefix.rstrip("/") or path.startswith(prefix)
            for prefix in LOCAL_ARTIFACT_PREFIXES
        )
    ]
    if forbidden:
        return CheckResult(
            name="tracked_local_artifacts",
            status="fail",
            message="tracked local OpenCode/Codex/AI artifact paths were found",
            details={"tracked_artifacts": forbidden[:50], "tracked_artifact_count": len(forbidden)},
        )

    return CheckResult(
        name="tracked_local_artifacts",
        status="pass",
        message="no local OpenCode/Codex/AI artifact paths are tracked",
        details={"forbidden_prefixes": list(LOCAL_ARTIFACT_PREFIXES)},
    )


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 10,
    output_limit: int = OUTPUT_LIMIT,
) -> CommandResult:
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            returncode=None,
            stdout="",
            stderr="",
            error=f"missing executable: {exc.filename}",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_output(exc.stdout, limit=output_limit)
        stderr = _decode_output(exc.stderr, limit=output_limit)
        return CommandResult(
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            error=f"timeout after {timeout} seconds",
        )

    return CommandResult(
        returncode=result.returncode,
        stdout=_decode_output(result.stdout, limit=output_limit),
        stderr=_decode_output(result.stderr, limit=output_limit),
        error=None,
    )


def _decode_output(value: str | bytes | None, *, limit: int = OUTPUT_LIMIT) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    return text[:limit]


def _overall_status(checks: Sequence[CheckResult]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _check_to_json(check: CheckResult) -> dict[str, Any]:
    return {
        "name": check.name,
        "status": check.status,
        "message": check.message,
        "details": check.details,
    }


def _print_text(payload: dict[str, Any]) -> None:
    print(f"OpenCode readiness: {payload['overall_status']}")
    print(f"Repo: {payload['repo_root']}")
    print(f"Mode: {payload['mode']}")
    for check in payload["checks"]:
        print(f"- [{check['status']}] {check['name']}: {check['message']}")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return path == parent
    return True


def _contains_term(text: str, term: str) -> bool:
    return " ".join(term.split()) in " ".join(text.split())


def _dedupe_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    deduped: list[Path] = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return tuple(deduped)


if __name__ == "__main__":
    raise SystemExit(main())
