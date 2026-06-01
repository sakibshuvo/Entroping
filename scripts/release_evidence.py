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
    "package-index proof",
    "real downstream user feedback",
    "stable-core compatibility decision",
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
        _validate_latest_main_ci(latest_main_ci, failures)
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


def _validate_latest_main_ci(latest_main_ci: dict[str, Any], failures: list[str]) -> None:
    if latest_main_ci.get("workflow") != "CI":
        failures.append("latest_main_ci.workflow must be CI")
    run_id = latest_main_ci.get("run_id")
    if not isinstance(run_id, int) or run_id <= 0:
        failures.append("latest_main_ci.run_id must be a positive integer")
    if latest_main_ci.get("conclusion") != "success":
        failures.append("latest_main_ci.conclusion must be success")
    if latest_main_ci.get("event") != "push":
        failures.append("latest_main_ci.event must be push")
    if not _valid_iso_z(latest_main_ci.get("created_at")):
        failures.append("latest_main_ci.created_at must be an ISO UTC timestamp")
    commit = latest_main_ci.get("commit")
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        failures.append("latest_main_ci.commit must be a 40-character git SHA")
    url = latest_main_ci.get("url")
    if not isinstance(url, str) or GITHUB_URL_RE.match(url) is None or "/actions/runs/" not in url:
        failures.append("latest_main_ci.url must be a GitHub Actions run URL")


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
