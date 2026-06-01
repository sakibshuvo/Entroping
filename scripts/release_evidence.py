#!/usr/bin/env python3
"""Validate and summarize committed release evidence without GitHub API access."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "entroping.release-evidence.v1"
LEDGER_RELATIVE_PATH = Path("docs") / "meta" / "release-evidence.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_URL_RE = re.compile(r"^https://github\.com/sakibshuvo/Entroping/")
REQUIRED_BLOCKERS = (
    "repeated release evidence",
    "package-index proof",
    "real downstream user feedback",
    "stable-core compatibility decision",
)
DOWNSTREAM_SMOKE_SCHEMA_VERSION = "entroping.downstream-smoke.v1"


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

    failures = _validation_failures(ledger)
    payload = _summary_payload(ledger, failures)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    if args.strict and failures:
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

    blockers = ledger.get("stable_core_blockers")
    if not isinstance(blockers, list) or not all(isinstance(item, str) for item in blockers):
        failures.append("stable_core_blockers must be a list of strings")
        blockers = []
    for blocker in REQUIRED_BLOCKERS:
        if blocker not in blockers:
            failures.append(f"stable_core_blockers missing {blocker}")

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


def _summary_payload(ledger: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    releases = ledger.get("releases")
    release_list = releases if isinstance(releases, list) else []
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
        "ledger_path": LEDGER_RELATIVE_PATH.as_posix(),
        "status": "pass" if not failures else "fail",
        "stable_core_ready": False,
        "stable_core_blockers": ledger.get("stable_core_blockers", []),
        "release_count": len(release_tags),
        "latest_release": latest_release,
        "release_tags": release_tags,
        "latest_main_ci": latest_main_ci if isinstance(latest_main_ci, dict) else {},
        "latest_pages_ci": latest_pages_ci if isinstance(latest_pages_ci, dict) else {},
        "downstream_smoke": downstream_smoke if isinstance(downstream_smoke, dict) else {},
        "failures": failures,
    }


def _error_payload(message: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ledger_path": LEDGER_RELATIVE_PATH.as_posix(),
        "status": "fail",
        "stable_core_ready": False,
        "stable_core_blockers": [],
        "release_count": 0,
        "latest_release": "",
        "release_tags": [],
        "latest_main_ci": {},
        "latest_pages_ci": {},
        "downstream_smoke": {},
        "failures": [message],
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Release Evidence",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Status: `{payload['status']}`",
        f"- Stable-core ready: `{str(payload['stable_core_ready']).lower()}`",
        f"- Release count: `{payload['release_count']}`",
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

    lines.extend(["## Stable-Core Blockers", ""])
    blockers = payload["stable_core_blockers"]
    if isinstance(blockers, list):
        lines.extend(f"- {blocker}" for blocker in blockers)
    lines.extend(["", "## Releases", ""])
    release_tags = payload["release_tags"]
    if isinstance(release_tags, list):
        lines.extend(f"- `{tag}`" for tag in release_tags)
    failures = payload["failures"]
    if isinstance(failures, list) and failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
