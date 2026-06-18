"""Local policy-pack vendoring workflow."""

import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution_evidence
from entroping.core.path_safety import first_symlink_path_component
from entroping.models.qanstitution_evidence import QanstitutionEvidence


class PolicyPackVendorError(ValueError):
    """Raised when a policy pack cannot be safely vendored."""


@dataclass(frozen=True, slots=True)
class PolicyPackVendorResult:
    """Result of vendoring a local policy pack into a project."""

    pack_id: str
    source: Path
    destination: Path
    import_ref: str
    gate_ids: tuple[str, ...]
    final_gate_ids: tuple[str, ...]


PolicyPackSelfTestStatus = Literal["pass", "fail"]
POLICY_PACK_SELF_TEST_SCHEMA_VERSION = "entroping.policy-pack-self-test.v1"
POLICY_PACK_VERIFICATION_ARTIFACT_TYPE = "policy-pack-verification"


@dataclass(frozen=True, slots=True)
class PolicyPackSelfTestCheck:
    """One local policy-pack validation check."""

    id: str
    status: PolicyPackSelfTestStatus
    message: str


@dataclass(frozen=True, slots=True)
class PolicyPackSelfTestResult:
    """Read-only validation evidence for a local policy pack."""

    status: PolicyPackSelfTestStatus
    source: Path
    pack_id: str | None
    entrypoint: str | None
    gate_ids: tuple[str, ...]
    final_gate_ids: tuple[str, ...]
    checks: tuple[PolicyPackSelfTestCheck, ...]


@dataclass(frozen=True, slots=True)
class _ValidatedPolicyPack:
    pack_id: str
    source: Path
    entrypoint: str
    gate_ids: tuple[str, ...]
    final_gate_ids: tuple[str, ...]


_REQUIRED_STRING_FIELDS = (
    "id",
    "name",
    "version",
    "license",
    "source",
    "entrypoint",
    "runtime_contract",
    "entroping",
    "evidence_command",
)
_REQUIRED_FILES = (
    "entroping-policy-pack.yaml",
    "README.md",
    "examples/consumer-qanstitution.yaml",
)


def vendor_policy_pack(
    *,
    project_root: Path,
    config_path: Path,
    pack_path: Path,
    name: str | None = None,
) -> PolicyPackVendorResult:
    """Validate and copy a local policy pack into ``policy-packs/``."""

    root = project_root.expanduser().resolve()
    config = _resolve_config(config_path, root=root)
    source = _resolve_source_pack(pack_path)
    validated = _validate_policy_pack(source)
    destination_name = _destination_name(name or source.name)
    destination = root / "policy-packs" / destination_name
    _validate_destination(destination, root=root)

    import_ref = f"./{(Path('policy-packs') / destination_name / validated.entrypoint).as_posix()}"
    try:
        _copy_pack(source, destination)
        _validate_vendored_entrypoint(destination / validated.entrypoint)
        _append_import(config, import_ref)
    except Exception as exc:
        if destination.exists():
            shutil.rmtree(destination)
        if isinstance(exc, PolicyPackVendorError):
            raise
        raise PolicyPackVendorError(str(exc)) from exc

    return PolicyPackVendorResult(
        pack_id=validated.pack_id,
        source=validated.source,
        destination=destination,
        import_ref=import_ref,
        gate_ids=validated.gate_ids,
        final_gate_ids=validated.final_gate_ids,
    )


def self_test_policy_pack(*, pack_path: Path) -> PolicyPackSelfTestResult:
    """Validate a local policy pack without copying or importing it."""

    source = pack_path.expanduser()
    checks: list[PolicyPackSelfTestCheck] = []
    try:
        source = _resolve_source_pack(pack_path)
    except PolicyPackVendorError as exc:
        return _policy_pack_self_test_result(
            status="fail",
            source=source,
            pack_id=None,
            entrypoint=None,
            gate_ids=(),
            final_gate_ids=(),
            checks=(
                PolicyPackSelfTestCheck(
                    id="source-boundary",
                    status="fail",
                    message=str(exc),
                ),
            ),
        )

    checks.append(
        PolicyPackSelfTestCheck(
            id="source-boundary",
            status="pass",
            message="source path is a local policy-pack directory without symlinks",
        )
    )

    try:
        validated = _validate_policy_pack(source)
    except PolicyPackVendorError as exc:
        checks.append(
            PolicyPackSelfTestCheck(
                id="manifest-entrypoint-gates",
                status="fail",
                message=str(exc),
            )
        )
        return _policy_pack_self_test_result(
            status="fail",
            source=source,
            pack_id=None,
            entrypoint=None,
            gate_ids=(),
            final_gate_ids=(),
            checks=tuple(checks),
        )

    checks.append(
        PolicyPackSelfTestCheck(
            id="manifest-entrypoint-gates",
            status="pass",
            message="manifest, entrypoint, gate ids, and final gates are consistent",
        )
    )

    try:
        _validate_consumer_example(source, validated=validated)
    except PolicyPackVendorError as exc:
        checks.append(
            PolicyPackSelfTestCheck(
                id="consumer-example",
                status="fail",
                message=str(exc),
            )
        )
        return _policy_pack_self_test_result(
            status="fail",
            source=source,
            pack_id=validated.pack_id,
            entrypoint=validated.entrypoint,
            gate_ids=validated.gate_ids,
            final_gate_ids=validated.final_gate_ids,
            checks=tuple(checks),
        )

    checks.extend(
        (
            PolicyPackSelfTestCheck(
                id="consumer-example",
                status="pass",
                message="consumer example loads the policy-pack gates",
            ),
            PolicyPackSelfTestCheck(
                id="local-only",
                status="pass",
                message="validation used local files only",
            ),
        )
    )
    return _policy_pack_self_test_result(
        status="pass",
        source=source,
        pack_id=validated.pack_id,
        entrypoint=validated.entrypoint,
        gate_ids=validated.gate_ids,
        final_gate_ids=validated.final_gate_ids,
        checks=tuple(checks),
    )


def policy_pack_self_test_payload(
    result: PolicyPackSelfTestResult,
    *,
    root: Path,
) -> dict[str, object]:
    """Return machine-readable policy-pack self-test evidence."""

    resolved_root = root.expanduser().resolve()
    return {
        "schema_version": POLICY_PACK_SELF_TEST_SCHEMA_VERSION,
        "artifact_type": POLICY_PACK_VERIFICATION_ARTIFACT_TYPE,
        "status": result.status,
        "pack_path": _display_path(result.source, root=resolved_root),
        "pack_id": result.pack_id,
        "entrypoint": result.entrypoint,
        "gate_ids": list(result.gate_ids),
        "final_gate_ids": list(result.final_gate_ids),
        "checks": [
            {
                "id": check.id,
                "status": check.status,
                "message": check.message,
            }
            for check in result.checks
        ],
    }


def _policy_pack_self_test_result(
    *,
    status: PolicyPackSelfTestStatus,
    source: Path,
    pack_id: str | None,
    entrypoint: str | None,
    gate_ids: tuple[str, ...],
    final_gate_ids: tuple[str, ...],
    checks: tuple[PolicyPackSelfTestCheck, ...],
) -> PolicyPackSelfTestResult:
    return PolicyPackSelfTestResult(
        status=status,
        source=source,
        pack_id=pack_id,
        entrypoint=entrypoint,
        gate_ids=gate_ids,
        final_gate_ids=final_gate_ids,
        checks=checks,
    )


def _validate_consumer_example(
    pack_path: Path,
    *,
    validated: _ValidatedPolicyPack,
) -> None:
    example_path = pack_path / "examples" / "consumer-qanstitution.yaml"
    consumer_document = _read_yaml_mapping(example_path)
    _validate_consumer_example_imports(consumer_document)
    with tempfile.TemporaryDirectory(prefix="entroping-policy-pack-self-test-") as temp_dir:
        temp_root = Path(temp_dir)
        vendored_pack = temp_root / "policy-packs" / "policy-pack"
        shutil.copytree(pack_path, vendored_pack)
        consumer_document["imports"] = [
            f"./policy-packs/policy-pack/{validated.entrypoint}"
        ]
        consumer_config = temp_root / "qanstitution.yaml"
        consumer_config.write_text(
            yaml.safe_dump(consumer_document, sort_keys=False),
            encoding="utf-8",
        )
        evidence = _load_pack_entrypoint(consumer_config)
    loaded_gate_ids = {gate.rule.id for gate in evidence.gates}
    missing_gate_ids = tuple(
        gate_id for gate_id in validated.gate_ids if gate_id not in loaded_gate_ids
    )
    if missing_gate_ids:
        missing = ", ".join(missing_gate_ids)
        msg = f"consumer example does not load policy-pack gates: {missing}"
        raise PolicyPackVendorError(msg)


def _validate_consumer_example_imports(document: Mapping[str, object]) -> None:
    imports = document.get("imports")
    if not isinstance(imports, list) or not imports:
        msg = "consumer example must declare at least one local import"
        raise PolicyPackVendorError(msg)
    for index, import_ref in enumerate(imports):
        if not isinstance(import_ref, str) or not import_ref.strip():
            msg = f"consumer example import {index} must be a non-empty string"
            raise PolicyPackVendorError(msg)
        if "://" in import_ref or import_ref.startswith("git@"):
            msg = "consumer example imports must be local paths"
            raise PolicyPackVendorError(msg)


def _resolve_config(path: Path, *, root: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        msg = f"Refusing to update symlinked QAnstitution file: {expanded}"
        raise PolicyPackVendorError(msg)
    resolved = expanded.resolve()
    if not resolved.is_file():
        msg = f"QAnstitution file not found: {resolved}"
        raise PolicyPackVendorError(msg)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"QAnstitution file must stay under project root {root}: {resolved}"
        raise PolicyPackVendorError(msg) from exc
    return resolved


def _resolve_source_pack(path: Path) -> Path:
    expanded = path.expanduser()
    symlink_component = first_symlink_path_component(expanded)
    if symlink_component is not None:
        msg = f"Policy-pack source must not use symlinks: {symlink_component}"
        raise PolicyPackVendorError(msg)
    resolved = expanded.resolve()
    if not resolved.is_dir():
        msg = f"Policy-pack source must be a directory: {resolved}"
        raise PolicyPackVendorError(msg)
    _reject_symlinked_pack_content(resolved)
    return resolved


def _reject_symlinked_pack_content(pack_path: Path) -> None:
    for path in pack_path.rglob("*"):
        if path.is_symlink():
            msg = f"Policy-pack content must not use symlinks: {path}"
            raise PolicyPackVendorError(msg)


def _validate_policy_pack(pack_path: Path) -> _ValidatedPolicyPack:
    for required_file in _REQUIRED_FILES:
        if not (pack_path / required_file).is_file():
            if required_file == "entroping-policy-pack.yaml":
                msg = f"manifest file missing: {required_file}"
            else:
                msg = f"required policy-pack file missing: {required_file}"
            raise PolicyPackVendorError(msg)

    manifest = _read_yaml_mapping(pack_path / "entroping-policy-pack.yaml")
    for field in _REQUIRED_STRING_FIELDS:
        _string_field(manifest, field)
    pack_id = _string_field(manifest, "id")
    runtime_contract = _string_field(manifest, "runtime_contract")
    if runtime_contract != "qanstitution-import":
        msg = "runtime_contract must be 'qanstitution-import'"
        raise PolicyPackVendorError(msg)

    entrypoint = _pack_relative_path(_string_field(manifest, "entrypoint"), field="entrypoint")
    gate_prefixes = _string_list_field(manifest, "gate_prefixes")
    documented_final_gates = tuple(sorted(_string_list_field(manifest, "final_gates")))
    manifest_gates = _manifest_gates(manifest)

    evidence = _load_pack_entrypoint(pack_path / entrypoint)
    gate_ids = tuple(sorted(gate.rule.id for gate in evidence.gates))
    final_gate_ids = tuple(sorted(gate.rule.id for gate in evidence.gates if gate.rule.final))

    if tuple(gate.id for gate in manifest_gates) != gate_ids:
        msg = "manifest gate ids must match loaded gate ids"
        raise PolicyPackVendorError(msg)
    if tuple(gate.id for gate in manifest_gates if gate.final) != final_gate_ids:
        msg = "manifest final flags must match loaded final gates"
        raise PolicyPackVendorError(msg)
    if documented_final_gates != final_gate_ids:
        msg = "manifest final_gates must match loaded final gates"
        raise PolicyPackVendorError(msg)
    for gate in manifest_gates:
        gate_file = _pack_relative_path(gate.file, field=f"gate {gate.id} file")
        if not (pack_path / gate_file).is_file():
            msg = f"manifest gate file not found for {gate.id}: {gate.file}"
            raise PolicyPackVendorError(msg)
    for gate_id in gate_ids:
        if not any(gate_id.startswith(f"{prefix}.") for prefix in gate_prefixes):
            msg = f"gate id {gate_id!r} does not use a declared gate prefix"
            raise PolicyPackVendorError(msg)

    return _ValidatedPolicyPack(
        pack_id=pack_id,
        source=pack_path,
        entrypoint=entrypoint,
        gate_ids=gate_ids,
        final_gate_ids=final_gate_ids,
    )


@dataclass(frozen=True, slots=True)
class _ManifestGate:
    id: str
    file: str
    final: bool


def _manifest_gates(manifest: Mapping[str, object]) -> tuple[_ManifestGate, ...]:
    raw_gates = manifest.get("gates")
    if not isinstance(raw_gates, list):
        msg = "manifest field 'gates' must be a list"
        raise PolicyPackVendorError(msg)
    gates: list[_ManifestGate] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_gates):
        if not isinstance(item, Mapping):
            msg = f"manifest gate {index} must be a mapping"
            raise PolicyPackVendorError(msg)
        gate_id = _string_field(item, "id")
        gate_file = _string_field(item, "file")
        final = item.get("final")
        if not isinstance(final, bool):
            msg = f"manifest gate {gate_id!r} final must be true or false"
            raise PolicyPackVendorError(msg)
        if gate_id in seen:
            msg = f"duplicate manifest gate id: {gate_id}"
            raise PolicyPackVendorError(msg)
        seen.add(gate_id)
        gates.append(_ManifestGate(id=gate_id, file=gate_file, final=final))
    return tuple(sorted(gates, key=lambda gate: gate.id))


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"invalid YAML in policy-pack file {path}: {exc}"
        raise PolicyPackVendorError(msg) from exc
    except OSError as exc:
        msg = f"could not read policy-pack file {path}: {exc}"
        raise PolicyPackVendorError(msg) from exc
    if not isinstance(loaded, Mapping):
        msg = f"policy-pack YAML file must contain a mapping: {path}"
        raise PolicyPackVendorError(msg)
    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            msg = f"policy-pack YAML keys must be strings: {path}"
            raise PolicyPackVendorError(msg)
        document[key] = value
    return document


def _string_field(document: Mapping[str, object], field: str) -> str:
    value = document.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    msg = f"manifest field {field!r} must be a non-empty string"
    raise PolicyPackVendorError(msg)


def _string_list_field(document: Mapping[str, object], field: str) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list):
        msg = f"manifest field {field!r} must be a list of strings"
        raise PolicyPackVendorError(msg)
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            msg = f"manifest field {field!r} item {index} must be a non-empty string"
            raise PolicyPackVendorError(msg)
        result.append(item.strip())
    return tuple(sorted(result))


def _pack_relative_path(value: str, *, field: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        msg = f"manifest {field} must not contain control characters"
        raise PolicyPackVendorError(msg)
    parsed = urlparse(value)
    if parsed.scheme:
        msg = f"manifest {field} must be a local relative path: {value}"
        raise PolicyPackVendorError(msg)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        msg = f"manifest {field} must stay inside the policy-pack directory: {value}"
        raise PolicyPackVendorError(msg)
    return path.as_posix()


def _load_pack_entrypoint(path: Path) -> QanstitutionEvidence:
    try:
        return load_qanstitution_evidence(path)
    except QanstitutionLoadError as exc:
        msg = f"entrypoint failed to load: {exc}"
        raise PolicyPackVendorError(msg) from exc


def _destination_name(value: str) -> str:
    name = value.strip()
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
    ):
        msg = f"policy-pack destination name is not safe: {value!r}"
        raise PolicyPackVendorError(msg)
    return name


def _validate_destination(destination: Path, *, root: Path) -> None:
    try:
        destination.relative_to(root)
    except ValueError as exc:
        msg = f"policy-pack destination must stay under project root {root}: {destination}"
        raise PolicyPackVendorError(msg) from exc
    symlink_component = first_symlink_path_component(destination, root=root)
    if symlink_component is not None:
        msg = f"policy-pack destination must not use symlinks: {symlink_component}"
        raise PolicyPackVendorError(msg)
    if destination.exists():
        msg = f"policy-pack destination already exists: {destination}"
        raise PolicyPackVendorError(msg)


def _copy_pack(source: Path, destination: Path) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(
                ".git",
                ".DS_Store",
                ".entroping",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                ".venv",
                "__pycache__",
                "dist",
                "reports",
            ),
        )
    except OSError as exc:
        msg = f"could not copy policy pack into project: {exc}"
        raise PolicyPackVendorError(msg) from exc


def _validate_vendored_entrypoint(path: Path) -> None:
    _ = _load_pack_entrypoint(path)


def _append_import(config_path: Path, import_ref: str) -> None:
    document = _read_config_mapping(config_path)
    imports = _imports_list(document, path=config_path)
    if import_ref in imports:
        msg = f"QAnstitution already imports vendored policy pack: {import_ref}"
        raise PolicyPackVendorError(msg)
    updated = dict(document)
    updated["imports"] = [*imports, import_ref]
    content = yaml.safe_dump(updated, sort_keys=False)
    temporary_path = _write_temporary_file(config_path, content)
    try:
        _ = _load_pack_entrypoint(temporary_path)
        temporary_path.replace(config_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def _read_config_mapping(path: Path) -> dict[str, object]:
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in QAnstitution file {path}: {exc}"
        raise PolicyPackVendorError(msg) from exc
    except OSError as exc:
        msg = f"Could not read QAnstitution file {path}: {exc}"
        raise PolicyPackVendorError(msg) from exc
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, Mapping):
        msg = f"QAnstitution file must contain a YAML mapping: {path}"
        raise PolicyPackVendorError(msg)
    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            msg = f"QAnstitution keys must be strings in {path}"
            raise PolicyPackVendorError(msg)
        document[key] = value
    return document


def _imports_list(document: Mapping[str, object], *, path: Path) -> list[str]:
    value = document.get("imports")
    if value is None:
        return []
    if not isinstance(value, list):
        msg = f"QAnstitution imports must be a list in {path}"
        raise PolicyPackVendorError(msg)
    imports: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            msg = f"QAnstitution import {index} must be a non-empty string in {path}"
            raise PolicyPackVendorError(msg)
        imports.append(item)
    return imports


def _write_temporary_file(path: Path, content: str) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            return temporary_path
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        msg = f"Could not write temporary QAnstitution file for {path}: {exc}"
        raise PolicyPackVendorError(msg) from exc


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return str(path)
