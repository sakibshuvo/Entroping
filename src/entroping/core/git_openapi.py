"""Load configured OpenAPI specs from a Git base ref."""

import shutil
import subprocess  # nosec B404
from pathlib import Path

from entroping.core.openapi_loader import OpenApiLoadError, load_openapi_document_text


class GitOpenApiError(ValueError):
    """Raised when a Git-backed OpenAPI baseline cannot be loaded safely."""


def load_openapi_document_at_ref(
    *,
    project_root: Path,
    base_ref: str,
    spec_path: Path,
) -> dict[str, object]:
    """Load ``spec_path`` from ``base_ref`` as an OpenAPI document."""

    root = project_root.expanduser().resolve()
    safe_ref = _validate_base_ref(base_ref)
    resolved_spec = spec_path.expanduser().resolve()
    if spec_path.is_symlink():
        msg = f"Refusing to load symlinked OpenAPI spec for --changed-from: {spec_path}"
        raise GitOpenApiError(msg)
    try:
        relative_spec = resolved_spec.relative_to(root)
    except ValueError as exc:
        msg = f"OpenAPI spec for --changed-from must be inside project root: {spec_path}"
        raise GitOpenApiError(msg) from exc

    git_binary = shutil.which("git")
    if git_binary is None:
        msg = "Could not load OpenAPI baseline: git executable not found"
        raise GitOpenApiError(msg)

    revision_path = f"{safe_ref}:{relative_spec.as_posix()}"
    result = subprocess.run(  # nosec B603
        [git_binary, "-C", str(root), "show", revision_path],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        msg = f"Could not load OpenAPI spec {relative_spec.as_posix()} from {safe_ref!r}{detail}"
        raise GitOpenApiError(msg)

    try:
        loaded = load_openapi_document_text(
            result.stdout,
            source_name=f"{safe_ref}:{relative_spec.as_posix()}",
        )
    except OpenApiLoadError as exc:
        raise GitOpenApiError(str(exc)) from exc
    return dict(loaded)


def _validate_base_ref(base_ref: str) -> str:
    ref = base_ref.strip()
    if (
        not ref
        or ref.startswith("-")
        or ":" in ref
        or "\\" in ref
        or ".." in ref
        or "@{" in ref
        or any(character.isspace() for character in ref)
        or any(ord(character) < 32 or ord(character) == 127 for character in ref)
    ):
        msg = f"unsafe Git base ref for OpenAPI comparison: {base_ref!r}"
        raise GitOpenApiError(msg)
    return ref
