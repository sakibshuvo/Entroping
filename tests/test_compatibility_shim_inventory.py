from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "meta" / "compatibility-shim-retirement.json"
AUDIT_PATH = ROOT / "docs" / "technical" / "CLI_COMPATIBILITY_AUDIT.md"
REVIEW_ON = date(2026, 8, 31)
PLACEHOLDER_TOKENS = ("placeholder", "tbd", "todo", "unknown", "unowned")

ShimKind = Literal[
    "module-proxy",
    "package-monkeypatch-proxy",
    "legacy-attribute-proxy",
    "late-bound-monkeypatch-adapter",
]
Disposition = Literal["retain", "retire-when-eligible"]
SpecialShim = tuple[str, ShimKind, str, str, str, str]


class InventoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str
    kind: ShimKind
    surface: str
    source_paths: tuple[str, ...] = Field(min_length=1)
    canonical_targets: tuple[str, ...] = Field(min_length=1)
    owner: str
    disposition: Disposition
    evidence: tuple[str, ...] = Field(min_length=1)
    review_on: date
    retirement_criteria: tuple[str, ...] = Field(min_length=1)


class CompatibilityInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["entroping.compatibility-shim-retirement.v1"]
    entries: tuple[InventoryEntry, ...]


@dataclass(frozen=True, slots=True)
class DiscoveredShim:
    id: str
    kind: ShimKind
    surface: str
    source_paths: tuple[str, ...]
    canonical_targets: tuple[str, ...]
    owner: str


def _load_inventory() -> CompatibilityInventory:
    return CompatibilityInventory.model_validate_json(INVENTORY_PATH.read_text(encoding="utf-8"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _functions(path: Path) -> set[str]:
    return {
        node.name for node in ast.walk(_parse(path)) if isinstance(node, ast.FunctionDef)
    }


def _module_proxy(path: Path, root: Path) -> DiscoveredShim | None:
    tree = _parse(path)
    installs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) == "install_core_module_compat"
    ]
    if not installs:
        return None
    implementations = [
        (node.module, alias.name)
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.asname == "_implementation" and node.module is not None
    ]
    assert len(installs) == 1, f"{path}: expected one install_core_module_compat call"
    assert tuple(ast.unparse(argument) for argument in installs[0].args) == (
        "globals()", "__name__", "_implementation",
    )
    assert not installs[0].keywords
    assert len(implementations) == 1, f"{path}: expected one canonical _implementation import"
    implementation_module, implementation_name = implementations[0]
    owner = implementation_module.removeprefix("entroping.core.").replace(".", "-")
    module_name = path.stem
    return DiscoveredShim(
        f"core-{module_name.replace('_', '-')}-module-proxy",
        "module-proxy",
        f"entroping.core.{module_name}",
        (path.relative_to(root).as_posix(),),
        (f"{implementation_module}.{implementation_name}",),
        f"core-{owner}",
    )


def _assert_function(path: Path, function_name: str) -> None:
    assert function_name in _functions(path), (
        f"{path}: compatibility function {function_name!r} disappeared"
    )


def _discover_live_shims(root: Path = ROOT) -> tuple[DiscoveredShim, ...]:
    core_root = root / "src" / "entroping" / "core"
    discovered = [
        shim
        for path in sorted(core_root.rglob("*.py"))
        if (shim := _module_proxy(path, root)) is not None
    ]
    openapi_path = root / "src/entroping/bridge/openapi_to_hurl/__init__.py"
    report_init = root / "src/entroping/cli/commands/report/__init__.py"
    report_deps = root / "src/entroping/cli/commands/report/_deps.py"
    _assert_function(openapi_path, "__setattr__")
    _assert_function(openapi_path, "__getattr__")
    _assert_function(report_init, "__getattr__")
    _assert_function(report_deps, "report_dependency")
    openapi = "entroping.bridge.openapi_to_hurl"
    report = "entroping.cli.commands.report"
    specials: tuple[SpecialShim, ...] = (
        (
            "bridge-openapi-package-monkeypatch-proxy", "package-monkeypatch-proxy",
            openapi, openapi_path.relative_to(root).as_posix(),
            f"{openapi}.compiler", "bridge-openapi",
        ),
        (
            "cli-report-legacy-attribute-proxy", "legacy-attribute-proxy",
            report, report_init.relative_to(root).as_posix(), f"{report}._deps", "cli-report",
        ),
        (
            "cli-report-late-bound-monkeypatch-adapter", "late-bound-monkeypatch-adapter",
            f"{report}.report_dependency", report_deps.relative_to(root).as_posix(),
            report, "cli-report",
        ),
    )
    discovered.extend(
        DiscoveredShim(identifier, kind, surface, (source,), (target,), owner)
        for identifier, kind, surface, source, target, owner in specials
    )
    return tuple(sorted(discovered, key=lambda shim: shim.id))


def _assert_inventory_owns(
    inventory: CompatibilityInventory,
    discovered: tuple[DiscoveredShim, ...],
) -> None:
    entries = {entry.id: entry for entry in inventory.entries}
    live = {shim.id: shim for shim in discovered}
    missing = sorted(live.keys() - entries.keys())
    stale = sorted(entries.keys() - live.keys())
    missing_surfaces = [
        f"{live[shim_id].surface} ({live[shim_id].source_paths[0]})" for shim_id in missing
    ]
    assert not missing, (
        f"Unowned live shims {missing_surfaces}. Add one inventory entry for each surface."
    )
    assert not stale, f"Inventory entries have no live shim: {stale}. Retire or correct them."
    for shim_id, shim in live.items():
        entry = entries[shim_id]
        assert entry.kind == shim.kind
        assert entry.surface == shim.surface
        assert entry.source_paths == shim.source_paths
        assert entry.canonical_targets == shim.canonical_targets
        assert entry.owner == shim.owner


def _repo_file(relative_path: str, prefix: tuple[str, ...], root: Path = ROOT) -> Path:
    relative = Path(relative_path)
    assert not relative.is_absolute() and ".." not in relative.parts
    assert relative.parts[: len(prefix)] == prefix
    path = root / relative
    assert path.resolve().is_relative_to(root)
    assert not any(
        root.joinpath(*relative.parts[:index]).is_symlink()
        for index in range(1, len(relative.parts) + 1)
    )
    assert path.is_file(), f"Repository file does not exist: {relative_path}"
    return path


def _assert_evidence_exists(node_id: str) -> None:
    parts = node_id.split("::")
    assert len(parts) == 2, f"Evidence must be path::test_node: {node_id!r}"
    assert parts[0].startswith("tests/") and parts[0].endswith(".py")
    assert parts[1].startswith("test_")
    path = _repo_file(parts[0], ("tests",))
    assert parts[1] in _functions(path), f"Evidence test node does not exist: {node_id}"


def test_inventory_is_strict_complete_and_evidence_backed() -> None:
    inventory = _load_inventory()

    assert len(inventory.entries) == 42
    ids = tuple(entry.id for entry in inventory.entries)
    assert ids == tuple(sorted(ids))
    for entry in inventory.entries:
        assert entry.review_on == REVIEW_ON
        assert entry.source_paths == tuple(sorted(set(entry.source_paths)))
        assert entry.canonical_targets == tuple(sorted(set(entry.canonical_targets)))
        assert entry.evidence == tuple(sorted(set(entry.evidence)))
        for value in (
            entry.id,
            entry.surface,
            entry.owner,
            *entry.source_paths,
            *entry.canonical_targets,
            *entry.evidence,
            *entry.retirement_criteria,
        ):
            assert value.strip()
            assert not any(token in value.casefold() for token in PLACEHOLDER_TOKENS)
        for source_path in entry.source_paths:
            _repo_file(source_path, ("src", "entroping"))
        for evidence in entry.evidence:
            _assert_evidence_exists(evidence)


def test_inventory_matches_every_ast_discovered_live_shim() -> None:
    inventory = _load_inventory()
    discovered = _discover_live_shims()

    assert len(discovered) == 42
    _assert_inventory_owns(inventory, discovered)


def test_synthetic_failures_are_actionable_and_path_safe(tmp_path: Path) -> None:
    source = tmp_path / "src/entroping/core/unowned.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from entroping.core._compat import install_core_module_compat\n"
        "from entroping.core.evidence import agent_bundle as _implementation\n"
        "install_core_module_compat(globals(), __name__, _implementation)\n",
        encoding="utf-8",
    )
    shim = _module_proxy(source, tmp_path)
    assert shim is not None

    with pytest.raises(AssertionError, match=r"Unowned live shims.*Add one inventory entry"):
        _assert_inventory_owns(_load_inventory(), (shim,))
    sandbox = tmp_path / "sandbox"
    (sandbox / "tests").mkdir(parents=True)
    (sandbox / "tests/linked.py").symlink_to(sandbox / "missing.py")
    for unsafe in ("tests/../outside.py", "tests/linked.py"):
        with pytest.raises(AssertionError):
            _repo_file(unsafe, ("tests",), sandbox)


def test_live_identity_and_monkeypatch_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    for shim in _discover_live_shims():
        if shim.kind == "module-proxy":
            assert importlib.import_module(shim.surface) is importlib.import_module(
                shim.canonical_targets[0],
            )

    openapi = importlib.import_module("entroping.bridge.openapi_to_hurl")
    compiler = importlib.import_module("entroping.bridge.openapi_to_hurl.compiler")

    def replacement() -> None:
        return None

    monkeypatch.setattr(openapi, "compile_openapi_to_hurl", replacement)
    assert compiler.compile_openapi_to_hurl is replacement

    report = importlib.import_module("entroping.cli.commands.report")
    report_deps = importlib.import_module("entroping.cli.commands.report._deps")
    report_name = "run_test_quality_report"
    assert getattr(report, report_name) is getattr(report_deps, report_name)
    adapter = report_deps.report_dependency(report_name)
    with monkeypatch.context() as report_patch:
        report_patch.setattr(report, report_name, replacement)
        assert adapter() is None
    delattr(report, report_name)
    assert report_name not in vars(report)


def test_compatibility_audit_documents_census_and_retirement_protocol() -> None:
    audit = AUDIT_PATH.read_text(encoding="utf-8")

    assert "## Compatibility Shim Retirement" in audit
    assert "42 live compatibility surfaces" in audit
    assert "39 module proxies" in audit
    assert "### Six-step retirement protocol" in audit
    assert all(f"{step}." in audit for step in range(1, 7))
