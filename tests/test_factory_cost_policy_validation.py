from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = REPO_ROOT / "docs" / "meta" / "factory-cost-policy.example.json"


def _run_policy(
    tmp_path: Path,
    document: str,
    as_of: str,
) -> subprocess.CompletedProcess[str]:
    policy_path = tmp_path / "factory-cost-policy.json"
    policy_path.write_text(document, encoding="utf-8")
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


def test_factory_cost_policy_rejects_unresolved_price_references(tmp_path: Path) -> None:
    document = EXAMPLE_POLICY.read_text(encoding="utf-8").replace(
        '"price_snapshot_ids": [\n        "example-input-price"',
        '"price_snapshot_ids": [\n        "missing-price"',
    )

    result = _run_policy(tmp_path, document, "2026-07-15T00:00:00Z")

    assert result.returncode == 2
    assert "unknown price snapshot" in result.stderr
