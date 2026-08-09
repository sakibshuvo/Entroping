#!/usr/bin/env python3
"""Validate release evidence offline, with optional GitHub CLI freshness checks."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import readiness_contract as readiness

SCHEMA_VERSION = "entroping.release-evidence.v1"
LEDGER_RELATIVE_PATH = Path("docs") / "meta" / "release-evidence.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_URL_RE = re.compile(r"^https://github\.com/sakibshuvo/Entroping/")
DOWNSTREAM_SMOKE_SCHEMA_VERSION = "entroping.downstream-smoke.v1"
RELEASE_CANDIDATE_KIND = "local-release-candidate"
RELEASE_CANDIDATE_GATE = "scripts/release_check.sh --require-live-demo"
ACTIONS_WORKFLOWS = {
    "latest_main_ci": "CI",
    "latest_pages_ci": "Pages",
}
SELF_REFRESH_PATHS = frozenset(
    {
        ".context/changelog.md",
        "docs/meta/release-evidence.json",
        "tests/test_release_evidence.py",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate docs/meta/release-evidence.json and summarize release evidence."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to inspect.",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the ledger is missing or invalid.",
    )
    parser.add_argument(
        "--check-freshness",
        action="store_true",
        help="Optionally compare recorded CI/Pages evidence with latest successful main runs.",
    )
    parser.add_argument(
        "--freshness-input",
        type=Path,
        help="Read latest CI/Pages run evidence from a fixture JSON file instead of gh.",
    )
    parser.add_argument(
        "--repo",
        default="sakibshuvo/Entroping",
        help="GitHub repository for optional gh freshness checks.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    ledger_path = root / LEDGER_RELATIVE_PATH
    try:
        ledger = _load_ledger(ledger_path)
    except ValueError as exc:
        if args.format == "json":
            print(
                json.dumps(
                    _error_payload(str(exc)),
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"# Release Evidence\n\n- Status: `invalid`\n- Error: {exc}")
        if args.strict:
            print("release evidence check failed:", file=sys.stderr)
            print(f"  {exc}", file=sys.stderr)
            return 1
        return 0

    validation_failures = _validation_failures(ledger)
    freshness = _freshness_not_checked()
    freshness_failures: list[str] = []
    if args.check_freshness:
        freshness = _freshness_report(
            ledger,
            root=root,
            repo=args.repo,
            input_path=args.freshness_input,
        )
        if freshness["status"] == "stale":
            freshness_failures = [
                failure
                for failure in freshness["failures"]
                if isinstance(failure, str)
            ]
    failures = [*validation_failures, *freshness_failures]
    payload = _summary_payload(ledger, failures, freshness)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    if args.strict and failures:
        if freshness_failures and not validation_failures:
            print("release evidence freshness check failed:", file=sys.stderr)
        else:
            print("release evidence check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{LEDGER_RELATIVE_PATH.as_posix()}: missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{LEDGER_RELATIVE_PATH.as_posix()}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{LEDGER_RELATIVE_PATH.as_posix()}: root must be an object")
    return payload


def _validation_failures(ledger: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if ledger.get("schema_version") != SCHEMA_VERSION:
        failures.append(f"schema_version must be {SCHEMA_VERSION}")
    if ledger.get("stable_core_ready") is not False:
        failures.append("stable_core_ready must remain false")

    failures.extend(readiness.stable_core_blocker_failures(ledger))

    releases = ledger.get("releases")
    if not isinstance(releases, list):
        failures.append("releases must be a list")
        releases = []
    if len(releases) < 2:
        failures.append("releases must contain at least two entries")
    for index, release in enumerate(releases):
        if not isinstance(release, dict):
            failures.append(f"releases[{index}] must be an object")
            continue
        _validate_release(release, index, failures)

    release_candidates = ledger.get("release_candidates")
    if not isinstance(release_candidates, list):
        failures.append("release_candidates must be a list")
        release_candidates = []
    if not release_candidates:
        failures.append("release_candidates must contain at least one entry")
    for index, candidate in enumerate(release_candidates):
        if not isinstance(candidate, dict):
            failures.append(f"release_candidates[{index}] must be an object")
            continue
        _validate_release_candidate(candidate, index, failures)

    latest_main_ci = ledger.get("latest_main_ci")
    if not isinstance(latest_main_ci, dict):
        failures.append("latest_main_ci must be an object")
    else:
        _validate_actions_run(latest_main_ci, "latest_main_ci", "CI", failures)

    latest_pages_ci = ledger.get("latest_pages_ci")
    if not isinstance(latest_pages_ci, dict):
        failures.append("latest_pages_ci must be an object")
    else:
        _validate_actions_run(latest_pages_ci, "latest_pages_ci", "Pages", failures)

    downstream_smoke = ledger.get("downstream_smoke")
    if not isinstance(downstream_smoke, dict):
        failures.append("downstream_smoke must be an object")
    else:
        _validate_downstream_smoke(downstream_smoke, failures)
    return failures


def _validate_release(release: dict[str, Any], index: int, failures: list[str]) -> None:
    tag = release.get("tag")
    if not isinstance(tag, str) or not tag.startswith("v"):
        failures.append(f"releases[{index}].tag must start with v")
    if release.get("kind") != "github-prerelease":
        failures.append(f"releases[{index}].kind must be github-prerelease")
    if not _valid_iso_z(release.get("published_at")):
        failures.append(f"releases[{index}].published_at must be an ISO UTC timestamp")
    commit = release.get("commit")
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        failures.append(f"releases[{index}].commit must be a 40-character git SHA")
    url = release.get("url")
    if not isinstance(url, str) or GITHUB_URL_RE.match(url) is None:
        failures.append(f"releases[{index}].url must be a GitHub Entroping URL")
    evidence = release.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        failures.append(f"releases[{index}].evidence must be a non-empty object")


def _validate_release_candidate(
    candidate: dict[str, Any],
    index: int,
    failures: list[str],
) -> None:
    name = candidate.get("name")
    if not isinstance(name, str) or not name.startswith("v"):
        failures.append(f"release_candidates[{index}].name must start with v")
    if candidate.get("kind") != RELEASE_CANDIDATE_KIND:
        failures.append(
            f"release_candidates[{index}].kind must be {RELEASE_CANDIDATE_KIND}"
        )
    if not _valid_iso_z(candidate.get("recorded_at")):
        failures.append(
            f"release_candidates[{index}].recorded_at must be an ISO UTC timestamp"
        )
    commit = candidate.get("commit")
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        failures.append(f"release_candidates[{index}].commit must be a 40-character git SHA")
    if candidate.get("release_gate") != RELEASE_CANDIDATE_GATE:
        failures.append(
            f"release_candidates[{index}].release_gate must be {RELEASE_CANDIDATE_GATE}"
        )
    if candidate.get("release_gate_result") != "pass":
        failures.append(f"release_candidates[{index}].release_gate_result must be pass")
    for field_name in ("ci_run_id", "pages_run_id"):
        value = candidate.get(field_name)
        if not isinstance(value, int) or value <= 0:
            failures.append(f"release_candidates[{index}].{field_name} must be a positive integer")
    release_notes = candidate.get("release_notes")
    if not isinstance(release_notes, str) or "not stable-core" not in release_notes:
        failures.append(
            f"release_candidates[{index}].release_notes must preserve alpha/stable-core boundaries"
        )
    stable_boundary = candidate.get("stable_boundary")
    if (
        not isinstance(stable_boundary, str)
        or "not package-index" not in stable_boundary
        or "not stable-core" not in stable_boundary
    ):
        failures.append(
            f"release_candidates[{index}].stable_boundary must avoid stable-core overclaims"
        )


def _validate_actions_run(
    entry: dict[str, Any],
    field_name: str,
    workflow: str,
    failures: list[str],
) -> None:
    if entry.get("workflow") != workflow:
        failures.append(f"{field_name}.workflow must be {workflow}")
    run_id = entry.get("run_id")
    if not isinstance(run_id, int) or run_id <= 0:
        failures.append(f"{field_name}.run_id must be a positive integer")
    if entry.get("conclusion") != "success":
        failures.append(f"{field_name}.conclusion must be success")
    if entry.get("event") != "push":
        failures.append(f"{field_name}.event must be push")
    if not _valid_iso_z(entry.get("created_at")):
        failures.append(f"{field_name}.created_at must be an ISO UTC timestamp")
    commit = entry.get("commit")
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        failures.append(f"{field_name}.commit must be a 40-character git SHA")
    url = entry.get("url")
    if not isinstance(url, str) or GITHUB_URL_RE.match(url) is None or "/actions/runs/" not in url:
        failures.append(f"{field_name}.url must be a GitHub Actions run URL")


def _validate_downstream_smoke(
    downstream_smoke: dict[str, Any],
    failures: list[str],
) -> None:
    if downstream_smoke.get("status") != "local-pass":
        failures.append("downstream_smoke.status must be local-pass")
    if downstream_smoke.get("schema_version") != DOWNSTREAM_SMOKE_SCHEMA_VERSION:
        failures.append(
            f"downstream_smoke.schema_version must be {DOWNSTREAM_SMOKE_SCHEMA_VERSION}"
        )
    command = downstream_smoke.get("command")
    if not isinstance(command, str) or "scripts/downstream_smoke.py" not in command:
        failures.append("downstream_smoke.command must run scripts/downstream_smoke.py")
    if not _valid_iso_z(downstream_smoke.get("recorded_at")):
        failures.append("downstream_smoke.recorded_at must be an ISO UTC timestamp")
    stable_boundary = downstream_smoke.get("stable_boundary")
    if (
        not isinstance(stable_boundary, str)
        or "not real downstream user feedback" not in stable_boundary
    ):
        failures.append(
            "downstream_smoke.stable_boundary must say it is not real downstream user feedback"
        )


def _valid_iso_z(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value))


def _freshness_not_checked() -> dict[str, Any]:
    return {
        "status": "not_checked",
        "source": "",
        "message": (
            "Run with --check-freshness to compare against latest successful "
            "main CI and Pages runs."
        ),
        "latest": {},
        "failures": [],
    }


def _freshness_report(
    ledger: dict[str, Any],
    *,
    root: Path,
    repo: str,
    input_path: Path | None,
) -> dict[str, Any]:
    if input_path is not None:
        source = str(input_path)
        latest, unavailable = _load_freshness_fixture(input_path)
    else:
        source = f"gh run list --repo {repo}"
        latest, unavailable = _load_latest_runs_from_gh(repo)
    if unavailable:
        return {
            "status": "unavailable",
            "source": source,
            "message": unavailable,
            "latest": {},
            "failures": [],
        }

    failures = _freshness_failures(ledger, latest)
    if failures and _is_self_refresh_only(root, ledger, latest):
        return {
            "status": "current",
            "source": source,
            "message": (
                "Latest successful main runs are newer only because of a "
                "release-evidence self-refresh commit."
            ),
            "latest": latest,
            "failures": [],
        }
    return {
        "status": "stale" if failures else "current",
        "source": source,
        "message": (
            "Recorded evidence is behind the latest successful main runs."
            if failures
            else "Recorded evidence matches the latest successful main runs."
        ),
        "latest": latest,
        "failures": failures,
    }


def _load_freshness_fixture(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"freshness fixture unavailable: {exc}"
    if not isinstance(payload, dict):
        return {}, "freshness fixture root must be an object"
    latest: dict[str, dict[str, Any]] = {}
    for field_name in ACTIONS_WORKFLOWS:
        entry = payload.get(field_name)
        if not isinstance(entry, dict):
            return {}, f"freshness fixture missing {field_name} object"
        latest[field_name] = entry
    return latest, ""


def _load_latest_runs_from_gh(repo: str) -> tuple[dict[str, dict[str, Any]], str]:
    latest: dict[str, dict[str, Any]] = {}
    for field_name, workflow in ACTIONS_WORKFLOWS.items():
        entry, unavailable = _load_latest_workflow_from_gh(repo=repo, workflow=workflow)
        if unavailable:
            return {}, unavailable
        latest[field_name] = entry
    return latest, ""


def _load_latest_workflow_from_gh(
    *,
    repo: str,
    workflow: str,
) -> tuple[dict[str, Any], str]:
    command = [
        "gh",
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        workflow,
        "--branch",
        "main",
        "--status",
        "success",
        "--limit",
        "1",
        "--json",
        "databaseId,workflowName,headSha,conclusion,event,createdAt,url",
    ]
    try:
        completed = subprocess.run(  # nosec B603
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError as exc:
        return {}, f"gh executable unavailable: {exc}"
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "gh run list failed"
        return {}, f"gh run list failed for {workflow}: {detail}"
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {}, f"gh run list returned invalid JSON for {workflow}: {exc}"
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return {}, f"gh run list returned no successful main {workflow} runs"
    return _normalise_gh_run(payload[0], workflow), ""


def _normalise_gh_run(run: dict[str, Any], workflow: str) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "run_id": run.get("databaseId"),
        "created_at": run.get("createdAt"),
        "event": run.get("event"),
        "conclusion": run.get("conclusion"),
        "commit": run.get("headSha"),
        "url": run.get("url"),
    }


def _freshness_failures(
    ledger: dict[str, Any],
    latest: dict[str, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    for field_name in ACTIONS_WORKFLOWS:
        recorded = ledger.get(field_name)
        current = latest.get(field_name)
        if not isinstance(recorded, dict) or not isinstance(current, dict):
            continue
        for key in ("run_id", "commit"):
            recorded_value = recorded.get(key)
            current_value = current.get(key)
            if recorded_value != current_value:
                failures.append(
                    f"{field_name}.{key} is {recorded_value} "
                    f"but latest successful main run is {current_value}"
                )
    return failures


def _is_self_refresh_only(
    root: Path,
    ledger: dict[str, Any],
    latest: dict[str, dict[str, Any]],
) -> bool:
    recorded_commits = _actions_commits(ledger)
    latest_commits = _actions_commits(latest)
    if len(recorded_commits) != 1 or len(latest_commits) != 1:
        return False

    recorded_commit = next(iter(recorded_commits))
    latest_commit = next(iter(latest_commits))
    if recorded_commit == latest_commit:
        return False

    changed_paths = _git_changed_paths(root, recorded_commit, latest_commit)
    if not changed_paths:
        return False
    return changed_paths <= SELF_REFRESH_PATHS


def _actions_commits(source: dict[str, Any]) -> set[str]:
    commits: set[str] = set()
    for field_name in ACTIONS_WORKFLOWS:
        entry = source.get(field_name)
        if not isinstance(entry, dict):
            return set()
        commit = entry.get("commit")
        if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
            return set()
        commits.add(commit)
    return commits


def _git_changed_paths(root: Path, old_commit: str, new_commit: str) -> set[str]:
    command = [
        "git",
        "-C",
        str(root),
        "diff",
        "--name-only",
        f"{old_commit}..{new_commit}",
    ]
    try:
        completed = subprocess.run(  # nosec B603
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except OSError:
        return set()
    if completed.returncode != 0:
        return set()
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def _summary_payload(
    ledger: dict[str, Any],
    failures: list[str],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    releases = ledger.get("releases")
    release_list = releases if isinstance(releases, list) else []
    release_candidates = ledger.get("release_candidates")
    release_candidate_list = release_candidates if isinstance(release_candidates, list) else []
    release_tags = [
        release.get("tag")
        for release in release_list
        if isinstance(release, dict) and isinstance(release.get("tag"), str)
    ]
    latest_release = release_tags[0] if release_tags else ""
    latest_main_ci = ledger.get("latest_main_ci")
    latest_pages_ci = ledger.get("latest_pages_ci")
    downstream_smoke = ledger.get("downstream_smoke")
    return {
        "schema_version": SCHEMA_VERSION,
        **readiness.readiness_metadata("recorded-execution-ledger"),
        "ledger_path": LEDGER_RELATIVE_PATH.as_posix(),
        "status": "pass" if not failures else "fail",
        "stable_core_ready": False,
        "stable_core_blocker_ids": ledger.get("stable_core_blocker_ids", []),
        "stable_core_blockers": ledger.get("stable_core_blockers", []),
        "release_count": len(release_tags),
        "release_candidate_count": len(release_candidate_list),
        "latest_release": latest_release,
        "release_tags": release_tags,
        "release_candidates": release_candidate_list,
        "latest_main_ci": latest_main_ci if isinstance(latest_main_ci, dict) else {},
        "latest_pages_ci": latest_pages_ci if isinstance(latest_pages_ci, dict) else {},
        "downstream_smoke": downstream_smoke if isinstance(downstream_smoke, dict) else {},
        "freshness": freshness,
        "failures": failures,
    }


def _error_payload(message: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        **readiness.readiness_metadata("recorded-execution-ledger"),
        "ledger_path": LEDGER_RELATIVE_PATH.as_posix(),
        "status": "fail",
        "stable_core_ready": False,
        "stable_core_blocker_ids": [],
        "stable_core_blockers": [],
        "release_count": 0,
        "release_candidate_count": 0,
        "latest_release": "",
        "release_tags": [],
        "release_candidates": [],
        "latest_main_ci": {},
        "latest_pages_ci": {},
        "downstream_smoke": {},
        "freshness": _freshness_not_checked(),
        "failures": [message],
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Release Evidence",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Contract version: `{payload['contract_version']}`",
        f"- Product maturity: `{payload['product_maturity']}`",
        f"- Readiness basis: `{payload['readiness_basis']}`",
        f"- Status: `{payload['status']}`",
        f"- Stable-core ready: `{str(payload['stable_core_ready']).lower()}`",
        f"- Release count: `{payload['release_count']}`",
        f"- Release candidate count: `{payload['release_candidate_count']}`",
        f"- Latest release: `{payload['latest_release']}`",
        "",
        "## Recorded main CI evidence",
        "",
    ]
    latest_main_ci = payload["latest_main_ci"]
    if isinstance(latest_main_ci, dict) and latest_main_ci:
        lines.extend(
            [
                f"- Workflow: `{latest_main_ci.get('workflow', '')}`",
                f"- Conclusion: `{latest_main_ci.get('conclusion', '')}`",
                f"- Commit: `{latest_main_ci.get('commit', '')}`",
                f"- URL: {latest_main_ci.get('url', '')}",
                "",
            ]
        )
    else:
        lines.extend(["- No recorded main CI evidence.", ""])

    lines.extend(["## Recorded Pages evidence", ""])
    latest_pages_ci = payload["latest_pages_ci"]
    if isinstance(latest_pages_ci, dict) and latest_pages_ci:
        lines.extend(
            [
                f"- Workflow: `{latest_pages_ci.get('workflow', '')}`",
                f"- Conclusion: `{latest_pages_ci.get('conclusion', '')}`",
                f"- Commit: `{latest_pages_ci.get('commit', '')}`",
                f"- URL: {latest_pages_ci.get('url', '')}",
                "",
            ]
        )
    else:
        lines.extend(["- No recorded Pages evidence.", ""])

    lines.extend(["## Downstream smoke evidence", ""])
    downstream_smoke = payload["downstream_smoke"]
    if isinstance(downstream_smoke, dict) and downstream_smoke:
        lines.extend(
            [
                f"- Status: `{downstream_smoke.get('status', '')}`",
                f"- Schema: `{downstream_smoke.get('schema_version', '')}`",
                f"- Command: `{downstream_smoke.get('command', '')}`",
                f"- Stable boundary: {downstream_smoke.get('stable_boundary', '')}",
                "",
            ]
        )
    else:
        lines.extend(["- No recorded downstream smoke evidence.", ""])

    freshness = payload["freshness"]
    lines.extend(["## Freshness", ""])
    if isinstance(freshness, dict):
        lines.extend(
            [
                f"- Status: `{freshness.get('status', '')}`",
                f"- Source: `{freshness.get('source', '')}`",
                f"- Message: {freshness.get('message', '')}",
                "",
            ]
        )

    lines.extend(["## Stable-Core Blockers", ""])
    lines.extend(readiness.render_stable_core_blockers(payload))
    lines.extend(["", "## Releases", ""])
    release_tags = payload["release_tags"]
    if isinstance(release_tags, list):
        lines.extend(f"- `{tag}`" for tag in release_tags)
    release_candidates = payload["release_candidates"]
    lines.extend(["", "## Release candidates", ""])
    if isinstance(release_candidates, list):
        for candidate in release_candidates:
            if not isinstance(candidate, dict):
                continue
            lines.append(
                f"- `{candidate.get('name', '')}` at `{candidate.get('commit', '')}` "
                f"({candidate.get('release_gate_result', '')})"
            )
    failures = payload["failures"]
    if isinstance(failures, list) and failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
