from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pydantic import TypeAdapter

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.example.json"
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, JsonValue])


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _run_policy(
    tmp_path: Path,
    document: str,
    as_of: str,
) -> subprocess.CompletedProcess[str]:
    policy_path = tmp_path / "factory-cost-policy.json"
    _ = policy_path.write_text(document, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_cost_policy",
            "validate",
            "--policy",
            str(policy_path),
            "--as-of",
            as_of,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_factory_cost_policy_rejects_exact_policy_expiry_boundary(tmp_path: Path) -> None:
    result = _run_policy(
        tmp_path,
        EXAMPLE_POLICY.read_text(encoding="utf-8"),
        "2026-12-31T00:00:00Z",
    )

    assert result.returncode == 2
    assert "policy is stale" in result.stderr


def test_factory_cost_policy_rejects_reserve_that_consumes_the_cash_cap(
    tmp_path: Path,
) -> None:
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        '"emergency_reserve_microcents": 2000000000',
        '"emergency_reserve_microcents": 20000000000',
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "reserve must be less than the cash cap" in result.stderr


def test_factory_cost_policy_rejects_duplicate_lane_identifiers(tmp_path: Path) -> None:
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        '"id": "metered-example-lane"',
        '"id": "included-example-lane"',
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "duplicate automation lane id" in result.stderr


def test_factory_cost_policy_rejects_stale_price_for_enabled_metered_lane(
    tmp_path: Path,
) -> None:
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        '"billing_mode": "metered",\n      "enabled": false',
        '"billing_mode": "metered",\n      "enabled": true',
    )

    result = _run_policy(tmp_path, document, "2026-08-01T00:00:00Z")

    assert result.returncode == 2
    assert "price snapshot is stale" in result.stderr


def test_factory_cost_policy_rejects_duplicate_json_members(tmp_path: Path) -> None:
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        '"policy_id": "example-budget-policy",',
        '"policy_id": "first-policy",\n  "policy_id": "example-budget-policy",',
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "duplicate JSON key is forbidden" in result.stderr


def test_factory_cost_policy_rejects_secret_fields_without_echoing_values(
    tmp_path: Path,
) -> None:
    secret_value = "sk-example-secret-value"
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        '"policy_id": "example-budget-policy",',
        f'"policy_id": "example-budget-policy",\n  "api_key": "{secret_value}",',
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "secret-like content" in result.stderr
    assert secret_value not in result.stderr


def test_factory_cost_policy_rejects_secret_shaped_values_without_echoing_them(
    tmp_path: Path,
) -> None:
    secret_value = "sk-example-secret-value"
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        "example-budget-policy",
        secret_value,
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "secret-like content" in result.stderr
    assert secret_value not in result.stderr


def test_factory_cost_policy_rejects_unicode_escaped_secret_content(
    tmp_path: Path,
) -> None:
    escaped_secret = r"sk\u002dexample\u002dsecret\u002dvalue"
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        "example-budget-policy",
        escaped_secret,
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "secret-like content" in result.stderr
    assert "sk-example-secret-value" not in result.stderr


def test_factory_cost_policy_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    policy_path = tmp_path / "factory-cost-policy.json"
    os.mkfifo(policy_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_cost_policy",
            "validate",
            "--policy",
            str(policy_path),
            "--as-of",
            "2026-07-15T00:00:00Z",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )

    assert result.returncode == 2
    assert "not a file" in result.stderr


def test_factory_cost_policy_rejects_unresolved_price_references(tmp_path: Path) -> None:
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        '"price_snapshot_ids": [\n        "example-input-price"',
        '"price_snapshot_ids": [\n        "missing-price"',
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "unknown price snapshot" in result.stderr


def test_factory_cost_policy_rejects_ambiguous_price_snapshots(tmp_path: Path) -> None:
    document = EXAMPLE_POLICY.read_text(encoding="utf-8")
    policy = JSON_OBJECT_ADAPTER.validate_json(document)
    price_snapshots = _array(policy["price_snapshots"])
    conflicting_snapshot = _object(price_snapshots[0]).copy()
    conflicting_snapshot["id"] = "conflicting-input-price"
    conflicting_snapshot["price_microcents"] = 20_000_000
    price_snapshots.append(conflicting_snapshot)
    automation_lanes = _array(policy["automation_lanes"])
    metered_lane = _object(automation_lanes[1])
    _array(metered_lane["price_snapshot_ids"]).append(
        "conflicting-input-price",
    )

    result = _run_policy(tmp_path, json.dumps(policy), "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "ambiguous price snapshot unit" in result.stderr


def test_factory_cost_policy_does_not_echo_invalid_discriminator_values(
    tmp_path: Path,
) -> None:
    attacker_value = "untrusted-visible-value"
    substitutions = (
        ('"billing_mode": "included_quota"', f'"billing_mode": "{attacker_value}"'),
        ('"kind": "annual"', f'"kind": "{attacker_value}"'),
        ('"kind": "rolling"', f'"kind": "{attacker_value}"'),
    )

    for source, replacement in substitutions:
        document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
            source,
            replacement,
            1,
        )
        result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

        assert result.returncode == 2
        assert "unsupported tagged policy variant" in result.stderr
        assert attacker_value not in result.stderr
