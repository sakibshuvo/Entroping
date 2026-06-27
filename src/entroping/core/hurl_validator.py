"""Parser-backed validation for generated Hurl content."""

import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path

from entroping.core.hurl_runner import _minimal_subprocess_env


class HurlValidationError(ValueError):
    """Raised when generated Hurl content fails parser-backed validation."""


def validate_hurl_content(
    content: str,
    display_path: str,
    *,
    binary: str = "hurlfmt",
    timeout_ms: int = 5_000,
) -> None:
    """Validate generated Hurl through the external Hurl formatter/parser."""

    binary_path = shutil.which(binary)
    if binary_path is None:
        msg = f"Hurl validation binary not found: {binary}"
        raise HurlValidationError(msg)

    with tempfile.TemporaryDirectory(prefix="entroping-hurl-validate-") as temp_dir:
        candidate_path = Path(temp_dir) / "candidate.hurl"
        candidate_path.write_text(content, encoding="utf-8")
        try:
            with (
                tempfile.TemporaryFile(mode="w+b") as stdout_file,
                tempfile.TemporaryFile(mode="w+b") as stderr_file,
            ):
                completed = subprocess.run(  # nosec B603
                    [binary_path, "--out", "json", str(candidate_path)],
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=timeout_ms / 1000,
                    check=False,
                    env=_minimal_subprocess_env(binary_path),
                    shell=False,
                )
        except subprocess.TimeoutExpired as exc:
            msg = f"Generated Hurl parser validation timed out: {display_path}"
            raise HurlValidationError(msg) from exc
        except OSError as exc:
            msg = f"Hurl validation subprocess failed for {display_path}: {exc}"
            raise HurlValidationError(msg) from exc

        if completed.returncode != 0:
            msg = f"Generated Hurl failed parser validation: {display_path}"
            raise HurlValidationError(msg)
