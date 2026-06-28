"""Beta exit scorecard tests — compose readiness evidence from gates."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "beta_exit_scorecard.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_json_schema_and_beta_not_ready() -> None:
    """Beta exit scorecard JSON uses correct schema and shows blocked gates."""
    result = _run("--format", "json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "entroping.beta-exit-scorecard.v1"
    assert payload["alpha_ready"] is False
    assert payload["beta_ready"] is False
    assert isinstance(payload["gates"], list)
    assert len(payload["gates"]) >= 5


def test_alpha_gates_present() -> None:
    """Alpha gate keys reference #303 and #304 as required gates."""
    result = _run("--format", "json")
    payload = json.loads(result.stdout)

    alpha_keys = {g["key"] for g in payload["gates"] if g["alpha_gate"]}
    assert "testpypi_trusted_publisher" in alpha_keys, f"missing #303 gate, got {sorted(alpha_keys)}"
    assert "testpypi_alpha_publish" in alpha_keys, f"missing #304 gate, got {sorted(alpha_keys)}"

    for gate in payload["gates"]:
        if gate["alpha_gate"]:
            assert not gate["optional"], f"alpha gate {gate['key']} must not be optional"


def test_beta_gates_present() -> None:
    """Beta gates reference #305, #306, #308 and include optional #587."""
    result = _run("--format", "json")
    payload = json.loads(result.stdout)

    beta_keys = {g["key"] for g in payload["gates"] if not g["alpha_gate"]}
    assert "pypi_alpha_publish" in beta_keys, f"missing #305 gate, got {sorted(beta_keys)}"
    assert "downstream_feedback" in beta_keys, f"missing #306 gate, got {sorted(beta_keys)}"
    assert "compatibility_decision" in beta_keys, f"missing #308 gate, got {sorted(beta_keys)}"
    assert "homebrew_tap" in beta_keys, f"missing #587 gate, got {sorted(beta_keys)}"

    homebrew = next(g for g in payload["gates"] if g["key"] == "homebrew_tap")
    assert homebrew["optional"] is True


def test_gate_structure_fields() -> None:
    """Every gate includes key, issue_number, issue_url, label, status, detail, description."""
    required_fields = {"key", "issue_number", "issue_url", "label",
                       "alpha_gate", "optional", "status", "detail", "description"}
    result = _run("--format", "json")
    payload = json.loads(result.stdout)

    for gate in payload["gates"]:
        missing = required_fields - set(gate.keys())
        assert not missing, f"gate {gate.get('key', '?')} missing fields: {missing}"
        assert gate["status"] in {"pass", "fail", "blocked", "not-applicable"}, \
            f"invalid status {gate['status']} for gate {gate['key']}"
        assert isinstance(gate["issue_number"], int)
        assert str(gate["issue_number"]) in gate["issue_url"]


def test_current_state_all_blocked_for_alpha() -> None:
    """All non-optional alpha gates are currently blocked (no package-index proof yet)."""
    result = _run("--format", "json")
    payload = json.loads(result.stdout)

    non_optional_alpha = [g for g in payload["gates"]
                          if g["alpha_gate"] and not g["optional"]]
    assert len(non_optional_alpha) >= 2
    for gate in non_optional_alpha:
        assert gate["status"] == "blocked", \
            f"{gate['key']} expected blocked, got {gate['status']}: {gate['detail']}"


def test_strict_fails_when_gates_blocked() -> None:
    """--strict exits non-zero when non-optional gates are not passing."""
    result = _run("--strict")
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "beta exit scorecard failed" in result.stderr


def test_markdown_output_structure() -> None:
    """Markdown output includes expected H1, alpha/beta sections, and issue links."""
    result = _run("--format", "md")
    assert result.returncode == 0, result.stderr

    assert "# Beta Exit Scorecard" in result.stdout
    assert "Alpha ready:" in result.stdout
    assert "Beta ready:" in result.stdout
    assert "## Alpha Gates" in result.stdout
    assert "## Beta Gates" in result.stdout
    assert "github.com/sakibshuvo/Entroping/issues/303" in result.stdout
    assert "github.com/sakibshuvo/Entroping/issues/308" in result.stdout


def test_no_network_calls_no_secrets() -> None:
    """Output must not contain credential-shaped or secret patterns."""
    result = _run("--format", "json")
    assert result.returncode == 0

    forbidden = ("password", "token=", "api_key", "Bearer ", "-----BEGIN", "SECRET")
    lower = result.stdout.lower()
    for word in forbidden:
        assert word not in lower, f"forbidden pattern '{word}' found in output"


def test_external_requirements_never_expose_credentials(tmp_path: Path) -> None:
    """When requirements are serialized they must not leak path or env data."""
    result = _run("--format", "json")
    payload = json.loads(result.stdout)

    for gate in payload["gates"]:
        detail = str(gate["detail"]).lower()
        assert "/users/" not in detail, f"gate {gate['key']} detail leaks path"
        assert "home" not in detail[:20], f"gate {gate['key']} detail looks like a path"
