"""Core loaders for effective policy diff reports."""

from pathlib import Path
from typing import Literal

from entroping.bridge.effective_policy import EffectivePolicyReport

EffectivePolicyDiffOutput = Literal["md", "json"]


class EffectivePolicyDiffReportError(ValueError):
    """Raised when effective policy diff inputs cannot be loaded."""


def load_effective_policy_report(path: Path) -> EffectivePolicyReport:
    """Load a checked-in effective policy report artifact."""

    try:
        content = path.expanduser().read_text(encoding="utf-8")
        return EffectivePolicyReport.model_validate_json(content)
    except (OSError, ValueError) as exc:
        msg = f"Could not read effective policy report {path}: {exc}"
        raise EffectivePolicyDiffReportError(msg) from exc
