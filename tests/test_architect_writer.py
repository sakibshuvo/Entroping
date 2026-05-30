"""Architect staged writer tests."""

from pathlib import Path

import pytest

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
