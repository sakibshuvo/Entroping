"""Guardrails for the OWASP API Top 10-inspired starter policy pack."""

import json
import re
import subprocess
from pathlib import Path

import yaml

from entroping.core.config_loader import load_qanstitution

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "policy_pack_smoke.py"
PACK_ROOT = REPO_ROOT / "examples" / "policy-packs" / "owasp-api-top-10"


def run_policy_pack_smoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_owasp_api_top_10_pack_smoke_json_evidence() -> None:
    result = run_policy_pack_smoke(
        "--pack",
        "examples/policy-packs/owasp-api-top-10",
        "--format",
        "json",
        "--strict",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.policy-pack-smoke.v1"
    assert payload["artifact_type"] == "policy-pack-verification"
    assert payload["status"] == "pass"
    assert payload["pack_id"] == "entroping.owasp-api-top-10"
    assert payload["gate_count"] == 6
    assert payload["final_gate_ids"] == ["owasp-api.resources.no_server_errors"]
    assert payload["gate_ids"] == [
        "owasp-api.authn.unauthenticated_denied",
        "owasp-api.authz.object_access_denied",
        "owasp-api.inventory.deprecated_endpoint_header",
        "owasp-api.misconfig.request_id",
        "owasp-api.resources.latency_budget",
        "owasp-api.resources.no_server_errors",
    ]
    assert payload["consumer_example"]["local_gate_ids"] == [
        "checkout.local_owasp_latency"
    ]
    assert payload["provenance"]["source"] == (
        "examples/policy-packs/owasp-api-top-10"
    )
    assert payload["provenance"]["evidence_command"] == (
        "uv run python scripts/policy_pack_smoke.py "
        "--pack examples/policy-packs/owasp-api-top-10 --strict"
    )
    assert payload["failures"] == []


def test_owasp_api_top_10_pack_is_loadable_and_runtime_neutral() -> None:
    manifest = yaml.safe_load(
        (PACK_ROOT / "entroping-policy-pack.yaml").read_text(encoding="utf-8")
    )
    effective_pack = load_qanstitution(PACK_ROOT / "qanstitution.yaml")

    assert manifest["id"] == "entroping.owasp-api-top-10"
    assert manifest["runtime_contract"] == "qanstitution-import"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["source"] == "examples/policy-packs/owasp-api-top-10"
    assert manifest["gate_prefixes"] == [
        "owasp-api.authn",
        "owasp-api.authz",
        "owasp-api.inventory",
        "owasp-api.misconfig",
        "owasp-api.resources",
    ]
    assert effective_pack.agents == {}
    assert effective_pack.sources is None
    assert {gate.id for gate in effective_pack.gates} == set(manifest["final_gates"]) | {
        "owasp-api.authn.unauthenticated_denied",
        "owasp-api.authz.object_access_denied",
        "owasp-api.inventory.deprecated_endpoint_header",
        "owasp-api.misconfig.request_id",
        "owasp-api.resources.latency_budget",
    }


def test_owasp_pack_docs_preserve_honest_starter_pack_claims() -> None:
    readme = (PACK_ROOT / "README.md").read_text(encoding="utf-8")
    normalized_readme = re.sub(r"\s+", " ", readme)
    open_core = (
        REPO_ROOT / "docs" / "product" / "OPEN_CORE_BOUNDARIES.md"
    ).read_text(encoding="utf-8")
    layout = (
        REPO_ROOT / "docs" / "technical" / "POLICY_PACK_LAYOUT.md"
    ).read_text(encoding="utf-8")

    required_readme_phrases = [
        "OWASP API Security Top 10 2023-inspired starter pack",
        "not official OWASP endorsement",
        "not complete OWASP compliance",
        "starter examples, not certification evidence",
        "https://owasp.org/API-Security/editions/2023/en/0x11-t10/",
    ]
    for phrase in required_readme_phrases:
        assert phrase in normalized_readme

    assert "owasp-api-top-10" in open_core
    assert "deeper maintained packs and support can be commercial" in open_core
    assert "examples/policy-packs/owasp-api-top-10/" in layout
