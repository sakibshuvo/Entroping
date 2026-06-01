"""Smoke evidence for reusable QAnstitution policy packs."""

import json
import shutil
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "policy_pack_smoke.py"
EXAMPLE_PACK = REPO_ROOT / "examples" / "policy-packs" / "api-baseline"


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
    assert payload["provenance"] == {
        "source": "examples/policy-packs/api-baseline",
        "license": "Apache-2.0",
        "supported_entroping": ">=0.1.1-alpha,<1.0",
        "evidence_command": "uv run python scripts/policy_pack_smoke.py --strict",
        "gates": [
            {
                "id": "api-reliability.latency",
                "file": "rules/reliability.yaml",
                "final": False,
            },
            {
                "id": "api-security.no_5xx",
                "file": "rules/security.yaml",
                "final": True,
            },
            {
                "id": "api-security.request_id",
                "file": "rules/security.yaml",
                "final": False,
            },
        ],
    }
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


def test_policy_pack_smoke_strict_rejects_provenance_gate_drift(tmp_path: Path) -> None:
    pack_path = tmp_path / "api-baseline"
    shutil.copytree(EXAMPLE_PACK, pack_path)
    manifest_path = pack_path / "entroping-policy-pack.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["gates"][0]["id"] = "api-security.renamed"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = run_policy_pack_smoke("--pack", str(pack_path), "--strict")

    assert result.returncode == 1
    assert "policy-pack smoke failed" in result.stderr
    assert "manifest gate ids must match loaded gate ids" in result.stderr


def test_policy_pack_smoke_markdown_is_release_owner_readable() -> None:
    result = run_policy_pack_smoke()

    assert result.returncode == 0, result.stderr
    assert "# Policy-Pack Smoke Evidence" in result.stdout
    assert "- Status: `pass`" in result.stdout
    assert "- Source: `examples/policy-packs/api-baseline`" in result.stdout
    assert (
        "- Evidence command: `uv run python scripts/policy_pack_smoke.py --strict`"
        in result.stdout
    )
    assert "`api-security.no_5xx`" in result.stdout
