"""Shared helpers for report command submodules."""


def _gate_coverage_percent(*, matched_gates: int, total_gates: int) -> float:
    if total_gates <= 0:
        return 0.0
    return (matched_gates / total_gates) * 100


def _format_percent(value: float) -> str:
    if value.is_integer():
        return f"{int(value)}%"
    return f"{value:.1f}%"
