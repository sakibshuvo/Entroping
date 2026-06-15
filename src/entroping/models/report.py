"""Pure report models for deterministic Entroping runs."""

from dataclasses import dataclass, field


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
class KnownFailureEvidence:
    """Known-failure exception applied during deterministic gate injection."""

    test: str
    rule_id: str
    issue_id: str
    expires: str
    reason: str


@dataclass(frozen=True)
class RunAttemptEvidence:
    """Report-safe evidence for one Hurl execution attempt."""

    attempt: int
    status: str
    exit_code: int
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool


@dataclass(frozen=True)
class RunRetryEvidence:
    """Bounded retry evidence for one run-report test row."""

    retry_count: int = 0
    unstable: bool = False
    attempts: tuple[RunAttemptEvidence, ...] = ()


@dataclass(frozen=True)
class RunSafetyEvidence:
    """Protected-run safety evidence for one selected Hurl test."""

    protected_environment: bool
    safety: str | None
    safety_source: str | None
    methods: tuple[str, ...]
    blocked_reason: str | None


@dataclass(frozen=True)
class RunAuthEvidence:
    """Value-free auth-chain evidence for one selected Hurl test."""

    flow: str | None = None
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()


def build_run_auth_evidence(
    *,
    flow: str | None,
    requires: tuple[str, ...],
    produces: tuple[str, ...],
) -> RunAuthEvidence | None:
    """Return report-safe auth evidence only when a test declares auth metadata."""

    if flow is None and not requires and not produces:
        return None
    return RunAuthEvidence(flow=flow, requires=requires, produces=produces)


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
    timeout_ms: int = 0
    operation_id: str | None = None
    source: str | None = None
    negative_category: str | None = None
    severity: str | None = None
    response_status_code: int | None = None
    response_headers: tuple[tuple[str, str], ...] = ()
    response_body_shape: tuple[str, ...] = ()
    known_failures: tuple[KnownFailureEvidence, ...] = ()
    retry: RunRetryEvidence = field(default_factory=RunRetryEvidence)
    safety: RunSafetyEvidence | None = None
    auth: RunAuthEvidence | None = None

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
    selected: int | None = None
    executed: int | None = None
    not_scheduled: int = 0
    fail_fast: bool = False

    @property
    def selected_count(self) -> int:
        """Return selected tests, defaulting to executed total for old reports."""

        total = _non_negative_count(self.total)
        return total if self.selected is None else _non_negative_count(self.selected, default=total)

    @property
    def executed_count(self) -> int:
        """Return executed tests, defaulting to total for old reports."""

        total = _non_negative_count(self.total)
        return total if self.executed is None else _non_negative_count(self.executed, default=total)

    @property
    def not_scheduled_count(self) -> int:
        """Return selected tests that did not produce a report row."""

        selected_gap = max(0, self.selected_count - self.executed_count)
        return max(_non_negative_count(self.not_scheduled), selected_gap)

    @property
    def has_scheduling_evidence(self) -> bool:
        """Return whether suite scheduling fields add evidence beyond totals."""

        return self.fail_fast or self.not_scheduled_count > 0


@dataclass(frozen=True)
class RunReport:
    """Serializable deterministic run report."""

    project: str
    environment: str
    generated_at: str
    summary: RunReportSummary
    tests: tuple[RunTestReport, ...]


def _non_negative_count(value: object, *, default: int = 0) -> int:
    if type(value) is int and value >= 0:
        return value
    return default
