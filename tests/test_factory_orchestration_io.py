from __future__ import annotations

import importlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest
from factory_orchestration_test_support import (
    private_file,
    repository,
    request_payload,
    update_patch,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

io = importlib.import_module("scripts.factory_orchestration_io")
models = importlib.import_module("scripts.factory_orchestration_models")


def test_loads_owner_only_request_and_exact_proposal_once(tmp_path: Path) -> None:
    # Given: owner-only request and proposal artifacts with matching digest.
    main, worktree, base = repository(tmp_path)
    proposal = update_patch()
    payload = request_payload(main, worktree, base)
    payload["proposal_sha256"] = io.sha256_bytes(proposal)
    request_path = tmp_path / "private" / "request.json"
    proposal_path = Path(str(payload["proposal_path"]))
    private_file(request_path, json.dumps(payload).encode())
    private_file(proposal_path, proposal)

    # When: both artifacts cross their descriptor-authorized boundaries.
    request = io.load_request(request_path)
    loaded = io.load_exact_proposal(request)

    # Then: strict identity and exact bytes are preserved.
    assert request.issue_number == 1574
    assert loaded == proposal


def test_secure_inputs_reject_symlink_mode_duplicate_and_drift(tmp_path: Path) -> None:
    # Given: a valid request payload used to create unsafe boundary variants.
    main, worktree, base = repository(tmp_path)
    payload = request_payload(main, worktree, base)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    real = private / "real.json"
    private_file(real, json.dumps(payload).encode())
    linked = private / "linked.json"
    os.symlink(real, linked)

    # When/Then: request symlinks and permissive modes are rejected.
    with pytest.raises(io.OrchestrationInputError):
        io.load_request(linked)
    os.chmod(
        real,
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
    )
    with pytest.raises(io.OrchestrationInputError):
        io.load_request(real)

    # Given: duplicate JSON keys and proposal bytes that drift from their digest.
    duplicate = private / "duplicate.json"
    private_file(duplicate, b'{"schema_version":"a","schema_version":"b"}')
    with pytest.raises(io.OrchestrationInputError):
        io.load_request(duplicate)
    request = models.OrchestrationRequest.model_validate(payload, strict=True)
    private_file(Path(request.proposal_path), update_patch())

    # When/Then: proposal digest drift fails before inspection or mutation.
    with pytest.raises(io.OrchestrationInputError) as drift:
        io.load_exact_proposal(request)
    assert drift.value.code == "proposal-drift"
