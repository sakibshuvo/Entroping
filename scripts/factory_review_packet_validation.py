from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.ai_worker_file_safety import secret_like_content_reason
from scripts.factory_patch_inspection import proposal_control_plane_violations
from scripts.factory_review_packet_model import PacketError


def validate_packet(packet: dict[str, Any]) -> None:
    artifact = packet.get("artifact")
    if not isinstance(artifact, dict):
        raise PacketError("artifact is required in packet")
    job = packet.get("job")
    if job is not None and not isinstance(job, dict):
        raise PacketError("job must be an object when present")

    metadata_value = artifact.get("metadata")
    result_summary = artifact.get("result_summary")
    if metadata_value is not None and not isinstance(metadata_value, dict):
        raise PacketError("artifact metadata must be an object when present")
    if result_summary is not None and not isinstance(result_summary, dict):
        raise PacketError("artifact result_summary must be an object when present")

    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    summary = result_summary if isinstance(result_summary, dict) else {}
    job_payload = job if isinstance(job, dict) else {}

    status = _first_value(metadata, "status")
    issue = _first_non_empty(
        _first_value(job_payload, "issue"),
        _first_value(metadata, "issue"),
    )
    provider_lane = _first_non_empty(
        _first_value(job_payload, "provider_lane"),
        _first_value(metadata, "provider_lane"),
    )
    merge_authority = _first_non_empty(
        _first_value(job_payload, "merge_authority"),
        _first_value(metadata, "merge_authority"),
    )
    verification_lane = _first_non_empty(
        _first_value(summary, "VERIFICATION_LANE"),
        _first_value(metadata, "verification_lane"),
    )
    ci_status = _first_non_empty(
        _first_value(summary, "CI_STATUS"),
        _first_value(metadata, "ci_status"),
    )

    if status != "completed":
        return
    required = {
        "issue": issue,
        "provider_lane": provider_lane,
        "verification_lane": verification_lane,
        "ci_status": ci_status,
        "merge_authority": merge_authority,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise PacketError(
            f"review packet missing required fields: {', '.join(missing)}"
        )


def enforce_tier_a_proposal_policy(
    packet: dict[str, Any],
    *,
    repo_root: Path,
) -> None:
    job = packet.get("job")
    artifact = packet.get("artifact")
    if not isinstance(artifact, dict):
        return
    autonomy_tier = job.get("autonomy_tier") if isinstance(job, dict) else None
    proposal = artifact.get("proposal_diff")
    if not isinstance(proposal, dict):
        return
    violations = proposal_control_plane_violations(proposal, repo_root=repo_root)
    if violations and (autonomy_tier == "tier_a" or job is None):
        details = ", ".join(f"{path} ({reason})" for path, reason in violations)
        raise PacketError(
            "Tier A control-plane protection denied proposal paths: "
            f"{details}; route this proposal to Codex/human review"
        )


def safe_packet_json(packet: dict[str, Any]) -> str:
    try:
        serialized = json.dumps(packet, indent=2, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise PacketError("review packet could not be serialized safely") from exc
    secret_reason = secret_like_content_reason(serialized)
    if secret_reason is not None:
        raise PacketError(
            f"review packet contains secret-like output: {secret_reason}"
        )
    return serialized


def _first_value(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _first_non_empty(*values: str | None) -> str | None:
    return next((value for value in values if value is not None), None)
