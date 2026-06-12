"""Subprocess boundary for the external Hurl binary."""

import os
import re
import shutil
import subprocess  # nosec B404
import tempfile
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from entroping.models.secrets import REDACTED, redact_secret_like_values

_DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024
_TRUNCATION_TEMPLATE = "\n[entroping: {stream_name} truncated]\n"
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VERSION_RE = re.compile(r"\b(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?\b")
_VERSION_TIMEOUT_SECONDS = 2.0
_VERSION_OUTPUT_LIMIT_BYTES = 4 * 1024
HURL_MINIMUM_SUPPORTED_VERSION = (4, 3, 0)
HURL_MINIMUM_SUPPORTED_VERSION_TEXT = "4.3.0"

HurlRunStatus = Literal["passed", "failed", "timeout", "error", "blocked"]


@dataclass(frozen=True)
class HurlBinaryStatus:
    """Resolved availability of the Hurl executable."""

    available: bool
    path: str | None
    version_checked: bool = False
    version: str | None = None
    version_parts: tuple[int, int, int] | None = None
    version_output: str | None = None
    version_error: str | None = None


class HurlRunnerError(RuntimeError):
    """Base class for deterministic Hurl runner failures."""


class HurlBinaryNotFoundError(HurlRunnerError):
    """Raised when the external Hurl binary cannot be found."""


@dataclass(frozen=True)
class HurlRunOptions:
    """Execution options for one or more Hurl files."""

    binary: str = "hurl"
    timeout_ms: int = 30_000
    retry: int = 0
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
        if self.retry < 0:
            msg = "Hurl retry count must not be negative"
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
class HurlAttemptEvidence:
    """Sanitized evidence for one bounded Hurl subprocess attempt."""

    attempt: int
    status: HurlRunStatus
    exit_code: int
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool


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
    timeout_ms: int = 0
    attempts: tuple[HurlAttemptEvidence, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether Hurl reported success."""

        return self.status == "passed" and self.exit_code == 0

    @property
    def retry_count(self) -> int:
        """Return how many retry attempts were needed or exhausted."""

        return max(0, len(self.attempts) - 1)

    @property
    def unstable(self) -> bool:
        """Return whether attempts changed status or exit code during retry."""

        observed = {(attempt.status, attempt.exit_code) for attempt in self.attempts}
        return len(observed) > 1


@dataclass(frozen=True)
class HurlSuiteResult:
    """Aggregated result for a deterministic Hurl run."""

    results: tuple[HurlFileResult, ...]
    selected_count: int | None = None
    fail_fast: bool = False

    @property
    def total(self) -> int:
        """Return number of executed files."""

        return len(self.results)

    @property
    def not_scheduled(self) -> int:
        """Return selected files that were not scheduled after fail-fast stopped."""

        selected = self.selected_count if self.selected_count is not None else self.total
        return max(0, selected - self.total)

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

    try:
        resolved = _resolve_hurl_binary(binary)
    except HurlBinaryNotFoundError:
        return HurlBinaryStatus(available=False, path=None)
    if not _should_check_hurl_version(binary, resolved):
        return HurlBinaryStatus(available=True, path=resolved)
    version, version_parts, version_output, version_error = _read_hurl_version(resolved)
    return HurlBinaryStatus(
        available=True,
        path=resolved,
        version_checked=True,
        version=version,
        version_parts=version_parts,
        version_output=version_output,
        version_error=version_error,
    )


def run_hurl_files(
    paths: Sequence[Path],
    options: HurlRunOptions | None = None,
    *,
    max_workers: int = 1,
    fail_fast: bool = False,
) -> HurlSuiteResult:
    """Run Hurl once per file and aggregate deterministic results."""

    if max_workers <= 0:
        msg = "Hurl worker count must be greater than zero"
        raise ValueError(msg)

    run_options = options or HurlRunOptions()
    if fail_fast:
        return _run_hurl_files_fail_fast(paths, run_options, max_workers=max_workers)
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


def _run_hurl_files_fail_fast(
    paths: Sequence[Path],
    options: HurlRunOptions,
    *,
    max_workers: int,
) -> HurlSuiteResult:
    selected_count = len(paths)
    if max_workers == 1 or len(paths) <= 1:
        results: list[HurlFileResult] = []
        for path in paths:
            result = run_hurl_file(path, options)
            results.append(result)
            if not result.passed:
                break
        return HurlSuiteResult(
            results=tuple(results),
            selected_count=selected_count,
            fail_fast=True,
        )

    ordered_results: list[HurlFileResult | None] = [None] * selected_count
    bounded_workers = min(max_workers, selected_count)
    next_index = 0
    stop_scheduling = False
    with ThreadPoolExecutor(
        max_workers=bounded_workers,
        thread_name_prefix="entroping-hurl",
    ) as executor:
        futures: dict[Future[HurlFileResult], int] = {}
        next_index = _schedule_hurl_workers(
            executor=executor,
            futures=futures,
            paths=paths,
            options=options,
            next_index=next_index,
            max_in_flight=bounded_workers,
        )
        while futures:
            done, _pending = wait(futures, return_when=FIRST_COMPLETED)
            for future in sorted(done, key=lambda item: futures[item]):
                index = futures.pop(future)
                result = future.result()
                ordered_results[index] = result
                if not result.passed:
                    stop_scheduling = True
            if not stop_scheduling:
                next_index = _schedule_hurl_workers(
                    executor=executor,
                    futures=futures,
                    paths=paths,
                    options=options,
                    next_index=next_index,
                    max_in_flight=bounded_workers,
                )

    executed_results = tuple(result for result in ordered_results if result is not None)
    return HurlSuiteResult(
        results=executed_results,
        selected_count=selected_count,
        fail_fast=True,
    )


def _schedule_hurl_workers(
    *,
    executor: ThreadPoolExecutor,
    futures: dict[Future[HurlFileResult], int],
    paths: Sequence[Path],
    options: HurlRunOptions,
    next_index: int,
    max_in_flight: int,
) -> int:
    while next_index < len(paths) and len(futures) < max_in_flight:
        futures[executor.submit(run_hurl_file, paths[next_index], options)] = next_index
        next_index += 1
    return next_index


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

    total_start = time.perf_counter()
    attempts: list[HurlAttemptEvidence] = []
    final_status: HurlRunStatus = "error"
    final_exit_code = 126
    final_stdout = ""
    final_stderr = ""
    final_stdout_truncated = False
    final_stderr_truncated = False

    try:
        for attempt_number in range(1, run_options.retry + 2):
            attempt_start = time.perf_counter()
            (
                final_status,
                final_exit_code,
                final_stdout,
                final_stderr,
                final_stdout_truncated,
                final_stderr_truncated,
            ) = _run_hurl_attempt(
                command=command,
                subprocess_env=subprocess_env,
                options=run_options,
            )
            attempts.append(
                HurlAttemptEvidence(
                    attempt=attempt_number,
                    status=final_status,
                    exit_code=final_exit_code,
                    duration_ms=max(0, int((time.perf_counter() - attempt_start) * 1000)),
                    stdout_truncated=final_stdout_truncated,
                    stderr_truncated=final_stderr_truncated,
                )
            )
            if final_status == "passed":
                break
    finally:
        if variables_file is not None:
            variables_file.unlink(missing_ok=True)

    return HurlFileResult(
        path=hurl_path,
        command=command,
        status=final_status,
        exit_code=final_exit_code,
        stdout=final_stdout,
        stderr=final_stderr,
        stdout_truncated=final_stdout_truncated,
        stderr_truncated=final_stderr_truncated,
        duration_ms=max(0, int((time.perf_counter() - total_start) * 1000)),
        timeout_ms=run_options.timeout_ms,
        attempts=tuple(attempts),
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


def _run_hurl_attempt(
    *,
    command: tuple[str, ...],
    subprocess_env: dict[str, str],
    options: HurlRunOptions,
) -> tuple[HurlRunStatus, int, str, str, bool, bool]:
    status: HurlRunStatus = "error"
    exit_code = 126
    extra_stderr = ""

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
                timeout=options.timeout_seconds,
                check=False,
                env=subprocess_env,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            status = "timeout"
            exit_code = 124
            extra_stderr = f"Hurl subprocess timed out after {options.timeout_ms} ms"
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
            limit_bytes=options.output_limit_bytes,
            redacted_values=_redaction_values(options),
        )
        stderr, stderr_truncated = _read_process_output(
            stderr_file,
            stream_name="stderr",
            limit_bytes=options.output_limit_bytes,
            redacted_values=_redaction_values(options),
        )

    if extra_stderr:
        stderr = f"{stderr}\n{extra_stderr}" if stderr else extra_stderr
    return status, exit_code, stdout, stderr, stdout_truncated, stderr_truncated


def redact_hurl_output(text: str, extra_secret_values: Sequence[str] = ()) -> str:
    """Redact sensitive values from captured Hurl output."""

    redacted = redact_secret_like_values(text)
    for secret_value in extra_secret_values:
        if secret_value:
            redacted = redacted.replace(secret_value, REDACTED)
    return redacted


def _resolve_hurl_binary(binary: str) -> str:
    selector = binary.strip()
    if _is_path_like_binary_selector(selector):
        return _resolve_explicit_hurl_binary_path(selector)

    resolved = shutil.which(selector)
    if resolved is None:
        msg = f"Hurl binary not found: {selector}"
        raise HurlBinaryNotFoundError(msg)
    return resolved


def _is_path_like_binary_selector(binary: str) -> bool:
    return any(separator is not None and separator in binary for separator in (os.sep, os.altsep))


def _resolve_explicit_hurl_binary_path(binary: str) -> str:
    expanded = Path(binary).expanduser()
    if not expanded.is_absolute():
        msg = "Hurl binary path must be absolute when a path is provided"
        raise ValueError(msg)

    resolved = expanded.resolve()
    if not resolved.is_file():
        msg = f"Hurl binary not found: {binary}"
        raise HurlBinaryNotFoundError(msg)
    if not os.access(resolved, os.X_OK):
        msg = f"Hurl binary is not executable: {resolved}"
        raise HurlBinaryNotFoundError(msg)
    return str(resolved)


def _should_check_hurl_version(binary: str, resolved: str) -> bool:
    selector = binary.strip()
    if selector == "hurl":
        return True
    return _is_path_like_binary_selector(selector) and Path(resolved).name == "hurl"


def _minimal_subprocess_env(binary_path: str) -> dict[str, str]:
    path_entries = [
        str(Path(binary_path).resolve().parent),
        "/usr/bin",
        "/bin",
    ]
    return {"PATH": ":".join(dict.fromkeys(path_entries))}


def _read_hurl_version(
    binary_path: str,
) -> tuple[str | None, tuple[int, int, int] | None, str | None, str | None]:
    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_file,
        tempfile.TemporaryFile(mode="w+b") as stderr_file,
    ):
        try:
            completed = subprocess.run(  # nosec B603
                [binary_path, "--version"],
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=_VERSION_TIMEOUT_SECONDS,
                check=False,
                env=_minimal_subprocess_env(binary_path),
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return None, None, None, "hurl --version timed out after 2 seconds"
        except OSError as exc:
            return None, None, None, f"hurl --version failed: {exc}"

        stdout, _stdout_truncated = _read_process_output(
            stdout_file,
            stream_name="stdout",
            limit_bytes=_VERSION_OUTPUT_LIMIT_BYTES,
            redacted_values=(),
        )
        stderr, _stderr_truncated = _read_process_output(
            stderr_file,
            stream_name="stderr",
            limit_bytes=_VERSION_OUTPUT_LIMIT_BYTES,
            redacted_values=(),
        )

    combined_output = _version_output_summary(stdout, stderr)
    if completed.returncode != 0:
        detail = f": {combined_output}" if combined_output else ""
        return None, None, combined_output or None, (
            f"hurl --version exited with code {completed.returncode}{detail}"
        )

    version_parts = _parse_version_parts(combined_output)
    if version_parts is None:
        return None, None, combined_output or None, None
    return _format_version(version_parts), version_parts, combined_output or None, None


def _version_output_summary(stdout: str, stderr: str) -> str:
    combined = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    first_line = combined.splitlines()[0].strip() if combined else ""
    return first_line[:256]


def _parse_version_parts(text: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    patch = match.group("patch")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(patch) if patch is not None else 0,
    )


def _format_version(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]}.{version[2]}"


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
