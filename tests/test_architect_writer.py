"""Architect staged writer tests."""

from pathlib import Path

import pytest

import entroping.brain.architect_writer as architect_writer
from entroping.brain.architect_writer import (
    ArchitectWriteError,
    PreparedHurlWrite,
    write_architect_edits,
    write_refactor_hurl_edits,
)
from entroping.models import ArchitectEdit, ArchitectEditSet


def _edit_set(path: str, content: str) -> ArchitectEditSet:
    return ArchitectEditSet(
        summary="Add generated coverage",
        edits=[ArchitectEdit(path=path, content=content)],
    )


def test_write_architect_edits_writes_new_file_with_source_marker(tmp_path: Path) -> None:
    edit_set = _edit_set("tests/generated/refund.hurl", "GET {{base_url}}/refunds\nHTTP 200\n")

    written = write_architect_edits(edit_set, project_root=tmp_path)

    output_path = tmp_path / "tests" / "generated" / "refund.hurl"
    assert written == (output_path,)
    assert output_path.read_text(encoding="utf-8").startswith("# entroping: source=architect\n")


def test_write_architect_edits_preserves_existing_architect_marker(tmp_path: Path) -> None:
    content = "# entroping: source=architect\n\nGET {{base_url}}/refunds\nHTTP 200\n"
    write_architect_edits(_edit_set("tests/generated/refund.hurl", content), project_root=tmp_path)

    output = (tmp_path / "tests" / "generated" / "refund.hurl").read_text(encoding="utf-8")

    assert output.count("# entroping: source=architect") == 1


def test_write_architect_edits_prepends_marker_when_marker_appears_later(
    tmp_path: Path,
) -> None:
    content = "# note: # entroping: source=architect\n\nGET {{base_url}}/refunds\nHTTP 200\n"

    write_architect_edits(_edit_set("tests/generated/refund.hurl", content), project_root=tmp_path)

    output = (tmp_path / "tests" / "generated" / "refund.hurl").read_text(encoding="utf-8")
    assert output.startswith("# entroping: source=architect\n")
    assert output.count("# entroping: source=architect") == 2


def test_write_architect_edits_overwrites_existing_architect_owned_file(tmp_path: Path) -> None:
    output_path = tmp_path / "tests" / "generated" / "refund.hurl"
    output_path.parent.mkdir(parents=True)
    output_path.write_text(
        "# entroping: source=architect\n\nGET {{base_url}}/old\nHTTP 200\n",
        encoding="utf-8",
    )

    write_architect_edits(
        _edit_set("tests/generated/refund.hurl", "GET {{base_url}}/new\nHTTP 200\n"),
        project_root=tmp_path,
    )

    assert "GET {{base_url}}/new" in output_path.read_text(encoding="utf-8")


def test_write_architect_edits_refuses_existing_file_with_spoofed_marker(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "tests" / "manual.hurl"
    output_path.parent.mkdir(parents=True)
    output_path.write_text(
        "# human note mentioning # entroping: source=architect\n"
        "\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    with pytest.raises(ArchitectWriteError, match="Refusing to overwrite non-Architect Hurl file"):
        write_architect_edits(
            _edit_set("tests/manual.hurl", "GET {{base_url}}/new\nHTTP 200\n"),
            project_root=tmp_path,
        )

    assert "GET {{base_url}}/health" in output_path.read_text(encoding="utf-8")


def test_write_architect_edits_refuses_non_architect_owned_existing_file(tmp_path: Path) -> None:
    output_path = tmp_path / "tests" / "manual.hurl"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("# manual\n\nGET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(ArchitectWriteError, match="Refusing to overwrite non-Architect Hurl file"):
        write_architect_edits(
            _edit_set("tests/manual.hurl", "GET {{base_url}}/new\nHTTP 200\n"),
            project_root=tmp_path,
        )

    assert "GET {{base_url}}/health" in output_path.read_text(encoding="utf-8")


def test_write_architect_edits_checks_existing_header_without_full_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "tests" / "manual.hurl"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("# manual\n" + ("GET /health\nHTTP 200\n" * 10_000), encoding="utf-8")
    original_read_text = Path.read_text

    def reject_full_target_read(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == output_path:
            raise AssertionError("ownership guard must not read the full target")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", reject_full_target_read)

    with pytest.raises(ArchitectWriteError, match="Refusing to overwrite non-Architect Hurl file"):
        write_architect_edits(
            _edit_set("tests/manual.hurl", "GET {{base_url}}/new\nHTTP 200\n"),
            project_root=tmp_path,
        )


def test_write_architect_edits_accepts_owned_file_when_prefix_splits_utf8(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "tests" / "generated" / "refund.hurl"
    output_path.parent.mkdir(parents=True)
    content = "# entroping: source=architect\n"
    if (
        architect_writer._OWNERSHIP_HEADER_READ_LIMIT_BYTES
        - len(content.encode("utf-8"))
    ) % 2 == 0:
        content += "x"
    output_path.write_text(
        content
        + ("é" * architect_writer._OWNERSHIP_HEADER_READ_LIMIT_BYTES)
        + "\nGET /old\nHTTP 200\n",
        encoding="utf-8",
    )

    write_architect_edits(
        _edit_set("tests/generated/refund.hurl", "GET /new\nHTTP 200\n"),
        project_root=tmp_path,
    )

    assert "GET /new" in output_path.read_text(encoding="utf-8")


def test_write_architect_edits_refuses_symlink_targets(tmp_path: Path) -> None:
    victim_path = tmp_path / "victim.hurl"
    victim_path.write_text("do not overwrite\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "generated.hurl").symlink_to(victim_path)

    with pytest.raises(ArchitectWriteError, match="Refusing to write symlinked Hurl file"):
        write_architect_edits(
            _edit_set("tests/generated.hurl", "GET {{base_url}}/new\nHTTP 200\n"),
            project_root=tmp_path,
        )

    assert victim_path.read_text(encoding="utf-8") == "do not overwrite\n"


def test_write_architect_edits_refuses_symlink_parent(tmp_path: Path) -> None:
    real_tests_dir = tmp_path / "real-tests"
    real_tests_dir.mkdir()
    (tmp_path / "tests").symlink_to(real_tests_dir)

    with pytest.raises(ArchitectWriteError, match="Refusing to write symlinked Hurl file"):
        write_architect_edits(
            _edit_set("tests/generated.hurl", "GET {{base_url}}/new\nHTTP 200\n"),
            project_root=tmp_path,
        )

    assert not (real_tests_dir / "generated.hurl").exists()


def test_write_architect_edits_does_not_follow_predictable_temp_symlink(tmp_path: Path) -> None:
    victim_path = tmp_path / "victim.hurl"
    victim_path.write_text("do not overwrite\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / ".generated.hurl.tmp").symlink_to(victim_path)

    write_architect_edits(
        _edit_set("tests/generated.hurl", "GET {{base_url}}/new\nHTTP 200\n"),
        project_root=tmp_path,
    )

    assert victim_path.read_text(encoding="utf-8") == "do not overwrite\n"
    assert (tests_dir / "generated.hurl").is_file()


def test_write_architect_edits_preflights_all_edits_before_writing(tmp_path: Path) -> None:
    manual_path = tmp_path / "tests" / "manual.hurl"
    manual_path.parent.mkdir(parents=True)
    manual_path.write_text("# manual\n\nGET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")
    edit_set = ArchitectEditSet(
        summary="Generate mixed edits",
        edits=[
            ArchitectEdit(path="tests/generated/new.hurl", content="GET /new\nHTTP 200\n"),
            ArchitectEdit(path="tests/manual.hurl", content="GET /overwrite\nHTTP 200\n"),
        ],
    )

    with pytest.raises(ArchitectWriteError, match="Refusing to overwrite non-Architect Hurl file"):
        write_architect_edits(edit_set, project_root=tmp_path)

    assert not (tmp_path / "tests" / "generated" / "new.hurl").exists()
    assert "GET {{base_url}}/health" in manual_path.read_text(encoding="utf-8")


def test_write_architect_edits_rejects_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "tests" / "generated.hurl"
    output.parent.mkdir()
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside.hurl"
    outside.write_text("outside\n", encoding="utf-8")
    output.symlink_to(outside)

    def allow_symlink_path(candidate: Path, *, root: Path) -> None:
        _ = candidate, root

    monkeypatch.setattr(architect_writer, "_reject_symlink_path", allow_symlink_path)

    with pytest.raises(ArchitectWriteError, match="must stay under project root"):
        write_architect_edits(
            _edit_set("tests/generated.hurl", "GET /new\nHTTP 200\n"),
            project_root=tmp_path,
        )


def test_write_architect_edits_refuses_non_file_existing_target(tmp_path: Path) -> None:
    output = tmp_path / "tests" / "generated.hurl"
    output.mkdir(parents=True)

    with pytest.raises(ArchitectWriteError, match="non-file Hurl target"):
        write_architect_edits(
            _edit_set("tests/generated.hurl", "GET /new\nHTTP 200\n"),
            project_root=tmp_path,
        )


def test_write_refactor_hurl_edits_preserves_manual_ownership(tmp_path: Path) -> None:
    manual_path = tmp_path / "tests" / "manual.hurl"
    manual_path.parent.mkdir(parents=True)
    manual_path.write_text("# manual\nGET /old\nHTTP 200\n", encoding="utf-8")

    written = write_refactor_hurl_edits(
        [
            PreparedHurlWrite(
                path="tests/manual.hurl",
                content="# manual\nGET /new\nHTTP 200\n",
                require_architect_header=False,
            )
        ],
        project_root=tmp_path,
    )

    assert written == (manual_path,)
    assert manual_path.read_text(encoding="utf-8") == "# manual\nGET /new\nHTTP 200\n"
    assert "# entroping: source=architect" not in manual_path.read_text(encoding="utf-8")


def test_write_refactor_hurl_edits_refuses_missing_targets(tmp_path: Path) -> None:
    with pytest.raises(ArchitectWriteError, match="Refusing to create missing refactor target"):
        write_refactor_hurl_edits(
            [
                PreparedHurlWrite(
                    path="tests/missing.hurl",
                    content="GET /new\nHTTP 200\n",
                    require_architect_header=False,
                )
            ],
            project_root=tmp_path,
        )


def test_write_refactor_hurl_edits_rejects_control_characters_in_paths(
    tmp_path: Path,
) -> None:
    with pytest.raises(ArchitectWriteError, match="must not contain control characters"):
        write_refactor_hurl_edits(
            [
                PreparedHurlWrite(
                    path="tests/bad\u0000path.hurl",
                    content="GET /new\nHTTP 200\n",
                    require_architect_header=False,
                )
            ],
            project_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("", "must not be empty"),
        ("tests\\bad.hurl", "POSIX separators"),
        ("../bad.hurl", "project root"),
        ("/tmp/bad.hurl", "project root"),
        ("docs/bad.hurl", "tests/ .hurl"),
        ("tests/bad.txt", "tests/ .hurl"),
    ],
)
def test_write_refactor_hurl_edits_rejects_unsafe_paths(
    tmp_path: Path,
    path: str,
    message: str,
) -> None:
    with pytest.raises(ArchitectWriteError, match=message):
        write_refactor_hurl_edits(
            [
                PreparedHurlWrite(
                    path=path,
                    content="GET /new\nHTTP 200\n",
                    require_architect_header=False,
                )
            ],
            project_root=tmp_path,
        )


def test_write_refactor_hurl_edits_rejects_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "tests" / "generated.hurl"
    output.parent.mkdir()
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside.hurl"
    outside.write_text("outside\n", encoding="utf-8")
    output.symlink_to(outside)

    def allow_symlink_path(candidate: Path, *, root: Path) -> None:
        _ = candidate, root

    monkeypatch.setattr(architect_writer, "_reject_symlink_path", allow_symlink_path)

    with pytest.raises(ArchitectWriteError, match="must stay under project root"):
        write_refactor_hurl_edits(
            [
                PreparedHurlWrite(
                    path="tests/generated.hurl",
                    content="GET /new\nHTTP 200\n",
                    require_architect_header=False,
                )
            ],
            project_root=tmp_path,
        )


def test_write_refactor_hurl_edits_refuses_symlink_and_non_file_targets(tmp_path: Path) -> None:
    victim = tmp_path / "victim.hurl"
    victim.write_text("victim\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    symlink = tests_dir / "linked.hurl"
    symlink.symlink_to(victim)

    with pytest.raises(ArchitectWriteError, match="symlinked Hurl file"):
        architect_writer._validate_existing_refactor_target(
            symlink,
            require_architect_header=False,
        )

    with pytest.raises(ArchitectWriteError, match="symlinked Hurl file"):
        architect_writer._validate_existing_target(symlink)

    directory = tests_dir / "directory.hurl"
    directory.mkdir()
    with pytest.raises(ArchitectWriteError, match="non-file Hurl target"):
        architect_writer._validate_existing_refactor_target(
            directory,
            require_architect_header=False,
        )


def test_architect_writer_helpers_cover_blank_headers_and_newline_preservation() -> None:
    assert not architect_writer._has_architect_header("")
    assert architect_writer._has_architect_header("\n# entroping: source=architect\n")
    assert not architect_writer._has_architect_header("\n# manual\n")
    assert architect_writer._ensure_trailing_newline("GET /health\n") == "GET /health\n"
    assert architect_writer._ensure_trailing_newline("GET /health") == "GET /health\n"


def test_write_text_atomically_wraps_replace_and_temporary_write_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "tests" / "generated.hurl"
    output.parent.mkdir()
    output.write_text("# entroping: source=architect\nGET /old\nHTTP 200\n", encoding="utf-8")
    original_replace = Path.replace

    def fail_replace(self: Path, target: Path) -> Path:
        if target == output:
            raise OSError("replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(ArchitectWriteError, match="replace failed"):
        architect_writer._write_text_atomically(output, "GET /new\nHTTP 200\n")
    assert output.read_text(encoding="utf-8").startswith("# entroping: source=architect")
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []

    monkeypatch.setattr(Path, "replace", original_replace)

    def fail_named_temporary_file(*args: object, **kwargs: object) -> object:
        _ = args, kwargs
        raise OSError("temp failed")

    monkeypatch.setattr(
        "entroping.brain.architect_writer.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )
    with pytest.raises(ArchitectWriteError, match="temp failed"):
        architect_writer._write_text_atomically(output, "GET /new\nHTTP 200\n")


def test_write_refactor_hurl_edits_preflights_before_writing(tmp_path: Path) -> None:
    architect_path = tmp_path / "tests" / "generated.hurl"
    manual_path = tmp_path / "tests" / "manual.hurl"
    architect_path.parent.mkdir(parents=True)
    architect_path.write_text(
        "# entroping: source=architect\nGET /old\nHTTP 200\n",
        encoding="utf-8",
    )
    manual_path.write_text("# manual\nGET /old\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(ArchitectWriteError, match="Refusing to overwrite non-Architect Hurl file"):
        write_refactor_hurl_edits(
            [
                PreparedHurlWrite(
                    path="tests/generated.hurl",
                    content="GET /new\nHTTP 200\n",
                    require_architect_header=True,
                ),
                PreparedHurlWrite(
                    path="tests/manual.hurl",
                    content="GET /bad\nHTTP 200\n",
                    require_architect_header=True,
                ),
            ],
            project_root=tmp_path,
        )

    assert "GET /old" in architect_path.read_text(encoding="utf-8")
    assert "GET /old" in manual_path.read_text(encoding="utf-8")


def test_write_refactor_hurl_edits_checks_existing_header_without_full_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manual_path = tmp_path / "tests" / "manual.hurl"
    manual_path.parent.mkdir(parents=True)
    manual_path.write_text("# manual\n" + ("GET /old\nHTTP 200\n" * 10_000), encoding="utf-8")
    original_read_text = Path.read_text

    def reject_full_target_read(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == manual_path:
            raise AssertionError("ownership guard must not read the full target")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", reject_full_target_read)

    with pytest.raises(ArchitectWriteError, match="Refusing to overwrite non-Architect Hurl file"):
        write_refactor_hurl_edits(
            [
                PreparedHurlWrite(
                    path="tests/manual.hurl",
                    content="GET /new\nHTTP 200\n",
                    require_architect_header=True,
                ),
            ],
            project_root=tmp_path,
        )
