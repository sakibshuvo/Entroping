#!/usr/bin/env python3
"""Validate the local example policy pack as release evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution_evidence

SCHEMA_VERSION = "entroping.policy-pack-smoke.v1"
DEFAULT_PACK = Path("examples/policy-packs/api-baseline")
REQUIRED_FILES = (
    "README.md",
    "entroping-policy-pack.yaml",
    "qanstitution.yaml",
    "rules/security.yaml",
    "rules/reliability.yaml",
    "examples/consumer-qanstitution.yaml",
)

Status = Literal["pass", "fail"]


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
    runtime_contract = _string_field(manifest, "runtime_contract", failures)
    entrypoint = _string_field(manifest, "entrypoint", failures)
    gate_prefixes = _string_list_field(manifest, "gate_prefixes", failures)
    documented_final_gates = _string_list_field(manifest, "final_gates", failures)
    _require_string_fields(
        manifest,
        fields=("name", "version", "license", "entroping"),
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

    consumer_gate_ids = _load_consumer_gate_ids(pack_path=pack_path, failures=failures)
    status: Status = "fail" if failures else "pass"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "pack_path": _display_path(pack_path, root=root),
        "pack_id": pack_id,
        "runtime_contract": runtime_contract,
        "entrypoint": entrypoint,
        "imports": import_paths,
        "gate_count": len(gate_ids),
        "gate_ids": gate_ids,
        "final_gate_ids": final_gate_ids,
        "consumer_gate_ids": consumer_gate_ids,
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


def _load_consumer_gate_ids(*, pack_path: Path, failures: list[str]) -> list[str]:
    consumer_path = pack_path / "examples" / "consumer-qanstitution.yaml"
    if not consumer_path.is_file():
        failures.append("consumer example missing: examples/consumer-qanstitution.yaml")
        return []
    try:
        consumer_document = _read_yaml_mapping(consumer_path)
    except ValueError as exc:
        failures.append(str(exc))
        return []

    with tempfile.TemporaryDirectory(prefix="entroping-policy-pack-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        vendored_pack = temp_root / "policy-packs" / "api-baseline"
        shutil.copytree(pack_path, vendored_pack)
        consumer_document["imports"] = ["./policy-packs/api-baseline/qanstitution.yaml"]
        consumer_config = temp_root / "qanstitution.yaml"
        with consumer_config.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(consumer_document, handle, sort_keys=False)
        try:
            evidence = load_qanstitution_evidence(consumer_config)
        except QanstitutionLoadError as exc:
            failures.append(f"consumer example failed to load: {exc}")
            return []
    return sorted(gate.rule.id for gate in evidence.gates)


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
    failures = _payload_failures(payload)
    lines = [
        "# Policy-Pack Smoke Evidence",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Pack: `{payload.get('pack_id', '')}`",
        f"- Path: `{payload.get('pack_path', '')}`",
        f"- Runtime contract: `{payload.get('runtime_contract', '')}`",
        f"- Gates: `{payload.get('gate_count', 0)}`",
        "",
        "## Effective Gates",
        "",
    ]
    lines.extend(f"- `{gate_id}`" for gate_id in gate_ids)
    lines.extend(["", "## Final Gates", ""])
    lines.extend(f"- `{gate_id}`" for gate_id in final_gate_ids)
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


if __name__ == "__main__":
    raise SystemExit(main())
