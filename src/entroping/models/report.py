"""Pure report models for deterministic Entroping runs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseHeader:
    """One normalized response header selected for drift comparison."""

    name: str
    value: str


@dataclass(frozen=True)
class ResponseSnapshot:
    """Sanitized response fingerprint for drift checks."""

    status_code: int | None
    headers: tuple[ResponseHeader, ...]
    body_shape: tuple[str, ...]


@dataclass(frozen=True)
class RunTestReport:
    """Report row for one source Hurl test."""

    path: str
    execution_path: str
    status: str
    exit_code: int
    duration_ms: int
    rule_ids: tuple[str, ...]
    stdout: str
    stderr: str
    response_status_code: int | None = None
    response_headers: tuple[tuple[str, str], ...] = ()
    response_body_shape: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether this test passed."""

        return self.status == "passed" and self.exit_code == 0

    @property
    def response(self) -> ResponseSnapshot | None:
        """Return the structured response fingerprint when one is available."""

        if (
            self.response_status_code is None
            and not self.response_headers
            and not self.response_body_shape
        ):
            return None
        return ResponseSnapshot(
            status_code=self.response_status_code,
            headers=tuple(
                ResponseHeader(name=name, value=value) for name, value in self.response_headers
            ),
            body_shape=self.response_body_shape,
        )


@dataclass(frozen=True)
class RunReportSummary:
    """Aggregate report summary."""

    total: int
    passed: int
    failed: int
    exit_code: int


@dataclass(frozen=True)
class RunReport:
    """Serializable deterministic run report."""

    project: str
    environment: str
    generated_at: str
    summary: RunReportSummary
    tests: tuple[RunTestReport, ...]
