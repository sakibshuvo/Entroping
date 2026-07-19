#!/usr/bin/env python3
"""Emit a deterministic taxonomy of the Entroping test suite."""

from __future__ import annotations

import argparse
import ast
import json
import keyword
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "entroping.test-taxonomy.v1"
GENERATED_BY = "scripts/test_taxonomy.py"


class TaxonomyError(Exception):
    pass


@dataclass(frozen=True)
class Category:
    name: str
    description: str


@dataclass(frozen=True)
class TestFileSummary:
    path: str
    static_test_count: int
    markers: tuple[str, ...]
    effective_markers: tuple[str, ...]
    categories: tuple[str, ...]
    attributions: tuple[CategoryAttribution, ...]


@dataclass(frozen=True)
class CategoryAttribution:
    category: str
    explicit_markers: tuple[str, ...]
    inference_rules: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class CollectedTestEvidence:
    definition_count: int
    effective_markers: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category(
        "behavior",
        "Runtime, domain, adapter, and compiler behavior tests for product code.",
    ),
    Category(
        "docs-compliance",
        "Tests that keep public docs, roadmap, release evidence, and claims honest.",
    ),
    Category(
        "script-integrity",
        "Tests that protect maintainer scripts, CI helpers, and local automation.",
    ),
    Category(
        "integration",
        "Cross-subsystem tests, installed CLI paths, and end-to-end local workflows.",
    ),
    Category("smoke", "Boot, demo, install, and fast confidence checks."),
    Category(
        "regression",
        "Tests preserving fragile behavior, compatibility promises, or fixed bugs.",
    ),
    Category(
        "security",
        "Negative tests for secrets, redaction, path handling, subprocess, and policy risk.",
    ),
)

REQUIRED_CATEGORIES = tuple(category.name for category in CATEGORIES)
STRICT_EXPLICIT_CATEGORIES = ("integration", "regression", "security")
PROVENANCE_NAMES = ("explicit", "inferred", "mixed")

PYTEST_MARKER_TO_CATEGORY = {
    "unit": "behavior",
    "adapter": "behavior",
    "integration": "integration",
    "smoke": "smoke",
    "regression": "regression",
    "security": "security",
}

DOCS_TOKENS = (
    "docs",
    "documentation",
    "readme",
    "release_docs",
    "release_evidence",
    "launch_readiness",
    "stable_core_readiness",
    "public_claims",
    "ci_workflow",
)

SCRIPT_TOKENS = (
    "script",
    "scripts",
    "repo_hygiene",
    "shell_quality",
    "audit_quality",
    "backlog_health",
    "dependency_license",
    "deepseek_worker",
    "opencode_worker",
    "ai_jobs",
    "release_check",
    "release_evidence",
    "performance_smoke",
    "policy_pack_smoke",
    "downstream_smoke",
    "local_wheel_install_smoke",
)

INTEGRATION_TOKENS = (
    "integration",
    "e2e",
    "downstream",
    "local_wheel_install",
    "cli_real_hurl",
)

SMOKE_TOKENS = (
    "smoke",
    "demo",
    "cli_real_hurl",
    "local_wheel_install",
    "downstream",
)

REGRESSION_TOKENS = (
    "regression",
    "architecture_boundaries",
    "compatibility",
    "schema_contract",
    "release_docs",
    "stable_core_readiness",
)

SECURITY_TOKENS = (
    "security",
    "redaction",
    "secret",
    "path_safety",
    "safe_write",
    "hurl_runner",
    "hurl_validator",
    "traffic_redactor",
    "policy_pack_vendor",
    "litellm_client",
    "config_writer",
)


def _marker_name(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not isinstance(target, ast.Attribute):
        return None
    marker = target.attr
    mark_value = target.value
    if (
        isinstance(mark_value, ast.Attribute)
        and mark_value.attr == "mark"
        and isinstance(mark_value.value, ast.Name)
        and mark_value.value.id == "pytest"
    ):
        return marker
    return None


def _is_literal_expression(expression: ast.expr) -> bool:
    if any(isinstance(node, ast.Call) for node in ast.walk(expression)):
        return False
    try:
        ast.literal_eval(expression)
    except (ValueError, TypeError, RecursionError):
        return False
    return True


def _marker_arguments_are_static(expression: ast.expr) -> bool:
    if not isinstance(expression, ast.Call):
        return True
    keyword_values = _call_keyword_values(expression)
    return (
        keyword_values is not None
        and all(_is_literal_expression(argument) for argument in expression.args)
        and all(
            _is_literal_expression(value) for value in keyword_values.values()
        )
    )


def _markers(tree: ast.AST) -> tuple[str, ...]:
    markers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for decorator in node.decorator_list:
                marker = _marker_name(decorator)
                if marker:
                    markers.add(marker)
    return tuple(sorted(markers))


def _static_marker_names(expression: ast.expr) -> tuple[str, ...] | None:
    if isinstance(expression, ast.List | ast.Tuple):
        markers: set[str] = set()
        for element in expression.elts:
            if isinstance(element, ast.List | ast.Tuple):
                return None
            element_markers = _static_marker_names(element)
            if element_markers is None:
                return None
            markers.update(element_markers)
        return tuple(sorted(markers))
    marker = _marker_name(expression)
    if (
        marker is None
        or marker == "parametrize"
        or not _marker_arguments_are_static(expression)
    ):
        return None
    return (marker,)


def _import_bound_name(statement: ast.Import | ast.ImportFrom, imported: ast.alias) -> str:
    return imported.asname or imported.name.split(".", maxsplit=1)[0]


def _is_canonical_pytest_import(
    statement: ast.Import | ast.ImportFrom,
    imported: ast.alias,
) -> bool:
    bound_name = _import_bound_name(statement, imported)
    return (
        isinstance(statement, ast.Import)
        and imported.name == "pytest"
        and bound_name == "pytest"
    ) or (
        isinstance(statement, ast.ImportFrom)
        and statement.level == 0
        and statement.module == "cli_test_support"
        and imported.name == "pytest"
        and bound_name == "pytest"
    )


def _unmodeled_scope_binds_pytest(statement: ast.stmt) -> bool:
    for node in ast.walk(statement):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if node.id == "pytest":
                return True
        elif isinstance(node, ast.Import | ast.ImportFrom):
            if any(
                _import_bound_name(node, imported) == "pytest"
                for imported in node.names
            ):
                return True
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name == "pytest":
                return True
        elif (
            isinstance(node, ast.ExceptHandler)
            and node.name == "pytest"
        ) or (
            isinstance(node, ast.MatchAs | ast.MatchStar)
            and node.name == "pytest"
        ) or (
            isinstance(node, ast.MatchMapping)
            and node.rest == "pytest"
        ):
            return True
    return False


def _target_root_name(target: ast.expr) -> str | None:
    current = target
    while isinstance(current, ast.Attribute | ast.Subscript):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _assignment_mutates_pytest_namespace(statement: ast.stmt) -> bool:
    targets, _value = _assignment_targets_and_value(statement)
    return any(_target_root_name(target) == "pytest" for target in targets)


def _statement_pytest_binding(
    statement: ast.stmt,
    pytest_available: bool,
) -> bool:
    if isinstance(statement, ast.Import | ast.ImportFrom):
        for imported in statement.names:
            if _import_bound_name(statement, imported) != "pytest":
                continue
            pytest_available = _is_canonical_pytest_import(statement, imported)
        return pytest_available
    if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytest"
            for target in statement.targets
    ):
        return False
    if _assignment_mutates_pytest_namespace(statement):
        return False
    if (
        isinstance(statement, ast.AnnAssign | ast.AugAssign)
        and isinstance(statement.target, ast.Name)
        and statement.target.id == "pytest"
    ) or (
        isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and statement.name == "pytest"
    ):
        return False
    modeled = isinstance(
        statement,
        ast.Assign
        | ast.AnnAssign
        | ast.AugAssign
        | ast.FunctionDef
        | ast.AsyncFunctionDef
        | ast.ClassDef,
    )
    if not modeled and _unmodeled_scope_binds_pytest(statement):
        return False
    return pytest_available


def _assigned_pytest_markers(
    body: list[ast.stmt],
    *,
    inherited_pytest_available: bool,
) -> tuple[str, ...] | None:
    markers: tuple[str, ...] = ()
    pytest_available = inherited_pytest_available
    for statement in body:
        if isinstance(statement, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in statement.targets
            ):
                parsed_markers = (
                    _static_marker_names(statement.value) if pytest_available else None
                )
                if parsed_markers is None:
                    return None
                markers = parsed_markers
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "pytestmark"
            and statement.value is not None
        ):
            parsed_markers = (
                _static_marker_names(statement.value) if pytest_available else None
            )
            if parsed_markers is None:
                return None
            markers = parsed_markers
        elif _direct_bound_names(statement) & {"*", "pytestmark"}:
            return None
        pytest_available = _statement_pytest_binding(statement, pytest_available)
    return markers


def _decorator_markers(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    *,
    pytest_available: bool,
) -> tuple[str, ...]:
    if not pytest_available:
        return ()
    return tuple(
        sorted(
            marker
            for decorator in node.decorator_list
            if (marker := _marker_name(decorator)) is not None
        )
    )


def _call_keyword_values(call: ast.Call) -> dict[str, ast.expr] | None:
    if any(keyword.arg is None for keyword in call.keywords):
        return None
    names = [keyword.arg for keyword in call.keywords if keyword.arg is not None]
    if len(names) != len(set(names)):
        return None
    return {
        keyword.arg: keyword.value
        for keyword in call.keywords
        if keyword.arg is not None
    }


def _static_argname_values(
    expression: ast.expr | None,
) -> tuple[tuple[str, ...], bool] | None:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        names = tuple(part.strip() for part in expression.value.split(","))
        sequence_form = False
    elif isinstance(expression, ast.List | ast.Tuple):
        static_names: list[str] = []
        for element in expression.elts:
            if not (
                isinstance(element, ast.Constant)
                and isinstance(element.value, str)
            ):
                return None
            static_names.append(element.value)
        names = tuple(static_names)
        sequence_form = True
    else:
        return None
    if (
        not names
        or any(
            not name
            or not name.isidentifier()
            or keyword.iskeyword(name)
            or name in {"cls", "request", "self"}
            for name in names
        )
        or len(names) != len(set(names))
    ):
        return None
    return names, sequence_form


def _static_indirect(
    expression: ast.expr | None,
    argnames: tuple[str, ...],
) -> bool:
    if expression is None:
        return True
    if isinstance(expression, ast.Constant):
        return isinstance(expression.value, bool)
    if not isinstance(expression, ast.List | ast.Tuple):
        return False
    names: list[str] = []
    for element in expression.elts:
        if not (
            isinstance(element, ast.Constant)
            and isinstance(element.value, str)
        ):
            return False
        names.append(element.value)
    return len(names) == len(set(names)) and set(names) <= set(argnames)


def _static_scope(expression: ast.expr | None) -> bool:
    return expression is None or (
        isinstance(expression, ast.Constant)
        and (
            expression.value is None
            or expression.value
            in {"class", "function", "module", "package", "session"}
        )
    )


def _static_ids(expression: ast.expr | None, *, row_count: int) -> bool:
    if expression is None:
        return True
    if isinstance(expression, ast.Constant):
        return expression.value is None
    return (
        isinstance(expression, ast.List | ast.Tuple)
        and len(expression.elts) == row_count
        and all(
            isinstance(element, ast.Constant)
            and (element.value is None or isinstance(element.value, str))
            for element in expression.elts
        )
    )


def _static_parametrize_contract(
    decorator: ast.Call,
) -> tuple[tuple[str, ...], bool, ast.List | ast.Tuple] | None:
    keyword_values = _call_keyword_values(decorator)
    if keyword_values is None or len(decorator.args) > 4:
        return None
    supported = {"argnames", "argvalues", "ids", "indirect", "scope"}
    if not keyword_values.keys() <= supported:
        return None
    positional_names = ("argnames", "argvalues", "indirect", "ids")
    if any(name in keyword_values for name in positional_names[: len(decorator.args)]):
        return None
    argnames = decorator.args[0] if decorator.args else keyword_values.get("argnames")
    argvalues = (
        decorator.args[1]
        if len(decorator.args) >= 2
        else keyword_values.get("argvalues")
    )
    indirect = (
        decorator.args[2]
        if len(decorator.args) >= 3
        else keyword_values.get("indirect")
    )
    ids = (
        decorator.args[3]
        if len(decorator.args) >= 4
        else keyword_values.get("ids")
    )
    static_contract = _static_argname_values(argnames)
    if static_contract is None:
        return None
    static_argnames, sequence_form = static_contract
    if not _static_indirect(indirect, static_argnames):
        return None
    if not isinstance(argvalues, ast.List | ast.Tuple) or not argvalues.elts:
        return None
    if not _static_scope(keyword_values.get("scope")) or not _static_ids(
        ids,
        row_count=len(argvalues.elts),
    ):
        return None
    return static_argnames, sequence_form, argvalues


def _pytest_param_row_markers(row: ast.Call) -> tuple[str, ...] | None:
    if not (
        isinstance(row.func, ast.Attribute)
        and isinstance(row.func.value, ast.Name)
        and row.func.value.id == "pytest"
        and row.func.attr == "param"
    ):
        return None
    keyword_values = _call_keyword_values(row)
    if keyword_values is None or not keyword_values.keys() <= {"id", "marks"}:
        return None
    if not row.args or any(
        not _is_literal_expression(argument) for argument in row.args
    ):
        return None
    row_id = keyword_values.get("id")
    if row_id is not None and not (
        isinstance(row_id, ast.Constant)
        and (row_id.value is None or isinstance(row_id.value, str))
    ):
        return None
    marks = keyword_values.get("marks")
    if marks is None:
        return ()
    return _static_marker_names(marks)


def _parametrize_preserves_collection(
    decorator: ast.Call,
) -> tuple[str, ...] | None:
    contract = _static_parametrize_contract(decorator)
    if contract is None:
        return None
    argnames, sequence_form, argvalues = contract
    for row in argvalues.elts:
        if isinstance(row, ast.Call):
            if (
                _pytest_param_row_markers(row) is None
                or len(row.args) != len(argnames)
            ):
                return None
        elif not _is_literal_expression(row) or (
            (sequence_form or len(argnames) > 1)
            and (
                not isinstance(row, ast.List | ast.Tuple)
                or len(row.elts) != len(argnames)
            )
        ):
            return None
    return argnames


def _parameter_row_markers(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    *,
    pytest_available: bool,
) -> tuple[str, ...]:
    if not pytest_available:
        return ()
    markers: set[str] = set()
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or _marker_name(decorator) != "parametrize":
            continue
        contract = _static_parametrize_contract(decorator)
        if contract is None:
            continue
        _argnames, _sequence_form, argvalues = contract
        decorator_markers: set[str] = set()
        for row in argvalues.elts:
            if not isinstance(row, ast.Call):
                continue
            row_markers = _pytest_param_row_markers(row)
            if row_markers is None:
                decorator_markers.clear()
                break
            decorator_markers.update(row_markers)
        markers.update(decorator_markers)
    return tuple(sorted(markers))


def _test_class_is_statically_collectable(node: ast.ClassDef) -> bool:
    if node.bases or node.keywords:
        return False
    test_enabled = True
    for statement in node.body:
        bound_names = _direct_bound_names(statement)
        if bound_names & {"__init__", "__new__"}:
            return False
        assigned, assigned_value = _assigned_boolean(statement, "__test__")
        if assigned:
            test_enabled = assigned_value
    return test_enabled


def _decorators_preserve_collection(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    *,
    pytest_available: bool,
) -> bool:
    if not node.decorator_list:
        return True
    if not pytest_available:
        return False
    parametrized_names: set[str] = set()
    defaulted_arguments: set[str] = set()
    function_arguments = (
        {
            argument.arg
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        }
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        else None
    )
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        positional = [*node.args.posonlyargs, *node.args.args]
        defaulted_arguments.update(
            argument.arg
            for argument in (
                positional[-len(node.args.defaults) :]
                if node.args.defaults
                else []
            )
        )
        defaulted_arguments.update(
            argument.arg
            for argument, default in zip(
                node.args.kwonlyargs,
                node.args.kw_defaults,
                strict=True,
            )
            if default is not None
        )
    for decorator in node.decorator_list:
        marker = _marker_name(decorator)
        if marker is None:
            return False
        if marker == "parametrize":
            if not isinstance(decorator, ast.Call):
                return False
            argnames = _parametrize_preserves_collection(decorator)
            if (
                argnames is None
                or function_arguments is None
                or parametrized_names.intersection(argnames)
                or not set(argnames) <= function_arguments
                or bool(defaulted_arguments.intersection(argnames))
            ):
                return False
            parametrized_names.update(argnames)
        elif not _marker_arguments_are_static(decorator):
            return False
    return True


def _assignment_target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.List | ast.Tuple):
        names: set[str] = set()
        for element in target.elts:
            names.update(_assignment_target_names(element))
        return names
    if (
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Call)
        and isinstance(target.value.func, ast.Name)
        and target.value.func.id in {"globals", "locals", "vars"}
        and not target.value.args
        and not target.value.keywords
        and isinstance(target.slice, ast.Constant)
        and isinstance(target.slice.value, str)
    ):
        return {target.slice.value}
    return set()


def _namespace_mutation_call(node: ast.AST) -> ast.Call | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Name)
        and node.func.value.func.id in {"globals", "locals", "vars"}
        and not node.func.value.args
        and not node.func.value.keywords
    ):
        return node
    return None


def _namespace_update_names(call: ast.Call) -> set[str]:
    if len(call.args) > 1 or any(item.arg is None for item in call.keywords):
        return {"*"}
    names = {item.arg for item in call.keywords if item.arg is not None}
    if not call.args:
        return names
    mapping = call.args[0]
    if not isinstance(mapping, ast.Dict):
        return {"*"}
    for key in mapping.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            names.add(key.value)
        else:
            names.add("*")
    return names


def _namespace_single_key_name(call: ast.Call) -> set[str]:
    if (
        call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ):
        return {call.args[0].value}
    return {"*"}


def _namespace_call_mutation_names(call: ast.Call) -> set[str]:
    assert isinstance(call.func, ast.Attribute)
    if call.func.attr == "update":
        return _namespace_update_names(call)
    if call.func.attr in {"__delitem__", "__setitem__", "pop", "setdefault"}:
        return _namespace_single_key_name(call)
    if call.func.attr in {"clear", "popitem"}:
        return {"*"}
    return set()


def _namespace_mutation_names(statement: ast.stmt) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(statement):
        call = _namespace_mutation_call(node)
        if call is not None:
            names.update(_namespace_call_mutation_names(call))
    return names


def _direct_bound_names(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.Assign):
        names: set[str] = set()
        for target in statement.targets:
            names.update(_assignment_target_names(target))
        return names
    if isinstance(statement, ast.AnnAssign | ast.AugAssign):
        return _assignment_target_names(statement.target)
    if isinstance(statement, ast.Import | ast.ImportFrom):
        return {
            _import_bound_name(statement, imported) for imported in statement.names
        }
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return {statement.name}
    names = {
        node.id
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store | ast.Del)
    }
    names.update(_namespace_mutation_names(statement))
    for node in ast.walk(statement):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names.update(
                _import_bound_name(node, imported) for imported in node.names
            )
            continue
        bound_name: str | None = None
        if isinstance(
            node,
            ast.FunctionDef
            | ast.AsyncFunctionDef
            | ast.ClassDef
            | ast.ExceptHandler
            | ast.MatchAs
            | ast.MatchStar,
        ):
            bound_name = node.name
        elif isinstance(node, ast.MatchMapping):
            bound_name = node.rest
        if bound_name is not None:
            names.add(bound_name)
    return names


def _assigned_boolean(
    statement: ast.stmt,
    name: str,
) -> tuple[bool, bool]:
    is_assignment = (
        isinstance(statement, ast.Assign)
        and any(
            name in _assignment_target_names(target)
            for target in statement.targets
        )
    ) or (
        isinstance(statement, ast.AnnAssign)
        and name in _assignment_target_names(statement.target)
    )
    if is_assignment:
        assert isinstance(statement, ast.Assign | ast.AnnAssign)
        value: ast.expr | None = statement.value
    elif (
        name in _direct_bound_names(statement)
        or "*" in _direct_bound_names(statement)
    ):
        return True, False
    else:
        return False, False
    enabled = (
        isinstance(value, ast.Constant)
        and isinstance(value.value, bool)
        and value.value
    )
    return True, enabled


def _module_collection_enabled(body: list[ast.stmt]) -> bool:
    enabled = True
    for statement in body:
        assigned, assigned_value = _assigned_boolean(statement, "__test__")
        if assigned:
            enabled = assigned_value
    return enabled


def _module_scope_can_abort(node: ast.AST) -> bool:
    if isinstance(node, ast.Raise | ast.Assert):
        return True
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
        return False
    return any(_module_scope_can_abort(child) for child in ast.iter_child_nodes(node))


def _assignment_targets_and_value(
    statement: ast.stmt,
) -> tuple[list[ast.expr], ast.expr | None]:
    if isinstance(statement, ast.Assign):
        return statement.targets, statement.value
    if isinstance(statement, ast.AnnAssign):
        return [statement.target], statement.value
    if isinstance(statement, ast.AugAssign):
        return [statement.target], None
    return [], None


def _target_test_attribute_control(
    target: ast.expr,
    *,
    enabled: bool,
) -> tuple[str, bool] | None:
    if (
        isinstance(target, ast.Attribute)
        and target.attr == "__test__"
        and isinstance(target.value, ast.Name)
    ):
        return target.value.id, enabled
    if (
        isinstance(target, ast.Subscript)
        and isinstance(target.slice, ast.Constant)
        and target.slice.value == "__test__"
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "__dict__"
        and isinstance(target.value.value, ast.Name)
    ):
        return target.value.value.id, enabled
    return None


def _setattr_test_attribute_control(node: ast.AST) -> tuple[str, bool] | None:
    is_setattr = (
        isinstance(node, ast.Call)
        and (
            (
                isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
            )
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"__setattr__", "setattr"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"builtins", "object"}
            )
        )
    )
    if not (
        is_setattr
        and isinstance(node, ast.Call)
        and len(node.args) >= 3
        and isinstance(node.args[0], ast.Name)
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "__test__"
    ):
        return None
    assigned = node.args[2]
    enabled = (
        isinstance(assigned, ast.Constant)
        and isinstance(assigned.value, bool)
        and assigned.value
    )
    return node.args[0].id, enabled


def _dict_setitem_test_attribute_control(
    node: ast.AST,
) -> tuple[str, bool] | None:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setitem__"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "__dict__"
        and isinstance(node.func.value.value, ast.Name)
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "__test__"
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, bool)
    ):
        return None
    return node.func.value.value.id, node.args[1].value


def _dict_update_test_attribute_control(node: ast.AST) -> tuple[str, bool] | None:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "__dict__"
        and isinstance(node.func.value.value, ast.Name)
        and len(node.args) <= 1
        and all(item.arg is not None for item in node.keywords)
    ):
        return None
    entries: list[tuple[str | None, ast.expr]] = [
        (item.arg, item.value) for item in node.keywords
    ]
    if node.args:
        mapping = node.args[0]
        if not isinstance(mapping, ast.Dict):
            return None
        entries.extend(
            (
                key.value
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
                else None,
                value,
            )
            for key, value in zip(mapping.keys, mapping.values, strict=True)
        )
    for key, value in entries:
        if key == "__test__":
            enabled = (
                isinstance(value, ast.Constant)
                and isinstance(value.value, bool)
                and value.value
            )
            return node.func.value.value.id, enabled
    return None


def _test_attribute_controls(statement: ast.stmt) -> tuple[tuple[str, bool], ...]:
    targets, value = _assignment_targets_and_value(statement)
    enabled = (
        isinstance(value, ast.Constant)
        and isinstance(value.value, bool)
        and value.value
    )
    controls = [
        control
        for target in targets
        if (
            control := _target_test_attribute_control(
                target,
                enabled=enabled,
            )
        )
        is not None
    ]
    if isinstance(statement, ast.Expr):
        for parser in (
            _setattr_test_attribute_control,
            _dict_setitem_test_attribute_control,
            _dict_update_test_attribute_control,
        ):
            control = parser(statement.value)
            if control is not None:
                controls.append(control)
    return tuple(controls)


def _nested_test_attribute_names(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.Assign | ast.AnnAssign | ast.AugAssign | ast.Expr):
        return set()
    names: set[str] = set()
    for node in ast.walk(statement):
        control = (
            _target_test_attribute_control(node, enabled=False)
            if isinstance(node, ast.expr)
            else None
        )
        if control is not None:
            names.add(control[0])
            continue
        for parser in (
            _setattr_test_attribute_control,
            _dict_setitem_test_attribute_control,
            _dict_update_test_attribute_control,
        ):
            parsed = parser(node)
            if parsed is not None:
                names.add(parsed[0])
    return names


def _function_evidence(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    inherited_markers: set[str],
    pytest_available: bool,
) -> CollectedTestEvidence | None:
    if not _decorators_preserve_collection(
        node,
        pytest_available=pytest_available,
    ):
        return None
    markers = (
        inherited_markers
        | set(_decorator_markers(node, pytest_available=pytest_available))
        | set(_parameter_row_markers(node, pytest_available=pytest_available))
    )
    return CollectedTestEvidence(1, tuple(sorted(markers)))


def _apply_test_attribute_controls(
    active: dict[str, CollectedTestEvidence],
    known: dict[str, CollectedTestEvidence],
    controls: tuple[tuple[str, bool], ...],
) -> None:
    for controlled_name, enabled in controls:
        if enabled and controlled_name in known:
            active[controlled_name] = known[controlled_name]
        elif not enabled:
            active.pop(controlled_name, None)


def _class_evidence(
    node: ast.ClassDef,
    *,
    module_markers: set[str],
    pytest_available: bool,
) -> CollectedTestEvidence | None:
    if not _test_class_is_statically_collectable(node) or not (
        _decorators_preserve_collection(
            node,
            pytest_available=pytest_available,
        )
    ):
        return None
    assigned_class_markers = _assigned_pytest_markers(
        node.body,
        inherited_pytest_available=pytest_available,
    )
    if assigned_class_markers is None:
        return None
    class_markers = (
        module_markers
        | set(assigned_class_markers)
        | set(_decorator_markers(node, pytest_available=pytest_available))
        | set(_parameter_row_markers(node, pytest_available=pytest_available))
    )
    candidates: dict[str, CollectedTestEvidence] = {}
    known_candidates: dict[str, CollectedTestEvidence] = {}
    class_pytest_available = pytest_available
    for member in node.body:
        if isinstance(
            member,
            ast.FunctionDef | ast.AsyncFunctionDef,
        ) and member.name.startswith("test"):
            evidence = _function_evidence(
                member,
                inherited_markers=class_markers,
                pytest_available=class_pytest_available,
            )
            if evidence is None:
                candidates.pop(member.name, None)
                known_candidates.pop(member.name, None)
            else:
                candidates[member.name] = evidence
                known_candidates[member.name] = evidence
        else:
            uncertain_names = _nested_test_attribute_names(member)
            bound_names = _direct_bound_names(member) | uncertain_names
            if "*" in bound_names:
                candidates.clear()
                known_candidates.clear()
            for bound_name in bound_names:
                candidates.pop(bound_name, None)
                known_candidates.pop(bound_name, None)
            _apply_test_attribute_controls(
                candidates,
                known_candidates,
                _test_attribute_controls(member),
            )
        class_pytest_available = _statement_pytest_binding(
            member,
            class_pytest_available,
        )
    markers = {
        marker
        for evidence in candidates.values()
        for marker in evidence.effective_markers
    }
    return CollectedTestEvidence(
        definition_count=sum(
            evidence.definition_count for evidence in candidates.values()
        ),
        effective_markers=tuple(sorted(markers)),
    )


def _collected_test_evidence(tree: ast.Module) -> CollectedTestEvidence:
    if not _module_collection_enabled(tree.body) or any(
        _module_scope_can_abort(statement) for statement in tree.body
    ):
        return CollectedTestEvidence(0, ())
    assigned_module_markers = _assigned_pytest_markers(
        tree.body,
        inherited_pytest_available=False,
    )
    if assigned_module_markers is None:
        return CollectedTestEvidence(0, ())
    module_markers = set(assigned_module_markers)
    candidates: dict[str, CollectedTestEvidence] = {}
    known_candidates: dict[str, CollectedTestEvidence] = {}
    pytest_available = False
    for statement in tree.body:
        if isinstance(
            statement, ast.FunctionDef | ast.AsyncFunctionDef
        ) and statement.name.startswith("test"):
            evidence = _function_evidence(
                statement,
                inherited_markers=module_markers,
                pytest_available=pytest_available,
            )
            if evidence is None:
                candidates.pop(statement.name, None)
                known_candidates.pop(statement.name, None)
            else:
                candidates[statement.name] = evidence
                known_candidates[statement.name] = evidence
        elif (
            isinstance(statement, ast.ClassDef)
            and statement.name.startswith("Test")
        ):
            evidence = _class_evidence(
                statement,
                module_markers=module_markers,
                pytest_available=pytest_available,
            )
            if evidence is None:
                candidates.pop(statement.name, None)
                known_candidates.pop(statement.name, None)
            else:
                candidates[statement.name] = evidence
                known_candidates[statement.name] = evidence
        else:
            uncertain_names = _nested_test_attribute_names(statement)
            bound_names = _direct_bound_names(statement) | uncertain_names
            if "*" in bound_names:
                candidates.clear()
                known_candidates.clear()
            for bound_name in bound_names:
                candidates.pop(bound_name, None)
                known_candidates.pop(bound_name, None)
            _apply_test_attribute_controls(
                candidates,
                known_candidates,
                _test_attribute_controls(statement),
            )
        pytest_available = _statement_pytest_binding(statement, pytest_available)
    markers = {
        marker
        for evidence in candidates.values()
        for marker in evidence.effective_markers
    }
    return CollectedTestEvidence(
        definition_count=sum(
            evidence.definition_count for evidence in candidates.values()
        ),
        effective_markers=tuple(sorted(markers)),
    )
def _category_attributions(path: str, markers: tuple[str, ...]) -> tuple[CategoryAttribution, ...]:
    lowered = path.lower().replace("-", "_")
    explicit: dict[str, set[str]] = {}
    inferred: dict[str, set[str]] = {}

    for marker in markers:
        category = PYTEST_MARKER_TO_CATEGORY.get(marker)
        if category:
            explicit.setdefault(category, set()).add(marker)

    token_groups = (
        ("docs-compliance", DOCS_TOKENS),
        ("script-integrity", SCRIPT_TOKENS),
        ("integration", INTEGRATION_TOKENS),
        ("smoke", SMOKE_TOKENS),
        ("regression", REGRESSION_TOKENS),
        ("security", SECURITY_TOKENS),
    )
    for category, tokens in token_groups:
        for token in tokens:
            if token in lowered:
                inferred.setdefault(category, set()).add(f"filename:{token}")

    if "docs-compliance" not in inferred and "script-integrity" not in inferred:
        inferred.setdefault("behavior", set()).add("fallback:behavior")

    attributions: list[CategoryAttribution] = []
    for category in REQUIRED_CATEGORIES:
        explicit_markers = tuple(sorted(explicit.get(category, ())))
        inference_rules = tuple(sorted(inferred.get(category, ())))
        if not explicit_markers and not inference_rules:
            continue
        if explicit_markers and inference_rules:
            provenance = "mixed"
        elif explicit_markers:
            provenance = "explicit"
        else:
            provenance = "inferred"
        attributions.append(
            CategoryAttribution(
                category=category,
                explicit_markers=explicit_markers,
                inference_rules=inference_rules,
                provenance=provenance,
            )
        )
    return tuple(attributions)


def _declared_pytest_markers(repo_root: Path) -> tuple[str, ...]:
    pyproject = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    raw_markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", ())
    declared: list[str] = []
    if isinstance(raw_markers, list):
        for raw_marker in raw_markers:
            if isinstance(raw_marker, str):
                declared.append(raw_marker.split(":", maxsplit=1)[0].strip())
    return tuple(sorted(marker for marker in declared if marker))


def collect_test_files(repo_root: Path) -> tuple[TestFileSummary, ...]:
    tests_root = repo_root / "tests"
    summaries: list[TestFileSummary] = []
    for path in sorted(tests_root.glob("test_*.py")):
        relative = path.relative_to(repo_root).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative)
            compile(source, relative, "exec", dont_inherit=True)
        except SyntaxError as error:
            raise TaxonomyError(
                f"source syntax error: {relative}: {error.msg}"
            ) from error
        collection_evidence = _collected_test_evidence(tree)
        markers = _markers(tree)
        effective_markers = collection_evidence.effective_markers
        attributions = _category_attributions(relative, effective_markers)
        summaries.append(
            TestFileSummary(
                path=relative,
                static_test_count=collection_evidence.definition_count,
                markers=markers,
                effective_markers=effective_markers,
                categories=tuple(attribution.category for attribution in attributions),
                attributions=attributions,
            )
        )
    return tuple(summaries)


def _category_attribution(
    file_summary: TestFileSummary,
    category_name: str,
) -> CategoryAttribution:
    return next(
        attribution
        for attribution in file_summary.attributions
        if attribution.category == category_name
    )


def _provenance_summary(
    category_files: list[TestFileSummary],
    category_name: str,
) -> dict[str, dict[str, int]]:
    summaries = {
        name: {"file_count": 0, "static_test_count": 0} for name in PROVENANCE_NAMES
    }
    for file_summary in category_files:
        provenance = _category_attribution(file_summary, category_name).provenance
        summaries[provenance]["file_count"] += 1
        summaries[provenance]["static_test_count"] += file_summary.static_test_count
    return summaries


def _category_file_evidence(
    category_files: list[TestFileSummary],
    category_name: str,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for file_summary in category_files:
        attribution = _category_attribution(file_summary, category_name)
        evidence.append(
            {
                "path": file_summary.path,
                "static_test_count": file_summary.static_test_count,
                "markers": list(file_summary.markers),
                "provenance": attribution.provenance,
                "explicit_markers": list(attribution.explicit_markers),
                "inference_rules": list(attribution.inference_rules),
            }
        )
    return evidence


def _category_report(
    category: Category,
    files: tuple[TestFileSummary, ...],
) -> dict[str, object]:
    category_files = [
        file_summary for file_summary in files if category.name in file_summary.categories
    ]
    return {
        "description": category.description,
        "file_count": len(category_files),
        "static_test_count": sum(
            file_summary.static_test_count for file_summary in category_files
        ),
        "provenance": _provenance_summary(category_files, category.name),
        "files": _category_file_evidence(category_files, category.name),
    }


def _marker_usage(files: tuple[TestFileSummary, ...]) -> dict[str, int]:
    usage: dict[str, int] = {}
    for file_summary in files:
        for marker in file_summary.markers:
            usage[marker] = usage.get(marker, 0) + 1
    return usage


def build_report(repo_root: Path) -> dict[str, object]:
    files = collect_test_files(repo_root)
    categories = {category.name: _category_report(category, files) for category in CATEGORIES}
    marker_usage = _marker_usage(files)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "test_file_count": len(files),
        "static_test_count": sum(file_summary.static_test_count for file_summary in files),
        "strict_explicit_categories": list(STRICT_EXPLICIT_CATEGORIES),
        "required_categories": list(REQUIRED_CATEGORIES),
        "declared_pytest_markers": list(_declared_pytest_markers(repo_root)),
        "used_pytest_markers": {marker: marker_usage[marker] for marker in sorted(marker_usage)},
        "categories": categories,
    }


def _summary_lines(report: dict[str, object]) -> list[str]:
    categories = report["categories"]
    if not isinstance(categories, dict):
        raise TypeError("invalid taxonomy categories")
    lines = [
        (
            f"Test taxonomy: {report['test_file_count']} files, "
            f"{report['static_test_count']} static tests"
        )
    ]
    for category in REQUIRED_CATEGORIES:
        entry = categories[category]
        if not isinstance(entry, dict):
            raise TypeError(f"invalid taxonomy category: {category}")
        lines.append(
            f"{category}: {entry['file_count']} files, {entry['static_test_count']} static tests"
        )
    return lines


def _validate_strict(report: dict[str, object]) -> list[str]:
    categories = report["categories"]
    if not isinstance(categories, dict):
        return ["taxonomy categories must be a mapping"]
    failures: list[str] = []
    for category in REQUIRED_CATEGORIES:
        entry = categories.get(category)
        if not isinstance(entry, dict):
            failures.append(f"missing taxonomy category: {category}")
            continue
        if int(entry.get("file_count", 0)) <= 0:
            failures.append(f"taxonomy category has no files: {category}")
        if int(entry.get("static_test_count", 0)) <= 0:
            failures.append(f"taxonomy category has no static tests: {category}")
        if category in STRICT_EXPLICIT_CATEGORIES:
            provenance = entry.get("provenance")
            explicit_test_count = 0
            if isinstance(provenance, dict):
                for name in ("explicit", "mixed"):
                    evidence = provenance.get(name)
                    if isinstance(evidence, dict):
                        explicit_test_count += int(evidence.get("static_test_count", 0))
            if explicit_test_count <= 0:
                failures.append(f"taxonomy category {category} has no explicit marker evidence")
    return failures


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/test-taxonomy.json"),
        help="JSON artifact path to write.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the taxonomy summary without writing the JSON artifact.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail when required categories lack file/test evidence or protected "
            "categories lack explicit marker evidence."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root.resolve()
    output = args.output
    if not output.is_absolute():
        output = repo_root / output

    try:
        report = build_report(repo_root)
    except TaxonomyError as error:
        print(f"test taxonomy failed: {error}", file=sys.stderr)
        return 2
    for line in _summary_lines(report):
        print(line)

    failures = _validate_strict(report) if args.strict else []
    if failures:
        for failure in failures:
            print(f"test taxonomy failed: {failure}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Would write test taxonomy: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote test taxonomy: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
