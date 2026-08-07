"""Bounded subprocess tests for aggregate finish evidence."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import finish_issue_aggregate_support as subject


@pytest.mark.parametrize("stream", ("stdout", "stderr"))
def test_run_rejects_oversized_output_without_leaking_payload(
    stream: str,
) -> None:
    marker = "attacker-output-marker"
    code = (
        "import sys; "
        f"getattr(sys, '{stream}').write(({marker!r} + 'x' * 200000)); "
        f"getattr(sys, '{stream}').flush()"
    )

    with pytest.raises(subject.AggregateEvidenceError) as error:
        subject.run([sys.executable, "-c", code], 1024)

    assert str(error.value) == "bounded evidence command exceeded output limit"
    assert marker not in str(error.value)


def test_run_terminates_timed_out_command_without_leaking_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "_COMMAND_TIMEOUT_SECONDS", 0.05)
    marker = "attacker-timeout-marker"
    code = (
        "import sys,time; "
        f"sys.stderr.write({marker!r}); sys.stderr.flush(); time.sleep(1)"
    )

    with pytest.raises(subject.AggregateEvidenceError) as error:
        subject.run([sys.executable, "-c", code], 1024)

    assert str(error.value) == "bounded evidence command timed out"
    assert marker not in str(error.value)


def test_patch_id_uses_bounded_bytes_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    setup_commands: tuple[tuple[str, ...], ...] = (
        ("init", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test User"),
    )
    for command in setup_commands:
        result = subprocess.run(
            ["git", *command], cwd=repo, check=False, capture_output=True
        )
        assert result.returncode == 0, result.stderr
    (repo / "README.md").write_text("bounded\n", encoding="utf-8")
    for command in (("add", "README.md"), ("commit", "-m", "bounded")):
        result = subprocess.run(
            ["git", *command], cwd=repo, check=False, capture_output=True
        )
        assert result.returncode == 0, result.stderr
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    value = subject.patch_id(repo, head)

    assert len(value) == 40
