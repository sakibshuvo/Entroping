"""Tests for the bounded OpenCode worker harness."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "opencode_worker.py"


def run_worker(
    *args: str,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env is not None:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=command_env,
    )


def write_fake_opencode(path: Path, *, body: str) -> Path:
    binary = path / "opencode"
    binary.write_text(body, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def write_fake_git(path: Path) -> Path:
    binary = path / "git"
    binary.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "if [[ \"$1 $2\" == 'rev-parse --show-toplevel' ]]; then\n"
        f"  printf '%s\\n' '{REPO_ROOT}'\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected git args: $*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def read_metadata(artifact_dir: Path) -> dict[str, object]:
    payload = json.loads((artifact_dir / "metadata.json").read_text(encoding="utf-8"))
    return cast(dict[str, object], payload)


def test_opencode_worker_help_documents_review_and_patch_modes() -> None:
    result = run_worker("--help")

    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "review" in result.stdout
    assert "patch" in result.stdout
    assert "DeepSeek" in result.stdout


def test_opencode_worker_dry_run_writes_prompt_and_metadata(tmp_path: Path) -> None:
    target_file = REPO_ROOT / "README.md"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_git(fake_bin)

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(target_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--dry-run",
        "--json",
        env={"PATH": str(fake_bin)},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)

    assert metadata["status"] == "dry-run"
    assert metadata["mode"] == "review"
    assert metadata["model"] == "deepseek/deepseek-v4-pro"
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Codex remains the integrator" in prompt
    assert str(target_file.resolve()) in prompt
    assert not (artifact_dir / "stdout.txt").exists()


def test_opencode_worker_patch_mode_captures_unified_diff(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' 'diff --git a/example.py b/example.py'\n"
            "printf '%s\\n' '--- a/example.py' '+++ b/example.py'\n"
            "printf '%s\\n' '@@ -1 +1 @@' '-old' '+new'\n"
        ),
    )

    target_file = REPO_ROOT / "README.md"
    original_content = target_file.read_text(encoding="utf-8")

    result = run_worker(
        "--mode",
        "patch",
        "--file",
        str(target_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)

    assert metadata["status"] == "patch-proposed"
    assert metadata["returncode"] == 0
    command = cast(list[str], metadata["command"])
    assert command[:3] == [str(fake_opencode), "run", "--model"]
    proposal = (artifact_dir / "proposal.diff").read_text(encoding="utf-8")
    assert "diff --git a/example.py b/example.py" in proposal
    assert target_file.read_text(encoding="utf-8") == original_content


def test_opencode_worker_patch_mode_extracts_diff_from_noisy_output(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' 'I found one improvement:'\n"
            "printf '%s\\n' '```diff'\n"
            "printf '%s\\n' 'diff --git a/example.py b/example.py'\n"
            "printf '%s\\n' '--- a/example.py' '+++ b/example.py'\n"
            "printf '%s\\n' '@@ -1 +1 @@' '-old' '+new'\n"
            "printf '%s\\n' '```'\n"
        ),
    )
    target_file = REPO_ROOT / "README.md"

    result = run_worker(
        "--mode",
        "patch",
        "--file",
        str(target_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    raw_output = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    proposal = (artifact_dir / "proposal.diff").read_text(encoding="utf-8")

    assert "I found one improvement" in raw_output
    assert proposal.startswith("diff --git a/example.py b/example.py\n")
    assert "```" not in proposal


def test_opencode_worker_nonzero_subprocess_exits_failed_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' 'Some normal output on stdout'\n"
            "printf '%s\\n' 'Ack! An error occurred.' >&2\n"
            "exit 7\n"
        ),
    )
    target_file = REPO_ROOT / "README.md"
    original_content = target_file.read_text(encoding="utf-8")

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(target_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)

    assert metadata["status"] == "failed"
    assert metadata["returncode"] == 7
    command = cast(list[str], metadata["command"])
    assert command[:3] == [str(fake_opencode), "run", "--model"]
    assert "Some normal output" in (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    assert "Ack! An error occurred." in (artifact_dir / "stderr.txt").read_text(
        encoding="utf-8"
    )
    assert not (artifact_dir / "proposal.diff").exists()
    assert target_file.read_text(encoding="utf-8") == original_content


def test_opencode_worker_timeout_is_inconclusive_and_bounded(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nsleep 5\n",
    )
    target_file = REPO_ROOT / "README.md"

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(target_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--timeout-seconds",
        "0.1",
        "--json",
    )

    assert result.returncode == 124
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)

    assert metadata["status"] == "timed-out"
    assert metadata["timeout_seconds"] == 0.1
    assert "timed out" in (artifact_dir / "stderr.txt").read_text(encoding="utf-8")


def test_opencode_worker_rejects_missing_file_before_model_call(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nexit 99\n",
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(tmp_path / "missing.py"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
    )

    assert result.returncode == 2
    assert "input file does not exist" in result.stderr
    assert not (tmp_path / "reviews").exists()


def test_opencode_worker_rejects_file_outside_repo_before_model_call(tmp_path: Path) -> None:
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("print('secret')\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nexit 99\n",
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(outside_file),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
    )

    assert result.returncode == 2
    assert "input file must be inside repository" in result.stderr
    assert not (tmp_path / "reviews").exists()
