"""Local policy-pack vendoring workflow tests."""

from pathlib import Path

import pytest
import yaml

from entroping.core import policy_pack_vendor as vendor_module
from entroping.core.config_loader import load_qanstitution_evidence
from entroping.core.policy_pack_vendor import PolicyPackVendorError, vendor_policy_pack


def write_policy_pack(
    pack_path: Path,
    *,
    gate_id: str = "acme-security.no_server_errors",
    final: bool = True,
) -> None:
    (pack_path / "policies").mkdir(parents=True)
    (pack_path / "examples").mkdir()
    (pack_path / "README.md").write_text("# Acme API Pack\n", encoding="utf-8")
    (pack_path / "entroping-policy-pack.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "acme.strict-api",
                "name": "Acme Strict API",
                "version": "0.2.0",
                "license": "Apache-2.0",
                "source": ".",
                "entrypoint": "policies/main.yaml",
                "runtime_contract": "qanstitution-import",
                "entroping": ">=0.1.1-alpha,<1.0",
                "evidence_command": "uv run python scripts/policy_pack_smoke.py --strict",
                "gate_prefixes": ["acme-security"],
                "final_gates": [gate_id] if final else [],
                "gates": [{"id": gate_id, "file": "policies/security.yaml", "final": final}],
                "maintainers": ["Acme QA"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (pack_path / "policies" / "main.yaml").write_text(
        yaml.safe_dump(
            {
                "project": "acme-pack",
                "version": "4.1",
                "imports": ["./security.yaml"],
                "gates": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (pack_path / "policies" / "security.yaml").write_text(
        yaml.safe_dump(
            {
                "project": "acme-pack-security",
                "version": "4.1",
                "gates": [
                    {
                        "id": gate_id,
                        "condition": "true",
                        "gate": "status < 500",
                        "enforcement": "block",
                        "final": final,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (pack_path / "examples" / "consumer-qanstitution.yaml").write_text(
        "project: consumer\nimports:\n  - ../policies/main.yaml\ngates: []\n",
        encoding="utf-8",
    )


def write_project_config(
    project_root: Path,
    body: str = "project: checkout-api\ngates: []\n",
) -> None:
    (project_root / "qanstitution.yaml").write_text(body, encoding="utf-8")


def load_manifest(pack_path: Path) -> dict[str, object]:
    manifest = yaml.safe_load(
        (pack_path / "entroping-policy-pack.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(manifest, dict)
    return manifest


def write_manifest(pack_path: Path, manifest: dict[str, object]) -> None:
    (pack_path / "entroping-policy-pack.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def first_manifest_gate(manifest: dict[str, object]) -> dict[str, object]:
    gates = manifest["gates"]
    assert isinstance(gates, list)
    gate = gates[0]
    assert isinstance(gate, dict)
    return gate


def test_vendor_policy_pack_copies_pack_and_adds_import(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)

    result = vendor_policy_pack(
        project_root=project_root,
        config_path=project_root / "qanstitution.yaml",
        pack_path=source_pack,
    )

    assert result.pack_id == "acme.strict-api"
    assert result.destination == project_root / "policy-packs" / "acme-strict-api"
    assert result.import_ref == "./policy-packs/acme-strict-api/policies/main.yaml"
    assert result.gate_ids == ("acme-security.no_server_errors",)
    assert result.final_gate_ids == ("acme-security.no_server_errors",)
    assert (result.destination / "policies" / "security.yaml").is_file()
    document = yaml.safe_load((project_root / "qanstitution.yaml").read_text(encoding="utf-8"))
    assert document["imports"] == ["./policy-packs/acme-strict-api/policies/main.yaml"]
    evidence = load_qanstitution_evidence(project_root / "qanstitution.yaml")
    assert [gate.rule.id for gate in evidence.gates] == ["acme-security.no_server_errors"]
    assert str(result.destination) in str(evidence.gates[0].source_path)


def test_vendor_policy_pack_rejects_invalid_policy_fragment(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (source_pack / "policies" / "security.yaml").write_text(
        "project: broken\ngates:\n  - id: missing_fields\n",
        encoding="utf-8",
    )

    with pytest.raises(PolicyPackVendorError, match="entrypoint failed to load"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs").exists()
    assert (project_root / "qanstitution.yaml").read_text(encoding="utf-8") == (
        "project: checkout-api\ngates: []\n"
    )


def test_vendor_policy_pack_rejects_unsafe_destination_name(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match="destination name"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
            name="../escape",
        )

    assert not (tmp_path / "escape").exists()


def test_vendor_policy_pack_rejects_duplicate_manifest_gate_ids(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    manifest_path = source_pack / "entroping-policy-pack.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["gates"].append(dict(manifest["gates"][0]))
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(PolicyPackVendorError, match="duplicate manifest gate id"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_preserves_final_gate_behavior(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(
        project_root,
        """
project: checkout-api
gates:
  - id: acme-security.no_server_errors
    condition: "true"
    gate: status < 500
    enforcement: warn
""".lstrip(),
    )
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match="final imported gate"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs" / "acme-strict-api").exists()
    document = yaml.safe_load((project_root / "qanstitution.yaml").read_text(encoding="utf-8"))
    assert "imports" not in document


def test_vendor_policy_pack_rejects_symlinked_pack_content(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (source_pack / "policies" / "security.yaml").unlink()
    (source_pack / "outside.yaml").write_text("project: outside\ngates: []\n", encoding="utf-8")
    (source_pack / "policies" / "security.yaml").symlink_to(source_pack / "outside.yaml")

    with pytest.raises(PolicyPackVendorError, match="symlink"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs").exists()


def test_vendor_policy_pack_rejects_symlinked_config_file(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    (project_root / "real-qanstitution.yaml").write_text(
        "project: checkout-api\ngates: []\n",
        encoding="utf-8",
    )
    (project_root / "qanstitution.yaml").symlink_to(project_root / "real-qanstitution.yaml")
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match="symlinked QAnstitution"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_missing_config_file(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match="QAnstitution file not found"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_config_outside_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    outside_config = tmp_path / "outside-qanstitution.yaml"
    project_root.mkdir()
    outside_config.write_text("project: checkout-api\ngates: []\n", encoding="utf-8")
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match="must stay under project root"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=outside_config,
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_symlinked_source_pack_path(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    real_pack = tmp_path / "acme-strict-api"
    symlink_pack = tmp_path / "pack-link"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(real_pack)
    symlink_pack.symlink_to(real_pack, target_is_directory=True)

    with pytest.raises(PolicyPackVendorError, match="must not use symlinks"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=symlink_pack,
        )


def test_vendor_policy_pack_rejects_source_that_is_not_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    missing_pack = tmp_path / "missing-pack"
    project_root.mkdir()
    write_project_config(project_root)

    with pytest.raises(PolicyPackVendorError, match="source must be a directory"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=missing_pack,
        )


def test_vendor_policy_pack_rejects_missing_required_pack_file(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (source_pack / "README.md").unlink()

    with pytest.raises(PolicyPackVendorError, match="required policy-pack file missing"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("name", "", "non-empty string"),
        ("runtime_contract", "other-contract", "runtime_contract"),
        ("gate_prefixes", "acme-security", "list of strings"),
        ("gate_prefixes", [""], "item 0"),
        ("entrypoint", "https://example.com/qanstitution.yaml", "local relative path"),
        ("entrypoint", "../outside.yaml", "inside the policy-pack directory"),
        ("entrypoint", "policies/main.yaml\nbad", "control characters"),
    ],
)
def test_vendor_policy_pack_rejects_invalid_manifest_fields(
    tmp_path: Path,
    field: str,
    value: object,
    expected: str,
) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    manifest = load_manifest(source_pack)
    manifest[field] = value
    write_manifest(source_pack, manifest)

    with pytest.raises(PolicyPackVendorError, match=expected):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        ("gate_id_mismatch", "manifest gate ids"),
        ("final_flag_mismatch", "manifest final flags"),
        ("final_gates_mismatch", "manifest final_gates"),
        ("missing_gate_file", "manifest gate file not found"),
        ("prefix_mismatch", "declared gate prefix"),
        ("gate_file_url", "local relative path"),
        ("gate_file_escape", "inside the policy-pack directory"),
        ("gate_file_control", "control characters"),
        ("gates_not_list", "must be a list"),
        ("gate_not_mapping", "gate 0 must be a mapping"),
        ("gate_final_not_bool", "final must be true or false"),
    ],
)
def test_vendor_policy_pack_rejects_manifest_gate_drift(
    tmp_path: Path,
    mutator: str,
    expected: str,
) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    manifest = load_manifest(source_pack)

    if mutator == "gate_id_mismatch":
        first_manifest_gate(manifest)["id"] = "acme-security.other_gate"
    elif mutator == "final_flag_mismatch":
        first_manifest_gate(manifest)["final"] = False
    elif mutator == "final_gates_mismatch":
        manifest["final_gates"] = []
    elif mutator == "missing_gate_file":
        first_manifest_gate(manifest)["file"] = "policies/missing.yaml"
    elif mutator == "prefix_mismatch":
        manifest["gate_prefixes"] = ["other-prefix"]
    elif mutator == "gate_file_url":
        first_manifest_gate(manifest)["file"] = "https://example.com/rules.yaml"
    elif mutator == "gate_file_escape":
        first_manifest_gate(manifest)["file"] = "../rules.yaml"
    elif mutator == "gate_file_control":
        first_manifest_gate(manifest)["file"] = "policies/security.yaml\nbad"
    elif mutator == "gates_not_list":
        manifest["gates"] = {"id": "acme-security.no_server_errors"}
    elif mutator == "gate_not_mapping":
        manifest["gates"] = ["acme-security.no_server_errors"]
    elif mutator == "gate_final_not_bool":
        first_manifest_gate(manifest)["final"] = "true"
    else:
        pytest.fail(f"Unknown mutator: {mutator}")

    write_manifest(source_pack, manifest)

    with pytest.raises(PolicyPackVendorError, match=expected):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_invalid_manifest_yaml(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (source_pack / "entroping-policy-pack.yaml").write_text("[", encoding="utf-8")

    with pytest.raises(PolicyPackVendorError, match="invalid YAML"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_non_mapping_manifest_yaml(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (source_pack / "entroping-policy-pack.yaml").write_text("- item\n", encoding="utf-8")

    with pytest.raises(PolicyPackVendorError, match="must contain a mapping"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_non_string_manifest_key(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (source_pack / "entroping-policy-pack.yaml").write_text("1: value\n", encoding="utf-8")

    with pytest.raises(PolicyPackVendorError, match="keys must be strings"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_existing_destination(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (project_root / "policy-packs" / "acme-strict-api").mkdir(parents=True)

    with pytest.raises(PolicyPackVendorError, match="destination already exists"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_symlinked_destination_component(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    outside = tmp_path / "outside-policy-packs"
    project_root.mkdir()
    outside.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (project_root / "policy-packs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PolicyPackVendorError, match="destination must not use symlinks"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_destination_outside_root_directly(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(PolicyPackVendorError, match="destination must stay under project root"):
        vendor_module._validate_destination(tmp_path / "outside" / "pack", root=root)


def test_vendor_policy_pack_rolls_back_when_policy_pack_copy_fails(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)
    (project_root / "policy-packs").write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(PolicyPackVendorError, match="could not copy policy pack"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )


def test_vendor_policy_pack_rejects_duplicate_import_and_rolls_back(tmp_path: Path) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(
        project_root,
        """
project: checkout-api
imports:
  - ./policy-packs/acme-strict-api/policies/main.yaml
gates: []
""".lstrip(),
    )
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match="already imports"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs" / "acme-strict-api").exists()


@pytest.mark.parametrize(
    ("config_body", "expected"),
    [
        ("[", "Invalid YAML"),
        ("- item\n", "must contain a YAML mapping"),
        ("1: value\nproject: checkout-api\ngates: []\n", "keys must be strings"),
        (
            "project: checkout-api\nimports: rules/security.yaml\ngates: []\n",
            "imports must be a list",
        ),
        ("project: checkout-api\nimports:\n  - ''\ngates: []\n", "import 0"),
    ],
)
def test_vendor_policy_pack_rejects_invalid_consumer_config_and_rolls_back(
    tmp_path: Path,
    config_body: str,
    expected: str,
) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root, config_body)
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match=expected):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs" / "acme-strict-api").exists()


def test_vendor_policy_pack_rolls_back_empty_config_after_validation_failure(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root, "")
    write_policy_pack(source_pack)

    with pytest.raises(PolicyPackVendorError, match="entrypoint failed to load"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs" / "acme-strict-api").exists()
    assert not list(project_root.glob(".qanstitution.yaml.*.tmp"))


def test_vendor_policy_pack_rolls_back_unexpected_entrypoint_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)

    def fail_entrypoint(_path: Path) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(vendor_module, "_validate_vendored_entrypoint", fail_entrypoint)

    with pytest.raises(PolicyPackVendorError, match="boom"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs" / "acme-strict-api").exists()


def test_vendor_policy_pack_rolls_back_temporary_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "consumer"
    source_pack = tmp_path / "acme-strict-api"
    project_root.mkdir()
    write_project_config(project_root)
    write_policy_pack(source_pack)

    def fail_named_temporary_file(
        _mode: str,
        *,
        encoding: str,
        dir: Path,
        prefix: str,
        suffix: str,
        delete: bool,
    ) -> object:
        _ = (encoding, dir, prefix, suffix, delete)
        raise OSError("disk full")

    monkeypatch.setattr(
        "entroping.core.policy_pack_vendor.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )

    with pytest.raises(PolicyPackVendorError, match="temporary QAnstitution"):
        vendor_policy_pack(
            project_root=project_root,
            config_path=project_root / "qanstitution.yaml",
            pack_path=source_pack,
        )

    assert not (project_root / "policy-packs" / "acme-strict-api").exists()


def test_vendor_policy_pack_wraps_direct_yaml_read_os_error(tmp_path: Path) -> None:
    with pytest.raises(PolicyPackVendorError, match="could not read policy-pack file"):
        vendor_module._read_yaml_mapping(tmp_path)


def test_vendor_policy_pack_wraps_direct_config_read_os_error(tmp_path: Path) -> None:
    with pytest.raises(PolicyPackVendorError, match="Could not read QAnstitution file"):
        vendor_module._read_config_mapping(tmp_path)
