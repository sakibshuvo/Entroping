"""Git-backed OpenAPI baseline loading."""

import subprocess
from pathlib import Path

import pytest

from entroping.core.git_openapi import GitOpenApiError, load_openapi_document_at_ref


def _git(project_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        check=True,
        text=True,
    )


def _init_repo(project_root: Path) -> None:
    _git(project_root, "init", "-b", "main")
    _git(project_root, "config", "user.email", "entroping@example.test")
    _git(project_root, "config", "user.name", "Entroping Test")


def test_load_openapi_document_at_ref_reads_baseline_spec(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(
        """
openapi: "3.1.0"
paths:
  /health:
    get:
      operationId: getHealth
      responses:
        "200":
          description: ok
""".lstrip(),
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    spec_path.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    document = load_openapi_document_at_ref(
        project_root=tmp_path,
        base_ref="HEAD",
        spec_path=spec_path,
    )

    assert document["paths"] == {
        "/health": {
            "get": {
                "operationId": "getHealth",
                "responses": {"200": {"description": "ok"}},
            },
        },
    }


def test_load_openapi_document_at_ref_rejects_specs_outside_project(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-openapi.yaml"
    outside.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    with pytest.raises(GitOpenApiError, match="must be inside project root"):
        load_openapi_document_at_ref(project_root=tmp_path, base_ref="HEAD", spec_path=outside)


def test_load_openapi_document_at_ref_rejects_symlinked_current_spec(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")
    symlink = tmp_path / "openapi.yaml"
    symlink.symlink_to(target)

    with pytest.raises(GitOpenApiError, match="symlinked OpenAPI spec"):
        load_openapi_document_at_ref(project_root=tmp_path, base_ref="HEAD", spec_path=symlink)


def test_load_openapi_document_at_ref_rejects_unsafe_base_refs(tmp_path: Path) -> None:
    with pytest.raises(GitOpenApiError, match="unsafe Git base ref"):
        load_openapi_document_at_ref(
            project_root=tmp_path,
            base_ref="--help",
            spec_path=tmp_path / "openapi.yaml",
        )


def test_load_openapi_document_at_ref_reports_missing_git_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("entroping.core.git_openapi.shutil.which", lambda binary: None)

    with pytest.raises(GitOpenApiError, match="git executable not found"):
        load_openapi_document_at_ref(
            project_root=tmp_path,
            base_ref="HEAD",
            spec_path=tmp_path / "openapi.yaml",
        )


def test_load_openapi_document_at_ref_reports_git_show_failure(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    with pytest.raises(GitOpenApiError, match="Could not load OpenAPI spec"):
        load_openapi_document_at_ref(
            project_root=tmp_path,
            base_ref="HEAD",
            spec_path=tmp_path / "missing.yaml",
        )


def test_load_openapi_document_at_ref_wraps_invalid_baseline_yaml(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text("openapi: [\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "invalid baseline")
    spec_path.write_text("openapi: '3.1.0'\npaths: {}\n", encoding="utf-8")

    with pytest.raises(GitOpenApiError, match="Invalid OpenAPI YAML"):
        load_openapi_document_at_ref(
            project_root=tmp_path,
            base_ref="HEAD",
            spec_path=spec_path,
        )
