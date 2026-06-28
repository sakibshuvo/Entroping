import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "beta_readiness.py"


def run_beta_readiness(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def beta_readiness_module() -> ModuleType:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    import scripts.beta_readiness as beta_readiness

    return beta_readiness


def test_beta_readiness_json_reports_current_truth() -> None:
    result = run_beta_readiness("--format", "json")

    assert result.returncode == 0
    payload = _json_payload(result.stdout)
    assert payload["schema_version"] == "entroping.beta-readiness.v1"
    assert payload["alpha"]["ready"] is True
    assert payload["stable_core"]["ready"] is False
    assert payload["package_index"]["ready"] is False
    assert payload["beta_ready"] is False

    blockers = _string_list(payload, "blockers")
    assert any(blocker.startswith("stable_core:") for blocker in blockers)
    assert any("package_index" in blocker for blocker in blockers)


def test_beta_readiness_markdown_distinguishes_alpha_from_beta_paths() -> None:
    result = run_beta_readiness()

    assert result.returncode == 0
    assert "# Beta Readiness" in result.stdout
    assert "### Alpha blockers" in result.stdout
    assert "### Stable-core blockers" in result.stdout
    assert "### Package-index blockers" in result.stdout
    assert "Beta ready: `false`" in result.stdout


def test_beta_readiness_strict_fails_when_blocked() -> None:
    result = run_beta_readiness("--format", "json", "--strict")

    assert result.returncode != 0
    assert "beta readiness check failed" in result.stderr


def test_beta_readiness_rejects_unreachable_readiness_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beta_readiness = beta_readiness_module()

    monkeypatch.setattr(
        beta_readiness,
        "run_readiness_script",
        lambda *_args: {"error": "script execution failed"},
    )

    payload = beta_readiness.build_beta_readiness_payload(root=REPO_ROOT)
    assert payload.beta_ready is False
    assert any(
        blocker.startswith("package_index:") or blocker.startswith("stable_core:")
        for blocker in payload.blockers
    )


def test_beta_readiness_blocker_mapping_for_synthetic_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beta_readiness = beta_readiness_module()

    launch_payload = {
        "schema_version": "entroping.alpha-launch-readiness.v1",
        "alpha_launch_ready": False,
        "checks": {
            "demo_matrix": {"status": "missing"},
            "public_claims_audit": {"status": "present"},
        },
        "stable_core_blockers": [
            "stable-core still requires package-index proof",
        ],
    }
    stable_payload = {
        "schema_version": "entroping.stable-core-readiness.v1",
        "stable_core_ready": False,
        "blockers": ["package-index proof", "real downstream user feedback"],
    }
    package_payload = {
        "schema_version": "entroping.package-index-readiness.v1",
        "package_index_ready": False,
        "repo_guardrails_ready": False,
        "repo_failures": ["publish workflow permissions invalid"],
    }

    monkeypatch.setattr(
        beta_readiness,
        "run_readiness_script",
        lambda *_args: (
            launch_payload
            if _args[0] == "scripts/launch_readiness.py"
            else stable_payload
            if _args[0] == "scripts/stable_core_readiness.py"
            else package_payload
        ),
    )

    payload = beta_readiness.build_beta_readiness_payload(root=REPO_ROOT)

    assert payload.alpha["ready"] is False
    assert payload.stable_core["ready"] is False
    assert payload.package_index["ready"] is False
    assert payload.beta_ready is False
    assert "alpha:demo_matrix: missing" in payload.alpha["blockers"]
    assert "stable_core:package-index proof" in payload.stable_core["blockers"]
    assert (
        "package_index: package index proof not complete"
        in payload.package_index["blockers"]
    )
    assert (
        "package_index: publish workflow permissions invalid"
        in payload.package_index["blockers"]
    )


def test_beta_readiness_markdown_reports_ready_when_components_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beta_readiness = beta_readiness_module()

    monkeypatch.setattr(
        beta_readiness,
        "run_readiness_script",
        lambda *_args: (
            {
                "alpha_launch_ready": True,
                "checks": {},
            }
            if _args[0] == "scripts/launch_readiness.py"
            else {
                "stable_core_ready": True,
                "blockers": [],
            }
            if _args[0] == "scripts/stable_core_readiness.py"
            else {
                "package_index_ready": True,
                "repo_guardrails_ready": True,
                "repo_failures": [],
            }
        ),
    )

    payload = beta_readiness.build_beta_readiness_payload(root=REPO_ROOT)
    rendered = _render(payload)

    assert payload.beta_ready is True
    assert "Beta ready: `true`" in rendered


def _json_payload(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload[key]
    assert isinstance(value, list)
    items = cast(list[str], value)
    result: list[str] = []
    for item in items:
        assert isinstance(item, str)
        result.append(item)
    return result


def _render(payload: dict[str, Any]) -> str:
    beta_readiness = beta_readiness_module()
    return cast(str, beta_readiness._render_markdown(payload))
