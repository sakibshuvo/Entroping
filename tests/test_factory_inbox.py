from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "factory_inbox.py"


def run_inbox(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def read_payload(stdout: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(stdout))


def write_handoff(
    artifact_root: Path,
    name: str,
    *,
    issue: str,
    status: str = "ready_for_codex",
    codex_inbox_status: str | None = None,
) -> Path:
    artifact_dir = artifact_root / name
    metadata: dict[str, object] = {
        "schema_version": "entroping.interactive-handoff.v1",
        "status": status,
        "issue": issue,
        "branch": f"opencode/issue-{issue}",
        "provider_lane": "opencode/native-deepseek",
        "provider_host": "OpenCode Desktop",
        "billing_path": "paid DeepSeek inside OpenCode",
        "model": "deepseek/deepseek-v4-pro",
        "autonomy_tier": "Tier B assisted lane",
        "merge_authority": "Codex/human required",
        "verification_lane": "tests-only",
        "ci_status": "pass",
    }
    if codex_inbox_status is not None:
        metadata["codex_inbox_status"] = codex_inbox_status
    write_json(artifact_dir / "metadata.json", metadata)
    (artifact_dir / "result.md").write_text(
        "STATUS: pass\n"
        "FILES_CHANGED: scripts/factory_inbox.py, tests/test_factory_inbox.py\n"
        "TESTS_RUN: uv run pytest tests/test_factory_inbox.py -q\n"
        "VERIFICATION_LANE: tests-only\n"
        "CI_STATUS: pass\n"
        "KNOWN_ISSUES: none\n"
        "SUMMARY: Ready for Codex pickup.\n",
        encoding="utf-8",
    )
    (artifact_dir / "tests.txt").write_text("not run by test fixture\n", encoding="utf-8")
    (artifact_dir / "stdout.txt").write_text(
        "raw transcript that must not appear in inbox output\n",
        encoding="utf-8",
    )
    return artifact_dir


def set_tree_mtime(artifact_dir: Path, timestamp: float) -> None:
    for name in ("metadata.json", "result.md", "tests.txt", "stdout.txt"):
        os.utime(artifact_dir / name, (timestamp, timestamp))


def test_factory_inbox_next_returns_oldest_ready_packet_without_transcripts(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    older = write_handoff(artifact_root, "issue-1163-report-split", issue="1163")
    newer = write_handoff(artifact_root, "issue-1165-evidence-packet", issue="1165")
    set_tree_mtime(older, 100)
    set_tree_mtime(newer, 200)

    result = run_inbox("next", "--artifact-root", str(artifact_root), "--json")

    assert result.returncode == 0, result.stderr
    assert "raw transcript that must not appear" not in result.stdout
    payload = read_payload(result.stdout)
    inbox = cast(dict[str, object], payload["inbox"])
    review_packet = cast(dict[str, object], payload["review_packet"])
    artifact = cast(dict[str, object], review_packet["artifact"])
    result_summary = cast(dict[str, str], artifact["result_summary"])

    assert payload["schema_version"] == "entroping.factory-inbox.v1"
    assert inbox["artifact_dir"] == str(older.resolve())
    assert inbox["issue"] == "1163"
    assert review_packet["schema_version"] == "entroping.factory-review-packet.v1"
    assert artifact["metadata_path"] == str(older.resolve() / "metadata.json")
    assert artifact["tests_path"] == str(older.resolve() / "tests.txt")
    assert result_summary["STATUS"] == "pass"


def test_factory_inbox_list_skips_incomplete_and_reviewed_artifacts(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    ready = write_handoff(artifact_root, "issue-1163-ready", issue="1163")
    write_handoff(
        artifact_root,
        "issue-1165-reviewed",
        issue="1165",
        codex_inbox_status="reviewed",
    )
    incomplete = artifact_root / "issue-1166-incomplete"
    write_json(
        incomplete / "metadata.json",
        {"schema_version": "entroping.interactive-handoff.v1", "status": "ready_for_codex"},
    )

    result = run_inbox("list", "--artifact-root", str(artifact_root), "--json")

    assert result.returncode == 0, result.stderr
    payload = read_payload(result.stdout)
    ready_items = cast(list[dict[str, object]], payload["ready"])
    skipped_items = cast(list[dict[str, object]], payload["skipped"])

    assert [item["artifact_dir"] for item in ready_items] == [str(ready.resolve())]
    assert any(
        item["artifact_dir"] == str(incomplete.resolve())
        and item["reason"] == "missing result.md or tests.txt"
        for item in skipped_items
    )
    assert all("reviewed" not in str(item) for item in ready_items)


def test_factory_inbox_mark_reviewed_updates_metadata(tmp_path: Path) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = write_handoff(artifact_root, "issue-1163-ready", issue="1163")

    result = run_inbox(
        "mark-reviewed",
        str(artifact_dir),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    metadata = read_json(artifact_dir / "metadata.json")
    payload = read_payload(result.stdout)

    assert metadata["codex_inbox_status"] == "reviewed"
    assert metadata["review_decision"] == "reviewed"
    assert "reviewed_at" in metadata
    assert payload["codex_inbox_status"] == "reviewed"
