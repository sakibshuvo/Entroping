"""Adapter tests for loading local OpenAPI documents."""

from pathlib import Path

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


def test_load_openapi_document_rejects_remote_urls() -> None:
    with pytest.raises(OpenApiLoadError, match="Remote OpenAPI specs are not supported"):
        load_openapi_document("https://example.test/openapi.yaml")


def test_load_openapi_document_rejects_symlinked_spec(tmp_path: Path) -> None:
    real_spec = tmp_path / "real.yaml"
    real_spec.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")
    symlink = tmp_path / "linked.yaml"
    symlink.symlink_to(real_spec)

    with pytest.raises(OpenApiLoadError, match="Refusing to load symlinked OpenAPI spec"):
        load_openapi_document(symlink)
