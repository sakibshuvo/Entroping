"""AST-derived commit-pinned internal import closure for delivery authority."""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from scripts.factory_orchestration_git_process import git_bytes, git_text

_MAX_INDEXED_PATHS: Final = 1_024
_MAX_CLOSURE_MODULES: Final = 256
_MAX_SOURCE_BYTES: Final = 1_048_576
_MAX_AST_NODES: Final = 100_000
_MAX_IMPORT_DEPTH: Final = 32


@dataclass(frozen=True, slots=True)
class PolicySource:
    path: str
    content: bytes


class PolicyImportError(RuntimeError):
    pass


def policy_import_closure(
    *,
    roots: tuple[str, ...],
    sources: Mapping[str, bytes],
) -> tuple[str, ...]:
    return _walk_closure(
        roots=roots,
        paths=frozenset(sources),
        load=lambda path: sources[path],
    )


def committed_policy_sources(
    root: Path,
    *,
    commit: str,
    roots: tuple[str, ...],
) -> tuple[PolicySource, ...]:
    """Read the complete internal closure from one commit without execution."""

    listed = git_text(
        root,
        "ls-tree",
        "-r",
        "--name-only",
        commit,
        "--",
        "scripts",
        "src/entroping",
    )
    paths = frozenset(
        path
        for path in listed.splitlines()
        if path.endswith(".py") and _internal_path(path)
    )
    cache: dict[str, bytes] = {}

    def load(path: str) -> bytes:
        if path not in cache:
            cache[path] = git_bytes(root, "show", f"{commit}:{path}")
        return cache[path]

    closure = _walk_closure(roots=roots, paths=paths, load=load)
    return tuple(PolicySource(path, load(path)) for path in closure)


def _walk_closure(
    *,
    roots: tuple[str, ...],
    paths: frozenset[str],
    load: Callable[[str], bytes],
) -> tuple[str, ...]:
    if len(paths) > _MAX_INDEXED_PATHS:
        raise PolicyImportError("policy-import-index-limit")
    modules = _module_index(paths)
    pending: list[tuple[str, int]] = []
    for root in reversed(roots):
        _enqueue_module(pending, root, depth=0, paths=paths)
    visited: set[str] = set()
    source_bytes = 0
    ast_nodes = 0
    while pending:
        path, depth = pending.pop()
        if path in visited:
            continue
        if depth > _MAX_IMPORT_DEPTH:
            raise PolicyImportError("policy-import-depth-limit")
        if path not in paths or not _internal_path(path):
            raise PolicyImportError("policy-import-missing")
        if len(visited) >= _MAX_CLOSURE_MODULES:
            raise PolicyImportError("policy-import-module-limit")
        visited.add(path)
        content = load(path)
        source_bytes += len(content)
        if source_bytes > _MAX_SOURCE_BYTES:
            raise PolicyImportError("policy-import-source-limit")
        try:
            tree = ast.parse(content, filename=path)
        except (SyntaxError, UnicodeDecodeError, RecursionError) as exc:
            raise PolicyImportError("policy-import-invalid") from exc
        module = _module_name(path)
        for node in ast.walk(tree):
            ast_nodes += 1
            if ast_nodes > _MAX_AST_NODES:
                raise PolicyImportError("policy-import-ast-limit")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependency = _resolve_module(alias.name, modules)
                    if _internal_module(alias.name) and dependency is None:
                        raise PolicyImportError("policy-import-missing")
                    if dependency is not None:
                        _enqueue_module(
                            pending,
                            dependency,
                            depth=depth + 1,
                            paths=paths,
                        )
            if isinstance(node, ast.ImportFrom):
                for dependency in reversed(
                    _from_dependencies(node, path, module, modules)
                ):
                    _enqueue_module(
                        pending,
                        dependency,
                        depth=depth + 1,
                        paths=paths,
                    )
    return tuple(sorted(visited))


def _enqueue_module(
    pending: list[tuple[str, int]],
    path: str,
    *,
    depth: int,
    paths: frozenset[str],
) -> None:
    execution_paths = (*_parent_initializers(path, paths), path)
    indexed = tuple(enumerate(execution_paths))
    if depth + len(indexed) - 1 > _MAX_IMPORT_DEPTH:
        raise PolicyImportError("policy-import-depth-limit")
    pending.extend((candidate, depth + offset) for offset, candidate in reversed(indexed))


def _parent_initializers(path: str, paths: frozenset[str]) -> tuple[str, ...]:
    pure = PurePosixPath(path)
    parts = pure.parts[:-1]
    start = 1 if parts[:1] == ("scripts",) else 2
    candidates = (
        PurePosixPath(*parts[:index], "__init__.py").as_posix()
        for index in range(start, len(parts) + 1)
    )
    return tuple(
        candidate for candidate in candidates if candidate in paths and candidate != path
    )


def _from_dependencies(
    node: ast.ImportFrom,
    path: str,
    current_module: str,
    modules: Mapping[str, str],
) -> tuple[str, ...]:
    base = _from_base(node, path, current_module)
    if base is None or not _internal_module(base):
        return ()
    dependencies: set[str] = set()
    resolved_base = _resolve_module(base, modules)
    if resolved_base is not None:
        dependencies.add(resolved_base)
    for alias in node.names:
        if alias.name == "*":
            continue
        child = _resolve_module(f"{base}.{alias.name}", modules)
        if child is not None:
            dependencies.add(child)
    if not dependencies:
        raise PolicyImportError("policy-import-missing")
    return tuple(sorted(dependencies))


def _from_base(node: ast.ImportFrom, path: str, current_module: str) -> str | None:
    if node.level == 0:
        return node.module
    package = current_module.split(".")
    if not path.endswith("/__init__.py"):
        package.pop()
    remove = node.level - 1
    if remove > len(package):
        raise PolicyImportError("policy-import-invalid")
    if remove:
        package = package[:-remove]
    if node.module:
        package.extend(node.module.split("."))
    return ".".join(package)


def _module_index(paths: frozenset[str]) -> Mapping[str, str]:
    modules: dict[str, str] = {}
    for path in paths:
        module = _module_name(path)
        if module in modules:
            raise PolicyImportError("policy-import-ambiguous")
        modules[module] = path
    return modules


def _module_name(path: str) -> str:
    pure = PurePosixPath(path)
    parts = list(pure.parts)
    if parts[:2] == ["src", "entroping"]:
        parts = parts[1:]
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def policy_module_name(path: str) -> str:
    return _module_name(path)


def _resolve_module(module: str, modules: Mapping[str, str]) -> str | None:
    if not _internal_module(module):
        return None
    return modules.get(module)


def _internal_module(module: str) -> bool:
    return module == "scripts" or module.startswith("scripts.") or (
        module == "entroping" or module.startswith("entroping.")
    )


def _internal_path(path: str) -> bool:
    return path.startswith("scripts/") or path.startswith("src/entroping/")
