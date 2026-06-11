"""Filesystem-backed QAnstitution loading and local import merging."""

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from entroping.core.path_safety import first_symlink_path_component
from entroping.models.qanstitution import (
    GateRule,
    Qanstitution,
    expand_qanstitution_gate_entries,
)
from entroping.models.qanstitution_evidence import EffectiveGateEvidence, QanstitutionEvidence


class QanstitutionLoadError(ValueError):
    """Raised when a QAnstitution file cannot be loaded into an effective policy."""


def load_qanstitution(path: str | Path = "qanstitution.yaml") -> Qanstitution:
    """Load and validate a QAnstitution file with local imports merged first."""

    return load_qanstitution_evidence(path).policy


def load_qanstitution_evidence(path: str | Path = "qanstitution.yaml") -> QanstitutionEvidence:
    """Load a QAnstitution file and retain provenance for the effective gates."""

    resolved = _resolve_existing_file(Path(path))
    return _load_effective_with_evidence(resolved, stack=(), root_dir=resolved.parent)


def _load_effective_with_evidence(
    path: Path,
    stack: tuple[Path, ...],
    root_dir: Path,
) -> QanstitutionEvidence:
    resolved = _resolve_existing_file(path)
    if resolved in stack:
        cycle = " -> ".join(str(item) for item in (*stack, resolved))
        msg = f"QAnstitution import cycle detected: {cycle}"
        raise QanstitutionLoadError(msg)

    raw_document = _read_yaml_mapping(resolved)
    law = _validate_document(raw_document, resolved)
    _reject_duplicate_gate_ids(law.gates, resolved)

    merged_gates: list[EffectiveGateEvidence] = []
    import_paths: list[Path] = []
    next_stack = (*stack, resolved)
    for import_ref in law.imports:
        imported_path = _resolve_import(import_ref, resolved.parent, root_dir)
        imported = _load_effective_with_evidence(
            imported_path,
            stack=next_stack,
            root_dir=root_dir,
        )
        _append_unique_path(import_paths, imported.root_path)
        for nested_import in imported.import_paths:
            _append_unique_path(import_paths, nested_import)
        merged_gates = _merge_gate_evidence(
            merged_gates,
            list(imported.gates),
            incoming_source=imported_path,
        )

    local_gates = [
        EffectiveGateEvidence(rule=gate.rule, source_path=resolved, group=gate.group)
        for gate in expand_qanstitution_gate_entries(raw_document)
    ]
    merged_gates = _merge_gate_evidence(
        merged_gates,
        local_gates,
        incoming_source=resolved,
        overriding_local=True,
    )

    effective_data = law.model_dump()
    effective_data["gates"] = [gate.rule.model_dump() for gate in merged_gates]
    policy = _validate_document(effective_data, resolved)
    return QanstitutionEvidence(
        policy=policy,
        root_path=resolved,
        import_paths=tuple(import_paths),
        gates=tuple(merged_gates),
    )


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
    if any(ord(character) < 32 or ord(character) == 127 for character in import_ref):
        msg = "QAnstitution import path must not contain control characters"
        raise QanstitutionLoadError(msg)

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

    raw_candidate = (base_dir / import_ref).expanduser()
    symlink_component = None
    if raw_candidate.is_relative_to(root_dir):
        symlink_component = first_symlink_path_component(raw_candidate, root=root_dir)
    if symlink_component is not None:
        msg = f"Import {import_ref!r} must not use symlinks: {symlink_component}"
        raise QanstitutionLoadError(msg)

    candidate = raw_candidate.resolve()
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


def _merge_gate_evidence(
    existing: list[EffectiveGateEvidence],
    incoming: list[EffectiveGateEvidence],
    *,
    incoming_source: Path,
    overriding_local: bool = False,
) -> list[EffectiveGateEvidence]:
    merged = list(existing)
    positions = {gate.rule.id: index for index, gate in enumerate(merged)}

    for gate_evidence in incoming:
        existing_index = positions.get(gate_evidence.rule.id)
        if existing_index is None:
            positions[gate_evidence.rule.id] = len(merged)
            merged.append(gate_evidence)
            continue

        previous = merged[existing_index]
        if previous.rule.final:
            source_kind = "local" if overriding_local else "imported"
            msg = (
                f"Cannot override final imported gate {gate_evidence.rule.id!r} while merging "
                f"{source_kind} gate from {incoming_source}"
            )
            raise QanstitutionLoadError(msg)
        merged[existing_index] = gate_evidence

    return merged


def _append_unique_path(paths: list[Path], path: Path) -> None:
    if path not in paths:
        paths.append(path)
