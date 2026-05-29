"""Filesystem-backed QAnstitution loading and local import merging."""

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from entroping.models.qanstitution import GateRule, Qanstitution


class QanstitutionLoadError(ValueError):
    """Raised when a QAnstitution file cannot be loaded into an effective policy."""


def load_qanstitution(path: str | Path = "qanstitution.yaml") -> Qanstitution:
    """Load and validate a QAnstitution file with local imports merged first."""

    resolved = _resolve_existing_file(Path(path))
    return _load_effective(resolved, stack=(), root_dir=resolved.parent)


def _load_effective(path: Path, stack: tuple[Path, ...], root_dir: Path) -> Qanstitution:
    resolved = _resolve_existing_file(path)
    if resolved in stack:
        cycle = " -> ".join(str(item) for item in (*stack, resolved))
        msg = f"QAnstitution import cycle detected: {cycle}"
        raise QanstitutionLoadError(msg)

    raw_document = _read_yaml_mapping(resolved)
    law = _validate_document(raw_document, resolved)
    _reject_duplicate_gate_ids(law.gates, resolved)

    merged_gates: list[GateRule] = []
    next_stack = (*stack, resolved)
    for import_ref in law.imports:
        imported_path = _resolve_import(import_ref, resolved.parent, root_dir)
        imported_law = _load_effective(imported_path, stack=next_stack, root_dir=root_dir)
        merged_gates = _merge_gates(
            merged_gates,
            imported_law.gates,
            incoming_source=imported_path,
        )

    merged_gates = _merge_gates(
        merged_gates,
        law.gates,
        incoming_source=resolved,
        overriding_local=True,
    )

    effective_data = law.model_dump()
    effective_data["gates"] = [gate.model_dump() for gate in merged_gates]
    return _validate_document(effective_data, resolved)


def _resolve_existing_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        msg = f"QAnstitution file not found: {resolved}"
        raise QanstitutionLoadError(msg)
    return resolved


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        with path.open(encoding="utf-8") as handle:
            loaded: object = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in {path}: {exc}"
        raise QanstitutionLoadError(msg) from exc
    except OSError as exc:
        msg = f"Could not read QAnstitution file {path}: {exc}"
        raise QanstitutionLoadError(msg) from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, Mapping):
        msg = f"QAnstitution file must contain a YAML mapping: {path}"
        raise QanstitutionLoadError(msg)

    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            msg = f"QAnstitution keys must be strings in {path}"
            raise QanstitutionLoadError(msg)
        document[key] = value
    return document


def _validate_document(document: Mapping[str, object], path: Path) -> Qanstitution:
    try:
        return Qanstitution.model_validate(document)
    except ValidationError as exc:
        msg = f"Invalid QAnstitution config in {path}: {exc}"
        raise QanstitutionLoadError(msg) from exc


def _resolve_import(import_ref: str, base_dir: Path, root_dir: Path) -> Path:
    parsed = urlparse(import_ref)
    if parsed.scheme in {"http", "https"}:
        msg = (
            "Remote QAnstitution imports are not supported in Phase 1A local loading: "
            f"{import_ref}"
        )
        raise QanstitutionLoadError(msg)
    if parsed.scheme:
        msg = f"Unsupported QAnstitution import scheme {parsed.scheme!r}: {import_ref}"
        raise QanstitutionLoadError(msg)

    candidate = (base_dir / import_ref).expanduser().resolve()
    if not candidate.is_file():
        msg = f"Import not found: {import_ref} resolved to {candidate}"
        raise QanstitutionLoadError(msg)
    if not candidate.is_relative_to(root_dir):
        msg = (
            f"Import {import_ref!r} resolved outside the QAnstitution root "
            f"{root_dir}: {candidate}"
        )
        raise QanstitutionLoadError(msg)
    return candidate


def _reject_duplicate_gate_ids(gates: list[GateRule], path: Path) -> None:
    seen: set[str] = set()
    for gate in gates:
        if gate.id in seen:
            msg = f"Duplicate gate id {gate.id!r} in {path}"
            raise QanstitutionLoadError(msg)
        seen.add(gate.id)


def _merge_gates(
    existing: list[GateRule],
    incoming: list[GateRule],
    *,
    incoming_source: Path,
    overriding_local: bool = False,
) -> list[GateRule]:
    merged = list(existing)
    positions = {gate.id: index for index, gate in enumerate(merged)}

    for gate in incoming:
        existing_index = positions.get(gate.id)
        if existing_index is None:
            positions[gate.id] = len(merged)
            merged.append(gate)
            continue

        previous = merged[existing_index]
        if previous.final:
            source_kind = "local" if overriding_local else "imported"
            msg = (
                f"Cannot override final imported gate {gate.id!r} while merging "
                f"{source_kind} gate from {incoming_source}"
            )
            raise QanstitutionLoadError(msg)
        merged[existing_index] = gate

    return merged
