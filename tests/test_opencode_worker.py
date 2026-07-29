"""Tests for the bounded OpenCode worker harness."""

from __future__ import annotations

import json
import os
import shlex
import shutil
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
    _shebang, separator, script_body = body.partition("\n")
    assert separator
    binary.write_text(
        "#!/bin/bash\n"
        "if [[ \"${1:-}\" == '--version' ]]; then printf '1.18.4\\n'; exit 0; fi\n"
        "if [[ \"${1:-} ${2:-}\" == 'run --help' ]]; then\n"
        "  printf '%s\\n' '--pure --agent --dir --format json --model --file "
        "--auto --attach --continue --session --share --interactive dangerous'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-} ${2:-} ${3:-}\" == '--pure debug config' ]]; then\n"
        "  printf '%s\\n' \"$OPENCODE_CONFIG_CONTENT\"\n"
        "  exit 0\n"
        "fi\n"
        + script_body,
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def event_script(payload: dict[str, object]) -> str:
    return f"printf '%s\\n' {shlex.quote(json.dumps(payload))}\n"


def text_event_script(text: str, *, session_id: str = "session-1") -> str:
    return event_script(
        {
            "type": "text",
            "sessionID": session_id,
            "part": {"text": text},
        }
    )


def usage_event_script(
    *,
    session_id: str = "session-1",
    part_id: str = "step-1",
    cost: float = 0.01,
) -> str:
    return event_script(
        {
            "type": "step_finish",
            "sessionID": session_id,
            "part": {
                "id": part_id,
                "messageID": "message-1",
                "sessionID": session_id,
                "cost": cost,
                "tokens": {
                    "input": 100,
                    "output": 20,
                    "reasoning": 5,
                    "cache": {"read": 7, "write": 3},
                },
            },
        }
    )


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


def read_usage_receipt(artifact_dir: Path) -> dict[str, object]:
    payload = json.loads((artifact_dir / "usage-receipt.json").read_text(encoding="utf-8"))
    return cast(dict[str, object], payload)


def read_metrics_events(ledger: Path) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], json.loads(line))
        for line in ledger.read_text(encoding="utf-8").splitlines()
    ]


def _assert_worker_environment_isolated(
    *,
    environment_keys: set[str],
    observed_text: str,
    repo: Path,
    sentinel: Path,
) -> None:
    forbidden = {
        "BASH_ENV",
        "HTTPS_PROXY",
        "NODE_EXTRA_CA_CERTS",
        "NODE_OPTIONS",
        "OPENCODE_CONFIG",
        "OPENCODE_ENABLE_EXA",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "UNRELATED_SECRET",
    }

    assert not sentinel.exists()
    assert f"cwd={repo}" not in observed_text
    assert forbidden.isdisjoint(environment_keys)
    assert "DEEPSEEK_API_KEY" in environment_keys


def _assert_worker_command_is_bounded(
    *, command: list[str], observed_text: str
) -> None:
    forbidden = {
        "--auto",
        "--attach",
        "--continue",
        "--session",
        "--share",
        "--interactive",
    }

    assert {"--pure", "--agent", "--dir"}.issubset(command)
    assert forbidden.isdisjoint(command)
    assert "--format json" in observed_text
    assert "OpenCode may use OpenCode-configured agents" not in observed_text
    assert "This unattended worker cannot use host agents" in observed_text
    assert "No model-issued tools are enabled" in observed_text


def _assert_value_free_artifacts(
    *,
    artifact_dir: Path,
    command: list[str],
    metadata: dict[str, object],
    raw_instruction: str,
) -> None:
    assert raw_instruction not in json.dumps(metadata)
    assert not (artifact_dir / "prompt.md").exists()
    assert command[-1] == "<prompt-redacted>"


def _assert_capability_receipt(
    *,
    receipt: dict[str, object],
    receipt_text: str,
    poison_value: str,
    provider_secret: str,
    raw_instruction: str,
    hostile_home: Path,
) -> None:
    assert receipt["schema_version"] == (
        "entroping.opencode-unattended-capability-receipt.v1"
    )
    assert receipt["profile_id"] == "entroping.opencode-unattended-review.v1"
    assert receipt["allowed_capabilities"] == ["explicit_file_attachment"]
    assert {"glob", "grep", "read"}.issubset(
        set(cast(list[str], receipt["denied_capabilities"]))
    )
    assert receipt["pure_mode"] is True
    assert receipt["raw_values_recorded"] is False
    assert all(
        forbidden not in receipt_text
        for forbidden in (
            poison_value,
            provider_secret,
            raw_instruction,
            str(hostile_home),
            "tool_args",
        )
    )
    assert "DEEPSEEK_API_KEY" in cast(
        list[str], receipt["sanitized_environment_keys"]
    )


def test_opencode_worker_help_documents_review_and_patch_modes() -> None:
    result = run_worker("--help")

    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "review" in result.stdout
    assert "patch" in result.stdout
    assert "DeepSeek" in result.stdout
    assert "--record-factory-metrics" in result.stdout
    assert "--factory-metrics-ledger" in result.stdout
    assert "--job-id" in result.stdout


def test_opencode_worker_scrubs_poison_and_records_value_free_capability_receipt(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    selected_file = repo / "notes.md"
    selected_file.write_text("vetted snapshot content\n", encoding="utf-8")
    hostile_home = tmp_path / "hostile-home"
    hostile_config = hostile_home / ".config" / "opencode" / "opencode.json"
    hostile_config.parent.mkdir(parents=True)
    poison_value = "poison-value-must-not-pass"
    provider_secret = "sk-deepseek-test-secret-must-not-persist"
    hostile_config.write_text(
        json.dumps({"plugin": [poison_value], "mcp": {"poison": {"enabled": True}}}),
        encoding="utf-8",
    )
    (repo / "opencode.json").write_text(
        json.dumps({"instructions": [poison_value], "tools": {"custom": True}}),
        encoding="utf-8",
    )
    observed = tmp_path / "observed.txt"
    sentinel = tmp_path / "poison-side-effect"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            f"if [[ \"$HOME\" == {shlex.quote(str(hostile_home))} ]]; then "
            f"touch {shlex.quote(str(sentinel))}; fi\n"
            f"printf 'cwd=%s\\n' \"$PWD\" > {shlex.quote(str(observed))}\n"
            f"printf 'keys=%s\\n' \"$(env | cut -d= -f1 | sort | tr '\\n' ',')\" >> "
            f"{shlex.quote(str(observed))}\n"
            f"printf 'args=%s\\n' \"$*\" >> {shlex.quote(str(observed))}\n"
            f"printf 'config=%s\\n' \"$OPENCODE_CONFIG_CONTENT\" >> "
            f"{shlex.quote(str(observed))}\n"
            + text_event_script("Concrete isolated review finding")
            + usage_event_script()
        ),
    )
    raw_instruction = "raw-instruction-must-not-be-persisted"

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "notes.md",
        "--instruction",
        raw_instruction,
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
        cwd=repo,
        env={
            "HOME": str(hostile_home),
            "XDG_CONFIG_HOME": str(hostile_home / ".config"),
            "OPENCODE_CONFIG": poison_value,
            "OPENCODE_CONFIG_CONTENT": poison_value,
            "HTTPS_PROXY": poison_value,
            "OPENCODE_ENABLE_EXA": poison_value,
            "BASH_ENV": poison_value,
            "NODE_OPTIONS": poison_value,
            "NODE_EXTRA_CA_CERTS": poison_value,
            "SSL_CERT_DIR": poison_value,
            "SSL_CERT_FILE": poison_value,
            "UNRELATED_SECRET": poison_value,
            "DEEPSEEK_API_KEY": provider_secret,
        },
    )

    assert result.returncode == 0, result.stderr
    payload = cast(dict[str, object], json.loads(result.stdout))
    artifact_dir = Path(cast(str, payload["artifact_dir"]))
    metadata = read_metadata(artifact_dir)
    receipt_text = (artifact_dir / "capability-receipt.json").read_text(
        encoding="utf-8"
    )
    receipt = cast(dict[str, object], json.loads(receipt_text))
    observed_text = observed.read_text(encoding="utf-8")
    environment_keys = set(
        observed_text.split("keys=", 1)[1].splitlines()[0].split(",")
    )
    config = cast(
        dict[str, object],
        json.loads(observed_text.split("config=", 1)[1].splitlines()[0]),
    )
    command = cast(list[str], metadata["command"])

    _assert_worker_environment_isolated(
        environment_keys=environment_keys,
        observed_text=observed_text,
        repo=repo,
        sentinel=sentinel,
    )
    _assert_worker_command_is_bounded(command=command, observed_text=observed_text)
    _assert_value_free_artifacts(
        artifact_dir=artifact_dir,
        command=command,
        metadata=metadata,
        raw_instruction=raw_instruction,
    )
    assert config["plugin"] == []
    assert config["mcp"] == {}
    assert config["instructions"] == []
    assert config["subagent_depth"] == 0
    assert poison_value not in json.dumps(config)
    _assert_capability_receipt(
        receipt=receipt,
        receipt_text=receipt_text,
        poison_value=poison_value,
        provider_secret=provider_secret,
        raw_instruction=raw_instruction,
        hostile_home=hostile_home,
    )


def test_opencode_worker_blocks_missing_cli_capability_before_provider_run(
    tmp_path: Path,
) -> None:
    provider_marker = tmp_path / "provider-run"
    fake_opencode = tmp_path / "opencode"
    fake_opencode.write_text(
        "#!/bin/bash\n"
        "if [[ \"${1:-}\" == '--version' ]]; then echo '1.18.4'; exit 0; fi\n"
        "if [[ \"${1:-} ${2:-}\" == 'run --help' ]]; then\n"
        "  echo '--agent --dir --format json --model --file --auto dangerous'\n"
        "  exit 0\n"
        "fi\n"
        f"touch {shlex.quote(str(provider_marker))}\n",
        encoding="utf-8",
    )
    fake_opencode.chmod(fake_opencode.stat().st_mode | stat.S_IXUSR)

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(REPO_ROOT / "README.md"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
    )

    assert result.returncode == 2
    assert "missing: --pure" in result.stderr
    assert not provider_marker.exists()


def test_opencode_worker_persists_only_sanitized_json_usage_evidence(
    tmp_path: Path,
) -> None:
    secret = "sk-test-super-secret-provider-value"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            + event_script(
                {
                    "type": "tool_use",
                    "sessionID": "session-1",
                    "part": {"state": {"input": {"token": secret}}},
                }
            )
            + event_script(
                {
                    "type": "reasoning",
                    "sessionID": "session-1",
                    "part": {"text": secret},
                }
            )
            + text_event_script("Concrete review finding")
            + usage_event_script()
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(REPO_ROOT / "README.md"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--job-id",
        "job-review-1",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = cast(dict[str, object], json.loads(result.stdout))
    artifact_dir = Path(cast(str, payload["artifact_dir"]))
    receipt = read_usage_receipt(artifact_dir)
    metadata = read_metadata(artifact_dir)
    command = cast(list[str], metadata["command"])
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            artifact_dir / "stdout.txt",
            artifact_dir / "stderr.txt",
            artifact_dir / "metadata.json",
            artifact_dir / "usage-receipt.json",
        )
    )

    assert payload["usage"] == {
        "cache_read_tokens": 7,
        "cache_write_tokens": 3,
        "cost_usd": 0.01,
        "input_tokens": 100,
        "output_tokens": 20,
        "reasoning_tokens": 5,
    }
    assert receipt["accounting_status"] == "accounted"
    assert receipt["accounting_reason"] == "complete"
    assert receipt["job_id"] == "job-review-1"
    assert receipt["requested_model"] == "deepseek/deepseek-v4-pro"
    assert receipt["run_id"] == artifact_dir.name
    assert receipt["session_fingerprint"] != "session-1"
    assert (artifact_dir / "stdout.txt").read_text(encoding="utf-8") == (
        "Concrete review finding"
    )
    assert command[command.index("--format") + 1] == "json"
    assert secret not in persisted
    assert '"type"' not in (artifact_dir / "stdout.txt").read_text(encoding="utf-8")


def test_opencode_worker_zero_cost_is_explicitly_unaccounted(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            + text_event_script("Review complete")
            + usage_event_script(cost=0.0)
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(REPO_ROOT / "README.md"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = cast(dict[str, object], json.loads(result.stdout))
    artifact_dir = Path(cast(str, payload["artifact_dir"]))
    receipt = read_usage_receipt(artifact_dir)
    assert receipt["accounting_status"] == "unaccounted"
    assert receipt["accounting_reason"] == "ambiguous_zero_cost"
    assert "usage" not in payload
    assert "usage" not in receipt


def test_opencode_worker_malformed_event_fails_without_persisting_raw_content(
    tmp_path: Path,
) -> None:
    secret = "api_key=abcdefghijklmnopqrstuvwxyz123456"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"printf '%s\\n' {shlex.quote(secret + ' not-json')}\n"
        ),
    )

    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(REPO_ROOT / "README.md"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 1
    payload = cast(dict[str, object], json.loads(result.stdout))
    artifact_dir = Path(cast(str, payload["artifact_dir"]))
    receipt = read_usage_receipt(artifact_dir)
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            artifact_dir / "stdout.txt",
            artifact_dir / "stderr.txt",
            artifact_dir / "metadata.json",
            artifact_dir / "usage-receipt.json",
        )
    )
    assert receipt["accounting_status"] == "unaccounted"
    assert receipt["accounting_reason"] == "malformed_event"
    assert secret not in persisted


def test_opencode_worker_records_accounted_usage_in_opt_in_metrics(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            + text_event_script("Review complete")
            + usage_event_script()
        ),
    )
    ledger = (
        Path(".entroping")
        / "factory-metrics"
        / "tests"
        / f"opencode-usage-{uuid.uuid4().hex}.jsonl"
    )
    full_ledger = REPO_ROOT / ledger

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            str(REPO_ROOT / "README.md"),
            "--artifact-root",
            str(tmp_path / "reviews"),
            "--opencode-bin",
            str(fake_opencode),
            "--record-factory-metrics",
            "--factory-metrics-ledger",
            ledger.as_posix(),
            "--json",
        )

        assert result.returncode == 0, result.stderr
        event = read_metrics_events(full_ledger)[0]
        metrics = cast(dict[str, object], event["metrics"])
        assert metrics["estimated_tokens"] == 125
        assert metrics["cost_usd"] == 0.01
        assert "Review complete" not in full_ledger.read_text(encoding="utf-8")
    finally:
        full_ledger.unlink(missing_ok=True)


def test_opencode_worker_dry_run_redacts_prompt_from_metadata(tmp_path: Path) -> None:
    target_file = REPO_ROOT / "README.md"
    raw_instruction = "dry-run-instruction-must-not-be-persisted"
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
        "--instruction",
        raw_instruction,
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
    command = cast(list[str], metadata["command"])
    assert command[-1] == "<prompt-redacted>"
    assert raw_instruction not in json.dumps(metadata)
    assert metadata["capability_receipt"] is None
    assert not (artifact_dir / "prompt.md").exists()
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

    assert metadata["mode"] == "patch"
    assert (
        metadata["capability_context_version"]
        == "entroping.opencode-host-capability-context.v1"
    )
    assert cast(list[str], metadata["command"])[-1] == "<prompt-redacted>"
    assert not (artifact_dir / "prompt.md").exists()


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
            + text_event_script(
                "diff --git a/example.py b/example.py\n"
                "--- a/example.py\n+++ b/example.py\n"
                "@@ -1 +1 @@\n-old\n+new\n"
            )
            + usage_event_script()
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
    assert command[:3] == [str(fake_opencode), "run", "--pure"]
    assert not Path(command[command.index("--dir") + 1]).exists()
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
            + text_event_script(
                "I found one improvement:\n```diff\n"
                "diff --git a/example.py b/example.py\n"
                "--- a/example.py\n+++ b/example.py\n"
                "@@ -1 +1 @@\n-old\n+new\n```\n"
            )
            + usage_event_script()
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
            + text_event_script('api_key = "abcdefghijklmnopqrstuvwxyz123456"')
            + usage_event_script()
            + "printf '%s\\n' 'ordinary diagnostic' >&2\n"
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
    assert "raw provider stderr was withheld" in persisted_stderr
    assert "ordinary diagnostic" not in persisted_stderr
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
            + text_event_script("Some normal output on stdout")
            + usage_event_script()
            + "printf '%s\\n' 'Ack! An error occurred.' >&2\n"
            + "exit 7\n"
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
    assert command[:3] == [str(fake_opencode), "run", "--pure"]
    assert not Path(command[command.index("--dir") + 1]).exists()
    assert "Some normal output" in (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    persisted_stderr = (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    assert "raw provider stderr was withheld" in persisted_stderr
    assert "Ack! An error occurred." not in persisted_stderr
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
            "if [[ \"$(cat \"$attached\")\" != 'vetted snapshot content' ]]; then exit 8; fi\n"
            + text_event_script(
                "snapshot:\nvetted snapshot content\n"
                "worker-cwd-note:\nmutated live file content\n"
            )
            + usage_event_script()
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
    assert command[-1] == "<prompt-redacted>"
    snapshot_path = Path(command[command.index("--file") + 1])
    assert snapshot_path == artifact_dir / "selected-files" / "notes.md"
    assert snapshot_path.read_text(encoding="utf-8") == "vetted snapshot content\n"
    raw_output = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    assert "snapshot:\nvetted snapshot content\n" in raw_output
    assert "worker-cwd-note:\nmutated live file content\n" in raw_output
    worker_cwd = Path(command[command.index("--dir") + 1])
    assert not worker_cwd.exists()
    assert REPO_ROOT not in worker_cwd.parents
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
            f"ln -sf {shlex.quote(str(victim))} stdout.txt\n"
            f"ln -sf {shlex.quote(str(victim))} ../stdout.txt\n"
            "printf '%s\\n' \"worker-cwd=$PWD\" > opencode-cwd.txt\n"
            + text_event_script("captured stdout stays in parent artifact file")
            + usage_event_script()
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
    worker_cwd = Path(command[command.index("--dir") + 1])
    raw_output = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")

    assert "captured stdout stays in parent artifact file" in raw_output
    assert not worker_cwd.exists()
    assert victim.read_text(encoding="utf-8") == "untouched\n"
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
    command = cast(list[str], metadata["command"])

    assert metadata["status"] == "timed-out"
    assert metadata["timeout_seconds"] == 0.1
    assert not Path(command[command.index("--dir") + 1]).exists()
    assert "timed out" in (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    receipt = read_usage_receipt(artifact_dir)
    assert receipt["accounting_status"] == "unaccounted"
    assert receipt["accounting_reason"] == "timed_out"


def test_opencode_worker_kills_and_bounds_output_flood(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "i=0\n"
            "while [ \"$i\" -lt 10000 ]; do printf '%0100d' 0; i=$((i + 1)); done\n"
        ),
    )
    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(REPO_ROOT / "README.md"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--max-output-bytes",
        "1024",
        "--json",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    artifact_dir = Path(str(payload["artifact_dir"]))
    stdout = (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    stderr = (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    metadata = read_metadata(artifact_dir)
    assert len(stdout.encode("utf-8")) <= 1024
    assert len(stderr.encode("utf-8")) <= 1024
    assert stdout == ""
    assert "exceeded the 1024-byte output limit" in stderr
    assert "0000000000" not in stderr
    assert read_usage_receipt(artifact_dir)["accounting_reason"] == (
        "output_limit_exceeded"
    )
    assert metadata["max_output_bytes"] == 1024
    command = cast(list[str], metadata["command"])
    assert not Path(command[command.index("--dir") + 1]).exists()


def test_opencode_worker_bounds_stderr_flood_after_adding_failure_context(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body=(
            "#!/usr/bin/env bash\n"
            "i=0\n"
            "while [ \"$i\" -lt 10000 ]; do printf '%0100d' 0 >&2; i=$((i + 1)); done\n"
        ),
    )
    result = run_worker(
        "--mode",
        "review",
        "--file",
        str(REPO_ROOT / "README.md"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
        "--max-output-bytes",
        "1024",
        "--json",
    )

    assert result.returncode == 1
    assert result.stdout, result.stderr
    payload = cast(dict[str, object], json.loads(result.stdout))
    artifact_dir = Path(str(payload["artifact_dir"]))
    stderr = (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    assert len(stderr.encode("utf-8")) <= 1024
    assert stderr.startswith("OpenCode worker exceeded the 1024-byte output limit.")
    assert "output truncated: byte limit exceeded" not in stderr
    assert "0000000000" not in stderr


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


def test_opencode_worker_rejects_unknown_model_before_provider_run(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "provider-run"
    fake_opencode = tmp_path / "opencode"
    fake_opencode.write_text(
        f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n",
        encoding="utf-8",
    )
    fake_opencode.chmod(fake_opencode.stat().st_mode | stat.S_IXUSR)

    result = run_worker(
        "--mode",
        "review",
        "--model",
        "opencode/unregistered-model",
        "--file",
        str(REPO_ROOT / "README.md"),
        "--artifact-root",
        str(tmp_path / "reviews"),
        "--opencode-bin",
        str(fake_opencode),
    )

    assert result.returncode == 2
    assert "active registered OpenCode queue model" in result.stderr
    assert not marker.exists()
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


def test_opencode_worker_rejects_symlinked_artifact_root_before_artifacts(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    target_file = repo / "target.md"
    target_file.write_text("safe content\n", encoding="utf-8")
    outside_artifact_root = tmp_path / "outside-reviews"
    outside_artifact_root.mkdir()
    linked_artifact_root = tmp_path / "linked-reviews"
    try:
        linked_artifact_root.symlink_to(outside_artifact_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "target.md",
        "--artifact-root",
        str(linked_artifact_root),
        "--dry-run",
        "--json",
        cwd=repo,
    )

    assert result.returncode == 2
    assert "artifact root must not use symlink components" in result.stderr
    assert list(outside_artifact_root.iterdir()) == []


def test_opencode_worker_rejects_relative_artifact_root_escape(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    target_file = repo / "target.md"
    target_file.write_text("safe content\n", encoding="utf-8")

    result = run_worker(
        "--mode",
        "review",
        "--file",
        "target.md",
        "--artifact-root",
        "../outside-reviews",
        "--dry-run",
        "--json",
        cwd=repo,
    )

    assert result.returncode == 2
    assert "artifact root must stay inside repository" in result.stderr
    assert not (tmp_path / "outside-reviews").exists()


def test_opencode_worker_rejects_arbitrary_absolute_artifact_root_outside_repo_and_temp(
    tmp_path: Path,
) -> None:
    repo = make_worker_repo(tmp_path)
    target_file = repo / "target.md"
    target_file.write_text("safe content\n", encoding="utf-8")
    outside_artifact_root = REPO_ROOT.parent / f"outside-reviews-{uuid.uuid4().hex}"

    try:
        result = run_worker(
            "--mode",
            "review",
            "--file",
            "target.md",
            "--artifact-root",
            str(outside_artifact_root),
            "--dry-run",
            "--json",
            cwd=repo,
        )
    finally:
        shutil.rmtree(outside_artifact_root, ignore_errors=True)

    assert result.returncode == 2
    assert (
        "artifact root must stay inside repository or system temp directory"
        in result.stderr
    )


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
