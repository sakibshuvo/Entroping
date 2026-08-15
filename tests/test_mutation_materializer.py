"""Tests for review-only status mutation materialization."""

import errno
import hashlib
import inspect
import json
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import pytest

import entroping.core.mutation_materializer_io as materializer_io
from entroping.core.mutation_materializer import (
    MutationMaterializerError,
    materialize_mutation_candidate,
)
from entroping.models.secrets import contains_secret_like_value


@pytest.fixture(autouse=True)
def _stub_external_hurlfmt_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep materializer unit tests independent of the optional Hurl binary."""

    monkeypatch.setattr(
        "entroping.core.mutation_materializer.validate_hurl_content",
        lambda _content, _display_path: None,
    )


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


def _install_linux_link(
    monkeypatch: pytest.MonkeyPatch,
    link: Callable[..., object],
) -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("requires the Linux descriptor-link publication path")
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, link})
    monkeypatch.setattr(
        os,
        "supports_follow_symlinks",
        {*os.supports_follow_symlinks, link},
    )


@pytest.mark.parametrize("outcome", ("success", "exists", "error"))
def test_descriptor_link_backend_maps_errno_without_platform_mutation(outcome: str) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_link(*args: object, **kwargs: object) -> None:
        calls.append((*args, *kwargs.values()))
        if outcome == "exists":
            raise FileExistsError(errno.EEXIST, "injected")
        if outcome == "error":
            raise OSError(errno.EIO, "injected")

    backend = materializer_io.descriptor_link_backend(fake_link)
    expected = {"success": 0, "exists": errno.EEXIST, "error": errno.EIO}[outcome]

    assert backend(7, 9, b"candidate.hurl", ".candidate.materializing") == expected
    assert calls == [
        ("/proc/self/fd/7", "candidate.hurl", 9, True),
    ]


@pytest.mark.parametrize(
    ("result", "message"),
    (
        (errno.EEXIST, "candidate output already exists"),
        (errno.ENOTSUP, "candidate output publication unsupported"),
        (errno.EIO, "candidate output could not be published"),
    ),
)
def test_publication_result_check_maps_fixed_errors(result: int, message: str) -> None:
    with pytest.raises(MutationMaterializerError, match=message) as caught:
        materializer_io.publication_result_check(result)
    assert str(caught.value) == message
    materializer_io.publication_result_check(0)


def _verification_fixture(
    tmp_path: Path,
    *,
    final_bytes: bytes | None,
) -> tuple[int, int, Path, tuple[int, int]]:
    destination = tmp_path / "destination"
    destination.mkdir()
    held_path = tmp_path / "held.hurl"
    content = b"GET /health\nHTTP 200\n"
    held_path.write_bytes(content)
    held_fd = os.open(held_path, os.O_RDONLY)
    held = os.fstat(held_fd)
    output = destination / "candidate.hurl"
    if final_bytes is not None:
        output.write_bytes(final_bytes)
    destination_fd = os.open(
        destination,
        os.O_RDONLY | materializer_io.DIRECTORY_FLAG | materializer_io.NOFOLLOW,
    )
    return held_fd, destination_fd, output, (held.st_dev, held.st_ino)


def test_verify_published_output_rejects_missing_final(tmp_path: Path) -> None:
    held_fd, destination_fd, _output, expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=None,
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                "candidate.hurl",
                expected_identity,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_verify_published_output_rejects_empty_final(tmp_path: Path) -> None:
    held_fd, destination_fd, _output, expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=b"",
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                "candidate.hurl",
                expected_identity,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_verify_published_output_rejects_distinct_inode(tmp_path: Path) -> None:
    content = b"GET /health\nHTTP 200\n"
    held_fd, destination_fd, output, expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=content,
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                output.name,
                expected_identity,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_verify_published_output_rejects_same_size_wrong_content(tmp_path: Path) -> None:
    held_fd, destination_fd, output, _expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=b"GET /health\nHTTP 201\n",
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                output.name,
                None,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_materializer_rejects_relative_and_symlink_roots(tmp_path: Path) -> None:
    with pytest.raises(MutationMaterializerError, match="root is unsafe"):
        materialize_mutation_candidate(Path("relative"), Path("relative/manifest.json"))

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(MutationMaterializerError, match="root is unsafe"):
        materialize_mutation_candidate(link, link / "manifest.json")


def test_materializer_rejects_unavailable_project_root_without_output(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing-project"

    with pytest.raises(MutationMaterializerError, match="root is unavailable") as caught:
        materialize_mutation_candidate(missing_root, missing_root / "manifest.json")

    assert str(caught.value) == "project root is unavailable"


@pytest.mark.parametrize(
    "source_path",
    ("", "tests//source.hurl", "tests/../source.hurl", "tests/token=abc.hurl"),
)
def test_materializer_rejects_unsafe_source_paths_without_output(
    tmp_path: Path,
    source_path: str,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["project_relative_source_path"] = source_path
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError) as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) in {
        "source path is unsafe",
        "source path must be project-relative",
        "manifest contains unsafe text",
    }
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


@pytest.mark.parametrize("source_path", ("source.hurl", "tests/source.hurl/"))
def test_materializer_rejects_unsafe_source_shape_without_output(
    tmp_path: Path,
    source_path: str,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["project_relative_source_path"] = source_path
    identity: dict[str, object] = {
        "category": document["category"],
        "project_relative_source_path": source_path,
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    candidate_id = _candidate_id(identity)
    document["candidate_id"] = candidate_id
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="source") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) in {
        "source path is unsafe",
        "source path must be project-relative",
    }
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_rejects_busy_temporary_without_overwrite(tmp_path: Path) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    temporary = output.with_name(f".{output.name}.materializing")
    temporary.write_text("busy", encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="already being materialized") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output is already being materialized"
    assert temporary.read_text(encoding="utf-8") == "busy"
    assert not output.exists()


def test_materializer_wraps_output_sync_error_and_cleans_temporary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)

    def fail_fsync(_fd: int) -> None:
        raise OSError("injected sync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(MutationMaterializerError, match="could not be written") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output could not be written"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()
    assert not output.with_name(f".{output.name}.materializing").exists()


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


def test_materializer_rejects_non_utf8_source(tmp_path: Path) -> None:
    import entroping.core.mutation_materializer as materializer

    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = b"# entroping: safety=read-only\n\nGET /health\nHTTP 200\n\xff"
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="source is not UTF-8"):
        materializer.materialize_mutation_candidate(tmp_path, manifest_path)


def test_materializer_rejects_malformed_source_metadata_without_output(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = b"# entroping: tags=\n\nGET /health\nHTTP 200\n"
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    candidate_id = _candidate_id(identity)
    document["candidate_id"] = candidate_id
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="source metadata is invalid") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "source metadata is invalid"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_wraps_public_hurl_validation_error_without_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import entroping.core.hurl_validator as hurl_validator

    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)

    def reject(_content: str, _display_path: str) -> None:
        raise hurl_validator.HurlValidationError("invalid")

    monkeypatch.setattr("entroping.core.mutation_materializer.validate_hurl_content", reject)
    with pytest.raises(
        MutationMaterializerError, match="generated Hurl failed validation"
    ) as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "generated Hurl failed validation"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_rejects_manifest_outside_root_and_duplicate_keys(tmp_path: Path) -> None:
    import entroping.core.mutation_materializer as materializer

    _write_status_fixture(tmp_path)
    outside = tmp_path.parent / "outside-manifest.json"
    with pytest.raises(MutationMaterializerError, match="project-relative"):
        materializer.materialize_mutation_candidate(tmp_path, outside)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version": "one", "schema_version": "two"}', encoding="utf-8")
    with pytest.raises(MutationMaterializerError, match="duplicate keys"):
        materializer.materialize_mutation_candidate(tmp_path, duplicate)


def test_materializer_rejects_destination_identity_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import entroping.core.mutation_materializer as materializer

    _source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    real_open_relative = materializer_io.open_relative_directory
    destination_calls = 0

    def changed_destination(
        root_fd: int, parts: tuple[str, ...]
    ) -> tuple[int, tuple[tuple[int, int], ...]]:
        nonlocal destination_calls
        result = real_open_relative(root_fd, parts)
        if parts == ("tests", "generated", "mutations"):
            destination_calls += 1
            if destination_calls == 2:
                return result[0], ((-1, -1),)
        return result

    monkeypatch.setattr(materializer_io, "open_relative_directory", changed_destination)
    with pytest.raises(MutationMaterializerError, match="destination changed"):
        materializer.materialize_mutation_candidate(tmp_path, manifest_path)


def test_materializer_wraps_bounded_source_read_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_read = materializer_io.read_bounded_fd
    reads = 0

    def fail_source_read(descriptor: int, limit: int) -> bytes:
        nonlocal reads
        reads += 1
        if reads == 2:
            raise MutationMaterializerError("bounded input is oversized")
        return real_read(descriptor, limit)

    monkeypatch.setattr(materializer_io, "read_bounded_fd", fail_source_read)
    with pytest.raises(MutationMaterializerError, match="source size is invalid") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "source size is invalid"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_rejects_source_inode_change_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    replaced = False

    real_stat = os.stat

    def replace_before_recheck(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal replaced
        if path == "source.hurl" and dir_fd is not None and not replaced:
            replaced = True
            source.unlink()
            source.write_bytes(source_before)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", replace_before_recheck)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, replace_before_recheck})
    monkeypatch.setattr(
        os,
        "supports_follow_symlinks",
        {*os.supports_follow_symlinks, replace_before_recheck},
    )
    with pytest.raises(MutationMaterializerError, match="source changed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "source changed before publication"
    assert source.read_bytes() == source_before
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_reports_output_close_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_close = os.close
    output_descriptor: int | None = None

    def fail_write(descriptor: int, _raw: bytes) -> int:
        nonlocal output_descriptor
        output_descriptor = descriptor
        return 0

    def fail_output_close(descriptor: int) -> None:
        if descriptor == output_descriptor:
            raise OSError("injected close failure")
        real_close(descriptor)

    monkeypatch.setattr(os, "write", fail_write)
    monkeypatch.setattr(os, "close", fail_output_close)
    try:
        with pytest.raises(MutationMaterializerError, match="cleanup failed") as caught:
            materialize_mutation_candidate(tmp_path, manifest_path)
    finally:
        monkeypatch.undo()
        if output_descriptor is not None:
            with suppress(OSError):
                real_close(output_descriptor)

    assert str(caught.value) == "candidate output cleanup failed"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


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


def test_materializer_ignores_replaced_temp_before_linux_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    attacker_target = destination / "attacker-controlled.hurl"
    attacker_target.write_text("attacker controlled", encoding="utf-8")
    real_unlink = os.unlink
    real_symlink = os.symlink
    real_link = os.link

    def replace_temp_then_link(
        source: str,
        name: str,
        *,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        real_unlink(f".{name}.materializing", dir_fd=dst_dir_fd)
        real_symlink(attacker_target.name, f".{name}.materializing", dir_fd=dst_dir_fd)
        real_link(
            source,
            name,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    _install_linux_link(monkeypatch, replace_temp_then_link)
    output = destination / f"{candidate_id}.hurl"
    materialize_mutation_candidate(tmp_path, manifest_path)
    assert output.exists()
    assert not output.is_symlink()
    assert "HTTP 500" in output.read_text(encoding="utf-8")
    assert not output.with_name(f".{output.name}.materializing").exists()


def test_materializer_rejects_filesystem_publication_refusal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def refuse_link(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOTSUP, "injected refusal")

    _install_linux_link(monkeypatch, refuse_link)
    with pytest.raises(MutationMaterializerError, match="publication unsupported") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output publication unsupported"
    assert not output.exists()
    assert not temporary.exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_generic_publication_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.EIO, "injected publication error")

    _install_linux_link(monkeypatch, fail_link)

    with pytest.raises(MutationMaterializerError, match="could not be published") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output could not be published"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()
    assert not output.with_name(f".{output.name}.materializing").exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_noop_publication_without_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def noop_backend(*_args: object) -> int:
        return 0

    _install_linux_link(monkeypatch, noop_backend)
    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    assert not output.exists()
    assert not temporary.exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_forged_final_without_trusting_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    attacker_target = destination / "attacker-controlled.hurl"
    attacker_target.write_bytes(b"attacker-controlled")
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def forge_final(
        _descriptor: int,
        destination_fd: int,
        name: bytes,
        _temporary_name: str,
    ) -> int:
        os.symlink(attacker_target.name, os.fsdecode(name), dir_fd=destination_fd)
        return 0

    _install_linux_link(monkeypatch, forge_final)
    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    assert output.is_symlink()
    assert output.resolve() == attacker_target
    assert not temporary.exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_forged_empty_final(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def forge_empty_final(
        _descriptor: int,
        destination_fd: int,
        name: bytes,
        _temporary_name: str,
    ) -> int:
        final_fd = os.open(
            os.fsdecode(name),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=destination_fd,
        )
        os.close(final_fd)
        return 0

    _install_linux_link(monkeypatch, forge_empty_final)
    with pytest.raises(MutationMaterializerError, match="verification failed"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert output.exists()
    assert output.stat().st_size == 0
    assert not temporary.exists()


def test_materializer_rejects_same_size_forged_final(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def forge_same_size_final(
        descriptor: int,
        destination_fd: int,
        name: bytes,
        _temporary_name: str,
    ) -> int:
        expected = os.pread(descriptor, os.fstat(descriptor).st_size, 0)
        replacement = bytes((expected[0] ^ 1,)) + expected[1:]
        final_fd = os.open(
            os.fsdecode(name),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=destination_fd,
        )
        try:
            os.write(final_fd, replacement)
        finally:
            os.close(final_fd)
        return 0

    _install_linux_link(monkeypatch, forge_same_size_final)
    with pytest.raises(MutationMaterializerError, match="verification failed"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert output.exists()
    assert output.read_bytes() != source.read_bytes()
    assert not temporary.exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="requires the Linux descriptor-link publication path",
)
def test_linux_public_materializer_rejects_distinct_inode_link(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"
    copied: list[bytes] = []

    def copy_as_distinct_inode(
        source: str,
        name: str,
        *,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        assert source.startswith("/proc/self/fd/")
        assert follow_symlinks
        content = Path(source).read_bytes()
        copied.append(content)
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=dst_dir_fd,
        )
        try:
            os.write(descriptor, content)
        finally:
            os.close(descriptor)

    monkeypatch.setattr(os, "link", copy_as_distinct_inode)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, copy_as_distinct_inode})
    monkeypatch.setattr(
        os,
        "supports_follow_symlinks",
        {*os.supports_follow_symlinks, copy_as_distinct_inode},
    )

    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    assert copied
    assert output.exists()
    assert output.read_bytes() == copied[0]
    assert not temporary.exists()


def test_materializer_wraps_verification_read_oserror(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_bounded_read = materializer_io.read_bounded_fd
    reads = 0

    def fail_final_read(descriptor: int, size: int) -> bytes:
        nonlocal reads
        reads += 1
        if reads == 4:
            raise OSError("injected verification read failure")
        return real_bounded_read(descriptor, size)

    monkeypatch.setattr(materializer_io, "read_bounded_fd", fail_final_read)
    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert output.exists()
    assert not output.with_name(f".{output.name}.materializing").exists()


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


def test_status_ordinal_rejects_ambiguous_body_status_without_output(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b"# entroping: safety=read-only\n\nPOST {{base_url}}/health\n"
        b"<request\nHTTP 201\n</request>\nHTTP 200\n"
    )
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    candidate_id = _candidate_id(identity)
    document["candidate_id"] = candidate_id
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="assertion is missing") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "status assertion is missing"
    assert source.read_bytes() == source_bytes
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()
