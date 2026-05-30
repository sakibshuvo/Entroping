"""Adapter tests for local Entroping environment files."""

from pathlib import Path

import pytest

from entroping.core.env_loader import EnvironmentLoadError, load_environment_variables


def test_load_environment_variables_reads_file_and_process_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "envs" / "local.env"
    env_file.parent.mkdir()
    env_file.write_text(
        """
# local checkout defaults
base_url=http://localhost:8080
cart_id=demo-cart-001
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("base_url", "http://localhost:18080")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-load")

    variables = load_environment_variables("local", root=tmp_path)

    assert variables == {
        "base_url": "http://localhost:18080",
        "cart_id": "demo-cart-001",
    }


def test_load_environment_variables_rejects_missing_env_file(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentLoadError, match="Environment file not found"):
        load_environment_variables("local", root=tmp_path)


def test_load_environment_variables_rejects_invalid_env_names(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentLoadError, match="Environment name"):
        load_environment_variables("../prod", root=tmp_path)


def test_load_environment_variables_rejects_invalid_lines(tmp_path: Path) -> None:
    env_file = tmp_path / "envs" / "local.env"
    env_file.parent.mkdir()
    env_file.write_text("base_url http://localhost:8080\n", encoding="utf-8")

    with pytest.raises(EnvironmentLoadError, match="expected KEY=value"):
        load_environment_variables("local", root=tmp_path)


def test_load_environment_variables_rejects_invalid_variable_names(tmp_path: Path) -> None:
    env_file = tmp_path / "envs" / "local.env"
    env_file.parent.mkdir()
    env_file.write_text("bad-name=value\n", encoding="utf-8")

    with pytest.raises(EnvironmentLoadError, match="Invalid environment variable name"):
        load_environment_variables("local", root=tmp_path)


def test_load_environment_variables_rejects_duplicate_variables(tmp_path: Path) -> None:
    env_file = tmp_path / "envs" / "local.env"
    env_file.parent.mkdir()
    env_file.write_text("base_url=http://one\nbase_url=http://two\n", encoding="utf-8")

    with pytest.raises(EnvironmentLoadError, match="duplicate environment variable"):
        load_environment_variables("local", root=tmp_path)


def test_load_environment_variables_rejects_non_utf8_files(tmp_path: Path) -> None:
    env_file = tmp_path / "envs" / "local.env"
    env_file.parent.mkdir()
    env_file.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(EnvironmentLoadError, match="Environment file is not valid UTF-8"):
        load_environment_variables("local", root=tmp_path)


def test_load_environment_variables_wraps_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "envs" / "local.env"
    env_file.parent.mkdir()
    env_file.write_text("base_url=http://localhost:8080\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == env_file.resolve():
            raise OSError("disk unavailable")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(EnvironmentLoadError, match="Could not read environment file"):
        load_environment_variables("local", root=tmp_path)


def test_load_environment_variables_rejects_symlinked_files(tmp_path: Path) -> None:
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    real_file = tmp_path / "real.env"
    real_file.write_text("base_url=http://localhost:8080\n", encoding="utf-8")
    (env_dir / "local.env").symlink_to(real_file)

    with pytest.raises(EnvironmentLoadError, match="symlinked environment path component"):
        load_environment_variables("local", root=tmp_path)


def test_load_environment_variables_rejects_symlinked_env_directory(tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside-envs"
    outside_dir.mkdir()
    (outside_dir / "local.env").write_text("base_url=http://localhost:8080\n", encoding="utf-8")
    (tmp_path / "envs").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(EnvironmentLoadError, match="symlinked environment path component"):
        load_environment_variables("local", root=tmp_path)
