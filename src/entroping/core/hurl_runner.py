"""Subprocess boundary for the external Hurl binary."""

import re
import shutil
import subprocess  # nosec B404
import tempfile
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

_DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024
_TRUNCATION_TEMPLATE = "\n[entroping: {stream_name} truncated]\n"
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b("
    r"authorization|cookie|set-cookie|x-api-key|api-key|access-token|refresh-token|"
    r"access_token|refresh_token|api_key|token|password|secret"
    r")(\s*[:=]\s*)([^\r\n;&\s]+(?:\s+[^\r\n;&\s]+)?)"
)
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

HurlRunStatus = Literal["passed", "failed", "timeout", "error"]


@dataclass(frozen=True)
class HurlBinaryStatus:
    """Resolved availability of the Hurl executable."""

    available: bool
    path: str | None


class HurlRunnerError(RuntimeError):
    """Base class for deterministic Hurl runner failures."""


class HurlBinaryNotFoundError(HurlRunnerError):
    """Raised when the external Hurl binary cannot be found."""


@dataclass(frozen=True)
class HurlRunOptions:
    """Execution options for one or more Hurl files."""

    binary: str = "hurl"
    timeout_ms: int = 30_000
    output_limit_bytes: int = _DEFAULT_OUTPUT_LIMIT_BYTES
    redacted_values: tuple[str, ...] = ()
    variables: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.binary.strip() == "":
            msg = "Hurl binary must not be empty"
            raise ValueError(msg)
        if self.timeout_ms <= 0:
            msg = "Hurl timeout must be greater than zero"
            raise ValueError(msg)
        if self.output_limit_bytes <= 0:
            msg = "Hurl output limit must be greater than zero"
            raise ValueError(msg)
        _validate_variables(self.variables or {})

    @property
    def timeout_seconds(self) -> float:
        """Return subprocess timeout in seconds."""

        return self.timeout_ms / 1000


@dataclass(frozen=True)
class HurlFileResult:
    """Result of one Hurl file subprocess execution."""

    path: Path
    command: tuple[str, ...]
    status: HurlRunStatus
    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    duration_ms: int

    @property
    def passed(self) -> bool:
        """Return whether Hurl reported success."""

        return self.status == "passed" and self.exit_code == 0


@dataclass(frozen=True)
class HurlSuiteResult:
    """Aggregated result for a deterministic Hurl run."""

    results: tuple[HurlFileResult, ...]

    @property
    def total(self) -> int:
        """Return number of executed files."""

        return len(self.results)

    @property
    def passed(self) -> int:
        """Return count of passing Hurl files."""

        return sum(1 for result in self.results if result.passed)

    @property
    def failed(self) -> int:
        """Return count of non-passing Hurl files."""

        return self.total - self.passed

    @property
    def exit_code(self) -> int:
        """Return deterministic process exit code for the suite."""

        return 0 if self.failed == 0 else 1


def discover_hurl(binary: str = "hurl") -> HurlBinaryStatus:
    """Find the Hurl binary without executing HTTP requests."""

    resolved = shutil.which(binary)
    return HurlBinaryStatus(available=resolved is not None, path=resolved)


def run_hurl_files(
    paths: Sequence[Path],
    options: HurlRunOptions | None = None,
    *,
    max_workers: int = 1,
) -> HurlSuiteResult:
    """Run Hurl once per file and aggregate deterministic results."""

    if max_workers <= 0:
        msg = "Hurl worker count must be greater than zero"
        raise ValueError(msg)

    run_options = options or HurlRunOptions()
    if max_workers == 1 or len(paths) <= 1:
        results = tuple(run_hurl_file(path, run_options) for path in paths)
        return HurlSuiteResult(results=results)

    ordered_results: list[HurlFileResult | None] = [None] * len(paths)
    bounded_workers = min(max_workers, len(paths))
    with ThreadPoolExecutor(
        max_workers=bounded_workers,
        thread_name_prefix="entroping-hurl",
    ) as executor:
        futures: dict[Future[HurlFileResult], int] = {
            executor.submit(run_hurl_file, path, run_options): index
            for index, path in enumerate(paths)
        }
        for future in as_completed(futures):
            ordered_results[futures[future]] = future.result()

    results_list: list[HurlFileResult] = []
    for result in ordered_results:
        if result is None:
            msg = "Hurl worker did not produce a result"
            raise HurlRunnerError(msg)
        results_list.append(result)
    results = tuple(results_list)
    return HurlSuiteResult(results=results)


def run_hurl_file(
    path: Path,
    options: HurlRunOptions | None = None,
) -> HurlFileResult:
    """Execute one Hurl file through the external binary."""

    run_options = options or HurlRunOptions()
    hurl_path = validate_hurl_path(path)
    binary_path = _resolve_hurl_binary(run_options.binary)
    variables_file = _write_variables_file(run_options.variables or {})
    command = (binary_path, *_variables_file_args(variables_file), str(hurl_path))
    subprocess_env = _minimal_subprocess_env(binary_path)

    start = time.perf_counter()
    status: HurlRunStatus = "error"
    exit_code = 126
    extra_stderr = ""

    try:
        with (
            tempfile.TemporaryFile(mode="w+b") as stdout_file,
            tempfile.TemporaryFile(mode="w+b") as stderr_file,
        ):
            try:
                # Uses a resolved binary, argument array, timeout, and shell=False.
                completed = subprocess.run(  # nosec B603
                    list(command),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=run_options.timeout_seconds,
                    check=False,
                    env=subprocess_env,
                    shell=False,
                )
            except subprocess.TimeoutExpired:
                status = "timeout"
                exit_code = 124
            except OSError as exc:
                status = "error"
                exit_code = 126
                extra_stderr = f"Hurl subprocess failed: {exc}"
            else:
                exit_code = completed.returncode
                status = "passed" if completed.returncode == 0 else "failed"

            stdout, stdout_truncated = _read_process_output(
                stdout_file,
                stream_name="stdout",
                limit_bytes=run_options.output_limit_bytes,
                redacted_values=_redaction_values(run_options),
            )
            stderr, stderr_truncated = _read_process_output(
                stderr_file,
                stream_name="stderr",
                limit_bytes=run_options.output_limit_bytes,
                redacted_values=_redaction_values(run_options),
            )
    finally:
        if variables_file is not None:
            variables_file.unlink(missing_ok=True)

    if extra_stderr:
        stderr = f"{stderr}\n{extra_stderr}" if stderr else extra_stderr

    return HurlFileResult(
        path=hurl_path,
        command=command,
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        duration_ms=max(0, int((time.perf_counter() - start) * 1000)),
    )


def validate_hurl_path(path: Path) -> Path:
    """Resolve a Hurl file path and reject non-Hurl inputs."""

    expanded = path.expanduser()
    if expanded.is_symlink():
        msg = f"Refusing to execute symlinked Hurl file: {expanded}"
        raise ValueError(msg)

    resolved = expanded.resolve()
    if resolved.suffix != ".hurl":
        msg = f"Expected a .hurl file, got: {resolved}"
        raise ValueError(msg)
    if not resolved.is_file():
        msg = f"Hurl file not found: {resolved}"
        raise ValueError(msg)
    return resolved


def redact_hurl_output(text: str, extra_secret_values: Sequence[str] = ()) -> str:
    """Redact sensitive values from captured Hurl output."""

    redacted = _KEY_VALUE_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    for secret_value in extra_secret_values:
        if secret_value:
            redacted = redacted.replace(secret_value, "[REDACTED]")
    return redacted


def _resolve_hurl_binary(binary: str) -> str:
    resolved = shutil.which(binary)
    if resolved is None:
        msg = f"Hurl binary not found: {binary}"
        raise HurlBinaryNotFoundError(msg)
    return resolved


def _minimal_subprocess_env(binary_path: str) -> dict[str, str]:
    path_entries = [
        str(Path(binary_path).resolve().parent),
        "/usr/bin",
        "/bin",
    ]
    return {"PATH": ":".join(dict.fromkeys(path_entries))}


def _variables_file_args(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    return ("--variables-file", str(path))


def _write_variables_file(variables: Mapping[str, str]) -> Path | None:
    if not variables:
        return None

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="entroping-hurl-vars-",
        suffix=".env",
        delete=False,
    ) as handle:
        for key in sorted(variables):
            handle.write(f"{key}={variables[key]}\n")
        return Path(handle.name)


def _validate_variables(variables: Mapping[str, str]) -> None:
    for key, value in variables.items():
        if _VARIABLE_NAME_RE.fullmatch(key) is None:
            msg = f"Invalid Hurl variable name: {key!r}"
            raise ValueError(msg)
        if "\n" in value or "\r" in value:
            msg = f"Hurl variable {key!r} must be single-line"
            raise ValueError(msg)


def _redaction_values(options: HurlRunOptions) -> tuple[str, ...]:
    variable_values = tuple((options.variables or {}).values())
    return (*options.redacted_values, *variable_values)


def _read_process_output(
    handle: BinaryIO,
    *,
    stream_name: Literal["stdout", "stderr"],
    limit_bytes: int,
    redacted_values: Sequence[str],
) -> tuple[str, bool]:
    handle.seek(0)
    raw_bytes = handle.read(limit_bytes + 1)
    truncated = len(raw_bytes) > limit_bytes
    if truncated:
        raw_bytes = raw_bytes[:limit_bytes]

    text = raw_bytes.decode("utf-8", errors="replace")
    text = redact_hurl_output(text, redacted_values)
    if truncated:
        text += _TRUNCATION_TEMPLATE.format(stream_name=stream_name)
    return text, truncated
