"""Pure report models for deterministic Entroping runs."""

from dataclasses import dataclass


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

    @property
    def passed(self) -> bool:
        """Return whether this test passed."""

        return self.status == "passed" and self.exit_code == 0


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
