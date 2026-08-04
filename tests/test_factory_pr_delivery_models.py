from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_pr_delivery_io import DeliveryInputError, load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_models import (  # noqa: E402
    DeliveryReceipt,
    DeliveryRequest,
)


def test_load_binds_strict_request_to_accepted_owner_only_artifacts(tmp_path: Path) -> None:
    # Given: an accepted #1574 receipt and three digest-bound private artifacts.
    main, worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)

    # When: the private delivery boundary loads the request.
    envelope = load_delivery_envelope(request_path)

    # Then: only content-bound values cross the boundary and result_head stays the base.
    assert envelope.request == DeliveryRequest.model_validate(payload, strict=True)
    assert envelope.orchestration_receipt.result_head == envelope.orchestration_request.base_commit
    assert envelope.pr_body == "## Summary\n\nExact docs delivery.\n"
    assert envelope.worktree_path == worktree.resolve()
    assert envelope.main_root == main.resolve()


@pytest.mark.parametrize("mutation", ["unknown", "digest", "identity", "relative"])
def test_load_rejects_unknown_drifted_or_noncanonical_request(
    tmp_path: Path, mutation: str
) -> None:
    # Given: one malformed delivery request boundary.
    _main, _worktree, payload = accepted_artifacts(tmp_path)
    if mutation == "unknown":
        payload["repository"] = "sakibshuvo/Entroping"
    elif mutation == "digest":
        payload["pr_body_sha256"] = "f" * 64
    elif mutation == "identity":
        payload["request_id"] = f"delivery_{'f' * 64}"
    else:
        payload["pr_body_path"] = "body.md"
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)

    # When/Then: no partially trusted envelope is returned.
    with pytest.raises(DeliveryInputError) as exc_info:
        load_delivery_envelope(request_path)
    assert exc_info.value.code == "request-invalid"


def test_load_rejects_duplicate_keys_and_nonfinite_constants(tmp_path: Path) -> None:
    # Given: JSON whose parser-level shape is ambiguous or non-finite.
    request_path = tmp_path / "private/delivery-request.json"
    request_path.parent.mkdir(mode=0o700)
    request_path.write_text('{"schema_version":"x","schema_version":NaN}', encoding="utf-8")
    os.chmod(request_path, 0o600)

    # When/Then: parser ambiguity fails before model validation.
    with pytest.raises(DeliveryInputError) as exc_info:
        load_delivery_envelope(request_path)
    assert exc_info.value.code == "request-invalid"


def test_load_rejects_non_private_referenced_artifact_and_invalid_utf8(tmp_path: Path) -> None:
    # Given: a world-readable body that is not valid UTF-8.
    _main, _worktree, payload = accepted_artifacts(tmp_path)
    body = Path(str(payload["pr_body_path"]))
    body.write_bytes(b"\xff")
    os.chmod(body, 0o644)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)

    # When/Then: owner/mode validation wins without exposing body bytes.
    with pytest.raises(DeliveryInputError) as exc_info:
        load_delivery_envelope(request_path)
    assert exc_info.value.code == "artifact-invalid"


def test_receipt_projection_rejects_values_and_inconsistent_lifecycle() -> None:
    # Given: a value-free pushed receipt projection.
    payload = {
        "schema_version": "entroping.factory-pr-delivery-receipt.v1",
        "receipt_id": f"delivery_receipt_{'0' * 64}",
        "request_id": f"delivery_{'1' * 64}",
        "request_digest": "2" * 64,
        "lifecycle": "pushed",
        "reason": "pushed",
        "accepted_local_head": "3" * 40,
        "committed_head": "4" * 40,
        "remote_head": "4" * 40,
        "commit_parent": "3" * 40,
        "commit_tree": "5" * 40,
        "accepted_diff_sha256": "6" * 64,
        "committed_diff_sha256": "6" * 64,
        "accepted_manifest_sha256": "7" * 64,
        "committed_manifest_sha256": "7" * 64,
        "approved_path_sha256": "8" * 64,
        "body_sha256": "9" * 64,
        "created_at": "2026-08-03T12:00:00Z",
        "updated_at": "2026-08-03T12:00:01Z",
    }

    # When/Then: identity and lifecycle are both content-addressed, never value-bearing.
    with pytest.raises(ValidationError):
        DeliveryReceipt.model_validate(payload, strict=True)
    with pytest.raises(ValidationError):
        DeliveryReceipt.model_validate({**payload, "pr_body": "secret"}, strict=True)
