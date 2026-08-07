from __future__ import annotations

import sys
from pathlib import Path

from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bounded_process import BoundedProcessResult  # noqa: E402
from scripts.factory_status import collect_factory_status  # noqa: E402


def test_status_root_discovery_uses_only_the_bounded_read_only_git_contract(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Status root discovery pins Git argv, environment, timeout, and output bound."""

    (tmp_path / ".git").mkdir()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def run(command: list[object], **kwargs: object) -> BoundedProcessResult:
        calls.append((tuple(command), kwargs))
        return BoundedProcessResult(
            args=tuple(str(item) for item in command),
            returncode=0,
            stdout=f"{tmp_path}\n{tmp_path / '.git'}\n",
            stderr="",
            timed_out=False,
            output_limit_exceeded=False,
        )

    monkeypatch.setattr("scripts.factory_scheduler_root.run_bounded_process", run)

    _ = collect_factory_status(tmp_path)

    assert calls == [
        (
            (
                Path("/usr/bin/git"),
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                "--git-common-dir",
            ),
            {
                "cwd": tmp_path,
                "timeout_seconds": 5.0,
                "max_output_bytes": 4096,
                "env": {"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            },
        )
    ]
