"""Shared fixtures for deterministic report-writer boundary tests."""

from pathlib import Path

from entroping.bridge.policy_to_hurl import HurlGateAssertion
from entroping.core.gate_injector import AppliedKnownFailure, HurlExecutionCopy
from entroping.core.hurl_runner import HurlFileResult, HurlSuiteResult


def _execution_copy(
    source: Path,
    execution: Path,
    known_failures: tuple[AppliedKnownFailure, ...] = (),
    operation_id: str | None = None,
    source_kind: str | None = None,
    negative_category: str | None = None,
    severity: str | None = None,
    auth_flow: str | None = None,
    auth_requires: tuple[str, ...] = (),
    auth_produces: tuple[str, ...] = (),
) -> HurlExecutionCopy:
    return HurlExecutionCopy(
        source_path=source,
        execution_path=execution,
        injected_gates=(
            HurlGateAssertion(
                rule_id="global_latency",
                assertion="duration < 2000",
                enforcement="block",
                condition="true",
            ),
        ),
        known_failures=known_failures,
        operation_id=operation_id,
        source=source_kind,
        negative_category=negative_category,
        severity=severity,
        auth_flow=auth_flow,
        auth_requires=auth_requires,
        auth_produces=auth_produces,
    )


def _suite_result(execution: Path, stderr: str) -> HurlSuiteResult:
    return HurlSuiteResult(
        results=(
            HurlFileResult(
                path=execution,
                command=("/bin/hurl", str(execution)),
                status="failed",
                exit_code=1,
                stdout="Authorization: Bearer live-secret\n",
                stderr=stderr,
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=123,
                timeout_ms=2500,
            ),
        ),
    )
