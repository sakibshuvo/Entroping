import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    not hasattr(os, "O_NONBLOCK"),
    reason="nonblocking filesystem flags are unavailable",
)
def test_best_effort_reader_rejects_fifo_without_blocking(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.fifo"
    os.mkfifo(path)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from entroping.core.evidence_common import "
                "read_local_evidence_artifact_bytes_best_effort; "
                "print(read_local_evidence_artifact_bytes_best_effort(Path(__import__('sys').argv[1])))"
            ),
            str(path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )

    assert result.returncode == 0, result.stderr
    assert "not a file" in result.stdout
