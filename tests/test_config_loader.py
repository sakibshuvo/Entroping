"""QAnstitution loading and import tests."""

from pathlib import Path

import pytest
import yaml

from entroping.core.config_loader import (
    QanstitutionLoadError,
    load_qanstitution,
    load_qanstitution_evidence,
)


def write_yaml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.lstrip(), encoding="utf-8")


def write_document(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


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


def test_load_qanstitution_evidence_tracks_effective_gate_provenance(tmp_path: Path) -> None:
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

    evidence = load_qanstitution_evidence(tmp_path / "qanstitution.yaml")

    assert evidence.root_path == (tmp_path / "qanstitution.yaml").resolve()
    assert evidence.import_paths == ((tmp_path / "rules" / "security.yaml").resolve(),)
    assert [gate.rule.id for gate in evidence.gates] == [
        "security_header",
        "smoke_latency",
        "global_latency",
    ]
    assert {
        gate.rule.id: gate.source_path.relative_to(tmp_path).as_posix()
        for gate in evidence.gates
    } == {
        "security_header": "rules/security.yaml",
        "smoke_latency": "qanstitution.yaml",
        "global_latency": "qanstitution.yaml",
    }
    assert evidence.policy.gates[1].gate == "duration < 500"


def test_load_qanstitution_evidence_tracks_nested_import_paths(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "rules" / "base.yaml",
        """
project: base
gates:
  - id: base_latency
    condition: "true"
    gate: duration < 2000
    enforcement: warn
""",
    )
    write_yaml(
        tmp_path / "rules" / "security.yaml",
        """
project: imported-security
imports:
  - ./base.yaml
gates:
  - id: security_header
    condition: "true"
    gate: header "X-Request-Id" exists
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

    evidence = load_qanstitution_evidence(tmp_path / "qanstitution.yaml")

    assert evidence.import_paths == (
        (tmp_path / "rules" / "security.yaml").resolve(),
        (tmp_path / "rules" / "base.yaml").resolve(),
    )
    assert [gate.rule.id for gate in evidence.gates] == [
        "base_latency",
        "security_header",
    ]


def test_load_qanstitution_expands_gate_groups_with_provenance(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gate_groups:
  latency:
    description: Latency checks shared by local suites
    gates:
      - id: smoke_latency
        condition: tags contains 'smoke'
        gate: duration < 500
        enforcement: block
  api_baseline:
    groups:
      - latency
    gates:
      - id: no_server_errors
        condition: "true"
        gate: status < 500
        enforcement: block
gates:
  - group: api_baseline
  - id: request_id
    condition: "true"
    gate: header "X-Request-Id" exists
    enforcement: warn
""",
    )

    evidence = load_qanstitution_evidence(tmp_path / "qanstitution.yaml")

    assert [gate.id for gate in evidence.policy.gates] == [
        "smoke_latency",
        "no_server_errors",
        "request_id",
    ]
    assert [(gate.rule.id, gate.group) for gate in evidence.gates] == [
        ("smoke_latency", "latency"),
        ("no_server_errors", "api_baseline"),
        ("request_id", None),
    ]


def test_load_qanstitution_rejects_missing_gate_group_reference(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - group: missing
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Unknown gate group 'missing'"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_rejects_gate_group_cycles(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gate_groups:
  api:
    groups:
      - security
  security:
    groups:
      - api
gates:
  - group: api
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Gate group cycle detected"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_gate_group_imports_preserve_final_semantics(
    tmp_path: Path,
) -> None:
    write_yaml(
        tmp_path / "rules" / "security.yaml",
        """
project: imported-security
gate_groups:
  baseline:
    gates:
      - id: no_server_errors
        condition: "true"
        gate: status < 500
        enforcement: block
        final: true
gates:
  - group: baseline
""",
    )
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/security.yaml
gates:
  - id: no_server_errors
    condition: "true"
    gate: status < 400
    enforcement: warn
""",
    )

    with pytest.raises(QanstitutionLoadError, match="final imported gate"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


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


def test_load_qanstitution_rejects_missing_root_file(tmp_path: Path) -> None:
    with pytest.raises(QanstitutionLoadError, match="QAnstitution file not found"):
        load_qanstitution(tmp_path / "missing.yaml")


def test_load_qanstitution_rejects_unsupported_version(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
version: "5.0"
gates:
  - id: versioned
    condition: "true"
    gate: duration < 500
    enforcement: block
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Unsupported QAnstitution version"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_rejects_import_cycles(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "a.yaml",
        """
project: a
imports:
  - ./b.yaml
""",
    )
    write_yaml(
        tmp_path / "b.yaml",
        """
project: b
imports:
  - ./a.yaml
""",
    )

    with pytest.raises(QanstitutionLoadError, match="import cycle detected"):
        load_qanstitution(tmp_path / "a.yaml")


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


def test_load_qanstitution_rejects_unsupported_import_schemes(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - s3://bucket/security.yaml
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Unsupported QAnstitution import scheme"):
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


def test_load_qanstitution_rejects_symlinked_local_import(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "rules" / "real-security.yaml",
        """
project: imported-security
gates:
  - id: security_header
    condition: "true"
    gate: header "X-Request-Id" exists
    enforcement: warn
""",
    )
    (tmp_path / "rules" / "linked-security.yaml").symlink_to(
        tmp_path / "rules" / "real-security.yaml"
    )
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/linked-security.yaml
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )

    with pytest.raises(QanstitutionLoadError, match="must not use symlinks"):
        load_qanstitution(tmp_path / "qanstitution.yaml")


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


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ("tags contains 'smoke", "Unsupported QAnstitution condition syntax"),
        ("tags contains ''", "Unsupported QAnstitution condition syntax"),
        ("tags contains 'smoke' or true", "Unsupported QAnstitution condition syntax"),
        ("meta.9story == 'CHK-001'", "Unsupported QAnstitution condition syntax"),
        ("method == 'GET' # comment", "Unsupported QAnstitution condition syntax"),
        ("tags contains 'smoke\ncritical'", "must not contain control characters"),
        ("tags contains 'smoke\x00critical'", "must not contain control characters"),
    ],
)
def test_load_qanstitution_rejects_adversarial_condition_strings(
    tmp_path: Path,
    condition: str,
    message: str,
) -> None:
    write_document(
        tmp_path / "qanstitution.yaml",
        {
            "project": "checkout-api",
            "gates": [
                {
                    "id": "adversarial_condition",
                    "condition": condition,
                    "gate": "duration < 2000",
                    "enforcement": "block",
                }
            ],
        },
    )

    with pytest.raises(QanstitutionLoadError, match=message):
        load_qanstitution(tmp_path / "qanstitution.yaml")


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"project": "checkout-api", "imports": {"rules": "security.yaml"}}, "Input should be"),
        ({"project": "checkout-api", "imports": [123]}, "Input should be a valid string"),
        (
            {"project": "checkout-api", "gate_groups": []},
            "gate_groups must be a mapping",
        ),
        ({"project": "checkout-api", "gates": "not-a-list"}, "gates must be a list"),
        (
            {
                "project": "checkout-api",
                "gate_groups": {"bad\x1fgroup": {"gates": []}},
                "gates": [{"group": "bad\x1fgroup"}],
            },
            "gate group name must not contain control characters",
        ),
    ],
)
def test_load_qanstitution_rejects_adversarial_authoring_shapes(
    tmp_path: Path,
    document: object,
    message: str,
) -> None:
    write_document(tmp_path / "qanstitution.yaml", document)

    with pytest.raises(QanstitutionLoadError, match=message):
        load_qanstitution(tmp_path / "qanstitution.yaml")


@pytest.mark.parametrize(
    ("import_ref", "message"),
    [
        ("file:///etc/passwd", "Unsupported QAnstitution import scheme"),
        ("rules/bad\x00policy.yaml", "must not contain control characters"),
    ],
)
def test_load_qanstitution_rejects_adversarial_import_references(
    tmp_path: Path,
    import_ref: str,
    message: str,
) -> None:
    write_document(
        tmp_path / "project" / "qanstitution.yaml",
        {"project": "checkout-api", "imports": [import_ref]},
    )

    with pytest.raises(QanstitutionLoadError, match=message):
        load_qanstitution(tmp_path / "project" / "qanstitution.yaml")


def test_load_qanstitution_rejects_existing_absolute_import_outside_root(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.yaml"
    write_document(outside, {"project": "outside"})
    write_document(
        tmp_path / "project" / "qanstitution.yaml",
        {"project": "checkout-api", "imports": [str(outside)]},
    )

    with pytest.raises(QanstitutionLoadError, match="outside the QAnstitution root"):
        load_qanstitution(tmp_path / "project" / "qanstitution.yaml")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("project: [", "Invalid YAML"),
        ("!!python/object/apply:os.system ['echo unsafe']", "Invalid YAML"),
        ("[]", "must contain a YAML mapping"),
        ("1: checkout-api", "keys must be strings"),
        ("", "Invalid QAnstitution config"),
    ],
)
def test_load_qanstitution_rejects_invalid_yaml_documents(
    tmp_path: Path,
    body: str,
    message: str,
) -> None:
    write_yaml(tmp_path / "qanstitution.yaml", body)

    with pytest.raises(QanstitutionLoadError, match=message):
        load_qanstitution(tmp_path / "qanstitution.yaml")


def test_load_qanstitution_wraps_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    write_yaml(config_path, "project: checkout-api\n")
    original_open = Path.open

    def fail_open(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> object:
        if self == config_path.resolve():
            raise OSError("disk unavailable")
        return original_open(
            self,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(QanstitutionLoadError, match="Could not read QAnstitution file"):
        load_qanstitution(config_path)
