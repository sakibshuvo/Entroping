"""Shared path-safety helper tests."""

from pathlib import Path

import pytest

from entroping.core.path_safety import display_path, first_symlink_path_component


def test_first_symlink_path_component_returns_none_for_plain_path(tmp_path: Path) -> None:
    target = tmp_path / "reports" / "run.json"
    target.parent.mkdir()
    target.write_text("{}\n", encoding="utf-8")

    assert first_symlink_path_component(target, root=tmp_path) is None


def test_first_symlink_path_component_reports_rooted_parent_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "reports"
    link.symlink_to(outside, target_is_directory=True)

    assert first_symlink_path_component(link / "run.json", root=tmp_path) == link


def test_first_symlink_path_component_reports_relative_target_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    real_file = tmp_path / "real.env"
    real_file.write_text("BASE_URL=http://localhost\n", encoding="utf-8")
    link = Path("envs") / "local.env"
    link.parent.mkdir()
    link.symlink_to(real_file)

    assert first_symlink_path_component(link) == link


def test_first_symlink_path_component_reports_absolute_target_symlink(
    tmp_path: Path,
) -> None:
    real_file = tmp_path / "real.env"
    real_file.write_text("BASE_URL=http://localhost\n", encoding="utf-8")
    link = tmp_path / "local.env"
    link.symlink_to(real_file)

    assert first_symlink_path_component(link) == link


def test_display_path_returns_project_relative_posix_path(tmp_path: Path) -> None:
    report_path = tmp_path / "reports" / "run-latest.json"

    assert display_path(report_path, root=tmp_path) == "reports/run-latest.json"


def test_display_path_returns_absolute_posix_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"

    assert display_path(outside, root=tmp_path) == outside.resolve(strict=False).as_posix()


def test_display_path_handles_unresolved_relative_path(tmp_path: Path) -> None:
    report_path = tmp_path / "reports" / "missing.json"

    assert display_path(report_path, root=tmp_path) == "reports/missing.json"
