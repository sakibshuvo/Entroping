from __future__ import annotations

import inspect
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_issue_selector_core import select_issue  # noqa: E402
from scripts.factory_issue_selector_models import (  # noqa: E402
    ActiveState,
    JsonObject,
    SelectionResult,
    SnapshotMetadata,
    UserEvidence,
)
from scripts.factory_issue_selector_parser import (  # noqa: E402
    normalize_scope,
    parse_issue,
    scopes_overlap,
)

AS_OF = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
NO_ISSUES = frozenset[int]()


def _body(
    *,
    lane: str = "normal-code",
    allowed_files: tuple[str, ...] = ("scripts/example.py",),
    dependencies: tuple[int, ...] = (),
    evidence: str = "",
) -> str:
    allowed = "\n".join(f"- {path}" for path in allowed_files)
    blocked = (
        "\n\n## Dependencies\n\nBlocked by "
        + " and ".join(f"#{number}" for number in dependencies)
        + "."
        if dependencies
        else ""
    )
    return (
        "## Outcome\n\nShip one bounded selector.\n\n"
        "## Scope\n\n- Read state.\n\n"
        "## Non-goals\n\n- No dispatch.\n\n"
        "## Acceptance criteria\n\n- Selection is deterministic.\n\n"
        f"## Verification\n\nVerification lane: `{lane}`.\n\n"
        "## Autonomy\n\nTier B assisted lane.\n\n"
        f"## Allowed files\n\n{allowed}"
        f"{blocked}{evidence}"
    )


def _raw_issue(
    number: int,
    *,
    state: str = "open",
    labels: tuple[str, ...] = (
        "type:feature",
        "priority:p1",
        "status:ready",
        "autonomy:tier-b",
    ),
    body: str | None = None,
    milestone: bool = True,
    assignees: int = 0,
) -> JsonObject:
    return {
        "number": number,
        "title": f"Issue {number}",
        "state": state,
        "html_url": f"https://github.com/sakibshuvo/Entroping/issues/{number}",
        "body": _body() if body is None else body,
        "labels": [{"name": label} for label in labels],
        "assignees": [{"login": f"owner-{index}"} for index in range(assignees)],
        "milestone": {"title": "Factory"} if milestone else None,
    }


def _metadata(*, complete: bool = True) -> SnapshotMetadata:
    return SnapshotMetadata(
        repo="sakibshuvo/Entroping",
        fetched_at=AS_OF - timedelta(seconds=10),
        expires_at=AS_OF + timedelta(seconds=50),
        complete=complete,
    )


def _active(
    *,
    complete: bool = True,
    owned: frozenset[int] = NO_ISSUES,
    scopes: tuple[str, ...] = (),
) -> ActiveState:
    return ActiveState(complete=complete, owned_issue_numbers=owned, occupied_scopes=scopes)


def test_selector_returns_stable_non_authorizing_selection() -> None:
    issue = parse_issue(_raw_issue(41))

    result = select_issue(
        issues=(issue,),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.status == "selected"
    assert result.paid_work_authorized is False
    assert result.selected is not None
    assert result.selected.issue_number == 41
    assert result.selected.verification_lane == "normal-code"
    payload = result.to_payload()
    assert payload["schema_version"] == "entroping.factory-issue-selection.v1"
    assert "body" not in repr(payload).lower()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"state": "closed"}, "issue-not-open"),
        ({"milestone": None}, "missing-milestone"),
        ({"labels": []}, "invalid-type-label"),
        (
            {
                "labels": [
                    {"name": "type:invented"},
                    {"name": "priority:p1"},
                    {"name": "status:ready"},
                    {"name": "autonomy:tier-b"},
                ]
            },
            "invalid-type-label",
        ),
        (
            {
                "labels": [
                    {"name": "type:feature"},
                    {"name": "priority:p1"},
                    {"name": "status:ready"},
                    {"name": "status:blocked"},
                    {"name": "autonomy:tier-b"},
                ]
            },
            "invalid-status-label",
        ),
        (
            {
                "labels": [
                    {"name": "type:feature"},
                    {"name": "priority:p1"},
                    {"name": "status:ready"},
                ]
            },
            "invalid-autonomy-label",
        ),
        ({"body": "## Outcome\n\nOnly one section."}, "missing-required-section"),
        ({"body": _body(allowed_files=())}, "ambiguous-file-scope"),
    ],
)
def test_selector_rejects_incomplete_issue_contract(
    mutation: JsonObject, reason: str
) -> None:
    raw = _raw_issue(42)
    raw.update(mutation)

    result = select_issue(
        issues=(parse_issue(raw),),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.selected is None
    assert reason in {rejection.reason for rejection in result.rejections}


def test_selector_rejects_open_or_missing_dependencies() -> None:
    candidate = parse_issue(_raw_issue(50, body=_body(dependencies=(48, 49))))
    closed_dependency = parse_issue(_raw_issue(48, state="closed"))

    result = select_issue(
        issues=(candidate, closed_dependency),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    reasons = [item.reason for item in result.rejections if item.issue_number == 50]
    assert reasons == ["unresolved-dependency"]


def test_selector_rejects_repeated_dependency_sections() -> None:
    body = _body(dependencies=(48,)) + "\n\n## Dependencies\n\nBlocked by #49."
    candidate = parse_issue(_raw_issue(50, body=body))
    closed_dependency = parse_issue(_raw_issue(48, state="closed"))

    result = select_issue(
        issues=(candidate, closed_dependency),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    reasons = [item.reason for item in result.rejections if item.issue_number == 50]
    assert "invalid-dependencies" in reasons


@pytest.mark.parametrize(
    "packet",
    (
        (
            "```yaml\n"
            "allowed_files:\n  - scripts/occupied.py\n"
            "allowed_files:\n  - scripts/safe.py\n"
            "```"
        ),
        (
            "```yaml\n"
            "allowed files:\n  - scripts/occupied.py\n"
            "allowed_files:\n  - scripts/safe.py\n"
            "```"
        ),
        (
            "```yaml\n"
            "<<: {allowed_files: [scripts/occupied.py]}\n"
            "allowed_files: [scripts/safe.py]\n"
            "```"
        ),
    ),
)
def test_selector_rejects_ambiguous_yaml_scope_packets(packet: str) -> None:
    issue = parse_issue(_raw_issue(50, body=f"{_body(allowed_files=())}\n\n{packet}"))

    result = select_issue(
        issues=(issue,),
        snapshot=_metadata(),
        active=_active(scopes=("scripts/occupied.py",)),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.selected is None
    assert "ambiguous-file-scope" in {
        rejection.reason for rejection in result.rejections
    }


@pytest.mark.parametrize(
    ("active", "reason"),
    [
        (_active(owned=frozenset({51})), "active-ownership"),
        (_active(scopes=("scripts/example.py",)), "overlapping-file-scope"),
        (_active(scopes=("scripts/**",)), "overlapping-file-scope"),
    ],
)
def test_selector_rejects_owned_or_overlapping_work(
    active: ActiveState, reason: str
) -> None:
    result = select_issue(
        issues=(parse_issue(_raw_issue(51)),),
        snapshot=_metadata(),
        active=active,
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.selected is None
    assert reason in {item.reason for item in result.rejections}


def test_selector_enforces_autonomy_ceiling() -> None:
    result = select_issue(
        issues=(parse_issue(_raw_issue(52)),),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-a",
    )

    assert result.selected is None
    assert result.rejections[0].reason == "autonomy-ceiling-exceeded"


def test_selector_fails_closed_for_stale_or_incomplete_state() -> None:
    issue = parse_issue(_raw_issue(53))

    stale = select_issue(
        issues=(issue,),
        snapshot=SnapshotMetadata(
            repo="sakibshuvo/Entroping",
            fetched_at=AS_OF - timedelta(minutes=2),
            expires_at=AS_OF - timedelta(minutes=1),
            complete=True,
        ),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )
    incomplete = select_issue(
        issues=(issue,),
        snapshot=_metadata(),
        active=_active(complete=False),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert stale.status == "blocked"
    assert stale.errors == ("snapshot-stale",)
    assert incomplete.errors == ("active-state-incomplete",)


def test_selector_prioritizes_p0_before_verified_user_blocker() -> None:
    receipt = "sha256:" + "a" * 64
    evidence = (
        "\n\n## User evidence\n\n```yaml\n"
        "user_evidence:\n"
        "  schema_version: entroping.user-evidence.v1\n"
        "  evidence_status: verified\n"
        "  affected_journey: first_run\n"
        "  severity: blocker\n"
        "  source_classification: design_partner\n"
        f"  verification_receipt: {receipt}\n"
        "```"
    )
    blocker = parse_issue(
        _raw_issue(
            60,
            labels=(
                "type:feature",
                "priority:p1",
                "status:ready",
                "autonomy:tier-b",
                "evidence:user-verified",
            ),
            body=_body(allowed_files=("scripts/blocker.py",), evidence=evidence),
        )
    )
    p0 = parse_issue(
        _raw_issue(
            61,
            labels=(
                "type:security",
                "priority:p0",
                "status:ready",
                "autonomy:tier-b",
            ),
            body=_body(allowed_files=("scripts/security.py",)),
        )
    )

    result = select_issue(
        issues=(blocker, p0),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.selected is not None
    assert result.selected.issue_number == 61


def test_selector_prioritizes_release_p0_before_verified_user_blocker() -> None:
    receipt = "sha256:" + "b" * 64
    evidence = (
        "\n\n## User evidence\n\n```yaml\n"
        "user_evidence:\n"
        "  schema_version: entroping.user-evidence.v1\n"
        "  evidence_status: verified\n"
        "  affected_journey: integrate\n"
        "  severity: blocker\n"
        "  source_classification: design_partner\n"
        f"  verification_receipt: {receipt}\n"
        "```"
    )
    blocker = parse_issue(
        _raw_issue(
            63,
            labels=(
                "type:feature",
                "priority:p1",
                "status:ready",
                "autonomy:tier-b",
                "evidence:user-verified",
            ),
            body=_body(allowed_files=("scripts/blocker.py",), evidence=evidence),
        )
    )
    release = parse_issue(
        _raw_issue(
            64,
            labels=(
                "type:regression",
                "priority:p0",
                "status:ready",
                "autonomy:tier-b",
                "area:release",
            ),
            body=_body(allowed_files=("scripts/release.py",)),
        )
    )

    result = select_issue(
        issues=(blocker, release),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.selected is not None
    assert result.selected.issue_number == 64


def test_malformed_evidence_loses_priority_but_remains_eligible() -> None:
    malformed = (
        "\n\n## User evidence\n\n```yaml\n"
        "user_evidence:\n  evidence_status: verified\n```"
    )
    issue = parse_issue(
        _raw_issue(
            62,
            labels=(
                "type:feature",
                "priority:p1",
                "status:ready",
                "autonomy:tier-b",
                "evidence:user-verified",
            ),
            body=_body(evidence=malformed),
        )
    )

    result = select_issue(
        issues=(issue,),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.selected is not None
    assert result.selected.bucket == "ordinary"
    assert result.warnings == ("issue-62:user-evidence-invalid",)


def test_invalid_in_memory_evidence_cannot_gain_priority() -> None:
    issue = parse_issue(_raw_issue(65))
    forged = replace(
        issue,
        evidence=UserEvidence(valid=False, verified=True, severity="blocker"),
    )

    result = select_issue(
        issues=(forged,),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.selected is not None
    assert result.selected.bucket == "ordinary"


def test_selector_output_is_deterministic_for_shuffled_input() -> None:
    issues = tuple(
        parse_issue(
            _raw_issue(number, body=_body(allowed_files=(f"scripts/{number}.py",)))
        )
        for number in (72, 70, 71)
    )
    forward = select_issue(
        issues=issues,
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    ).to_payload()
    reverse = select_issue(
        issues=tuple(reversed(issues)),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    ).to_payload()

    assert forward == reverse
    selected = forward["selected"]
    assert isinstance(selected, dict)
    assert selected["issue_number"] == 70


@pytest.mark.parametrize(
    "scope",
    ("scripts/**", "scripts/factory_issue_selector*.py", "src/*.py"),
)
def test_scope_parser_accepts_safe_file_families(scope: str) -> None:
    assert normalize_scope(scope) == scope
    assert scopes_overlap(scope, "scripts/factory_issue_selector_core.py") is (
        scope.startswith("scripts/")
    )


def test_scope_overlap_is_case_insensitive_for_portable_safety() -> None:
    assert scopes_overlap("Scripts/Selector.py", "scripts/selector.py") is True


def test_cyclic_user_evidence_fails_closed_without_crashing() -> None:
    evidence = (
        "\n\n## User evidence\n\n```yaml\n"
        "user_evidence: &cycle\n  nested: *cycle\n"
        "```"
    )
    issue = parse_issue(_raw_issue(74, body=_body(evidence=evidence)))

    result = select_issue(
        issues=(issue,),
        snapshot=_metadata(),
        active=_active(),
        as_of=AS_OF,
        autonomy_ceiling="tier-b",
    )

    assert result.status == "selected"
    assert result.warnings == ("issue-74:user-evidence-invalid",)


def test_paid_authorization_is_not_a_constructible_result_field() -> None:
    assert "paid_work_authorized" not in inspect.signature(SelectionResult).parameters
    result = SelectionResult(status="none", snapshot=_metadata())
    assert result.paid_work_authorized is False
