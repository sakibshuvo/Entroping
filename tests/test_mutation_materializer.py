"""Tests for review-only status mutation materialization."""

import errno
import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import entroping.core.mutation_materializer_io as materializer_io
from entroping.core.mutation_materializer import (
    MutationMaterializerError,
    materialize_mutation_candidate,
)
from entroping.models.secrets import contains_secret_like_value


def _candidate_id(manifest_without_id: dict[str, object]) -> str:
    canonical = json.dumps(
        manifest_without_id,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"mut-{hashlib.sha256(canonical).hexdigest()[:24]}"


def _write_status_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    source = tmp_path / "tests" / "source.hurl"
    source.parent.mkdir()
    (tmp_path / "tests" / "generated" / "mutations").mkdir(parents=True)
    source_bytes = b"# entroping: safety=read-only\n\nGET {{base_url}}/health\nHTTP 200\n"
    source.write_bytes(source_bytes)
    source_stat = source.stat()
    manifest_core: dict[str, object] = {
        "category": "status-code",
        "project_relative_source_path": "tests/source.hurl",
        "expected_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "reviewed_seed": 7,
        "category_selector": {"assertion_ordinal": 0, "replacement_status": 500},
    }
    candidate_id = _candidate_id(manifest_core)
    manifest = {
        "schema_version": "entroping.mutation-materialization.v1",
        **manifest_core,
        "source_size_bytes": len(source_bytes),
        "source_mtime_ns": source_stat.st_mtime_ns,
        "reviewed_seed": 7,
        "review_decision_id": "decision-1",
        "evidence_ids": ["evidence-1"],
        "candidate_id": candidate_id,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return source, manifest_path, candidate_id


def test_materialize_status_candidate_writes_deterministic_review_only_hurl(
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    source_stat_before = os.stat(source)

    output_path = materialize_mutation_candidate(tmp_path, manifest_path)

    assert output_path == tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert output_path.read_text(encoding="utf-8") == (
        "# entroping: materializer_schema=entroping.mutation-materialization.v1\n"
        "# entroping: review_only=true\n"
        f"# entroping: candidate_id={candidate_id}\n"
        "# entroping: mutation_category=status-code\n"
        "# entroping: mutation_seed=7\n"
        f"# entroping: source_sha256={hashlib.sha256(source_before).hexdigest()}\n"
        f"# entroping: source_size_bytes={len(source_before)}\n"
        f"# entroping: source_mtime_ns={source_stat_before.st_mtime_ns}\n"
        "# entroping: safety=read-only\n"
        "# entroping: review_decision_id=decision-1\n"
        "# entroping: evidence_ids=evidence-1\n\n"
        "GET {{base_url}}/health\n"
        "HTTP 500\n"
    )
    assert source.read_bytes() == source_before
    assert os.stat(source).st_mtime_ns == source_stat_before.st_mtime_ns


@pytest.mark.parametrize("capability", ("_NOFOLLOW", "_DIRECTORY_FLAG", "_NONBLOCK"))
def test_materializer_rejects_unsupported_platform_before_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capability: str,
) -> None:
    import entroping.core.mutation_materializer as materializer

    touched: list[str] = []
    monkeypatch.setattr(materializer, capability, 0)

    def fake_open_root(_root: Path) -> int:
        touched.append("root")
        return -1

    monkeypatch.setattr(materializer_io, "open_root", fake_open_root)
    monkeypatch.setattr(
        materializer_io,
        "open_relative_directory",
        lambda _root: touched.append("destination"),
    )
    monkeypatch.setattr(
        materializer,
        "_load_manifest",
        lambda _root, _fd, _manifest: touched.append("manifest"),
    )
    monkeypatch.setattr(
        materializer_io,
        "open_source",
        lambda _root, _parts: touched.append("source"),
    )

    with pytest.raises(MutationMaterializerError, match="platform capability"):
        materializer.materialize_mutation_candidate(tmp_path, tmp_path / "manifest.json")

    assert touched == []


@pytest.mark.parametrize(
    ("capability_set", "required_function"),
    (("supports_dir_fd", os.open), ("supports_follow_symlinks", os.stat)),
)
def test_materializer_rejects_missing_capability_set_before_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capability_set: str,
    required_function: object,
) -> None:
    import entroping.core.mutation_materializer as materializer

    supported = set(getattr(os, capability_set))
    supported.discard(required_function)
    monkeypatch.setattr(os, capability_set, supported)
    touched: list[str] = []
    monkeypatch.setattr(materializer_io, "open_root", lambda _root: touched.append("root"))

    with pytest.raises(MutationMaterializerError, match="platform capability"):
        materializer.materialize_mutation_candidate(tmp_path, tmp_path / "manifest.json")

    assert touched == []


def test_materializer_rejects_missing_publication_backend_before_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import entroping.core.mutation_materializer as materializer

    touched: list[str] = []
    monkeypatch.setattr(materializer_io, "_PUBLICATION_BACKEND", None)
    monkeypatch.setattr(materializer_io, "open_root", lambda _root: touched.append("root"))

    with pytest.raises(MutationMaterializerError, match="platform capability"):
        materializer.materialize_mutation_candidate(tmp_path, tmp_path / "manifest.json")

    assert touched == []


def test_materializer_reconstructs_short_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import entroping.core.mutation_materializer as materializer

    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_read = os.read

    def short_read(fd: int, size: int) -> bytes:
        return real_read(fd, min(size, 2))

    monkeypatch.setattr(os, "read", short_read)

    output_path = materializer.materialize_mutation_candidate(tmp_path, manifest_path)

    assert output_path.name == f"{candidate_id}.hurl"
    assert source.exists()


def test_materializer_rejects_nonregular_manifest_before_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import entroping.core.mutation_materializer as materializer

    _source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    manifest_path.unlink()
    manifest_path.mkdir()

    def read_must_not_run(_fd: int, _size: int) -> bytes:
        raise AssertionError("manifest read must not run for non-regular file")

    monkeypatch.setattr(os, "read", read_must_not_run)

    with pytest.raises(MutationMaterializerError, match="manifest"):
        materializer.materialize_mutation_candidate(tmp_path, manifest_path)


def test_materializer_rejects_fifo_source_without_blocking(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO support is unavailable")
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source.unlink()
    os.mkfifo(source)
    script = """
import sys
from pathlib import Path
from entroping.core.mutation_materializer import (
    MutationMaterializerError,
    materialize_mutation_candidate,
)
try:
    materialize_mutation_candidate(Path(sys.argv[1]), Path(sys.argv[2]))
except MutationMaterializerError:
    raise SystemExit(0)
raise SystemExit(3)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), str(manifest_path)],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=2,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_bounded_read_rejects_limit_plus_one(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"123456789")
    descriptor = os.open(oversized, os.O_RDONLY)
    try:
        with pytest.raises(MutationMaterializerError, match="oversized"):
            materializer_io.read_bounded_fd(descriptor, 8)
    finally:
        os.close(descriptor)


def test_materializer_rejects_zero_progress_write_without_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import entroping.core.mutation_materializer as materializer

    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    monkeypatch.setattr(os, "write", lambda _fd, _raw: 0)

    with pytest.raises(MutationMaterializerError, match="no progress"):
        materializer.materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("category", []),
        ("project_relative_source_path", 17),
        ("source_size_bytes", []),
        ("source_mtime_ns", {}),
        ("reviewed_seed", "7"),
        ("review_decision_id", []),
        ("evidence_ids", {}),
        ("candidate_id", []),
        ("category_selector", []),
    ),
)
def test_materializer_rejects_malformed_manifest_types_without_raw_errors(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document[field] = value
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="manifest field is invalid") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "manifest field is invalid"
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materializer_surfaces_output_cleanup_failure_without_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    monkeypatch.setattr(os, "write", lambda _fd, _raw: 0)

    real_unlink = os.unlink
    destination = tmp_path / "tests" / "generated" / "mutations"
    destination_identity = (destination.stat().st_dev, destination.stat().st_ino)

    def fail_unlink(_name: str, *, dir_fd: int | None = None) -> None:
        if _name.endswith(".materializing") and dir_fd is not None:
            identity = os.fstat(dir_fd)
            if (identity.st_dev, identity.st_ino) == destination_identity:
                raise OSError("injected cleanup failure")
        real_unlink(_name, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_unlink)
    supported_dir_fd = set(os.supports_dir_fd)
    supported_dir_fd.add(fail_unlink)
    monkeypatch.setattr(os, "supports_dir_fd", supported_dir_fd)

    with pytest.raises(MutationMaterializerError, match="output cleanup failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output cleanup failed"
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materializer_commits_after_link_when_temp_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_unlink = os.unlink

    def fail_temp_unlink(name: str, *, dir_fd: int | None = None) -> None:
        if name.endswith(".materializing") and dir_fd is not None:
            raise OSError("injected post-link cleanup failure")
        real_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_temp_unlink)
    supported_dir_fd = set(os.supports_dir_fd)
    supported_dir_fd.add(fail_temp_unlink)
    monkeypatch.setattr(os, "supports_dir_fd", supported_dir_fd)

    output = materialize_mutation_candidate(tmp_path, manifest_path)
    assert output == tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert output.exists()
    assert output.with_name(f".{output.name}.materializing").exists()


def test_materializer_rejects_replaced_temp_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    attacker_target = destination / "attacker-controlled.hurl"
    attacker_target.write_text("attacker controlled", encoding="utf-8")
    real_unlink = os.unlink
    real_symlink = os.symlink

    real_publish = materializer_io._publish_output

    def replace_temp_then_publish(
        descriptor: int,
        destination_fd: int,
        temporary_name: str,
        name: str,
    ) -> None:
        real_unlink(temporary_name, dir_fd=destination_fd)
        real_symlink(attacker_target.name, temporary_name, dir_fd=destination_fd)
        real_publish(descriptor, destination_fd, temporary_name, name)

    monkeypatch.setattr(materializer_io, "_publish_output", replace_temp_then_publish)

    output = destination / f"{candidate_id}.hurl"
    materialize_mutation_candidate(tmp_path, manifest_path)

    assert output.exists()
    assert not output.is_symlink()
    assert "HTTP 500" in output.read_text(encoding="utf-8")


def test_materializer_rejects_filesystem_publication_refusal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    backend = materializer_io._PUBLICATION_BACKEND
    assert backend is not None
    monkeypatch.setattr(materializer_io, "_PUBLICATION_BACKEND", lambda *_args: errno.ENOTSUP)

    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"
    with pytest.raises(MutationMaterializerError, match="publication unsupported") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output publication unsupported"
    assert not output.exists()
    assert not temporary.exists()
    assert source.read_bytes() == source_before


@pytest.mark.parametrize("first_write", (0, 1))
def test_materializer_failed_partial_write_cannot_claim_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    first_write: int,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    writes = 0

    def partial_write(_fd: int, raw: bytes) -> int:
        nonlocal writes
        writes += 1
        return first_write if writes == 1 else 0

    monkeypatch.setattr(os, "write", partial_write)

    with pytest.raises(MutationMaterializerError, match="no progress"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_imports_secret_checks_from_models() -> None:
    import entroping.core.mutation_materializer as materializer

    assert contains_secret_like_value.__module__ == "entroping.models.secrets"
    assert "from entroping.models.secrets import" in inspect.getsource(materializer)


@pytest.mark.parametrize(
    "manifest_change",
    (
        {"expected_sha256": "0" * 64},
        {"project_relative_source_path": "../outside.hurl"},
        {"project_relative_source_path": "tests//source.hurl"},
        {"project_relative_source_path": "tests/./source.hurl"},
        {"project_relative_source_path": "tests/source.hurl/"},
        {"candidate_id": "mut-invalid"},
        {"category": "request-shape"},
    ),
)
def test_materialize_rejects_invalid_manifest_before_output(
    tmp_path: Path,
    manifest_change: dict[str, object],
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document.update(manifest_change)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_duplicate_output_without_overwrite(tmp_path: Path) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    output.write_bytes(b"sentinel")

    with pytest.raises(MutationMaterializerError, match="already exists"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert output.read_bytes() == b"sentinel"


def test_materialize_rejects_source_symlink_without_writing(tmp_path: Path) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    target = tmp_path / "outside.hurl"
    target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_symlinked_destination_ancestry(tmp_path: Path) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "tests" / "generated").rename(tmp_path / "tests" / "generated-real")
    (tmp_path / "tests" / "generated").symlink_to(outside, target_is_directory=True)

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (outside / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_missing_safety_and_reserved_metadata(tmp_path: Path) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source.write_text("# entroping: candidate_id=old\n\nGET /health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_status_no_op_before_output(tmp_path: Path) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["category_selector"]["replacement_status"] = 200
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="no-op"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.exists()
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_status_ordinal_ignores_http_line_after_response(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = b"# entroping: safety=read-only\n\nGET /health\nHTTP 200\nHTTP 599\n"
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    document["category_selector"] = {"assertion_ordinal": 1, "replacement_status": 500}
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="assertion is missing"):
        materialize_mutation_candidate(tmp_path, manifest_path)


def test_status_ordinal_never_mutates_triple_backtick_body_status(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b"# entroping: safety=read-only\n\nPOST {{base_url}}/health\n```\nHTTP 201\n```\nHTTP 200\n"
    )
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    document["category_selector"] = {"assertion_ordinal": 0, "replacement_status": 500}
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    output = materialize_mutation_candidate(tmp_path, manifest_path).read_text(encoding="utf-8")

    assert "```\nHTTP 201\n```" in output
    assert "```\nHTTP 500\n```" not in output
    assert output.endswith("HTTP 500\n")


@pytest.mark.parametrize(
    ("body", "body_status"),
    (
        (b"```json\nHTTP 201\n```\n", b"```json\nHTTP 201\n```"),
        (b"<request>\nHTTP 201\n</request>\n", b"<request>\nHTTP 201\n</request>"),
        (
            b"<request>\n<inner>\nHTTP 201\n</inner>\n</request>\n",
            b"<request>\n<inner>\nHTTP 201\n</inner>\n</request>",
        ),
    ),
)
def test_status_ordinal_never_mutates_typed_or_xml_body_status(
    tmp_path: Path,
    body: bytes,
    body_status: bytes,
) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b"# entroping: safety=read-only\n\nPOST {{base_url}}/health\n" + body + b"HTTP 200\n"
    )
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    document["category_selector"] = {"assertion_ordinal": 0, "replacement_status": 500}
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    output = materialize_mutation_candidate(tmp_path, manifest_path).read_bytes()

    assert body_status in output
    assert body_status.replace(b"201", b"500") not in output
    assert output.endswith(b"HTTP 500\n")
