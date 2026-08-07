"""Authenticated fixtures for provider-scorecard CLI tests."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "factory_metrics.py"
SCORECARD_KEY_ENV = "ENTROPING_FACTORY_SCORECARD_EVIDENCE_HMAC_KEY_V1"
SCORECARD_KEY = "a" * 64
SCORECARD_KEY_ID = "maintainer-local-v1"


def identity(index: int) -> dict[str, object]:
    digit = f"{index:x}"
    return {
        "job_id": f"job-{index}",
        "reservation_id": f"reservation-{index}",
        "issue_number": 1573,
        "provider_lane_id": "deepseek-api/direct",
        "provider_host": "repo-local DeepSeek worker",
        "billing_path": "paid direct DeepSeek API",
        "model_id": "deepseek-v4-pro",
        "cost_provider_id": "deepseek",
        "cost_model_id": "deepseek/deepseek-v4-pro",
        "autonomy_tier": "tier_c",
        "base_revision": digit * 40,
        "head_revision": "b" * 39 + digit,
        "diff_sha256": "c" * 63 + digit,
    }


def cost_digest(case_identity: dict[str, object], cost_usd: float) -> str:
    payload = {"identity": case_identity, "cost_usd": cost_usd}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def case(
    index: int,
    *,
    observed_at: str = "2026-08-01T00:00:00Z",
    task_type: str = "implementation",
    verification_lane: str = "security-runtime",
    decision: str = "accepted",
    cost_usd: float | None = 1.5,
    later_outcomes: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    item_identity = identity(index)
    digit = f"{index:x}"
    result: dict[str, object] = {
        "task_type": task_type,
        "verification_lane": verification_lane,
        "observed_at": observed_at,
        "cost_usd": cost_usd,
        "cost_receipt_digest": cost_digest(item_identity, cost_usd)
        if cost_usd is not None
        else None,
        "identity": item_identity,
        "review": {**item_identity, "decision": decision, "digest": "d" * 63 + digit},
        "verification": {
            **item_identity,
            "verification_lane": verification_lane,
            "quality": "pass",
            "security": "pass",
            "digest": "e" * 63 + digit,
        },
        "ci": {
            **item_identity,
            "run_id": f"ci-{index}",
            "status": "success",
            "digest": "f" * 63 + digit,
        },
        "merge": {
            **item_identity,
            "pr_number": 1600 + index,
            "status": "merged",
            "merge_commit_revision": "f" * 39 + digit,
            "digest": "1" * 63 + digit,
        },
        "later_outcomes": later_outcomes or [],
    }
    return result


def update_case_identity(item: dict[str, object], **updates: object) -> None:
    """Update the case and every receipt identity, then rebind known cost."""

    item_identity = item["identity"]
    assert isinstance(item_identity, dict)
    item_identity.update(updates)
    for name in ("review", "verification", "ci", "merge"):
        receipt = item[name]
        if isinstance(receipt, dict):
            receipt.update(updates)
    outcomes = item["later_outcomes"]
    assert isinstance(outcomes, list)
    for outcome in outcomes:
        outcome.update(updates)
    cost_usd = item["cost_usd"]
    if isinstance(cost_usd, (int, float)):
        item["cost_receipt_digest"] = cost_digest(item_identity, float(cost_usd))


def document(*cases: dict[str, object]) -> dict[str, object]:
    unsigned: dict[str, object] = {
        "schema_version": "entroping.provider-scorecard-evidence.v1",
        "cases": list(cases),
    }
    return sign(unsigned)


def sign(unsigned: dict[str, object], *, key: str = SCORECARD_KEY) -> dict[str, object]:
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(bytes.fromhex(key), canonical, hashlib.sha256).hexdigest()
    return {
        **unsigned,
        "authentication": {
            "scheme": "hmac-sha256",
            "key_id": SCORECARD_KEY_ID,
            "signature": signature,
        },
    }


def resign(value: dict[str, object], *, key: str = SCORECARD_KEY) -> dict[str, object]:
    unsigned = {name: item for name, item in value.items() if name != "authentication"}
    return sign(unsigned, key=key)


def write_scorecard(
    tmp_path: Path, value: dict[str, object], *, name: str = "scorecard.json"
) -> Path:
    parent = tmp_path / ".entroping" / "factory-metrics"
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(tmp_path / ".entroping", 0o700)
    os.chmod(parent, 0o700)
    target = parent / name
    _ = target.write_text(json.dumps(value), encoding="utf-8")
    os.chmod(target, 0o600)
    return target


def write_scorecard_bytes(tmp_path: Path, value: bytes, *, name: str) -> Path:
    parent = tmp_path / ".entroping" / "factory-metrics"
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(tmp_path / ".entroping", 0o700)
    os.chmod(parent, 0o700)
    target = parent / name
    _ = target.write_bytes(value)
    os.chmod(target, 0o600)
    return target


def run(
    tmp_path: Path, *args: str, key: str | None = SCORECARD_KEY
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    if key is None:
        _ = environment.pop(SCORECARD_KEY_ENV, None)
    else:
        environment[SCORECARD_KEY_ENV] = key
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path), *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
        env=environment,
    )


def validate(
    tmp_path: Path, path: Path, *, key: str | None = SCORECARD_KEY
) -> subprocess.CompletedProcess[str]:
    return run(
        tmp_path,
        "provider-scorecard",
        "validate",
        "--input",
        str(path.relative_to(tmp_path)),
        "--json",
        key=key,
    )


def report(
    tmp_path: Path,
    path: Path,
    *,
    as_of: str = "2026-08-03T00:00:00Z",
    output_format: str = "json",
    output: str | None = None,
    key: str | None = SCORECARD_KEY,
) -> subprocess.CompletedProcess[str]:
    args = [
        "provider-scorecard",
        "report",
        "--input",
        str(path.relative_to(tmp_path)),
        "--as-of",
        as_of,
        "--format",
        output_format,
    ]
    if output is not None:
        args.extend(("--output", output))
    return run(
        tmp_path,
        *args,
        key=key,
    )


def json_object(raw: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(raw))
