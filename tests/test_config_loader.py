"""QAnstitution loading and import tests."""

import hashlib
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def test_load_qanstitution_evidence_tracks_source_digests_and_import_chains(
    tmp_path: Path,
) -> None:
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
gates:
  - id: local_latency
    condition: "true"
    gate: duration < 500
    enforcement: block
""",
    )

    evidence = load_qanstitution_evidence(tmp_path / "qanstitution.yaml")

    assert [
        (
            source.path.relative_to(tmp_path).as_posix(),
            source.sha256,
            tuple(path.relative_to(tmp_path).as_posix() for path in source.import_chain),
        )
        for source in evidence.sources
    ] == [
        ("qanstitution.yaml", _sha256(tmp_path / "qanstitution.yaml"), ("qanstitution.yaml",)),
        (
            "rules/security.yaml",
            _sha256(tmp_path / "rules" / "security.yaml"),
            ("qanstitution.yaml", "rules/security.yaml"),
        ),
        (
            "rules/base.yaml",
            _sha256(tmp_path / "rules" / "base.yaml"),
            ("qanstitution.yaml", "rules/security.yaml", "rules/base.yaml"),
        ),
    ]
    assert {
        gate.rule.id: tuple(
            path.relative_to(tmp_path).as_posix() for path in gate.import_chain
        )
        for gate in evidence.gates
    } == {
        "base_latency": ("qanstitution.yaml", "rules/security.yaml", "rules/base.yaml"),
        "security_header": ("qanstitution.yaml", "rules/security.yaml"),
        "local_latency": ("qanstitution.yaml",),
    }


def test_load_qanstitution_rejects_invalid_utf8_before_policy_validation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "qanstitution.yaml"
    path.write_bytes(b"\xff\xfe")

    with pytest.raises(QanstitutionLoadError, match="Invalid UTF-8"):
        load_qanstitution_evidence(path)


def test_load_qanstitution_rejects_duplicate_non_final_gate_ids_across_imports(
    tmp_path: Path,
) -> None:
    write_yaml(
        tmp_path / "rules" / "a.yaml",
        """
project: imported-a
gates:
  - id: shared_policy
    condition: "true"
    gate: status < 500
    enforcement: warn
""",
    )
    write_yaml(
        tmp_path / "rules" / "b.yaml",
        """
project: imported-b
gates:
  - id: shared_policy
    condition: "true"
    gate: duration < 2000
    enforcement: warn
""",
    )
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
imports:
  - ./rules/a.yaml
  - ./rules/b.yaml
""",
    )

    with pytest.raises(QanstitutionLoadError, match="Duplicate imported gate id") as exc_info:
        load_qanstitution(tmp_path / "qanstitution.yaml")

    message = str(exc_info.value)
    assert "shared_policy" in message
    assert "a.yaml" in message
    assert "b.yaml" in message


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


def test_load_qanstitution_rejects_normalized_gate_group_name_collision(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "qanstitution.yaml"
    write_yaml(
        config_path,
        """
project: checkout-api
gate_groups:
  " api ":
    gates: []
  api:
    gates: []
gates:
  - group: api
""",
    )

    with pytest.raises(
        QanstitutionLoadError,
        match="duplicate gate group name after normalization: ' api ' and 'api'",
    ) as exc_info:
        load_qanstitution(config_path)

    assert str(config_path) in str(exc_info.value)


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


def test_load_qanstitution_rejects_symlinked_root_file(tmp_path: Path) -> None:
    target_body = """
project: outside-content-marker
gates:
  - id: external_gate
    condition: "true"
    gate: duration < 2000
    enforcement: block
"""
    write_yaml(tmp_path / "outside" / "real-qanstitution.yaml", target_body)
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "qanstitution.yaml").symlink_to(
        tmp_path / "outside" / "real-qanstitution.yaml"
    )

    with pytest.raises(QanstitutionLoadError, match="Root QAnstitution file.*symlink") as exc_info:
        load_qanstitution_evidence(tmp_path / "project" / "qanstitution.yaml")

    assert "outside-content-marker" not in str(exc_info.value)


def test_load_qanstitution_rejects_symlinked_root_parent_directory(
    tmp_path: Path,
) -> None:
    target_body = """
project: outside-parent-marker
gates:
  - id: external_parent_gate
    condition: "true"
    gate: duration < 2000
    enforcement: block
"""
    write_yaml(tmp_path / "outside" / "qanstitution.yaml", target_body)
    (tmp_path / "project").symlink_to(tmp_path / "outside", target_is_directory=True)

    with pytest.raises(QanstitutionLoadError, match="Root QAnstitution file.*symlink") as exc_info:
        load_qanstitution_evidence(tmp_path / "project" / "qanstitution.yaml")

    assert "outside-parent-marker" not in str(exc_info.value)


def test_load_qanstitution_rejects_symlinked_root_ancestor_directory(
    tmp_path: Path,
) -> None:
    target_body = """
project: outside-ancestor-marker
gates:
  - id: external_ancestor_gate
    condition: "true"
    gate: duration < 2000
    enforcement: block
"""
    write_yaml(tmp_path / "outside" / "nested" / "qanstitution.yaml", target_body)
    (tmp_path / "project").symlink_to(tmp_path / "outside", target_is_directory=True)

    with pytest.raises(QanstitutionLoadError, match="Root QAnstitution file.*symlink") as exc_info:
        load_qanstitution_evidence(tmp_path / "project" / "nested" / "qanstitution.yaml")

    assert "outside-ancestor-marker" not in str(exc_info.value)


def test_load_qanstitution_accepts_legacy_missing_version_marker(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: versioned
    condition: "true"
    gate: duration < 500
    enforcement: block
""",
    )

    law = load_qanstitution(tmp_path / "qanstitution.yaml")

    assert law.version is None


@pytest.mark.parametrize("version", ["4.0", "4.2", "5.0"])
def test_load_qanstitution_rejects_unsupported_version_with_migration_guidance(
    tmp_path: Path,
    version: str,
) -> None:
    write_yaml(
        tmp_path / "qanstitution.yaml",
        f"""
project: checkout-api
version: "{version}"
gates:
  - id: versioned
    condition: "true"
    gate: duration < 500
    enforcement: block
""",
    )

    with pytest.raises(QanstitutionLoadError) as exc_info:
        load_qanstitution(tmp_path / "qanstitution.yaml")
    message = str(exc_info.value)
    assert f"Unsupported QAnstitution version '{version}'" in message
    assert "Supported versions: 4.1" in message
    assert "QANSTITUTION_REFERENCE.md#qanstitution-schema-compatibility" in message


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
        (" true", "leading or trailing whitespace"),
        ("true ", "leading or trailing whitespace"),
        (" tags contains 'smoke' ", "leading or trailing whitespace"),
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
    ("gate_id", "message"),
    [
        (" ", "gate id must not be blank"),
        ("\nvalid", "gate id must not contain control characters"),
        ("multi\nline", "gate id must not contain control characters"),
        ("valid\t", "gate id must not contain control characters"),
        ("bad\x00id", "gate id must not contain control characters"),
    ],
)
def test_load_qanstitution_rejects_invalid_gate_ids(
    tmp_path: Path,
    gate_id: str,
    message: str,
) -> None:
    write_document(
        tmp_path / "qanstitution.yaml",
        {
            "project": "checkout-api",
            "gates": [
                {
                    "id": gate_id,
                    "condition": "true",
                    "gate": "duration < 2000",
                    "enforcement": "block",
                }
            ],
        },
    )

    with pytest.raises(QanstitutionLoadError, match=message):
        load_qanstitution(tmp_path / "qanstitution.yaml")


@pytest.mark.parametrize(
    ("assertion", "message"),
    [
        ("", "gate assertion must not be blank"),
        ("  ", "gate assertion must not be blank"),
        ("status == 200\nheader exists", "gate assertion must not contain control characters"),
        ("status\r== 200", "gate assertion must not contain control characters"),
        ("status\x00== 200", "gate assertion must not contain control characters"),
        ("status\u2028== 200", "gate assertion must not contain control characters"),
        ("status\u2029== 200", "gate assertion must not contain control characters"),
        ("# no-op", "gate assertion must be executable Hurl"),
        ("\u00a0# no-op", "gate assertion must be executable Hurl"),
        ("[", "gate assertion must be executable Hurl"),
        ("[Options", "gate assertion must be executable Hurl"),
        ("[Options]", "gate assertion must be executable Hurl"),
        ("[Asserts]", "gate assertion must be executable Hurl"),
    ],
)
def test_load_qanstitution_rejects_invalid_gate_assertions(
    tmp_path: Path,
    assertion: str,
    message: str,
) -> None:
    write_document(
        tmp_path / "qanstitution.yaml",
        {
            "project": "checkout-api",
            "gates": [
                {
                    "id": "must_check_status",
                    "condition": "true",
                    "gate": assertion,
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
        ("C:\\Windows\\policy.yaml", "must be relative"),
        ("\\\\server\\share\\policy.yaml", "must be relative"),
        ("~/policy.yaml", "must be relative"),
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

    with pytest.raises(QanstitutionLoadError, match="must be relative"):
        load_qanstitution(tmp_path / "project" / "qanstitution.yaml")


def test_load_qanstitution_rejects_absolute_import_inside_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    imported = project / "rules" / "security.yaml"
    write_document(imported, {"project": "inside"})
    write_document(
        project / "qanstitution.yaml",
        {"project": "checkout-api", "imports": [str(imported)]},
    )

    with pytest.raises(QanstitutionLoadError, match="must be relative"):
        load_qanstitution(tmp_path / "project" / "qanstitution.yaml")


def test_load_qanstitution_rejects_absolute_import_symlink_resolving_inside_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    write_document(project / "rules" / "security.yaml", {"project": "inside"})
    outside_link = tmp_path / "outside-security.yaml"
    outside_link.symlink_to(project / "rules" / "security.yaml")
    write_document(
        project / "qanstitution.yaml",
        {"project": "checkout-api", "imports": [str(outside_link)]},
    )

    with pytest.raises(QanstitutionLoadError, match="must be relative"):
        load_qanstitution(project / "qanstitution.yaml")


def test_load_qanstitution_rejects_absolute_import_symlinked_ancestor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    write_document(project / "rules" / "security.yaml", {"project": "inside"})
    outside_project = tmp_path / "outside-project"
    outside_project.symlink_to(project, target_is_directory=True)
    write_document(
        project / "qanstitution.yaml",
        {"project": "checkout-api", "imports": [str(outside_project / "rules" / "security.yaml")]},
    )

    with pytest.raises(QanstitutionLoadError, match="must be relative"):
        load_qanstitution(project / "qanstitution.yaml")


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
