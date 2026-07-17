#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import errno
import json
import keyword
import os
import stat
import sys
import tempfile
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "entroping.pytest-collection-manifest.v1"
GENERATED_BY = "scripts/pytest_collection_manifest.py"
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_COLLECTED_CASES = 100_000
MAX_MANIFEST_OUTPUT_WORK = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = MAX_MANIFEST_OUTPUT_WORK
MAX_SCOPE_STATEMENTS = 100_000
MAX_STATIC_EXPRESSION_DEPTH = 128
COLLECTION_HOOKS = {
    "pytest_collect_file",
    "pytest_collection_modifyitems",
    "pytest_generate_tests",
    "pytest_pycollect_makeitem",
}
STATIC_HELPER_NAMES = {
    "Path",
    "bool",
    "bytes",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "object",
    "set",
    "str",
    "tuple",
    "type",
}
ANNOTATION_GENERIC_NAMES = {"dict", "frozenset", "list", "set", "tuple", "type"}
ANNOTATION_UNION_NAMES = {
    "bool",
    "bytes",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "object",
    "set",
    "str",
    "tuple",
    "type",
}
STATEMENT_FIELD_CLASSIFICATION: dict[type[ast.stmt], frozenset[str]] = {
    ast.Import: frozenset({"names"}),
    ast.ImportFrom: frozenset({"level", "module", "names"}),
    ast.Assign: frozenset({"targets", "type_comment", "value"}),
    ast.AnnAssign: frozenset({"annotation", "simple", "target", "value"}),
    ast.FunctionDef: frozenset(
        {"args", "body", "decorator_list", "name", "returns", "type_comment", "type_params"}
    ),
    ast.AsyncFunctionDef: frozenset(
        {"args", "body", "decorator_list", "name", "returns", "type_comment", "type_params"}
    ),
    ast.ClassDef: frozenset(
        {"bases", "body", "decorator_list", "keywords", "name", "type_params"}
    ),
    ast.Expr: frozenset({"value"}),
    ast.Pass: frozenset(),
}
_SUPPORTS_DESCRIPTOR_WALK = (
    hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd
)


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class CollectedNode:
    normalized_node_id: str
    effective_markers: tuple[str, ...]


@dataclass(frozen=True)
class LoadedManifest:
    test_definition_count: int
    collected_case_count: int
    nodes: tuple[CollectedNode, ...]


@dataclass
class BindingLedger:
    annotations_deferred: bool
    bound_names: set[str] = field(default_factory=lambda: set(STATIC_HELPER_NAMES))
    class_scope: bool = False
    path_constructor_available: bool = False
    path_names: set[str] = field(default_factory=set)
    pytest_available: bool = False
    test_class_scope: bool = False
    trusted_annotation_modules: set[str] = field(default_factory=set)

    def child_class(self, *, test_class_scope: bool) -> BindingLedger:
        return BindingLedger(
            annotations_deferred=self.annotations_deferred,
            bound_names=set(self.bound_names),
            class_scope=True,
            path_constructor_available=self.path_constructor_available,
            path_names=set(self.path_names),
            pytest_available=self.pytest_available,
            test_class_scope=test_class_scope,
            trusted_annotation_modules=set(self.trusted_annotation_modules),
        )


@dataclass
class ScopeBudget:
    statements: int = 0

    def consume(self, count: int) -> None:
        if count > MAX_SCOPE_STATEMENTS - self.statements:
            raise ManifestError("collection scope statement budget is unsupported")
        self.statements += count


def _register_descriptor(stack: ExitStack, descriptor: int) -> int:
    try:
        stack.callback(os.close, descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _descriptor_metadata(file_stat: os.stat_result) -> tuple[int, ...]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _read_descriptor(descriptor: int, label: str, max_bytes: int) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ManifestError(f"{label} is not a regular file")
    if before.st_size > max_bytes:
        raise ManifestError(f"{label} exceeds {max_bytes} bytes")
    chunks: list[bytes] = []
    bytes_read = 0
    while bytes_read <= max_bytes:
        chunk = os.read(descriptor, min(65536, max_bytes + 1 - bytes_read))
        if not chunk:
            break
        chunks.append(chunk)
        bytes_read += len(chunk)
    payload = b"".join(chunks)
    after = os.fstat(descriptor)
    if len(payload) > max_bytes:
        raise ManifestError(f"{label} exceeds {max_bytes} bytes")
    if len(payload) != before.st_size or _descriptor_metadata(before) != _descriptor_metadata(
        after
    ):
        raise ManifestError(f"{label} changed while being read")
    return payload


def _relative_source(raw: str, root: Path) -> Path:
    lexical = Path(os.path.abspath(root / raw if not Path(raw).is_absolute() else raw))
    try:
        relative = lexical.relative_to(root)
    except ValueError as error:
        raise ManifestError(f"source is outside repository: {raw}") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ManifestError(f"source has an unsafe relative path: {raw}")
    if relative.suffix != ".py":
        raise ManifestError(f"source is not a .py file: {raw}")
    return relative


def _read_relative_no_follow(
    root: Path,
    relative: Path,
    label: str,
    *,
    max_bytes: int,
) -> bytes:
    if not _SUPPORTS_DESCRIPTOR_WALK:
        raise ManifestError("runtime lacks descriptor-walk no-follow support")
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ManifestError(f"{label} has an unsafe relative path")
    with ExitStack() as descriptors:
        try:
            root_descriptor = _register_descriptor(
                descriptors,
                os.open(root, os.O_RDONLY | os.O_DIRECTORY),
            )
            root_path_stat = root.stat(follow_symlinks=False)
            root_descriptor_stat = os.fstat(root_descriptor)
            if (
                not stat.S_ISDIR(root_path_stat.st_mode)
                or not stat.S_ISDIR(root_descriptor_stat.st_mode)
                or (root_path_stat.st_dev, root_path_stat.st_ino)
                != (root_descriptor_stat.st_dev, root_descriptor_stat.st_ino)
            ):
                raise ManifestError(f"{label} root identity changed")
            directory_descriptor = root_descriptor
            for part in relative.parts[:-1]:
                directory_descriptor = _register_descriptor(
                    descriptors,
                    os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory_descriptor,
                    ),
                )
            file_descriptor = _register_descriptor(
                descriptors,
                os.open(
                    relative.name,
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=directory_descriptor,
                ),
            )
        except OSError as error:
            if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise ManifestError(f"{label} has a symlink component") from error
            raise ManifestError(f"{label} is not readable") from error
        return _read_descriptor(file_descriptor, label, max_bytes)


def _read_source(root: Path, relative: Path) -> bytes:
    return _read_relative_no_follow(
        root,
        relative,
        "source",
        max_bytes=MAX_INPUT_BYTES,
    )


def _read_absolute_no_follow(path: Path, label: str, *, max_bytes: int) -> bytes:
    lexical = Path(os.path.abspath(path))
    try:
        canonical_parent = lexical.parent.resolve(strict=True)
    except OSError as error:
        raise ManifestError(f"{label} parent is not readable") from error
    absolute = canonical_parent / lexical.name
    anchor = Path(absolute.anchor)
    try:
        relative = absolute.relative_to(anchor)
    except ValueError as error:
        raise ManifestError(f"{label} has an unsafe path") from error
    return _read_relative_no_follow(
        anchor,
        relative,
        label,
        max_bytes=max_bytes,
    )


def _marker_name(expression: ast.expr) -> str | None:
    target = expression.func if isinstance(expression, ast.Call) else expression
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "mark"
        and isinstance(target.value.value, ast.Name)
        and target.value.value.id == "pytest"
    ):
        return target.attr
    return None


def _is_literal_expression(expression: ast.expr) -> bool:
    if any(isinstance(node, ast.Call) for node in ast.walk(expression)):
        return False
    try:
        ast.literal_eval(expression)
    except (ValueError, TypeError, RecursionError):
        return False
    return True


def _validate_marker_arguments(expression: ast.expr) -> None:
    if not isinstance(expression, ast.Call):
        return
    keyword_names = [
        keyword.arg for keyword in expression.keywords if keyword.arg is not None
    ]
    if len(keyword_names) != len(set(keyword_names)):
        raise ManifestError("duplicate marker keyword is unsupported")
    if any(not _is_literal_expression(argument) for argument in expression.args):
        raise ManifestError("dynamic marker argument is unsupported")
    if any(
        keyword.arg is None or not _is_literal_expression(keyword.value)
        for keyword in expression.keywords
    ):
        raise ManifestError("dynamic marker argument is unsupported")


def _static_marks(expression: ast.expr) -> frozenset[str]:
    if isinstance(expression, ast.List | ast.Tuple):
        markers: set[str] = set()
        for element in expression.elts:
            if isinstance(element, ast.List | ast.Tuple):
                raise ManifestError("nested marker collection is unsupported")
            markers.update(_static_marks(element))
        return frozenset(markers)
    marker = _marker_name(expression)
    if marker is None or marker == "parametrize":
        raise ManifestError("dynamic marks are unsupported")
    _validate_marker_arguments(expression)
    return frozenset((marker,))


def _is_static_param_row_shape(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant | ast.Dict | ast.List | ast.Set | ast.Tuple)


def _static_argname_values(
    expression: ast.expr,
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


def _is_static_indirect(
    expression: ast.expr,
    argnames: tuple[str, ...],
) -> bool:
    if isinstance(expression, ast.Constant):
        return isinstance(expression.value, bool)
    if not isinstance(expression, ast.List | ast.Tuple):
        return False
    names = tuple(
        element.value
        for element in expression.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    )
    return (
        len(names) == len(expression.elts)
        and len(names) == len(set(names))
        and set(names) <= set(argnames)
    )


def _is_static_scope(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and (
        expression.value is None
        or expression.value in {"class", "function", "module", "package", "session"}
    )


def _parametrize_keyword_values(decorator: ast.Call) -> dict[str, ast.expr]:
    if any(keyword.arg is None for keyword in decorator.keywords):
        raise ManifestError("dynamic parametrize keyword is unsupported")
    if len(decorator.args) >= 4:
        raise ManifestError("positional parametrize ids are unsupported")
    keyword_names = [
        keyword.arg for keyword in decorator.keywords if keyword.arg is not None
    ]
    if len(keyword_names) != len(set(keyword_names)):
        raise ManifestError("duplicate parametrize keyword is unsupported")
    keyword_values = {
        keyword.arg: keyword.value for keyword in decorator.keywords if keyword.arg is not None
    }
    if "ids" in keyword_values:
        raise ManifestError("parametrize ids are unsupported")
    supported = {"argnames", "argvalues", "indirect", "scope"}
    if not keyword_values.keys() <= supported:
        raise ManifestError("dynamic parametrize keyword is unsupported")
    positional_names = ("argnames", "argvalues", "indirect")
    if any(name in keyword_values for name in positional_names[: len(decorator.args)]):
        raise ManifestError("duplicate parametrize argument is unsupported")
    return keyword_values


def _parametrize_argument(
    decorator: ast.Call,
    keyword_values: dict[str, ast.expr],
    position: int,
    name: str,
) -> ast.expr | None:
    if len(decorator.args) > position:
        return decorator.args[position]
    return keyword_values.get(name)


def _validate_parametrize_controls(
    decorator: ast.Call,
    keyword_values: dict[str, ast.expr],
) -> tuple[tuple[str, ...], bool, ast.List | ast.Tuple]:
    argnames = _parametrize_argument(decorator, keyword_values, 0, "argnames")
    argvalues = _parametrize_argument(decorator, keyword_values, 1, "argvalues")
    indirect = _parametrize_argument(decorator, keyword_values, 2, "indirect")
    static_contract = (
        _static_argname_values(argnames) if argnames is not None else None
    )
    if static_contract is None:
        raise ManifestError("dynamic parametrize argnames are unsupported")
    static_argnames, sequence_form = static_contract
    if not isinstance(argvalues, ast.List | ast.Tuple):
        raise ManifestError("dynamic parametrization is unsupported")
    if indirect is not None and not _is_static_indirect(indirect, static_argnames):
        raise ManifestError("dynamic parametrize indirect is unsupported")
    scope = keyword_values.get("scope")
    if scope is not None and not _is_static_scope(scope):
        raise ManifestError("dynamic parametrize scope is unsupported")
    if not argvalues.elts:
        raise ManifestError("empty parameter set is unsupported")
    return static_argnames, sequence_form, argvalues


def _pytest_param_markers(row: ast.Call) -> frozenset[str]:
    is_pytest_param = (
        isinstance(row.func, ast.Attribute)
        and isinstance(row.func.value, ast.Name)
        and row.func.value.id == "pytest"
        and row.func.attr == "param"
    )
    if not is_pytest_param:
        raise ManifestError("dynamic row call is unsupported")
    if any(isinstance(argument, ast.Starred) for argument in row.args):
        raise ManifestError("starred pytest.param argument is unsupported")
    keyword_names = [keyword.arg for keyword in row.keywords if keyword.arg is not None]
    if len(keyword_names) != len(set(keyword_names)):
        raise ManifestError("duplicate pytest.param keyword is unsupported")
    markers = frozenset(("parametrize",))
    for row_keyword in row.keywords:
        if row_keyword.arg == "id":
            raise ManifestError("pytest.param id is unsupported")
        if row_keyword.arg != "marks":
            raise ManifestError("dynamic pytest.param keyword is unsupported")
        markers |= _static_marks(row_keyword.value)
    return markers


def _parametrize_row_markers(
    row: ast.expr,
    *,
    expected_arity: int,
    sequence_argnames: bool,
) -> frozenset[str]:
    if isinstance(row, ast.Call):
        markers = _pytest_param_markers(row)
        if len(row.args) != expected_arity:
            raise ManifestError("parameter row arity is unsupported")
        return markers
    if not _is_static_param_row_shape(row):
        row_kind = "starred row" if isinstance(row, ast.Starred) else "dynamic row"
        raise ManifestError(f"{row_kind} is unsupported")
    if (sequence_argnames or expected_arity > 1) and (
        not isinstance(row, ast.List | ast.Tuple)
        or len(row.elts) != expected_arity
    ):
        raise ManifestError("parameter row arity is unsupported")
    return frozenset(("parametrize",))


def _parametrize_rows(
    decorator: ast.Call,
) -> tuple[tuple[str, ...], tuple[frozenset[str], ...]]:
    keyword_values = _parametrize_keyword_values(decorator)
    argnames, sequence_form, argvalues = _validate_parametrize_controls(
        decorator,
        keyword_values,
    )
    rows: list[frozenset[str]] = []
    for row in argvalues.elts:
        rows.append(
            _parametrize_row_markers(
                row,
                expected_arity=len(argnames),
                sequence_argnames=sequence_form,
            )
        )
    return argnames, tuple(rows)


def _definition_argument_names(
    definition: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    return {
        argument.arg
        for argument in (
            *definition.args.posonlyargs,
            *definition.args.args,
            *definition.args.kwonlyargs,
        )
    }


def _defaulted_argument_names(
    definition: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    positional = [*definition.args.posonlyargs, *definition.args.args]
    positional_defaults = (
        positional[-len(definition.args.defaults) :]
        if definition.args.defaults
        else []
    )
    keyword_defaults = {
        argument.arg
        for argument, default in zip(
            definition.args.kwonlyargs,
            definition.args.kw_defaults,
            strict=True,
        )
        if default is not None
    }
    return {
        *(argument.arg for argument in positional_defaults),
        *keyword_defaults,
    }


def _decorator_cases(
    decorators: list[ast.expr],
    inherited: frozenset[str],
    *,
    definition: ast.FunctionDef | ast.AsyncFunctionDef | None = None,
) -> tuple[frozenset[str], ...]:
    base = inherited
    layers: list[tuple[frozenset[str], ...]] = []
    parametrized_names: set[str] = set()
    definition_arguments = (
        _definition_argument_names(definition) if definition is not None else None
    )
    defaulted_arguments = (
        _defaulted_argument_names(definition) if definition is not None else set()
    )
    for decorator in decorators:
        marker = _marker_name(decorator)
        if marker is None:
            raise ManifestError("dynamic test decorator is unsupported")
        if marker == "parametrize":
            if not isinstance(decorator, ast.Call):
                raise ManifestError("dynamic parametrization is unsupported")
            argnames, rows = _parametrize_rows(decorator)
            if parametrized_names.intersection(argnames):
                raise ManifestError("duplicate parametrization is unsupported")
            if (
                definition_arguments is not None
                and (
                    not set(argnames) <= definition_arguments
                    or bool(defaulted_arguments.intersection(argnames))
                )
            ):
                raise ManifestError("parametrize function signature is unsupported")
            parametrized_names.update(argnames)
            layers.append(rows)
        else:
            _validate_marker_arguments(decorator)
            base |= frozenset((marker,))
    cases: tuple[frozenset[str], ...] = (base,)
    marker_universe = set(base)
    for layer in layers:
        if len(cases) > MAX_COLLECTED_CASES // len(layer):
            raise ManifestError(
                f"parametrized case expansion exceeds {MAX_COLLECTED_CASES}"
            )
        prospective_case_count = len(cases) * len(layer)
        for row in layer:
            marker_universe.update(row)
        marker_work = sum(len(marker.encode("utf-8")) + 4 for marker in marker_universe)
        if marker_work and prospective_case_count > MAX_MANIFEST_OUTPUT_WORK // marker_work:
            raise ManifestError("parametrized marker output work is unsupported")
        cases = tuple(existing | row for existing in cases for row in layer)
    return cases


def _collection_target_error(target: ast.expr, assignment_kind: str) -> str | None:
    if isinstance(target, ast.Name):
        if target.id == "pytestmark":
            if assignment_kind == "import":
                return "pytestmark import is unsupported"
            if assignment_kind not in {"assignment", "annotated"}:
                return f"{assignment_kind} pytestmark is unsupported"
            return None
        if target.id == "__test__":
            return "__test__ assignment is unsupported"
        if target.id == "pytest_plugins":
            return "plugin declaration is unsupported"
        if target.id in {"collect_ignore", "collect_ignore_glob"}:
            return "collect ignore control is unsupported"
        if target.id == "pytest":
            return f"{assignment_kind} pytest binding is unsupported"
        if target.id in COLLECTION_HOOKS:
            return f"{assignment_kind} collection hook binding is unsupported"
        if target.id in STATIC_HELPER_NAMES:
            return f"{assignment_kind} static helper binding is unsupported"
        if target.id.startswith("Test"):
            if assignment_kind == "import":
                return "test class import alias is unsupported"
            return f"{assignment_kind} test class binding is unsupported"
        if target.id.startswith("test"):
            if assignment_kind == "import":
                return "test import alias is unsupported"
            return f"{assignment_kind} test binding is unsupported"
        return None
    if isinstance(target, ast.Attribute) and target.attr == "__test__":
        return "__test__ assignment is unsupported"
    if isinstance(target, ast.List | ast.Tuple):
        for element in target.elts:
            error = _collection_target_error(element, assignment_kind)
            if error is not None:
                return error
    return None


def _subscript_label(target: ast.Subscript) -> str | None:
    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
        return target.slice.value
    return None


def _is_collection_namespace(expression: ast.expr) -> bool:
    return (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id in {"globals", "locals", "vars"}
    ) or (isinstance(expression, ast.Attribute) and expression.attr == "__dict__")


def _indirect_collection_target_error(target: ast.expr) -> str | None:
    if isinstance(target, ast.Subscript):
        label = _subscript_label(target)
        if label == "__test__":
            return "indirect __test__ mutation is unsupported"
        if _is_collection_namespace(target.value):
            return "indirect namespace mutation is unsupported"
    if isinstance(target, ast.List | ast.Tuple):
        for element in target.elts:
            error = _indirect_collection_target_error(element)
            if error is not None:
                return error
    return None


def _static_scope_value_kind(
    expression: ast.expr,
    *,
    bound_names: set[str],
    path_constructor_available: bool,
    path_names: set[str],
    depth: int = 0,
) -> str | None:
    if depth > MAX_STATIC_EXPRESSION_DEPTH:
        raise ManifestError("static expression depth is unsupported")
    if _is_literal_expression(expression):
        return "value"
    if isinstance(expression, ast.Name):
        if expression.id not in bound_names:
            return None
        return "path" if expression.id in path_names else "value"
    if _is_static_frozenset_call(expression):
        return "value"
    if _is_static_path_expression(
        expression,
        bound_names=bound_names,
        path_constructor_available=path_constructor_available,
        path_names=path_names,
        depth=depth,
    ):
        return "path"
    return None


def _is_static_frozenset_call(expression: ast.expr) -> bool:
    return (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "frozenset"
        and not expression.keywords
        and len(expression.args) <= 1
        and all(_is_literal_expression(argument) for argument in expression.args)
    )


def _is_path_constructor_call(
    expression: ast.expr,
    *,
    path_constructor_available: bool,
) -> bool:
    return (
        path_constructor_available
        and isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "Path"
        and len(expression.args) == 1
        and not expression.keywords
        and isinstance(expression.args[0], ast.Name)
        and expression.args[0].id == "__file__"
    )


def _resolved_path_receiver(expression: ast.expr) -> ast.expr | None:
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr == "resolve"
        and not expression.args
        and not expression.keywords
    ):
        return expression.func.value
    return None


def _parent_path_receiver(expression: ast.expr) -> ast.expr | None:
    if (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "parents"
        and isinstance(expression.slice, ast.Constant)
        and isinstance(expression.slice.value, int)
        and not isinstance(expression.slice.value, bool)
    ):
        return expression.value.value
    return None


def _joined_path_receiver(expression: ast.expr) -> ast.expr | None:
    if (
        isinstance(expression, ast.BinOp)
        and isinstance(expression.op, ast.Div)
        and isinstance(expression.right, ast.Constant)
        and isinstance(expression.right.value, str)
    ):
        return expression.left
    return None


def _is_static_path_expression(
    expression: ast.expr,
    *,
    bound_names: set[str],
    path_constructor_available: bool,
    path_names: set[str],
    depth: int,
) -> bool:
    if _is_path_constructor_call(
        expression,
        path_constructor_available=path_constructor_available,
    ):
        return True
    receivers = (
        _resolved_path_receiver(expression),
        _parent_path_receiver(expression),
        _joined_path_receiver(expression),
    )
    return any(
        receiver is not None
        and _static_scope_value_kind(
            receiver,
            bound_names=bound_names,
            path_constructor_available=path_constructor_available,
            path_names=path_names,
            depth=depth + 1,
        )
        == "path"
        for receiver in receivers
    )


def _validate_definition_expression(
    expression: ast.expr,
    *,
    bound_names: set[str],
    path_constructor_available: bool,
    path_names: set[str],
) -> str:
    kind = _static_scope_value_kind(
        expression,
        bound_names=bound_names,
        path_constructor_available=path_constructor_available,
        path_names=path_names,
    )
    if kind is None:
        raise ManifestError("dynamic definition-time expression is unsupported")
    return kind


def _is_trusted_annotation_attribute(
    expression: ast.expr,
    trusted_modules: set[str],
) -> bool:
    return (
        isinstance(expression, ast.Attribute)
        and isinstance(expression.value, ast.Name)
        and expression.value.id in trusted_modules
        and not expression.attr.startswith("__")
    )


def _is_safe_annotation_expression(
    expression: ast.expr,
    *,
    bound_names: set[str],
    trusted_modules: set[str],
) -> bool:
    if isinstance(expression, ast.Constant):
        return True
    if isinstance(expression, ast.Name):
        return expression.id in bound_names
    if _is_trusted_annotation_attribute(expression, trusted_modules):
        return True
    if isinstance(expression, ast.Tuple):
        return all(
            _is_safe_annotation_expression(
                element,
                bound_names=bound_names,
                trusted_modules=trusted_modules,
            )
            for element in expression.elts
        )
    if isinstance(expression, ast.Subscript):
        safe_origin = (
            isinstance(expression.value, ast.Name)
            and expression.value.id in ANNOTATION_GENERIC_NAMES
        ) or _is_trusted_annotation_attribute(expression.value, trusted_modules)
        return safe_origin and _is_safe_annotation_expression(
            expression.slice,
            bound_names=bound_names,
            trusted_modules=trusted_modules,
        )
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
        return _is_safe_annotation_union_operand(
            expression.left,
            bound_names=bound_names,
            trusted_modules=trusted_modules,
        ) and _is_safe_annotation_union_operand(
            expression.right,
            bound_names=bound_names,
            trusted_modules=trusted_modules,
        )
    return False


def _is_safe_annotation_union_operand(
    expression: ast.expr,
    *,
    bound_names: set[str],
    trusted_modules: set[str],
) -> bool:
    if isinstance(expression, ast.Constant):
        return expression.value is None
    if isinstance(expression, ast.Name):
        return expression.id in ANNOTATION_UNION_NAMES and expression.id in bound_names
    if isinstance(expression, ast.Subscript):
        return (
            isinstance(expression.value, ast.Name)
            and expression.value.id in ANNOTATION_GENERIC_NAMES
            and _is_safe_annotation_expression(
                expression.slice,
                bound_names=bound_names,
                trusted_modules=trusted_modules,
            )
        )
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
        return _is_safe_annotation_union_operand(
            expression.left,
            bound_names=bound_names,
            trusted_modules=trusted_modules,
        ) and _is_safe_annotation_union_operand(
            expression.right,
            bound_names=bound_names,
            trusted_modules=trusted_modules,
        )
    return False


def _validate_annotation_expression(
    expression: ast.expr,
    *,
    annotations_deferred: bool,
    bound_names: set[str],
    trusted_modules: set[str],
) -> None:
    if annotations_deferred:
        return
    if not _is_safe_annotation_expression(
        expression,
        bound_names=bound_names,
        trusted_modules=trusted_modules,
    ):
        raise ManifestError("dynamic annotation expression is unsupported")


def _validate_function_definition(
    statement: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    annotations_deferred: bool,
    bound_names: set[str],
    path_constructor_available: bool,
    path_names: set[str],
    pytest_available: bool,
    trusted_annotation_modules: set[str],
) -> None:
    if getattr(statement, "type_params", ()):
        raise ManifestError("generic test definitions are unsupported")
    defaults = [
        *statement.args.defaults,
        *(default for default in statement.args.kw_defaults if default is not None),
    ]
    for default in defaults:
        _validate_definition_expression(
            default,
            bound_names=bound_names,
            path_constructor_available=path_constructor_available,
            path_names=path_names,
        )
    arguments = [
        *statement.args.posonlyargs,
        *statement.args.args,
        *statement.args.kwonlyargs,
    ]
    if statement.args.vararg is not None:
        arguments.append(statement.args.vararg)
    if statement.args.kwarg is not None:
        arguments.append(statement.args.kwarg)
    for argument in arguments:
        if argument.annotation is not None:
            _validate_annotation_expression(
                argument.annotation,
                annotations_deferred=annotations_deferred,
                bound_names=bound_names,
                trusted_modules=trusted_annotation_modules,
            )
    if statement.returns is not None:
        _validate_annotation_expression(
            statement.returns,
            annotations_deferred=annotations_deferred,
            bound_names=bound_names,
            trusted_modules=trusted_annotation_modules,
        )
    if statement.name.startswith("test"):
        if statement.decorator_list and not pytest_available:
            raise ManifestError("test markers require a canonical pytest binding")
        _decorator_cases(
            statement.decorator_list,
            frozenset(),
            definition=statement,
        )
    elif statement.decorator_list:
        raise ManifestError("helper decorators are unsupported")


def _validate_assignment_target(target: ast.expr, assignment_kind: str) -> None:
    indirect_error = _indirect_collection_target_error(target)
    if indirect_error is not None:
        raise ManifestError(indirect_error)
    error = _collection_target_error(target, assignment_kind)
    if error is not None:
        raise ManifestError(error)
    if not isinstance(target, ast.Name):
        raise ManifestError("indirect assignment target is unsupported")


def _canonical_pytest_import(
    statement: ast.Import | ast.ImportFrom,
    imported: ast.alias,
    bound_name: str,
) -> bool:
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


def _trusted_annotation_module_import(
    statement: ast.Import | ast.ImportFrom,
    imported: ast.alias,
    bound_name: str,
) -> bool:
    if isinstance(statement, ast.Import):
        return imported.name in {"ast", "pytest", "subprocess"}
    if statement.level != 0:
        return False
    if statement.module == "cli_test_support":
        return imported.name in {"pytest", "subprocess"}
    return (
        statement.module == "entroping.bridge"
        and imported.name == "openapi_to_hurl"
        and bound_name == "openapi_compiler"
    )


def _target_has_name(target: ast.expr, names: set[str]) -> bool:
    if isinstance(target, ast.Name):
        return target.id in names
    if isinstance(target, ast.List | ast.Tuple):
        return any(_target_has_name(element, names) for element in target.elts)
    return False


def _require_classified_fields(node: ast.AST, classified: frozenset[str]) -> None:
    actual = frozenset(name for name, _value in ast.iter_fields(node))
    if actual != classified:
        unclassified = sorted(actual - classified)
        stale = sorted(classified - actual)
        details = ", ".join([*unclassified, *(f"missing:{name}" for name in stale)])
        raise ManifestError(
            f"unclassified AST field is unsupported: {type(node).__name__}: {details}"
        )


def _require_classified_statement_fields(statement: ast.stmt) -> None:
    classified = STATEMENT_FIELD_CLASSIFICATION.get(type(statement))
    if classified is None:
        raise ManifestError(
            f"executable collection scope is unsupported: {type(statement).__name__}"
        )
    _require_classified_fields(statement, classified)


def _invalidate_binding(ledger: BindingLedger, name: str) -> None:
    ledger.bound_names.add(name)
    ledger.path_names.discard(name)
    ledger.trusted_annotation_modules.discard(name)


def _validate_scope_target(
    target: ast.expr,
    assignment_kind: str,
    ledger: BindingLedger,
) -> None:
    if not ledger.class_scope and _target_has_name(target, {"__getattr__"}):
        raise ManifestError(f"module __getattr__ {assignment_kind} is unsupported")
    if ledger.test_class_scope and _target_has_name(target, {"__init__", "__new__"}):
        raise ManifestError(f"test class constructor {assignment_kind} is unsupported")
    _validate_assignment_target(target, assignment_kind)


def _validate_import_statement(
    statement: ast.Import | ast.ImportFrom,
    ledger: BindingLedger,
) -> None:
    _require_classified_statement_fields(statement)
    for imported in statement.names:
        if imported.name == "*":
            raise ManifestError("wildcard import is unsupported")
        bound_name = imported.asname or imported.name.split(".", maxsplit=1)[0]
        ledger.bound_names.add(bound_name)
        trusted_path_import = (
            isinstance(statement, ast.ImportFrom)
            and statement.level == 0
            and statement.module in {"cli_test_support", "pathlib"}
            and imported.name == "Path"
            and bound_name == "Path"
        )
        if trusted_path_import:
            ledger.path_constructor_available = True
            continue
        if _canonical_pytest_import(statement, imported, bound_name):
            ledger.pytest_available = True
            ledger.trusted_annotation_modules.add(bound_name)
            continue
        if not ledger.class_scope and bound_name == "__getattr__":
            raise ManifestError("module __getattr__ import is unsupported")
        if ledger.test_class_scope and bound_name in {"__init__", "__new__"}:
            raise ManifestError("test class constructor import is unsupported")
        error = _collection_target_error(
            ast.Name(id=bound_name, ctx=ast.Load()),
            "import",
        )
        if error is not None:
            raise ManifestError(error)
        if _trusted_annotation_module_import(statement, imported, bound_name):
            ledger.trusted_annotation_modules.add(bound_name)
        else:
            ledger.trusted_annotation_modules.discard(bound_name)
        ledger.path_names.discard(bound_name)


def _record_static_binding(
    name: str,
    kind: str,
    ledger: BindingLedger,
) -> None:
    ledger.bound_names.add(name)
    if kind == "path":
        ledger.path_names.add(name)
    else:
        ledger.path_names.discard(name)
    ledger.trusted_annotation_modules.discard(name)


def _validate_assign_statement(statement: ast.Assign, ledger: BindingLedger) -> None:
    _require_classified_statement_fields(statement)
    for target in statement.targets:
        _validate_scope_target(target, "assignment", ledger)
    assigns_pytestmark = any(
        isinstance(target, ast.Name) and target.id == "pytestmark"
        for target in statement.targets
    )
    if assigns_pytestmark:
        if len(statement.targets) != 1:
            raise ManifestError("multi-target pytestmark assignment is unsupported")
        if not ledger.pytest_available:
            raise ManifestError("pytestmark requires a canonical pytest binding")
        _static_marks(statement.value)
        return
    kind = _validate_definition_expression(
        statement.value,
        bound_names=ledger.bound_names,
        path_constructor_available=ledger.path_constructor_available,
        path_names=ledger.path_names,
    )
    for target in statement.targets:
        if isinstance(target, ast.Name):
            _record_static_binding(target.id, kind, ledger)


def _validate_annassign_statement(
    statement: ast.AnnAssign,
    ledger: BindingLedger,
) -> None:
    _require_classified_statement_fields(statement)
    _validate_scope_target(statement.target, "annotated", ledger)
    _validate_annotation_expression(
        statement.annotation,
        annotations_deferred=ledger.annotations_deferred,
        bound_names=ledger.bound_names,
        trusted_modules=ledger.trusted_annotation_modules,
    )
    if statement.value is None:
        return
    if isinstance(statement.target, ast.Name) and statement.target.id == "pytestmark":
        if not ledger.pytest_available:
            raise ManifestError("pytestmark requires a canonical pytest binding")
        _static_marks(statement.value)
        return
    kind = _validate_definition_expression(
        statement.value,
        bound_names=ledger.bound_names,
        path_constructor_available=ledger.path_constructor_available,
        path_names=ledger.path_names,
    )
    if isinstance(statement.target, ast.Name):
        _record_static_binding(statement.target.id, kind, ledger)


def _validate_function_statement(
    statement: ast.FunctionDef | ast.AsyncFunctionDef,
    ledger: BindingLedger,
) -> None:
    _require_classified_statement_fields(statement)
    if statement.name == "__getattr__" and not ledger.class_scope:
        raise ManifestError("module __getattr__ collection metaprogramming is unsupported")
    if statement.name == "pytest":
        raise ManifestError("pytest definition is unsupported")
    if statement.name in COLLECTION_HOOKS:
        raise ManifestError(f"collection hook is unsupported: {statement.name}")
    if statement.name in STATIC_HELPER_NAMES:
        raise ManifestError("static helper definition is unsupported")
    if ledger.test_class_scope and statement.name in {"__init__", "__new__"}:
        raise ManifestError("test class constructor is unsupported")
    _validate_function_definition(
        statement,
        annotations_deferred=ledger.annotations_deferred,
        bound_names=ledger.bound_names,
        path_constructor_available=ledger.path_constructor_available,
        path_names=ledger.path_names,
        pytest_available=ledger.pytest_available,
        trusted_annotation_modules=ledger.trusted_annotation_modules,
    )
    _invalidate_binding(ledger, statement.name)


def _validate_class_statement(
    statement: ast.ClassDef,
    ledger: BindingLedger,
    budget: ScopeBudget,
) -> None:
    _require_classified_statement_fields(statement)
    if ledger.class_scope:
        raise ManifestError("nested class definitions are unsupported")
    if statement.name == "__getattr__":
        raise ManifestError("module __getattr__ definition is unsupported")
    if statement.name == "pytest":
        raise ManifestError("pytest definition is unsupported")
    if statement.name in STATIC_HELPER_NAMES:
        raise ManifestError("static helper definition is unsupported")
    if statement.name.startswith("test"):
        raise ManifestError("test class binding is unsupported")
    if statement.type_params:
        raise ManifestError("generic test classes are unsupported")
    is_test_class = statement.name.startswith("Test")
    if is_test_class:
        if statement.bases or statement.keywords:
            raise ManifestError(f"unsupported test class inheritance: {statement.name}")
        if any(
            _marker_name(decorator) == "parametrize"
            for decorator in statement.decorator_list
        ):
            raise ManifestError("parametrized test classes are unsupported")
        if statement.decorator_list and not ledger.pytest_available:
            raise ManifestError("test markers require a canonical pytest binding")
        class_cases = _decorator_cases(statement.decorator_list, frozenset())
        if len(class_cases) != 1:
            raise ManifestError("parametrized test classes are unsupported")
    elif statement.bases or statement.keywords or statement.decorator_list:
        raise ManifestError("helper class metaprogramming is unsupported")
    _validate_collection_bindings(
        statement.body,
        ledger=ledger.child_class(test_class_scope=is_test_class),
        budget=budget,
    )
    _invalidate_binding(ledger, statement.name)


def _validate_collection_bindings(
    body: list[ast.stmt],
    *,
    ledger: BindingLedger,
    budget: ScopeBudget,
) -> None:
    budget.consume(len(body))
    for statement in body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            _validate_import_statement(statement, ledger)
            continue
        if isinstance(statement, ast.Assign):
            _validate_assign_statement(statement, ledger)
            continue
        if isinstance(statement, ast.AnnAssign):
            _validate_annassign_statement(statement, ledger)
            continue
        if isinstance(statement, ast.AugAssign):
            _validate_scope_target(statement.target, "augmented", ledger)
            raise ManifestError("augmented assignment is unsupported")
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            _validate_function_statement(statement, ledger)
            continue
        if isinstance(statement, ast.ClassDef):
            _validate_class_statement(statement, ledger, budget)
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            _require_classified_statement_fields(statement)
            continue
        if isinstance(statement, ast.Pass):
            _require_classified_statement_fields(statement)
            continue
        _require_classified_statement_fields(statement)
        raise ManifestError(
            f"executable collection scope is unsupported: {type(statement).__name__}"
        )


def _assigned_markers(body: list[ast.stmt]) -> frozenset[str]:
    markers: frozenset[str] = frozenset()
    for statement in body:
        if isinstance(statement, ast.Assign):
            names = [target.id for target in statement.targets if isinstance(target, ast.Name)]
            if "pytestmark" in names:
                markers = _static_marks(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "pytestmark"
            and statement.value is not None
        ):
            markers = _static_marks(statement.value)
    return markers


def _collect_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    prefix: str,
    inherited: frozenset[str],
) -> tuple[CollectedNode, ...]:
    cases = _decorator_cases(
        node.decorator_list,
        inherited,
        definition=node,
    )
    node_id = f"{prefix}::{node.name}" if prefix else node.name
    collected = tuple(
        CollectedNode(node_id, tuple(sorted(markers))) for markers in cases
    )
    if _nodes_output_work(collected) > MAX_MANIFEST_OUTPUT_WORK:
        raise ManifestError("collected node output work is unsupported")
    return collected


def _node_output_work(node: CollectedNode) -> int:
    return (
        len(node.normalized_node_id.encode("utf-8"))
        + sum(len(marker.encode("utf-8")) + 4 for marker in node.effective_markers)
        + 64
    )


def _nodes_output_work(nodes: tuple[CollectedNode, ...]) -> int:
    return sum(_node_output_work(node) for node in nodes)


def _extend_collected_nodes(
    target: list[CollectedNode],
    additions: tuple[CollectedNode, ...],
    current_work: int,
) -> int:
    addition_work = _nodes_output_work(additions)
    if addition_work > MAX_MANIFEST_OUTPUT_WORK - current_work:
        raise ManifestError("collection manifest output work is unsupported")
    target.extend(additions)
    return current_work + addition_work


def _register_collected_binding(seen: set[str], name: str) -> None:
    if name in seen:
        raise ManifestError(f"duplicate collected binding is unsupported: {name}")
    seen.add(name)


def _collect_tree(tree: ast.Module) -> tuple[int, tuple[CollectedNode, ...]]:
    annotations_deferred = any(
        isinstance(statement, ast.ImportFrom)
        and statement.module == "__future__"
        and any(imported.name == "annotations" for imported in statement.names)
        for statement in tree.body
    )
    _validate_collection_bindings(
        tree.body,
        ledger=BindingLedger(annotations_deferred=annotations_deferred),
        budget=ScopeBudget(),
    )
    module_markers = _assigned_markers(tree.body)
    definitions = 0
    nodes: list[CollectedNode] = []
    output_work = 0
    module_bindings: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            if statement.name.startswith("test"):
                _register_collected_binding(module_bindings, statement.name)
                definitions += 1
                output_work = _extend_collected_nodes(
                    nodes,
                    _collect_function(statement, "", module_markers),
                    output_work,
                )
        elif isinstance(statement, ast.ClassDef) and statement.name.startswith("Test"):
            _register_collected_binding(module_bindings, statement.name)
            if statement.bases or statement.keywords:
                raise ManifestError(f"unsupported test class inheritance: {statement.name}")
            if any(
                isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
                and member.name in {"__init__", "__new__"}
                for member in statement.body
            ):
                raise ManifestError(f"test class constructor is unsupported: {statement.name}")
            class_markers = module_markers | _assigned_markers(statement.body)
            class_cases = _decorator_cases(statement.decorator_list, class_markers)
            if len(class_cases) != 1:
                raise ManifestError("parametrized test classes are unsupported")
            method_bindings: set[str] = set()
            for member in statement.body:
                if isinstance(
                    member, ast.FunctionDef | ast.AsyncFunctionDef
                ) and member.name.startswith("test"):
                    _register_collected_binding(method_bindings, member.name)
                    definitions += 1
                    output_work = _extend_collected_nodes(
                        nodes,
                        _collect_function(member, statement.name, class_cases[0]),
                        output_work,
                    )
    return definitions, tuple(nodes)


def _output_path(raw: str) -> Path:
    lexical = Path(os.path.abspath(raw))
    try:
        parent = lexical.parent.resolve(strict=True)
    except OSError as error:
        raise ManifestError(f"output parent does not exist: {lexical.parent}") from error
    if not parent.is_dir():
        raise ManifestError(f"output parent is not a directory: {parent}")
    output = parent / lexical.name
    if os.path.lexists(output):
        raise ManifestError(f"output already exists: {output}")
    return output


def _write_exclusive(output: Path, payload: dict[str, object]) -> None:
    serialized = (
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    if len(serialized) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"manifest output exceeds {MAX_MANIFEST_BYTES} bytes")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as error:
            raise ManifestError(f"output already exists: {output}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _generate(output_raw: str, source_args: list[str]) -> int:
    if not source_args:
        raise ManifestError("at least one source file is required")
    root = Path.cwd().resolve(strict=True)
    output = _output_path(output_raw)
    sources = tuple(_relative_source(raw, root) for raw in source_args)
    if len(sources) != len(set(sources)):
        raise ManifestError("duplicate source path")
    if any(output == root / source for source in sources):
        raise ManifestError("output aliases a source file")
    definitions = 0
    nodes: list[CollectedNode] = []
    output_work = 0
    for source in sorted(sources):
        raw = _read_source(root, source)
        try:
            source_text = raw.decode("utf-8")
            tree = ast.parse(source_text, filename=source.as_posix())
            compile(
                source_text,
                source.as_posix(),
                "exec",
                dont_inherit=True,
            )
        except UnicodeDecodeError as error:
            raise ManifestError(f"source is not UTF-8: {source}") from error
        except SyntaxError as error:
            raise ManifestError(f"source syntax error: {source}: {error.msg}") from error
        source_definitions, source_nodes = _collect_tree(tree)
        if len(nodes) > MAX_COLLECTED_CASES - len(source_nodes):
            raise ManifestError(
                f"collected case total exceeds {MAX_COLLECTED_CASES}"
            )
        definitions += source_definitions
        output_work = _extend_collected_nodes(
            nodes,
            source_nodes,
            output_work,
        )
    ordered = sorted(nodes, key=lambda node: (node.normalized_node_id, node.effective_markers))
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "parameter_id_projection": "normalized-away",
        "source_files": [source.as_posix() for source in sorted(sources)],
        "test_definition_count": definitions,
        "collected_case_count": len(ordered),
        "nodes": [
            {
                "normalized_node_id": node.normalized_node_id,
                "effective_markers": list(node.effective_markers),
            }
            for node in ordered
        ],
    }
    _write_exclusive(output, payload)
    print(f"Wrote pytest collection manifest: {output}")
    return 0


def _validate_source_labels(source_files: object, path: Path) -> tuple[str, ...]:
    if not isinstance(source_files, list) or not source_files:
        raise ManifestError(f"invalid manifest source files: {path}")
    validated: list[str] = []
    for source in source_files:
        if not isinstance(source, str) or not source:
            raise ManifestError(f"invalid manifest source label: {path}")
        if PurePosixPath(source).is_absolute():
            raise ManifestError(f"absolute source label is unsupported: {path}")
        if ".." in source.split("/"):
            raise ManifestError(f"traversal source label is unsupported: {path}")
        normalized = PurePosixPath(source).as_posix()
        if (
            source != normalized
            or "\\" in source
            or "//" in source
            or not normalized.endswith(".py")
        ):
            raise ManifestError(f"invalid manifest source label: {path}")
        validated.append(source)
    if validated != sorted(set(validated)):
        raise ManifestError(f"manifest source labels are not canonical: {path}")
    return tuple(validated)


def _validate_node_id(node_id: object, path: Path) -> str:
    if not isinstance(node_id, str) or not node_id:
        raise ManifestError(f"invalid manifest node ID: {path}")
    if "[" in node_id or "]" in node_id:
        raise ManifestError(f"parameterized node suffix is unsupported: {path}")
    parts = node_id.split("::")
    valid_function = len(parts) == 1 and parts[0].startswith("test") and parts[0].isidentifier()
    valid_method = (
        len(parts) == 2
        and parts[0].startswith("Test")
        and parts[0].isidentifier()
        and parts[1].startswith("test")
        and parts[1].isidentifier()
    )
    if not valid_function and not valid_method:
        raise ManifestError(f"invalid manifest node ID: {path}")
    return node_id


def _validate_markers(markers: object, path: Path) -> tuple[str, ...]:
    if not isinstance(markers, list):
        raise ManifestError(f"invalid manifest markers: {path}")
    if any(
        not isinstance(marker, str) or not marker or not marker.isidentifier() for marker in markers
    ):
        raise ManifestError(f"invalid marker label: {path}")
    if markers != sorted(set(markers)):
        raise ManifestError(f"manifest markers are not canonical: {path}")
    return tuple(markers)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ManifestError(f"duplicate JSON key is unsupported: {key}")
        payload[key] = value
    return payload


def _decode_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(
            _read_absolute_no_follow(
                path,
                "manifest",
                max_bytes=MAX_MANIFEST_BYTES,
            ).decode("utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ManifestError(f"malformed JSON manifest: {path}") from error
    if not isinstance(payload, dict):
        raise ManifestError(f"manifest root must be an object: {path}")
    return payload


def _validate_manifest_header(payload: dict[str, object], path: Path) -> None:
    required = {
        "schema_version",
        "generated_by",
        "parameter_id_projection",
        "source_files",
        "test_definition_count",
        "collected_case_count",
        "nodes",
    }
    if set(payload) != required:
        raise ManifestError(f"invalid manifest fields: {path}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"unsupported schema: {path}")
    if payload.get("generated_by") != GENERATED_BY:
        raise ManifestError(f"invalid generated_by: {path}")
    if payload.get("parameter_id_projection") != "normalized-away":
        raise ManifestError(f"invalid parameter ID projection: {path}")


def _validate_manifest_counts(
    payload: dict[str, object],
    path: Path,
) -> tuple[int, int, int, list[object]]:
    source_files = payload.get("source_files")
    definition_count = payload.get("test_definition_count")
    case_count = payload.get("collected_case_count")
    raw_nodes = payload.get("nodes")
    if (
        not isinstance(definition_count, int)
        or isinstance(definition_count, bool)
        or definition_count < 0
        or not isinstance(case_count, int)
        or isinstance(case_count, bool)
        or case_count < 0
        or not isinstance(raw_nodes, list)
        or case_count != len(raw_nodes)
    ):
        raise ManifestError(f"invalid manifest counts or source files: {path}")
    validated_sources = _validate_source_labels(source_files, path)
    if definition_count > case_count:
        raise ManifestError(f"invalid manifest definition count: {path}")
    return definition_count, case_count, len(validated_sources), raw_nodes


def _normalize_manifest_nodes(raw_nodes: list[object], path: Path) -> list[CollectedNode]:
    normalized: list[CollectedNode] = []
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict) or set(raw_node) != {
            "normalized_node_id",
            "effective_markers",
        }:
            raise ManifestError(f"invalid manifest node: {path}")
        node_id = _validate_node_id(raw_node.get("normalized_node_id"), path)
        markers = _validate_markers(raw_node.get("effective_markers"), path)
        normalized.append(CollectedNode(node_id, markers))
    return normalized


def _validate_manifest_node_order(
    normalized: list[CollectedNode],
    definition_count: int,
    source_count: int,
    path: Path,
) -> None:
    canonical = sorted(
        normalized,
        key=lambda node: (node.normalized_node_id, node.effective_markers),
    )
    if normalized != canonical:
        raise ManifestError(f"manifest nodes are not canonical: {path}")
    unique_node_ids = {node.normalized_node_id for node in normalized}
    if not (
        len(unique_node_ids)
        <= definition_count
        <= len(unique_node_ids) * source_count
    ):
        raise ManifestError(f"invalid manifest definition count: {path}")


def _load_manifest(raw_path: str) -> LoadedManifest:
    path = Path(os.path.abspath(raw_path))
    payload = _decode_manifest(path)
    _validate_manifest_header(payload, path)
    definition_count, case_count, source_count, raw_nodes = _validate_manifest_counts(
        payload,
        path,
    )
    normalized = _normalize_manifest_nodes(raw_nodes, path)
    _validate_manifest_node_order(
        normalized,
        definition_count,
        source_count,
        path,
    )
    return LoadedManifest(definition_count, case_count, tuple(normalized))


def _compare(left_raw: str, right_raw: str) -> int:
    left = _load_manifest(left_raw)
    right = _load_manifest(right_raw)
    if (
        left.test_definition_count != right.test_definition_count
        or left.collected_case_count != right.collected_case_count
    ):
        print("collection manifest count drift", file=sys.stderr)
        return 1
    left_pairs = [(node.normalized_node_id, node.effective_markers) for node in left.nodes]
    right_pairs = [(node.normalized_node_id, node.effective_markers) for node in right.nodes]
    if {node_id for node_id, _markers in left_pairs} != {
        node_id for node_id, _markers in right_pairs
    }:
        print("collection manifest ID drift", file=sys.stderr)
        return 1
    if Counter(node_id for node_id, _markers in left_pairs) != Counter(
        node_id for node_id, _markers in right_pairs
    ):
        print("collection manifest duplicate drift", file=sys.stderr)
        return 1
    if Counter(left_pairs) != Counter(right_pairs):
        print("collection manifest marker drift", file=sys.stderr)
        return 1
    print("Pytest collection manifests match")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or compare static pytest collection manifests."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=str)
    mode.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument("sources", nargs="*")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.compare is not None:
            if args.sources:
                raise ManifestError("compare mode does not accept source files")
            return _compare(args.compare[0], args.compare[1])
        return _generate(args.output, args.sources)
    except RecursionError:
        print(
            "pytest collection manifest failed: input nesting depth is unsupported",
            file=sys.stderr,
        )
        return 2
    except (ManifestError, OSError) as error:
        print(f"pytest collection manifest failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
