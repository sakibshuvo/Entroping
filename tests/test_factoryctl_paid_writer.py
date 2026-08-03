from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts/factoryctl.py"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FACTORYCTL), *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def _paid_write(*authority: str) -> tuple[str, ...]:
    return (
        "tick",
        "--json",
        "--request-id",
        "paid-write-request",
        "--job-id",
        "paid-write-job",
        "--issue",
        "1574",
        "--worktree-id",
        f"wt_{'7' * 64}",
        "--worker-class",
        "paid",
        "--access-mode",
        "write",
        *authority,
    )


def test_paid_writer_with_reservation_uses_generic_cli_policy(tmp_path: Path) -> None:
    result = _run(tmp_path, *_paid_write("--reservation-id", f"res-{'a' * 32}"))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "would-assign"
    assert payload["authoritative"] is False
    assert payload["paid_work_authorized"] is False
    assert not (tmp_path / ".entroping").exists()


def test_paid_writer_without_dispatch_authority_is_model_rejected(tmp_path: Path) -> None:
    result = _run(tmp_path, *_paid_write())

    assert result.returncode == 2
    assert "paid assignments require a dispatch authorization" in result.stderr
    assert not (tmp_path / ".entroping").exists()
