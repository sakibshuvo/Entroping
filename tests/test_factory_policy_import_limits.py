from __future__ import annotations

import ast
from collections.abc import Mapping
from types import SimpleNamespace

import pytest

from scripts import factory_policy_import_closure as subject
from scripts.factory_policy_import_closure import PolicyImportError


def _package_chain(leaf_depth: int) -> tuple[str, Mapping[str, bytes], tuple[str, ...]]:
    packages = tuple(f"level_{index}" for index in range(leaf_depth - 1))
    root = "/".join(("scripts", *packages, "leaf.py"))
    initializers = ("scripts/__init__.py",) + tuple(
        "/".join(("scripts", *packages[: index + 1], "__init__.py"))
        for index in range(len(packages))
    )
    sources = {path: b"" for path in initializers}
    sources[root] = b"x=1\n"
    return root, sources, (*initializers, root)


def _limits(
    monkeypatch: pytest.MonkeyPatch,
    *,
    paths: int = 10,
    modules: int = 10,
    source_bytes: int = 100,
    ast_nodes: int = 100,
    depth: int = 10,
) -> None:
    monkeypatch.setattr(subject, "_MAX_INDEXED_PATHS", paths, raising=False)
    monkeypatch.setattr(subject, "_MAX_CLOSURE_MODULES", modules, raising=False)
    monkeypatch.setattr(subject, "_MAX_SOURCE_BYTES", source_bytes, raising=False)
    monkeypatch.setattr(subject, "_MAX_AST_NODES", ast_nodes, raising=False)
    monkeypatch.setattr(subject, "_MAX_IMPORT_DEPTH", depth, raising=False)


@pytest.mark.parametrize("path_count", (2, 3))
def test_policy_path_index_budget_has_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
    path_count: int,
) -> None:
    _limits(monkeypatch, paths=2)
    sources = {
        f"scripts/module_{index}.py": b"x=1\n" for index in range(path_count)
    }

    if path_count == 2:
        assert subject.policy_import_closure(
            roots=("scripts/module_0.py",), sources=sources
        ) == ("scripts/module_0.py",)
    else:
        with pytest.raises(PolicyImportError, match="policy-import-index-limit"):
            subject.policy_import_closure(
                roots=("scripts/module_0.py",), sources=sources
            )


@pytest.mark.parametrize("module_limit", (2, 1))
def test_policy_module_budget_has_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
    module_limit: int,
) -> None:
    _limits(monkeypatch, modules=module_limit)
    sources = {
        "scripts/root.py": b"import scripts.leaf\n",
        "scripts/leaf.py": b"x=1\n",
    }

    if module_limit == 2:
        assert len(subject.policy_import_closure(roots=("scripts/root.py",), sources=sources)) == 2
    else:
        with pytest.raises(PolicyImportError, match="policy-import-module-limit"):
            subject.policy_import_closure(roots=("scripts/root.py",), sources=sources)


@pytest.mark.parametrize("source_limit", (4, 3))
def test_policy_source_byte_budget_has_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
    source_limit: int,
) -> None:
    _limits(monkeypatch, source_bytes=source_limit)
    if source_limit == 4:
        assert subject.policy_import_closure(
            roots=("scripts/root.py",), sources={"scripts/root.py": b"x=1\n"}
        ) == ("scripts/root.py",)
    else:
        with pytest.raises(PolicyImportError, match="policy-import-source-limit"):
            subject.policy_import_closure(
                roots=("scripts/root.py",), sources={"scripts/root.py": b"x=1\n"}
            )


@pytest.mark.parametrize("node_limit", (5, 4))
def test_policy_ast_node_budget_has_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
    node_limit: int,
) -> None:
    _limits(monkeypatch, ast_nodes=node_limit)
    if node_limit == 5:
        assert subject.policy_import_closure(
            roots=("scripts/root.py",), sources={"scripts/root.py": b"x=1\n"}
        ) == ("scripts/root.py",)
    else:
        with pytest.raises(PolicyImportError, match="policy-import-ast-limit"):
            subject.policy_import_closure(
                roots=("scripts/root.py",), sources={"scripts/root.py": b"x=1\n"}
            )


@pytest.mark.parametrize("depth_limit", (1, 0))
def test_policy_import_depth_budget_has_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
    depth_limit: int,
) -> None:
    _limits(monkeypatch, depth=depth_limit)
    sources = {
        "scripts/root.py": b"import scripts.leaf\n",
        "scripts/leaf.py": b"x=1\n",
    }
    if depth_limit == 1:
        assert len(subject.policy_import_closure(roots=("scripts/root.py",), sources=sources)) == 2
    else:
        with pytest.raises(PolicyImportError, match="policy-import-depth-limit"):
            subject.policy_import_closure(roots=("scripts/root.py",), sources=sources)


def test_package_initializer_depth_exact_boundary_executes_parent_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, sources, expected_order = _package_chain(32)
    parsed: list[str] = []
    parse = ast.parse

    def record_parse(source: bytes, *, filename: str) -> ast.AST:
        parsed.append(filename)
        return parse(source, filename=filename)

    monkeypatch.setattr(
        subject,
        "ast",
        SimpleNamespace(
            parse=record_parse,
            walk=ast.walk,
            Import=ast.Import,
            ImportFrom=ast.ImportFrom,
        ),
    )

    closure = subject.policy_import_closure(roots=(root,), sources=sources)

    assert len(closure) == 33
    assert tuple(parsed) == expected_order


def test_package_initializer_depth_one_over_fails_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, sources, _expected_order = _package_chain(33)
    parsed: list[str] = []
    parse = ast.parse

    def record_parse(source: bytes, *, filename: str) -> ast.AST:
        parsed.append(filename)
        return parse(source, filename=filename)

    monkeypatch.setattr(
        subject,
        "ast",
        SimpleNamespace(
            parse=record_parse,
            walk=ast.walk,
            Import=ast.Import,
            ImportFrom=ast.ImportFrom,
        ),
    )

    with pytest.raises(PolicyImportError, match="policy-import-depth-limit"):
        subject.policy_import_closure(roots=(root,), sources=sources)

    assert parsed == []


def test_ast_parse_recursion_error_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def recurse(_source: bytes, *, filename: str) -> ast.AST:
        raise RecursionError(filename)

    monkeypatch.setattr(
        subject,
        "ast",
        SimpleNamespace(
            parse=recurse,
            walk=ast.walk,
            Import=ast.Import,
            ImportFrom=ast.ImportFrom,
        ),
    )

    with pytest.raises(PolicyImportError, match="policy-import-invalid"):
        subject.policy_import_closure(
            roots=("scripts/root.py",),
            sources={"scripts/root.py": b"x=1\n"},
        )
