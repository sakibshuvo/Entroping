"""QAnstitution loading and import tests."""

from pathlib import Path

import pytest

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution


def write_yaml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.lstrip(), encoding="utf-8")


def test_load_qanstitution_merges_local_imports_before_local_gates(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "rules" / "security.yaml",
        """
project: imported-security
gates:
  - id: security_header
    condition: path startswith '/api'
    gate: header "X-Request-Id" exists
    enforcement: warn
  - id: smoke_latency
    condition: tags contains 'smoke'
    gate: duration < 700
    enforcement: warn
""",
    )
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/security.yaml
gates:
  - id: smoke_latency
    condition: tags contains 'smoke'
    gate: duration < 500
    enforcement: block
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )

    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    assert [gate.id for gate in law.gates] == [
        "security_header",
        "smoke_latency",
        "global_latency",
    ]
    assert law.gates[1].gate == "duration < 500"
    assert law.gates[1].enforcement == "block"


def test_load_qanstitution_rejects_missing_import(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/missing.yaml
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Import not found"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_rejects_remote_imports_without_network(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - https://example.com/security.yaml
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Remote QAnstitution imports"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_rejects_imports_outside_root_directory(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "outside.yaml",
        """
project: outside-policy
gates:
  - id: outside_gate
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )
    write_yaml(
        tmp_path / "project" / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ../outside.yaml
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )

    with pytest.raises(QanstitutionLoadError, match="outside the QAnstitution root"):
        load_qanstitution(tmp_path / "project" / "qanstitution.yaml")


def test_load_qanstitution_rejects_duplicate_local_gate_ids(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
  - id: global_latency
    condition: tags contains 'smoke'
    gate: duration < 500
    enforcement: warn
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Duplicate gate id"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_rejects_overriding_imported_final_gate(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "rules" / "security.yaml",
        """
project: imported-security
gates:
  - id: no_5xx_in_smoke
    condition: tags contains 'smoke'
    gate: status < 500
    enforcement: block
    final: true
""",
    )
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/security.yaml
gates:
  - id: no_5xx_in_smoke
    condition: tags contains 'smoke'
    gate: status < 400
    enforcement: warn
""",
    )

    with pytest.raises(QanstitutionLoadError, match="final imported gate"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_rejects_invalid_imported_condition(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "rules" / "security.yaml",
        """
project: imported-security
gates:
  - id: bad_condition
    condition: tags includes 'smoke'
    gate: duration < 2000
    enforcement: block
""",
    )
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/security.yaml
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Unsupported QAnstitution condition syntax"):
        load_qanstitution(tmp_path / "qanstitution.yaml")
