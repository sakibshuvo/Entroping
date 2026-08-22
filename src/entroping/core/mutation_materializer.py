"""Review-only, create-once materialization of a reviewed Hurl mutation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypedDict, TypeGuard

from entroping.core import mutation_materializer_hurl_requests as _hurl_requests
from entroping.core import mutation_materializer_io as _io
from entroping.core import mutation_materializer_request_shape as _request_shape
from entroping.core.hurl_validator import HurlValidationError, validate_hurl_content
from entroping.models.hurl import (
    HurlMetadata,
    HurlMetadataSyntaxError,
    parse_hurl_exchanges,
    parse_hurl_metadata,
)
from entroping.models.secrets import contains_secret_like_value, has_disallowed_control


def _tokens(value: str) -> frozenset[str]:
    return frozenset(value.split())  # normalize compact field tables


MutationMaterializerError = _io.MutationMaterializerError
HURL_SOURCE_MAX_BYTES: Final = _io.HURL_SOURCE_MAX_BYTES
_SCHEMA: Final = "entroping.mutation-materialization.v1"  # manifest contract
_ROOT_KEYS: Final = _tokens(
    "schema_version category project_relative_source_path expected_sha256 source_size_bytes "
    "source_mtime_ns reviewed_seed category_selector review_decision_id evidence_ids candidate_id"
)
_TEXT_FIELDS: Final = _tokens(
    "schema_version category project_relative_source_path expected_sha256 review_decision_id "
    "candidate_id"
)
_INT_FIELDS: Final = frozenset({"source_size_bytes", "source_mtime_ns", "reviewed_seed"})
_RESERVED_SOURCE_KEYS: Final = _tokens(
    "materializer_schema review_only candidate_id mutation_category mutation_seed source_sha256 "
    "source_size_bytes source_mtime_ns review_decision_id evidence_ids"
)
_SAFETY_VALUES: Final = frozenset({"read-only", "idempotent", "teardown-backed", "destructive"})
_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SHA_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_SAFETY_RE: Final = re.compile(r"^# entroping:\s*safety=([^\r\n]+)\s*$")
_NOFOLLOW: Final = _io.NOFOLLOW
_DIRECTORY_FLAG: Final = _io.DIRECTORY_FLAG
_NONBLOCK: Final = _io.NONBLOCK


MutationCategory = Literal["status-code", "request-shape"]
JsonScalar = None | bool | int | float | str
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class StatusSelector(TypedDict):
    assertion_ordinal: int
    replacement_status: int


class _ManifestDocument(TypedDict):
    schema_version: str
    category: str
    project_relative_source_path: str
    expected_sha256: str
    source_size_bytes: int
    source_mtime_ns: int
    reviewed_seed: int
    category_selector: StatusSelector | _request_shape.RequestShapeSelector
    review_decision_id: str
    evidence_ids: list[str]
    candidate_id: str


def _is_json_object(value: object) -> TypeGuard[dict[str, JsonValue]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _reject(condition: bool, error: str) -> None:
    if condition:
        raise MutationMaterializerError(error)


@dataclass(frozen=True, slots=True)
class _ValidatedManifest:
    category: MutationCategory
    source_parts: tuple[str, ...]
    expected_sha256: str
    source_size_bytes: int
    source_mtime_ns: int
    reviewed_seed: int
    selector: StatusSelector | _request_shape.RequestShapeSelector
    review_decision_id: str
    evidence_ids: tuple[str, ...]
    candidate_id: str


def materialize_mutation_candidate(
    project_root: Path,
    manifest_path: Path,
) -> Path:
    _io.platform_capability_preflight(_NOFOLLOW, _DIRECTORY_FLAG, _NONBLOCK)
    root = project_root.expanduser()
    root_fd = _io.open_root(root)
    try:
        return _materialize_with_root(root, root_fd, manifest_path)
    except MutationMaterializerError:
        raise
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MutationMaterializerError("mutation materialization rejected") from exc
    finally:
        if root_fd >= 0:
            with suppress(OSError):
                os.close(root_fd)


def _materialize_with_root(
    root: Path,
    root_fd: int,
    manifest_path: Path,
) -> Path:
    destination_fd, destination_ids = _io.open_relative_directory(
        root_fd, ("tests", "generated", "mutations")
    )
    source_fd = parent_fd = -1
    try:
        manifest = _load_manifest(root, root_fd, manifest_path)
        source_fd, parent_fd, leaf = _io.open_source(root_fd, manifest.source_parts)
        first_stat, source_bytes = _read_source(source_fd, manifest)
        try:
            content = source_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MutationMaterializerError("source is not UTF-8") from exc
        safety = _validate_source_content(content)
        if manifest.category == "status-code":
            output = _render_status_candidate(content, manifest, safety)
        else:
            output = _render_request_shape_candidate(content, manifest)
        _validate_rendered_output(output)
        _recheck_source(parent_fd, leaf, source_fd, first_stat, manifest)
        rechecked_fd, rechecked_ids = _io.open_relative_directory(
            root_fd, ("tests", "generated", "mutations")
        )
        os.close(rechecked_fd)
        if rechecked_ids != destination_ids:
            raise MutationMaterializerError("destination changed before publication")
        output_name = f"{manifest.candidate_id}.hurl"
        output_path = root / "tests" / "generated" / "mutations" / output_name
        _io.create_output(destination_fd, output_name, output)
        return output_path
    finally:
        for descriptor in (source_fd, parent_fd, destination_fd):
            with suppress(OSError):
                os.close(descriptor)


def _load_manifest(root: Path, root_fd: int, manifest_path: Path) -> _ValidatedManifest:
    raw_path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    _reject(raw_path.is_symlink(), "manifest path is unsafe")
    try:
        relative = raw_path.relative_to(root)
    except ValueError as exc:
        raise MutationMaterializerError("manifest path must be project-relative") from exc
    parts = _io.relative_parts(relative.as_posix(), label="manifest path")
    parent_fd, _ = _io.open_relative_directory(root_fd, parts[:-1])
    try:
        descriptor = _io.open_regular(
            parent_fd,
            parts[-1],
            os.O_RDONLY | _NONBLOCK | _NOFOLLOW,
            "manifest is not a regular file",
        )
        try:
            raw = _io.read_bounded_fd(descriptor, 1_048_576)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)
    parsed_value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    _reject(not _is_json_object(parsed_value), "manifest field is invalid")
    _reject(set(parsed_value) != _ROOT_KEYS, "manifest keys are invalid")
    return _parse_manifest(parsed_value)


def _reject_duplicate_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise MutationMaterializerError("manifest contains duplicate keys")
        result[key] = value
    return result


def _parse_manifest(document: dict[str, JsonValue]) -> _ValidatedManifest:
    if not _validate_manifest_types(document):
        raise MutationMaterializerError("manifest field is invalid")
    schema_version = _manifest_text(document["schema_version"])
    _reject(schema_version != _SCHEMA, "manifest schema is unsupported")
    category = _parse_category(_manifest_text(document["category"]))
    source_path = _manifest_text(document["project_relative_source_path"])
    source_parts = _io.relative_parts(source_path, label="source path")
    expected = _manifest_text(document["expected_sha256"])
    _reject(_SHA_RE.fullmatch(expected) is None, "source hash is invalid")
    source_size = _bounded_int(
        document["source_size_bytes"], 1, HURL_SOURCE_MAX_BYTES, "source size is invalid"
    )
    mtime = _bounded_int(document["source_mtime_ns"], 0, None, "source mtime is invalid")
    seed = _bounded_int(document["reviewed_seed"], 0, 4_294_967_295, "mutation seed is invalid")
    decision = _manifest_text(document["review_decision_id"])
    _reject(_IDENTIFIER_RE.fullmatch(decision) is None, "review decision is invalid")
    evidence = _validate_evidence(document["evidence_ids"])
    candidate = _manifest_text(document["candidate_id"])
    _reject(_IDENTIFIER_RE.fullmatch(candidate) is None, "candidate id is invalid")
    selector = _validate_selector(category, document["category_selector"])
    identity = {
        "category": category,
        "project_relative_source_path": source_path,  # noqa: E501
        "expected_sha256": expected,
        "reviewed_seed": seed,
        "category_selector": selector,
    }
    canonical = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    derived = f"mut-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"
    _reject(candidate != derived, "candidate id does not match manifest")
    return _ValidatedManifest(
        category,
        source_parts,
        expected,
        source_size,
        mtime,
        seed,
        selector,
        decision,
        tuple(evidence),
        candidate,
    )


def _validate_manifest_types(
    document: dict[str, JsonValue],
) -> TypeGuard[_ManifestDocument]:
    return (
        _typed_fields(document, _TEXT_FIELDS, str)
        and _typed_fields(document, _INT_FIELDS, int)
        and _typed_list(document.get("evidence_ids"), str)
        and _selector_types_valid(document)
    )


def _typed_fields(doc: dict[str, JsonValue], keys: frozenset[str], expected: type[object]) -> bool:
    return all(type(doc.get(key)) is expected for key in keys)


def _typed_list(value: JsonValue, expected: type[object]) -> bool:
    return isinstance(value, list) and all(type(item) is expected for item in value)


def _selector_types_valid(document: dict[str, JsonValue]) -> bool:
    selector = document.get("category_selector")
    if not _is_json_object(selector) or not selector:
        return False
    return _selector_types_for_category(document.get("category"), selector)


def _selector_types_for_category(category: JsonValue, selector: dict[str, JsonValue]) -> bool:
    if category == "status-code":
        return all(type(value) is int for value in selector.values())
    if category != "request-shape":
        return False
    return _request_shape.selector_types_valid(selector)


def _parse_category(value: str) -> MutationCategory:
    if value == "status-code":
        return "status-code"
    if value == "request-shape":
        return "request-shape"
    raise MutationMaterializerError("manifest category is unsupported")


def _manifest_text(value: str) -> str:
    _reject(
        unicodedata.normalize("NFC", value) != value or has_disallowed_control(value),
        "manifest text is not normalized",
    )
    _reject(contains_secret_like_value(value), "manifest contains unsafe text")
    return value


def _bounded_int(value: int, lower: int, upper: int | None, error: str) -> int:
    _reject(value < lower or (upper is not None and value > upper), error)
    return value


def _validate_evidence(evidence: list[str]) -> list[str]:
    _reject(len(evidence) not in range(1, 33), "evidence ids are invalid")
    values: list[str] = []
    for item in evidence:
        values.append(_validate_evidence_item(item))
    _reject(tuple(values) != tuple(sorted(set(values))), "evidence ids are invalid")
    return values


def _validate_evidence_item(item: str) -> str:
    _reject(
        unicodedata.normalize("NFC", item) != item
        or has_disallowed_control(item)
        or contains_secret_like_value(item)
        or _IDENTIFIER_RE.fullmatch(item) is None,
        "evidence ids are invalid",
    )
    return item


def _is_status_selector(
    selector: StatusSelector | _request_shape.RequestShapeSelector,
) -> TypeGuard[StatusSelector]:
    return "assertion_ordinal" in selector and "replacement_status" in selector


def _is_request_shape_selector(
    selector: StatusSelector | _request_shape.RequestShapeSelector,
) -> TypeGuard[_request_shape.RequestShapeSelector]:
    return "request_ordinal" in selector and "json_pointer" in selector and "corpus_id" in selector


def _validate_selector(
    category: MutationCategory,
    selector: StatusSelector | _request_shape.RequestShapeSelector,
) -> StatusSelector | _request_shape.RequestShapeSelector:
    if category == "status-code":
        if not _is_status_selector(selector):
            raise MutationMaterializerError("category selector keys are invalid")
        _reject(
            set(selector) != {"assertion_ordinal", "replacement_status"},
            "category selector keys are invalid",
        )
        return {
            "assertion_ordinal": _bounded_int(
                selector["assertion_ordinal"], 0, 9_999, "status assertion ordinal is invalid"
            ),
            "replacement_status": _bounded_int(
                selector["replacement_status"], 100, 599, "replacement status is invalid"
            ),
        }

    if not _is_request_shape_selector(selector):
        raise MutationMaterializerError("request-shape selector is invalid")
    return _request_shape.validate_selector(selector)


def _render_metadata(manifest: _ValidatedManifest, safety: str) -> str:
    return f"# entroping: materializer_schema={_SCHEMA}\n# entroping: review_only=true\n# entroping: candidate_id={manifest.candidate_id}\n# entroping: mutation_category={manifest.category}\n# entroping: mutation_seed={manifest.reviewed_seed}\n# entroping: source_sha256={manifest.expected_sha256}\n# entroping: source_size_bytes={manifest.source_size_bytes}\n# entroping: source_mtime_ns={manifest.source_mtime_ns}\n# entroping: safety={safety}\n# entroping: review_decision_id={manifest.review_decision_id}\n# entroping: evidence_ids={','.join(manifest.evidence_ids)}\n"  # noqa: E501


def _read_source(source_fd: int, manifest: _ValidatedManifest) -> tuple[os.stat_result, bytes]:
    metadata = os.fstat(source_fd)
    _reject(
        metadata.st_size != manifest.source_size_bytes
        or metadata.st_mtime_ns != manifest.source_mtime_ns,
        "source identity does not match manifest",
    )
    os.lseek(source_fd, 0, os.SEEK_SET)
    try:
        raw = _io.read_bounded_fd(source_fd, HURL_SOURCE_MAX_BYTES)
    except MutationMaterializerError as exc:
        raise MutationMaterializerError("source size is invalid") from exc
    _reject(len(raw) != manifest.source_size_bytes, "source size is invalid")
    _reject(
        hashlib.sha256(raw).hexdigest() != manifest.expected_sha256,
        "source hash does not match manifest",
    )
    return metadata, raw  # identity is checked before the second read


def _validate_source_content(content: str) -> str:
    _reject(
        has_disallowed_control(content) or contains_secret_like_value(content),
        "source contains unsafe content",
    )
    metadata, safety = _parse_source_metadata(content)
    _reject(
        bool(_RESERVED_SOURCE_KEYS.intersection(metadata.meta)),
        "source contains reserved materializer metadata",
    )
    return safety


def _parse_source_metadata(content: str) -> tuple[HurlMetadata, str]:
    try:
        metadata = parse_hurl_metadata(content)
    except HurlMetadataSyntaxError as exc:
        raise MutationMaterializerError("source metadata is invalid") from exc
    safety_lines = [line for line in content.splitlines() if _SAFETY_RE.fullmatch(line)]
    _reject(
        len(safety_lines) != 1 or safety_lines[0].split("=", 1)[1] not in _SAFETY_VALUES,
        "source safety metadata is invalid",
    )
    return metadata, safety_lines[0].split("=", 1)[1].strip()


def _validate_rendered_output(output: str) -> None:
    try:
        parse_hurl_metadata(output)
        exchanges = parse_hurl_exchanges(output)
        validate_hurl_content(output, "tests/generated/mutations/output.hurl")
    except (HurlMetadataSyntaxError, HurlValidationError, OSError) as exc:
        raise MutationMaterializerError("generated Hurl failed validation") from exc
    _reject(
        not exchanges or output.count("# entroping: safety=") != 1,
        "generated Hurl structure is invalid",
    )


def _remove_source_safety_line(content: str) -> str:
    lines = content.splitlines(keepends=True)
    rendered: list[str] = []
    removed = False
    for line in lines:
        if _SAFETY_RE.fullmatch(line.rstrip("\r\n")):
            _reject(removed, "source safety metadata is invalid")
            removed = True
            continue
        rendered.append(line)
    _reject(not removed, "source safety metadata is invalid")
    return "".join(rendered)


def _render_status_candidate(content: str, manifest: _ValidatedManifest, safety: str) -> str:
    lines = content.splitlines(keepends=True)
    selector = manifest.selector
    if not _is_status_selector(selector):
        raise MutationMaterializerError("status-code selector is invalid")
    rendered, safety_removed, selected = _render_lines(
        lines, selector["assertion_ordinal"], selector["replacement_status"]
    )
    _reject(not safety_removed or not selected, "status assertion is missing")
    return _render_metadata(manifest, safety) + "".join(rendered)


def _render_request_shape_candidate(content: str, manifest: _ValidatedManifest) -> str:
    selector = manifest.selector
    if not _is_request_shape_selector(selector):
        raise MutationMaterializerError("request-shape selector is invalid")
    mutated = _request_shape.materialize_request_shape(content, selector, manifest.reviewed_seed)
    return _render_metadata(manifest, "destructive") + _remove_source_safety_line(mutated)


def _render_lines(lines: list[str], ordinal: int, replacement: int) -> tuple[list[str], bool, bool]:
    status_seen = 0
    rendered: list[str] = []
    safety_removed = False
    selected = False
    response_statuses = _hurl_requests.response_statuses(lines)
    for line_number, line in enumerate(lines):
        if _SAFETY_RE.fullmatch(line.rstrip("\r\n")):
            safety_removed = True
            continue
        match = response_statuses.get(line_number)
        if match is not None:
            if status_seen == ordinal:
                current = int(line[len(match.group(1)) :].split()[0])
                _reject(current == replacement, "status mutation is a no-op")
                end = len(line.rstrip("\r\n"))
                line = (
                    f"{match.group(1)}{replacement}"
                    + line[len(match.group(1)) + len(str(current)) : end]
                    + line[end:]
                )
                selected = True
            status_seen += 1
        rendered.append(line)
    return rendered, safety_removed, selected


def _recheck_source(
    parent_fd: int,
    leaf: str,
    source_fd: int,
    first_stat: os.stat_result,
    manifest: _ValidatedManifest,
) -> None:
    _read_source(source_fd, manifest)
    _io.recheck_source(parent_fd, leaf, first_stat)
