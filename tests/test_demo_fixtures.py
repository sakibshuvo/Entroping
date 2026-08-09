from pathlib import Path

import pytest

from entroping.core import demo_fixtures
from entroping.core.demo_fixtures import (
    DemoFixtureError,
    copy_demo_fixture,
    list_demo_fixtures,
    resolve_demo_fixture_source,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_demo_fixture_manifest_lists_curated_value_free_files() -> None:
    fixtures = {fixture.fixture_id: fixture for fixture in list_demo_fixtures()}

    assert sorted(fixtures) == ["ai-regression-demo", "checkout-api", "support-api"]
    for fixture in fixtures.values():
        assert fixture.relative_path == Path(fixture.fixture_id)
        assert fixture.files
        for relative_file in fixture.files:
            parts = relative_file.parts
            assert not relative_file.is_absolute()
            assert ".." not in parts
            assert ".entroping" not in parts
            assert "__pycache__" not in parts
            assert "reports" not in parts
            assert "envs" not in parts
            assert ".env" not in relative_file.suffixes


def test_copy_demo_fixture_from_source_checkout_writes_only_manifest_paths(
    tmp_path: Path,
) -> None:
    result = copy_demo_fixture(
        "checkout-api",
        tmp_path / "fixture",
        source_examples_root=REPO_ROOT / "examples",
    )

    copied = sorted(path.relative_to(result.root).as_posix() for path in result.files)
    assert copied == [
        "README.md",
        "demo_server.py",
        "openapi.yaml",
        "qanstitution.yaml",
        "tests/checkout_smoke.hurl",
    ]
    assert (result.root / "openapi.yaml").read_text(encoding="utf-8") == (
        REPO_ROOT / "examples" / "checkout-api" / "openapi.yaml"
    ).read_text(encoding="utf-8")
    assert not (result.root / "envs").exists()
    assert not (result.root / "reports").exists()
    copied_readme = (result.root / "README.md").read_text(encoding="utf-8")
    assert "cp envs/local.env.example envs/local.env" not in copied_readme
    assert "creates `envs/local.env`" in copied_readme


def test_demo_fixture_source_defaults_to_source_checkout() -> None:
    source = resolve_demo_fixture_source("support-api")

    assert source.kind == "source-checkout"
    assert source.root == REPO_ROOT / "examples" / "support-api"


def test_demo_fixture_source_can_resolve_package_resource_root(tmp_path: Path) -> None:
    package_root = tmp_path / "demo-fixtures"
    source_fixture = package_root / "checkout-api"
    source_fixture.mkdir(parents=True)
    (source_fixture / "README.md").write_text("# packaged checkout\n", encoding="utf-8")
    (source_fixture / "demo_server.py").write_text("print('demo')\n", encoding="utf-8")
    (source_fixture / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")
    (source_fixture / "qanstitution.yaml").write_text("version: 1\n", encoding="utf-8")
    (source_fixture / "tests").mkdir()
    (source_fixture / "tests" / "checkout_smoke.hurl").write_text(
        "GET http://x\n",
        encoding="utf-8",
    )

    source = resolve_demo_fixture_source("checkout-api", package_root=package_root)
    result = copy_demo_fixture("checkout-api", tmp_path / "copied", package_root=package_root)

    assert source.kind == "package-resource"
    assert sorted(path.relative_to(result.root).as_posix() for path in result.files) == [
        "README.md",
        "demo_server.py",
        "openapi.yaml",
        "qanstitution.yaml",
        "tests/checkout_smoke.hurl",
    ]


def test_copy_demo_fixture_rejects_unknown_fixture(tmp_path: Path) -> None:
    with pytest.raises(DemoFixtureError, match="Unknown demo fixture"):
        copy_demo_fixture("missing", tmp_path, source_examples_root=REPO_ROOT / "examples")


def test_demo_fixture_source_rejects_unavailable_known_fixture(tmp_path: Path) -> None:
    with pytest.raises(DemoFixtureError, match="is not available"):
        resolve_demo_fixture_source(
            "checkout-api",
            source_examples_root=tmp_path / "examples",
            package_root=tmp_path / "package",
        )


def test_demo_fixture_manifest_rejects_unsafe_relative_paths() -> None:
    with pytest.raises(DemoFixtureError, match="must be relative"):
        demo_fixtures._validate_manifest_file(Path("../README.md"))

    with pytest.raises(DemoFixtureError, match="not package-safe"):
        demo_fixtures._validate_manifest_file(Path("reports/run.json"))


def test_demo_fixture_source_rejects_escaped_missing_and_symlinked_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fixture"
    root.mkdir()

    with pytest.raises(DemoFixtureError, match="escapes fixture root"):
        demo_fixtures._validate_source_file(tmp_path / "outside.txt", source_root=root)

    with pytest.raises(DemoFixtureError, match="is missing"):
        demo_fixtures._validate_source_file(root / "missing.txt", source_root=root)

    target = root / "target.txt"
    target.write_text("target\n", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(target)
    with pytest.raises(DemoFixtureError, match="symlinked"):
        demo_fixtures._validate_source_file(link, source_root=root)


def test_copy_demo_fixture_wraps_safe_write_errors(tmp_path: Path) -> None:
    destination = tmp_path / "copied"
    (destination / "tests" / "checkout_smoke.hurl").mkdir(parents=True)

    with pytest.raises(DemoFixtureError, match="non-file demo fixture file"):
        copy_demo_fixture(
            "checkout-api",
            destination,
            source_examples_root=REPO_ROOT / "examples",
        )


def test_copy_demo_fixture_rejects_symlinked_destination_component(tmp_path: Path) -> None:
    symlink_root = tmp_path / "linked"
    real_root = tmp_path / "real"
    real_root.mkdir()
    symlink_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(DemoFixtureError, match="symlinked"):
        copy_demo_fixture(
            "support-api",
            symlink_root / "fixture",
            source_examples_root=REPO_ROOT / "examples",
        )
