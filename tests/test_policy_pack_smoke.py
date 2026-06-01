"""Smoke evidence for reusable QAnstitution policy packs."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "policy_pack_smoke.py"


def run_policy_pack_smoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_policy_pack_smoke_json_reports_example_pack_evidence() -> None:
    result = run_policy_pack_smoke("--format", "json", "--strict")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.policy-pack-smoke.v1"
    assert payload["status"] == "pass"
    assert payload["pack_id"] == "entroping.api-baseline"
    assert payload["runtime_contract"] == "qanstitution-import"
    assert payload["gate_count"] == 3
    assert payload["final_gate_ids"] == ["api-security.no_5xx"]
    assert "api-security.request_id" in payload["gate_ids"]
    assert "checkout.local_latency" in payload["consumer_gate_ids"]
    assert payload["failures"] == []


def test_policy_pack_smoke_strict_rejects_missing_required_pack_files(tmp_path: Path) -> None:
    (tmp_path / "entroping-policy-pack.yaml").write_text(
        "\n".join(
            [
                'id: "broken.pack"',
                'name: "Broken Pack"',
                'version: "0.1.0"',
                'license: "Apache-2.0"',
                'entrypoint: "missing.yaml"',
                'runtime_contract: "qanstitution-import"',
                "gate_prefixes: []",
                "final_gates: []",
            ]
        ),
        encoding="utf-8",
    )

    result = run_policy_pack_smoke("--pack", str(tmp_path), "--strict")

    assert result.returncode == 1
    assert "policy-pack smoke failed" in result.stderr
    assert "entrypoint file missing" in result.stderr


def test_policy_pack_smoke_markdown_is_release_owner_readable() -> None:
    result = run_policy_pack_smoke()

    assert result.returncode == 0, result.stderr
    assert "# Policy-Pack Smoke Evidence" in result.stdout
    assert "- Status: `pass`" in result.stdout
    assert "`api-security.no_5xx`" in result.stdout
