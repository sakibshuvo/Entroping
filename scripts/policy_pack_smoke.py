#!/usr/bin/env python3
"""Validate local policy packs as reusable release evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

import yaml

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution_evidence

SCHEMA_VERSION = "entroping.policy-pack-smoke.v1"
ARTIFACT_TYPE = "policy-pack-verification"
DEFAULT_PACK = Path("examples/policy-packs/api-baseline")
REQUIRED_FILES = (
    "README.md",
    "entroping-policy-pack.yaml",
    "examples/consumer-qanstitution.yaml",
)

Status = Literal["pass", "fail"]


class GateProvenance(TypedDict):
    """Manifest-declared local source evidence for one policy-pack gate."""

    id: str
    file: str
    final: bool


class PackProvenance(TypedDict):
    """Manifest-declared local provenance evidence for a policy pack."""

    source: str
    license: str
    supported_entroping: str
    evidence_command: str
    gates: list[GateProvenance]


class AttributionEvidence(TypedDict):
    """Human attribution evidence for a policy pack."""

    source: str
    license: str
    maintainers: list[str]
    publisher: str
    readme: str


class ConsumerExampleEvidence(TypedDict):
    """Evidence that a policy pack can be consumed as a local import."""

    path: str
    import_path: str
    local_gate_count: int
    local_gate_ids: list[str]
    gate_ids: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the example policy-pack layout through the current local "
            "QAnstitution import mechanism."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root for relative path rendering.",
    )
    parser.add_argument(
        "--pack",
        type=Path,
        default=DEFAULT_PACK,
        help="Policy-pack directory to validate.",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when required policy-pack evidence is missing.",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    pack_path = _resolve_pack_path(args.pack, root=root)
    payload = _build_payload(pack_path=pack_path, root=root)

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_markdown(payload))

    failures = _payload_failures(payload)
    if args.strict and failures:
        print("policy-pack smoke failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


def _resolve_pack_path(pack: Path, *, root: Path) -> Path:
    expanded = pack.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (root / expanded).resolve()


def _build_payload(*, pack_path: Path, root: Path) -> dict[str, object]:
    failures: list[str] = []
    manifest_path = pack_path / "entroping-policy-pack.yaml"
    manifest = _read_manifest(manifest_path, failures)

    pack_id = _string_field(manifest, "id", failures)
    license_id = _string_field(manifest, "license", failures)
    source = _local_source_field(manifest, failures)
    supported_entroping = _string_field(manifest, "entroping", failures)
    evidence_command = _string_field(manifest, "evidence_command", failures)
    gate_provenance = _gate_provenance_field(
        manifest,
        failures,
        pack_path=pack_path,
        root=root,
    )
    runtime_contract = _string_field(manifest, "runtime_contract", failures)
    entrypoint = _string_field(manifest, "entrypoint", failures)
    entrypoint = _pack_relative_path_field(
        field="entrypoint",
        value=entrypoint,
        failures=failures,
    )
    gate_prefixes = _string_list_field(manifest, "gate_prefixes", failures)
    documented_final_gates = _string_list_field(manifest, "final_gates", failures)
    maintainers = _optional_string_list_field(manifest, "maintainers", failures)
    publisher = _optional_string_field(manifest, "publisher", failures)
    _require_string_fields(
        manifest,
        fields=("name", "version"),
        failures=failures,
    )

    if runtime_contract and runtime_contract != "qanstitution-import":
        failures.append(
            "runtime_contract must be 'qanstitution-import' for current Entroping Core"
        )

    for relative_path in REQUIRED_FILES:
        if not (pack_path / relative_path).is_file():
            failures.append(f"required file missing: {relative_path}")

    entrypoint_path = pack_path / entrypoint if entrypoint else pack_path / "qanstitution.yaml"
    gate_ids: list[str] = []
    final_gate_ids: list[str] = []
    import_paths: list[str] = []
    if not entrypoint_path.is_file():
        failures.append(f"entrypoint file missing: {_display_path(entrypoint_path, root=root)}")
    else:
        try:
            evidence = load_qanstitution_evidence(entrypoint_path)
            gate_ids = sorted(gate.rule.id for gate in evidence.gates)
            final_gate_ids = sorted(gate.rule.id for gate in evidence.gates if gate.rule.final)
            import_paths = sorted(_display_path(path, root=root) for path in evidence.import_paths)
        except QanstitutionLoadError as exc:
            failures.append(f"entrypoint failed to load: {exc}")

    if gate_prefixes:
        for gate_id in gate_ids:
            if not any(gate_id.startswith(f"{prefix}.") for prefix in gate_prefixes):
                failures.append(f"gate id {gate_id!r} does not use a declared gate prefix")

    for final_gate_id in documented_final_gates:
        if final_gate_id not in gate_ids:
            failures.append(f"documented final gate {final_gate_id!r} is not loaded")
        elif final_gate_id not in final_gate_ids:
            failures.append(f"documented final gate {final_gate_id!r} is not marked final")
    _validate_gate_provenance(gate_provenance, gate_ids, final_gate_ids, failures)

    consumer_example = _load_consumer_example_evidence(
        pack_path=pack_path,
        entrypoint=entrypoint,
        failures=failures,
    )
    attribution: AttributionEvidence = {
        "source": source,
        "license": license_id,
        "maintainers": maintainers,
        "publisher": publisher,
        "readme": "README.md",
    }
    if not maintainers and not publisher:
        failures.append("manifest attribution must include at least one maintainer or publisher")

    status: Status = "fail" if failures else "pass"
    provenance: PackProvenance = {
        "source": source,
        "license": license_id,
        "supported_entroping": supported_entroping,
        "evidence_command": evidence_command,
        "gates": gate_provenance,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "status": status,
        "pack_path": _display_path(pack_path, root=root),
        "pack_id": pack_id,
        "runtime_contract": runtime_contract,
        "entrypoint": entrypoint,
        "attribution": attribution,
        "provenance": provenance,
        "imports": import_paths,
        "gate_count": len(gate_ids),
        "gate_ids": gate_ids,
        "final_gate_ids": final_gate_ids,
        "consumer_example": consumer_example,
        "consumer_gate_ids": consumer_example["gate_ids"],
        "failures": failures,
    }


def _read_manifest(path: Path, failures: list[str]) -> dict[str, object]:
    if not path.is_file():
        failures.append(f"manifest file missing: {path}")
        return {}
    try:
        return _read_yaml_mapping(path)
    except ValueError as exc:
        failures.append(str(exc))
        return {}


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        with path.open(encoding="utf-8") as handle:
            loaded: object = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"could not read YAML: {path}: {exc}") from exc

    if not isinstance(loaded, Mapping):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            raise ValueError(f"YAML keys must be strings: {path}")
        document[key] = value
    return document


def _string_field(
    document: Mapping[str, object],
    field: str,
    failures: list[str],
) -> str:
    value = document.get(field)
    if isinstance(value, str) and value.strip():
        return value
    failures.append(f"manifest field {field!r} must be a non-empty string")
    return ""


def _string_list_field(
    document: Mapping[str, object],
    field: str,
    failures: list[str],
) -> list[str]:
    value = document.get(field)
    if not isinstance(value, list):
        failures.append(f"manifest field {field!r} must be a list of strings")
        return []
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            failures.append(f"manifest field {field!r} item {index} must be a non-empty string")
            continue
        items.append(item)
    return items


def _optional_string_field(
    document: Mapping[str, object],
    field: str,
    failures: list[str],
) -> str:
    value = document.get(field)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    failures.append(f"manifest field {field!r} must be a string when present")
    return ""


def _optional_string_list_field(
    document: Mapping[str, object],
    field: str,
    failures: list[str],
) -> list[str]:
    value = document.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        failures.append(f"manifest field {field!r} must be a list of strings when present")
        return []
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            failures.append(f"manifest field {field!r} item {index} must be a non-empty string")
            continue
        items.append(item.strip())
    return items


def _pack_relative_path_field(
    *,
    field: str,
    value: str,
    failures: list[str],
) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        failures.append(f"manifest field {field!r} must be a local path under the pack")
        return ""
    return path.as_posix()


def _local_source_field(
    document: Mapping[str, object],
    failures: list[str],
) -> str:
    source = _string_field(document, "source", failures)
    if source and ("://" in source or source.startswith("git@")):
        failures.append("manifest field 'source' must be a local inspectable path")
    return source


def _gate_provenance_field(
    document: Mapping[str, object],
    failures: list[str],
    *,
    pack_path: Path,
    root: Path,
) -> list[GateProvenance]:
    value = document.get("gates")
    if not isinstance(value, list):
        failures.append("manifest field 'gates' must be a list of gate provenance objects")
        return []

    records: list[GateProvenance] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            failures.append(f"manifest field 'gates' item {index} must be an object")
            continue
        gate_id = item.get("id")
        file_value = item.get("file")
        final_value = item.get("final")
        if not isinstance(gate_id, str) or not gate_id.strip():
            failures.append(f"manifest field 'gates' item {index}.id must be a non-empty string")
            continue
        if not isinstance(file_value, str) or not file_value.strip():
            failures.append(f"manifest field 'gates' item {index}.file must be a non-empty string")
            continue
        if not isinstance(final_value, bool):
            failures.append(f"manifest field 'gates' item {index}.final must be a boolean")
            continue
        normalized_file = _pack_relative_path_field(
            field=f"gates[{index}].file",
            value=file_value,
            failures=failures,
        )
        if not normalized_file:
            continue
        file_path = Path(normalized_file)
        resolved_file = pack_path / file_path
        if not resolved_file.is_file():
            failures.append(
                "manifest gate "
                f"{gate_id!r} file is missing: {_display_path(resolved_file, root=root)}"
            )
            continue
        records.append({"id": gate_id, "file": normalized_file, "final": final_value})
    return sorted(records, key=lambda record: record["id"])


def _validate_gate_provenance(
    gate_provenance: list[GateProvenance],
    gate_ids: list[str],
    final_gate_ids: list[str],
    failures: list[str],
) -> None:
    manifest_gate_ids = sorted(record["id"] for record in gate_provenance)
    if manifest_gate_ids != gate_ids:
        failures.append("manifest gate ids must match loaded gate ids")

    final_gate_id_set = set(final_gate_ids)
    loaded_gate_id_set = set(gate_ids)
    for record in gate_provenance:
        gate_id = record["id"]
        if gate_id not in loaded_gate_id_set:
            continue
        expected_final = gate_id in final_gate_id_set
        if record["final"] is not expected_final:
            failures.append(
                f"manifest gate {gate_id!r} final flag must match loaded QAnstitution gate"
            )


def _require_string_fields(
    document: Mapping[str, object],
    *,
    fields: tuple[str, ...],
    failures: list[str],
) -> None:
    for field in fields:
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"manifest field {field!r} must be a non-empty string")


def _load_consumer_example_evidence(
    *,
    pack_path: Path,
    entrypoint: str,
    failures: list[str],
) -> ConsumerExampleEvidence:
    consumer_path = pack_path / "examples" / "consumer-qanstitution.yaml"
    default_evidence: ConsumerExampleEvidence = {
        "path": "examples/consumer-qanstitution.yaml",
        "import_path": "",
        "local_gate_count": 0,
        "local_gate_ids": [],
        "gate_ids": [],
    }
    if not consumer_path.is_file():
        failures.append("consumer example missing: examples/consumer-qanstitution.yaml")
        return default_evidence
    try:
        consumer_document = _read_yaml_mapping(consumer_path)
    except ValueError as exc:
        failures.append(str(exc))
        return default_evidence

    _validate_consumer_imports(consumer_document, failures)
    local_gate_ids = _consumer_local_gate_ids(consumer_document, failures)
    if not local_gate_ids:
        failures.append("consumer example must define at least one local gate")

    with tempfile.TemporaryDirectory(prefix="entroping-policy-pack-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        vendor_name = _vendor_directory_name(pack_path)
        vendored_pack = temp_root / "policy-packs" / vendor_name
        shutil.copytree(pack_path, vendored_pack)
        import_path = f"./policy-packs/{vendor_name}/{entrypoint or 'qanstitution.yaml'}"
        consumer_document["imports"] = [import_path]
        consumer_config = temp_root / "qanstitution.yaml"
        with consumer_config.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(consumer_document, handle, sort_keys=False)
        try:
            evidence = load_qanstitution_evidence(consumer_config)
        except QanstitutionLoadError as exc:
            failures.append(f"consumer example failed to load: {exc}")
            return {
                **default_evidence,
                "import_path": import_path,
                "local_gate_count": len(local_gate_ids),
                "local_gate_ids": local_gate_ids,
            }
    return {
        "path": "examples/consumer-qanstitution.yaml",
        "import_path": import_path,
        "local_gate_count": len(local_gate_ids),
        "local_gate_ids": local_gate_ids,
        "gate_ids": sorted(gate.rule.id for gate in evidence.gates),
    }


def _validate_consumer_imports(
    document: Mapping[str, object],
    failures: list[str],
) -> None:
    imports = document.get("imports")
    if not isinstance(imports, list) or not imports:
        failures.append("consumer example must declare at least one local import")
        return
    for index, import_ref in enumerate(imports):
        if not isinstance(import_ref, str) or not import_ref.strip():
            failures.append(f"consumer example import {index} must be a non-empty string")
            continue
        _validate_consumer_import_ref(import_ref, failures)


def _consumer_local_gate_ids(
    document: Mapping[str, object],
    failures: list[str],
) -> list[str]:
    gates = document.get("gates")
    if not isinstance(gates, list):
        failures.append("consumer example field 'gates' must be a list")
        return []
    gate_ids: list[str] = []
    for index, item in enumerate(gates):
        if not isinstance(item, Mapping):
            failures.append(f"consumer example gate {index} must be an object")
            continue
        gate_id = item.get("id")
        if not isinstance(gate_id, str) or not gate_id.strip():
            failures.append(f"consumer example gate {index}.id must be a non-empty string")
            continue
        gate_ids.append(gate_id.strip())
    return sorted(gate_ids)


def _validate_consumer_import_ref(import_ref: str, failures: list[str]) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in import_ref):
        failures.append("consumer example imports must not contain control characters")
        return
    parsed = urlparse(import_ref)
    path = Path(import_ref)
    if (
        parsed.scheme
        or parsed.netloc
        or import_ref.startswith("git@")
        or "\\" in import_ref
        or path.is_absolute()
    ):
        failures.append("consumer example imports must be local paths")
        return
    if ".." in path.parts:
        failures.append("consumer example imports must not contain traversal")


def _vendor_directory_name(pack_path: Path) -> str:
    name = pack_path.name.strip()
    if not name:
        return "policy-pack"
    safe_characters = [
        character if character.isalnum() or character in "-_." else "-"
        for character in name
    ]
    safe_name = "".join(safe_characters).strip(".-_")
    return safe_name or "policy-pack"


def _display_path(path: Path, *, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _payload_failures(payload: Mapping[str, object]) -> list[str]:
    raw_failures = payload.get("failures")
    if not isinstance(raw_failures, list):
        return ["payload failures field is not a list"]
    failures: list[str] = []
    for item in raw_failures:
        if isinstance(item, str):
            failures.append(item)
    return failures


def _render_markdown(payload: Mapping[str, object]) -> str:
    gate_ids = _string_sequence(payload.get("gate_ids"))
    final_gate_ids = _string_sequence(payload.get("final_gate_ids"))
    consumer_gate_ids = _string_sequence(payload.get("consumer_gate_ids"))
    provenance = _provenance_mapping(payload)
    provenance_gates = _gate_provenance_sequence(provenance.get("gates"))
    attribution = _mapping_field(payload.get("attribution"))
    consumer_example = _mapping_field(payload.get("consumer_example"))
    failures = _payload_failures(payload)
    lines = [
        "# Policy-Pack Smoke Evidence",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Artifact: `{payload.get('artifact_type', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Pack: `{payload.get('pack_id', '')}`",
        f"- Path: `{payload.get('pack_path', '')}`",
        f"- Runtime contract: `{payload.get('runtime_contract', '')}`",
        f"- Source: `{provenance.get('source', '')}`",
        f"- License: `{provenance.get('license', '')}`",
        f"- Maintainers: `{', '.join(_string_sequence(attribution.get('maintainers')))}`",
        f"- Publisher: `{attribution.get('publisher', '')}`",
        f"- Supported Entroping: `{provenance.get('supported_entroping', '')}`",
        f"- Evidence command: `{provenance.get('evidence_command', '')}`",
        f"- Gates: `{payload.get('gate_count', 0)}`",
        "",
        "## Provenance Gates",
        "",
    ]
    lines.extend(
        (
            f"- `{record['id']}` from `{record['file']}` "
            f"(final: `{str(record['final']).lower()}`)"
        )
        for record in provenance_gates
    )
    lines.extend(
        [
            "",
            "## Effective Gates",
            "",
        ]
    )
    lines.extend(f"- `{gate_id}`" for gate_id in gate_ids)
    lines.extend(["", "## Final Gates", ""])
    lines.extend(f"- `{gate_id}`" for gate_id in final_gate_ids)
    lines.extend(
        [
            "",
            "## Consumer Example",
            "",
            f"- Path: `{consumer_example.get('path', '')}`",
            f"- Import path: `{consumer_example.get('import_path', '')}`",
            f"- Local gates: `{consumer_example.get('local_gate_count', 0)}`",
        ]
    )
    lines.extend(["", "## Consumer Example Gates", ""])
    lines.extend(f"- `{gate_id}`" for gate_id in consumer_gate_ids)
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- none")
    return "\n".join(lines)


def _string_sequence(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _provenance_mapping(payload: Mapping[str, object]) -> Mapping[str, object]:
    provenance = payload.get("provenance")
    return _mapping_field(provenance)


def _mapping_field(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _gate_provenance_sequence(value: object) -> list[GateProvenance]:
    if not isinstance(value, list):
        return []
    records: list[GateProvenance] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        gate_id = item.get("id")
        file_value = item.get("file")
        final_value = item.get("final")
        if (
            isinstance(gate_id, str)
            and isinstance(file_value, str)
            and isinstance(final_value, bool)
        ):
            records.append({"id": gate_id, "file": file_value, "final": final_value})
    return records


if __name__ == "__main__":
    raise SystemExit(main())
