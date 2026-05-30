"""AST-based import boundary checks for the Entroping test suite."""

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportReference:
    """One imported module reference found in a Python source file."""

    module: str
    line: int


@dataclass(frozen=True)
class PythonModule:
    """A Python source module and its imported module references."""

    name: str
    path: Path
    imports: tuple[ImportReference, ...]


@dataclass(frozen=True)
class ImportBoundaryRule:
    """Forbidden import prefixes for a set of source module prefixes."""

    source_prefixes: tuple[str, ...]
    forbidden_import_prefixes: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ImportViolation:
    """A concrete architecture or provider import boundary violation."""

    source_module: str
    source_path: Path
    imported_module: str
    line: int
    reason: str


_DIRECT_PROVIDER_PREFIXES = (
    "anthropic",
    "cohere",
    "genai",
    "google.ai",
    "google.genai",
    "google.generativeai",
    "mistralai",
    "openai",
)


def collect_python_modules(root: Path, *, package_name: str) -> tuple[PythonModule, ...]:
    """Collect import references for every Python module under ``root``."""

    modules: list[PythonModule] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module_name = _module_name(path, root=root, package_name=package_name)
        modules.append(
            PythonModule(
                name=module_name,
                path=path,
                imports=_collect_imports(path, module_name=module_name),
            )
        )
    return tuple(modules)


def find_forbidden_imports(
    modules: tuple[PythonModule, ...],
    *,
    rules: tuple[ImportBoundaryRule, ...],
) -> tuple[ImportViolation, ...]:
    """Find imports that violate configured source-to-target prefix rules."""

    violations: list[ImportViolation] = []
    seen: set[tuple[str, int, str, str]] = set()
    for module in modules:
        for rule in rules:
            if not _matches_any_prefix(module.name, rule.source_prefixes):
                continue
            for imported in module.imports:
                if not _matches_any_prefix(imported.module, rule.forbidden_import_prefixes):
                    continue
                key = (module.name, imported.line, imported.module, rule.reason)
                if key in seen:
                    continue
                seen.add(key)
                violations.append(
                    ImportViolation(
                        source_module=module.name,
                        source_path=module.path,
                        imported_module=imported.module,
                        line=imported.line,
                        reason=rule.reason,
                    )
                )
    return tuple(violations)


def find_provider_imports(modules: tuple[PythonModule, ...]) -> tuple[ImportViolation, ...]:
    """Find direct model-provider SDK imports. LiteLLM is the only provider boundary."""

    rule = ImportBoundaryRule(
        source_prefixes=("entroping",),
        forbidden_import_prefixes=_DIRECT_PROVIDER_PREFIXES,
        reason="model providers must be accessed only through LiteLLM",
    )
    return find_forbidden_imports(modules, rules=(rule,))


def format_violations(violations: tuple[ImportViolation, ...]) -> str:
    """Render boundary violations as stable pytest assertion output."""

    if not violations:
        return ""
    return "\n".join(
        (
            f"{violation.source_path}:{violation.line}: "
            f"{violation.source_module} imports {violation.imported_module} "
            f"({violation.reason})"
        )
        for violation in violations
    )


def _collect_imports(path: Path, *, module_name: str) -> tuple[ImportReference, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[ImportReference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(ImportReference(alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_from_import_references(node, module_name=module_name))
        elif isinstance(node, ast.Call):
            dynamic_import = _dynamic_import_reference(node)
            if dynamic_import is not None:
                imports.append(dynamic_import)

    return tuple(_dedupe_imports(imports))


def _from_import_references(
    node: ast.ImportFrom,
    *,
    module_name: str,
) -> tuple[ImportReference, ...]:
    base = _resolve_import_from_base(node, module_name=module_name)
    if not base:
        return ()

    references = [ImportReference(base, node.lineno)]
    references.extend(ImportReference(f"{base}.{alias.name}", node.lineno) for alias in node.names)
    return tuple(references)


def _resolve_import_from_base(node: ast.ImportFrom, *, module_name: str) -> str:
    if node.level == 0:
        return node.module or ""

    current_parts = module_name.split(".")
    base_parts = current_parts[:-1]
    keep_count = max(0, len(base_parts) - (node.level - 1))
    resolved_parts = base_parts[:keep_count]
    if node.module:
        resolved_parts.extend(node.module.split("."))
    return ".".join(resolved_parts)


def _dynamic_import_reference(node: ast.Call) -> ImportReference | None:
    if not node.args:
        return None
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
        return None
    if _is_importlib_import_module(node.func) or _is_dunder_import(node.func):
        return ImportReference(first_arg.value, node.lineno)
    return None


def _is_importlib_import_module(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "import_module"
        and isinstance(node.value, ast.Name)
        and node.value.id == "importlib"
    )


def _is_dunder_import(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "__import__"


def _dedupe_imports(imports: list[ImportReference]) -> tuple[ImportReference, ...]:
    seen: set[tuple[str, int]] = set()
    deduped: list[ImportReference] = []
    for imported in imports:
        key = (imported.module, imported.line)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(imported)
    return tuple(deduped)


def _module_name(path: Path, *, root: Path, package_name: str) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    if not parts:
        return package_name
    return ".".join((package_name, *parts))


def _matches_any_prefix(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)
