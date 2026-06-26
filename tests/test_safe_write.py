"""Tests for durable local artifact writes."""

from pathlib import Path

import pytest

from entroping.core import safe_write
from entroping.core.safe_write import (
    SafeWriteError,
    safe_append_text,
    safe_report_output_path,
    safe_write_bytes,
    safe_write_text,
)


def test_safe_write_text_writes_utf8_file_atomically(tmp_path: Path) -> None:
    output = tmp_path / "reports" / "run-latest.json"

    written = safe_write_text(output, '{"ok": true}\n', artifact="run report", root=tmp_path)

    assert written == output.resolve()
    assert output.read_text(encoding="utf-8") == '{"ok": true}\n'


def test_safe_write_bytes_writes_binary_file_atomically(tmp_path: Path) -> None:
    output = tmp_path / "reports" / "dependency-map.png"

    written = safe_write_bytes(output, b"\x89PNG\r\n", artifact="dependency map", root=tmp_path)

    assert written == output.resolve()
    assert output.read_bytes() == b"\x89PNG\r\n"


def test_safe_append_text_appends_utf8_without_replacing_file(tmp_path: Path) -> None:
    output = tmp_path / ".entroping" / "latest-run-events.jsonl"
    safe_write_text(output, '{"event":"first"}\n', artifact="run event log", root=tmp_path)

    written = safe_append_text(
        output,
        '{"event":"second"}\n',
        artifact="run event log",
        root=tmp_path,
    )

    assert written == output.resolve()
    assert output.read_text(encoding="utf-8") == (
        '{"event":"first"}\n{"event":"second"}\n'
    )


def test_safe_append_text_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".entroping").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SafeWriteError, match="symlinked path component"):
        safe_append_text(
            tmp_path / ".entroping" / "latest-run-events.jsonl",
            "{}\n",
            artifact="run event log",
            root=tmp_path,
        )

    assert not (outside / "latest-run-events.jsonl").exists()


def test_safe_append_text_rechecks_symlink_target_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / ".entroping" / "latest-run-events.jsonl"
    output.parent.mkdir()
    output.write_text("old\n", encoding="utf-8")
    victim = tmp_path / "victim.txt"
    victim.write_text("victim\n", encoding="utf-8")

    def swap_after_prepare(
        path: Path,
        *,
        artifact: str,
        root: Path | None,
    ) -> Path:
        _ = path, artifact, root
        output.unlink()
        output.symlink_to(victim)
        return output

    monkeypatch.setattr(safe_write, "_prepare_destination", swap_after_prepare)

    with pytest.raises(SafeWriteError, match="symlinked run event log"):
        safe_append_text(output, "new\n", artifact="run event log", root=tmp_path)

    assert victim.read_text(encoding="utf-8") == "victim\n"


def test_safe_append_text_wraps_append_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / ".entroping" / "latest-run-events.jsonl"
    safe_write_text(output, "old\n", artifact="run event log", root=tmp_path)
    original_open = Path.open

    def fail_open(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> object:
        if self == output.resolve() and mode == "ab":
            raise OSError("append failed")
        return original_open(
            self,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(SafeWriteError, match="append failed"):
        safe_append_text(output, "new\n", artifact="run event log", root=tmp_path)

    assert output.read_text(encoding="utf-8") == "old\n"


def test_safe_write_resolves_relative_path_against_root(tmp_path: Path) -> None:
    written = safe_write_text(
        Path("reports/run-latest.json"),
        "{}\n",
        artifact="run report",
        root=tmp_path,
    )

    assert written == (tmp_path / "reports" / "run-latest.json").resolve()
    assert written.read_text(encoding="utf-8") == "{}\n"


def test_safe_write_can_write_relative_path_without_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    written = safe_write_text(Path("reports/run-latest.json"), "{}\n", artifact="run report")

    assert written == (tmp_path / "reports" / "run-latest.json").resolve()
    assert written.read_text(encoding="utf-8") == "{}\n"


def test_safe_write_without_root_rejects_existing_symlink_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "victim.md"
    victim.write_text("victim\n", encoding="utf-8")
    output = tmp_path / "reports" / "bug.md"
    output.parent.mkdir()
    output.symlink_to(victim)

    with pytest.raises(SafeWriteError, match="symlinked bug report"):
        safe_write_text(Path("reports") / "bug.md", "replacement\n", artifact="bug report")

    assert victim.read_text(encoding="utf-8") == "victim\n"


def test_safe_write_without_root_rejects_symlinked_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "reports").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SafeWriteError, match="symlinked path component"):
        safe_write_text(Path("reports") / "run-latest.json", "{}\n", artifact="run report")

    assert not (outside / "run-latest.json").exists()


def test_safe_write_rejects_existing_symlink_target(tmp_path: Path) -> None:
    victim = tmp_path / "victim.md"
    victim.write_text("victim\n", encoding="utf-8")
    output = tmp_path / "reports" / "bug.md"
    output.parent.mkdir()
    output.symlink_to(victim)

    with pytest.raises(SafeWriteError, match="symlinked bug report"):
        safe_write_text(output, "replacement\n", artifact="bug report", root=tmp_path)

    assert victim.read_text(encoding="utf-8") == "victim\n"


def test_safe_write_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "reports").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SafeWriteError, match="symlinked path component"):
        safe_write_text(
            tmp_path / "reports" / "run-latest.json",
            "{}\n",
            artifact="run report",
            root=tmp_path,
        )

    assert not (outside / "run-latest.json").exists()


def test_safe_write_rejects_non_file_target(tmp_path: Path) -> None:
    output = tmp_path / "reports" / "run-latest.json"
    output.mkdir(parents=True)

    with pytest.raises(SafeWriteError, match="non-file run report"):
        safe_write_text(output, "{}\n", artifact="run report", root=tmp_path)


def test_safe_write_rejects_root_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"

    with pytest.raises(SafeWriteError, match="must stay under"):
        safe_write_text(outside, "escape\n", artifact="bug report", root=tmp_path)

    assert not outside.exists()


def test_safe_report_output_path_can_limit_forbidden_components_to_first_part(
    tmp_path: Path,
) -> None:
    output = safe_report_output_path(
        Path("reports") / "envs" / "packet.json",
        root=tmp_path,
        artifact="report packet",
        forbid_components_anywhere=False,
    )

    assert output == tmp_path.resolve() / "reports" / "envs" / "packet.json"


def test_safe_report_output_path_supports_custom_forbidden_components(
    tmp_path: Path,
) -> None:
    with pytest.raises(SafeWriteError, match="must not be written into private"):
        safe_report_output_path(
            Path("reports") / "private" / "packet.json",
            root=tmp_path,
            artifact="report packet",
            forbidden_components=("private",),
        )


def test_safe_report_output_path_formats_external_symlink_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_component = tmp_path.parent / f"{tmp_path.name}-external-link"

    def find_external_component(path: Path, *, root: Path | None) -> Path:
        _ = path, root
        return external_component

    monkeypatch.setattr(
        safe_write,
        "first_symlink_path_component",
        find_external_component,
    )

    with pytest.raises(SafeWriteError) as exc_info:
        safe_report_output_path(
            Path("reports") / "packet.json",
            root=tmp_path,
            artifact="report packet",
        )

    assert external_component.as_posix() in str(exc_info.value)


def test_safe_write_wraps_parent_directory_creation_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "reports" / "run-latest.json"
    original_mkdir = Path.mkdir

    def fail_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if self == output.parent:
            raise OSError("mkdir failed")
        original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(SafeWriteError, match="mkdir failed"):
        safe_write_text(output, "{}\n", artifact="run report", root=tmp_path)

    assert not output.exists()


def test_safe_write_wraps_temporary_file_creation_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "reports" / "run-latest.json"

    def fail_named_temporary_file(*args: object, **kwargs: object) -> object:
        _ = args, kwargs
        raise OSError("temp failed")

    monkeypatch.setattr(
        "entroping.core.safe_write.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )

    with pytest.raises(SafeWriteError, match="temp failed"):
        safe_write_text(output, "{}\n", artifact="run report", root=tmp_path)

    assert not output.exists()


def test_failed_temporary_file_write_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "reports" / "run-latest.json"
    output.parent.mkdir()
    temporary_file = output.parent / ".run-latest.json.tmp"
    temporary_file.write_bytes(b"partial")

    class FailingTemporaryFile:
        name = str(temporary_file)

        def __enter__(self) -> "FailingTemporaryFile":
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def write(self, content: bytes) -> int:
            _ = content
            raise OSError("write failed")

    def fail_named_temporary_file(*args: object, **kwargs: object) -> FailingTemporaryFile:
        _ = args, kwargs
        return FailingTemporaryFile()

    monkeypatch.setattr(
        "entroping.core.safe_write.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )

    with pytest.raises(SafeWriteError, match="write failed"):
        safe_write_text(output, "{}\n", artifact="run report", root=tmp_path)

    assert not temporary_file.exists()
    assert not output.exists()


def test_safe_write_wraps_replace_failures_and_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "reports" / "run-latest.json"
    output.parent.mkdir()
    output.write_text("old\n", encoding="utf-8")
    original_replace = Path.replace

    def fail_replace(self: Path, target: Path) -> Path:
        if target == output.resolve():
            raise OSError("replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(SafeWriteError, match="replace failed"):
        safe_write_text(output, "new\n", artifact="run report", root=tmp_path)

    assert output.read_text(encoding="utf-8") == "old\n"
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []


def test_failed_temporary_write_does_not_replace_existing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "reports" / "run-latest.json"
    output.parent.mkdir()
    output.write_text("old\n", encoding="utf-8")

    def fail_temporary_write(path: Path, content: bytes) -> Path:
        _ = path, content
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(safe_write, "_write_temporary_file", fail_temporary_write)

    with pytest.raises(SafeWriteError, match="temporary write failed"):
        safe_write_text(output, "new\n", artifact="run report", root=tmp_path)

    assert output.read_text(encoding="utf-8") == "old\n"
