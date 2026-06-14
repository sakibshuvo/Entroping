"""Tests for the bounded OpenCode worker harness."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import cast

import pytest

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


def make_worker_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "worker-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    prompt_dir = repo / "prompts" / "opencode"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "review.md").write_text("Review template\n", encoding="utf-8")
    (prompt_dir / "patch.md").write_text("Patch template\n", encoding="utf-8")
    return repo


def read_metadata(artifact_dir: Path) -> dict[str, object]:
    payload = json.loads((artifact_dir / "metadata.json").read_text(encoding="utf-8"))
    return cast(dict[str, object], payload)


def read_metrics_events(ledger: Path) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], json.loads(line))
        for line in ledger.read_text(encoding="utf-8").splitlines()
    ]


def test_opencode_worker_help_documents_review_and_patch_modes() -> None:
    result = run_worker("--help")

    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "review" in result.stdout
    assert "patch" in result.stdout
    assert "DeepSeek" in result.stdout
    assert "--record-factory-metrics" in result.stdout
    assert "--factory-metrics-ledger" in result.stdout


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
    assert (
        metadata["capability_context_version"]
        == "entroping.opencode-host-capability-context.v1"
    )
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Codex remains the integrator" in prompt
    assert "## OpenCode Host Capability Context" in prompt
    assert "OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek lane" in prompt
    assert "OpenCode-configured agents, plugins, MCP servers, hooks" in prompt
    assert "Codex-native plugins, skills, Codex Security, Browser, Computer Use" in prompt
    assert "--dangerously-skip-permissions" in prompt
    assert "entroping run remains deterministic" in prompt
    assert "OpenCode receives preflight-vetted snapshots" in prompt
    assert "Allowed Snapshot Files" in prompt
    assert "Original Repo-Relative File Provenance" not in prompt
    assert "README.md" in prompt
    assert str(target_file.resolve()) not in prompt
    assert not (artifact_dir / "stdout.txt").exists()


def test_opencode_worker_patch_dry_run_includes_host_capability_context(
    tmp_path: Path,
) -> None:
    target_file = REPO_ROOT / "README.md"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_git(fake_bin)

    result = run_worker(
        "--mode",
        "patch",
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
    prompt = (artifact_dir / "prompt.md").read_text(encoding="utf-8")

    assert metadata["mode"] == "patch"
    assert (
        metadata["capability_context_version"]
        == "entroping.opencode-host-capability-context.v1"
    )
    assert "# Entroping OpenCode Patch Worker" in prompt
    assert "## OpenCode Host Capability Context" in prompt
    assert "OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek lane" in prompt
    assert "Patch mode may propose a single unified diff only" in prompt


def test_opencode_worker_records_opt_in_factory_metrics_for_dry_run(
    tmp_path: Path,
) -> None:
    target_file = REPO_ROOT / "README.md"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_git(fake_bin)
    ledger = (
        Path(".entroping")
        / "factory-metrics"
        / "tests"
        / f"opencode-{uuid.uuid4().hex}.jsonl"
    )
    full_ledger = REPO_ROOT / ledger

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            str(target_file),
            "--issue",
            "654",
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--record-factory-metrics",
            "--factory-role",
            "code_review_agent",
            "--factory-metrics-ledger",
            ledger.as_posix(),
            "--dry-run",
            "--json",
            env={"PATH": str(fake_bin)},
        )

        assert result.returncode == 0, result.stderr
        events = read_metrics_events(full_ledger)
        assert len(events) == 1
        event = events[0]
        metrics = cast(dict[str, object], event["metrics"])
        assert event["event_type"] == "worker_job"
        assert event["role"] == "code_review_agent"
        assert event["agent"] == "OpenCode"
        assert event["tool"] == "scripts/opencode_worker.py"
        assert event["provider"] == "deepseek"
        assert event["model"] == "deepseek-v4-pro"
        assert event["issue"] == "654"
        assert event["outcome"] == "success"
        assert event["decision"] == "not_applicable"
        assert metrics["context_bytes"] == target_file.stat().st_size
        assert metrics["estimated_tokens"] == max(1, (target_file.stat().st_size + 3) // 4)
        assert metrics["candidate_files"] == 1
        assert metrics["files_read"] == 1
        assert "Codex remains the integrator" not in full_ledger.read_text(
            encoding="utf-8"
        )
    finally:
        full_ledger.unlink(missing_ok=True)


def test_opencode_worker_metrics_failure_does_not_mask_dry_run(
    tmp_path: Path,
) -> None:
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
        "--record-factory-metrics",
        "--factory-metrics-ledger",
        str(tmp_path / "unsafe-ledger.jsonl"),
        "--dry-run",
        "--json",
        env={"PATH": str(fake_bin)},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "dry-run"
    assert "factory metrics warning" in result.stderr
    assert not (tmp_path / "unsafe-ledger.jsonl").exists()


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
    assert "--dangerously-skip-permissions" not in command
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


def test_opencode_worker_withholds_secret_like_subprocess_output(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' 'api_key = \"abcdefghijklmnopqrstuvwxyz123456\"'\n"
            "printf '%s\\n' 'ordinary diagnostic' >&2\n"
        ),
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
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    persisted_stdout = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    persisted_stderr = (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    persisted_metadata = (artifact_dir / "metadata.json").read_text(encoding="utf-8")

    assert metadata["status"] == "failed"
    assert "OpenCode stdout withheld because it contained secret-like content" in (
        persisted_stdout
    )
    assert "ordinary diagnostic" in persisted_stderr
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_stdout
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_stderr
    assert "abcdefghijklmnopqrstuvwxyz123456" not in persisted_metadata


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


def test_opencode_worker_attaches_preflight_snapshot_to_subprocess(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    selected_file = repo / "notes.md"
    selected_file.write_text("vetted snapshot content\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "attached=''\n"
            "previous=''\n"
            "for arg in \"$@\"; do\n"
            "  if [[ \"$previous\" == '--file' ]]; then attached=\"$arg\"; fi\n"
            "  previous=\"$arg\"\n"
            "done\n"
            "if [[ -z \"$attached\" ]]; then\n"
            "  printf '%s\\n' 'missing attached snapshot' >&2\n"
            "  exit 6\n"
            "fi\n"
            "printf '%s\\n' \"worker-cwd=$PWD\" > opencode-cwd.txt\n"
            "printf '%s\\n' 'mutated live file content' > notes.md\n"
            "printf '%s\\n' 'snapshot:'\n"
            "cat \"$attached\"\n"
            "printf '%s\\n' 'worker-cwd-note:'\n"
            "cat notes.md\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "notes.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
        cwd=repo,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    command = cast(list[str], metadata["command"])

    assert "--file" in command
    assert command[4].startswith("Review template")
    assert command.index("--file") > 4
    snapshot_path = Path(command[command.index("--file") + 1])
    assert snapshot_path == artifact_dir / "selected-files" / "notes.md"
    assert snapshot_path.read_text(encoding="utf-8") == "vetted snapshot content\n"
    raw_output = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    assert "snapshot:\nvetted snapshot content\n" in raw_output
    assert "worker-cwd-note:\nmutated live file content\n" in raw_output
    worker_cwd = artifact_dir / "worker-cwd"
    assert (worker_cwd / "opencode-cwd.txt").read_text(encoding="utf-8").strip() == (
        f"worker-cwd={worker_cwd}"
    )
    assert not (artifact_dir / "opencode-cwd.txt").exists()
    assert selected_file.read_text(encoding="utf-8") == "vetted snapshot content\n"


def test_opencode_worker_parent_artifacts_are_outside_worker_writable_cwd(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    selected_file = repo / "notes.md"
    selected_file.write_text("vetted snapshot content\n", encoding="utf-8")
    victim = tmp_path / "victim.txt"
    victim.write_text("untouched\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "ln -sf \"$VICTIM\" stdout.txt\n"
            "ln -sf \"$VICTIM\" ../stdout.txt\n"
            "printf '%s\\n' \"worker-cwd=$PWD\"\n"
            "printf '%s\\n' 'captured stdout stays in parent artifact file'\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "notes.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
        cwd=repo,
        env={"VICTIM": str(victim)},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    worker_cwd = artifact_dir / "worker-cwd"
    raw_output = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")

    assert f"worker-cwd={worker_cwd}\n" in raw_output
    assert "captured stdout stays in parent artifact file\n" in raw_output
    assert victim.read_text(encoding="utf-8") == "untouched\n"
    assert (worker_cwd / "stdout.txt").is_symlink()
    assert not (artifact_dir / "stdout.txt").is_symlink()


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


def test_opencode_worker_rejects_symlink_before_subprocess(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    target_file = repo / "target.md"
    target_file.write_text("safe content\n", encoding="utf-8")
    symlink_file = repo / "linked.md"
    try:
        symlink_file.symlink_to(target_file)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    marker = tmp_path / "opencode-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf invoked > '{marker}'\n"
            "exit 99\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "linked.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        cwd=repo,
    )

    assert result.returncode == 2
    assert "input path must be a regular non-symlink file" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "reviews").exists()


def test_opencode_worker_rejects_sensitive_path_before_subprocess(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    sensitive_file = repo / "secret.env.prod"
    sensitive_file.write_text("placeholder only\n", encoding="utf-8")
    marker = tmp_path / "opencode-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf invoked > '{marker}'\n"
            "exit 99\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "secret.env.prod",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        cwd=repo,
    )

    assert result.returncode == 2
    assert "refusing to send selected file to OpenCode" in result.stderr
    assert "sensitive credential file" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "reviews").exists()


@pytest.mark.parametrize(
    ("content", "label"),
    (
        ("-----BEGIN PRIVATE KEY-----\nnot-real\n", "private key block"),
        (
            "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456\n",
            "credential assignment",
        ),
        (
            '{"access_token": "ghp_abcdefghijklmnopqrstuvwxyz123456"}\n',
            "credential assignment",
        ),
        (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n",
            "bearer token",
        ),
    ),
)
def test_opencode_worker_rejects_secret_like_content_before_subprocess(
    tmp_path: Path,
    content: str,
    label: str,
) -> None:
    repo = make_worker_repo(tmp_path)
    selected_file = repo / "notes.md"
    selected_file.write_text(content, encoding="utf-8")
    marker = tmp_path / "opencode-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf invoked > '{marker}'\n"
            "exit 99\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "notes.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        cwd=repo,
    )

    assert result.returncode == 2
    assert "refusing to send selected file to OpenCode" in result.stderr
    assert f"secret-like content ({label})" in result.stderr
    assert "abcdefghijklmnopqrstuvwxyz123456" not in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "reviews").exists()


def test_opencode_worker_rejects_binary_file_before_subprocess(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    selected_file = repo / "notes.md"
    selected_file.write_bytes(b"not-text\x00payload")
    marker = tmp_path / "opencode-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf invoked > '{marker}'\n"
            "exit 99\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "notes.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        cwd=repo,
    )

    assert result.returncode == 2
    assert "refusing to send selected file to OpenCode" in result.stderr
    assert "binary content" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "reviews").exists()


def test_opencode_worker_rejects_oversized_file_before_subprocess(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    selected_file = repo / "notes.md"
    selected_file.write_text("x" * 12, encoding="utf-8")
    marker = tmp_path / "opencode-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf invoked > '{marker}'\n"
            "exit 99\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "notes.md",
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--max-file-bytes",
        "10",
        cwd=repo,
    )

    assert result.returncode == 2
    assert "refusing to send selected file to OpenCode" in result.stderr
    assert "exceeds --max-file-bytes" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "reviews").exists()
