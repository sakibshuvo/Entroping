"""Adapter tests for loading local OpenAPI documents."""

from pathlib import Path
from typing import TextIO

import pytest

from entroping.core.openapi_loader import OpenApiLoadError, load_openapi_document


def test_load_openapi_document_reads_local_yaml_mapping(tmp_path: Path) -> None:
    spec = tmp_path / "openapi.yaml"
    spec.write_text(
        """
openapi: "3.1.0"
paths: {}
""".lstrip(),
        encoding="utf-8",
    )

    document = load_openapi_document(spec)

    assert document["openapi"] == "3.1.0"
    assert document["paths"] == {}


def test_load_openapi_document_accepts_root_bounded_project_spec(tmp_path: Path) -> None:
    project = tmp_path / "project"
    spec_dir = project / "specs"
    spec_dir.mkdir(parents=True)
    spec = spec_dir / "openapi.yaml"
    spec.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    document = load_openapi_document(spec, root=project)

    assert document["openapi"] == "3.1.0"
    assert document["paths"] == {}


def test_load_openapi_document_accepts_root_relative_project_spec(tmp_path: Path) -> None:
    project = tmp_path / "project"
    spec_dir = project / "specs"
    spec_dir.mkdir(parents=True)
    (spec_dir / "openapi.yaml").write_text(
        "openapi: '3.1.0'\npaths: {}\n",
        encoding="utf-8",
    )

    document = load_openapi_document("specs/openapi.yaml", root=project)

    assert document["openapi"] == "3.1.0"
    assert document["paths"] == {}


def test_load_openapi_document_rejects_root_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    with pytest.raises(OpenApiLoadError, match="must be inside project root"):
        load_openapi_document(project / ".." / "outside.yaml", root=project)


def test_load_openapi_document_rejects_absolute_root_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    with pytest.raises(OpenApiLoadError, match="must be inside project root"):
        load_openapi_document(outside, root=project)


def test_load_openapi_document_rejects_root_bounded_symlink_components(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "openapi.yaml").write_text(
        "openapi: '3.1.0'\npaths: {}\n",
        encoding="utf-8",
    )
    (project / "linked-specs").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(OpenApiLoadError, match="symlinked OpenAPI spec path component"):
        load_openapi_document(project / "linked-specs" / "openapi.yaml", root=project)


def test_load_openapi_document_rejects_remote_urls() -> None:
    with pytest.raises(OpenApiLoadError, match="Remote OpenAPI specs are not supported"):
        load_openapi_document("https://example.test/openapi.yaml")


def test_load_openapi_document_rejects_unsupported_uri_scheme() -> None:
    with pytest.raises(OpenApiLoadError, match="Unsupported OpenAPI spec scheme 'file'"):
        load_openapi_document("file:///tmp/openapi.yaml")


def test_load_openapi_document_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OpenApiLoadError, match="OpenAPI spec file not found"):
        load_openapi_document(tmp_path / "missing.yaml")


def test_load_openapi_document_rejects_symlinked_spec(tmp_path: Path) -> None:
    real_spec = tmp_path / "real.yaml"
    real_spec.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")
    symlink = tmp_path / "linked.yaml"
    symlink.symlink_to(real_spec)

    with pytest.raises(OpenApiLoadError, match="Refusing to load symlinked OpenAPI spec"):
        load_openapi_document(symlink)


def test_load_openapi_document_wraps_yaml_parse_errors(tmp_path: Path) -> None:
    spec = tmp_path / "invalid.yaml"
    spec.write_text("openapi: [\n", encoding="utf-8")

    with pytest.raises(OpenApiLoadError, match="Invalid OpenAPI YAML"):
        load_openapi_document(spec)


def test_load_openapi_document_wraps_os_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = tmp_path / "openapi.yaml"
    spec.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    def raise_os_error(self: Path, *args: object, **kwargs: object) -> TextIO:
        raise OSError("disk failed")

    monkeypatch.setattr(Path, "open", raise_os_error)

    with pytest.raises(OpenApiLoadError, match="Could not read OpenAPI spec"):
        load_openapi_document(spec)


def test_load_openapi_document_treats_empty_file_as_empty_mapping(tmp_path: Path) -> None:
    spec = tmp_path / "empty.yaml"
    spec.write_text("", encoding="utf-8")

    assert load_openapi_document(spec) == {}


def test_load_openapi_document_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    spec = tmp_path / "list.yaml"
    spec.write_text("- openapi\n- paths\n", encoding="utf-8")

    with pytest.raises(OpenApiLoadError, match="OpenAPI spec must contain a YAML mapping"):
        load_openapi_document(spec)


def test_load_openapi_document_rejects_non_string_keys(tmp_path: Path) -> None:
    spec = tmp_path / "numeric-key.yaml"
    spec.write_text("1: value\n", encoding="utf-8")

    with pytest.raises(OpenApiLoadError, match="OpenAPI spec keys must be strings"):
        load_openapi_document(spec)
