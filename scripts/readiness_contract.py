"""Canonical public maturity and stable-core blocker contract."""

from __future__ import annotations

from collections.abc import Mapping

CONTRACT_VERSION = "4.1"
PRODUCT_MATURITY = "alpha"
STABLE_CORE_BLOCKERS = (
    "package-index proof",
    "real downstream user feedback",
)
STABLE_CORE_BLOCKER_IDS = (
    "package_index_proof",
    "real_downstream_feedback",
)


def readiness_metadata(readiness_basis: str) -> dict[str, str]:
    """Return the maturity fields shared by public readiness payloads."""

    return {
        "contract_version": CONTRACT_VERSION,
        "product_maturity": PRODUCT_MATURITY,
        "readiness_basis": readiness_basis,
    }


def stable_core_blocker_failures(payload: Mapping[str, object]) -> list[str]:
    """Validate the exact ordered blocker IDs and display names."""

    failures: list[str] = []
    if payload.get("stable_core_blocker_ids") != list(STABLE_CORE_BLOCKER_IDS):
        failures.append(
            "stable_core_blocker_ids must exactly match "
            f"{list(STABLE_CORE_BLOCKER_IDS)}"
        )
    if payload.get("stable_core_blockers") != list(STABLE_CORE_BLOCKERS):
        failures.append(
            "stable_core_blockers must exactly match "
            f"{list(STABLE_CORE_BLOCKERS)}"
        )
    return failures


def render_stable_core_blockers(payload: Mapping[str, object]) -> list[str]:
    """Render validated blocker IDs and names without trusting malformed values."""

    blocker_ids = payload.get("stable_core_blocker_ids")
    blockers = payload.get("stable_core_blockers")
    if not isinstance(blocker_ids, list) or not isinstance(blockers, list):
        return []
    return [
        f"- `{blocker_id}`: {blocker}"
        for blocker_id, blocker in zip(blocker_ids, blockers, strict=False)
    ]
