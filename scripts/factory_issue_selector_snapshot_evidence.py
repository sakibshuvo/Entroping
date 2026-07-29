from __future__ import annotations

from scripts.factory_issue_selector_models import UserEvidence

_WARNINGS = frozenset(
    {
        "user-evidence-invalid",
        "user-evidence-label-mismatch",
        "user-evidence-label-missing",
    }
)


class CachedEvidenceError(ValueError):
    pass


def validate_cached_evidence(
    evidence: UserEvidence, *, labels: tuple[str, ...]
) -> UserEvidence:
    label_present = "evidence:user-verified" in labels
    invalid = evidence.warning not in _WARNINGS | {None}
    if not evidence.valid:
        invalid = invalid or evidence.verified or evidence.severity is not None
        invalid = invalid or (
            evidence.warning == "user-evidence-label-mismatch" and not label_present
        )
    elif evidence.severity is None:
        invalid = True
    elif evidence.verified:
        invalid = invalid or evidence.warning is not None or not label_present
    else:
        allowed_warnings = (
            {"user-evidence-label-mismatch"}
            if label_present
            else {None, "user-evidence-label-missing"}
        )
        invalid = invalid or evidence.warning not in allowed_warnings
    if invalid:
        raise CachedEvidenceError("cached evidence state is invalid")
    return evidence
