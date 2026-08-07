from __future__ import annotations

import shlex
from pathlib import Path

from scripts.factory_control_plane_policy import protected_paths
from scripts.script_safety import (
    TRUNCATED_MESSAGE,
    ScriptSafetyError,
    read_text_file,
    run_subprocess,
)


class PatchInspectionError(ValueError):
    pass


def inspect_proposal_diff(path: Path) -> dict[str, object]:
    try:
        content = read_text_file(path)
    except ScriptSafetyError as exc:
        raise PatchInspectionError("proposal diff could not be read safely") from exc
    result = inspect_proposal_bytes(content.encode("utf-8"), strict_git_shapes=False)
    return {"proposal_diff_path": str(path), **result}


def inspect_proposal_bytes(payload: bytes, *, strict_git_shapes: bool = True) -> dict[str, object]:
    """Inspect already-authorized proposal bytes without reopening their path."""

    if b"\x00" in payload:
        raise PatchInspectionError("proposal diff must not contain NUL bytes")
    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchInspectionError("proposal diff must be valid UTF-8") from exc
    if strict_git_shapes:
        _reject_unsafe_git_shapes(content)
    additions, deletions, parsed_files = _git_patch_stats(content)
    changed_files: list[str] = []
    new_files: list[str] = []
    symlink_paths: list[str] = []
    current_paths: tuple[str, ...] = ()
    for line in content.splitlines():
        if line.startswith("diff --git "):
            current_paths = _changed_files_from_diff_header(line)
            for changed_file in current_paths:
                if changed_file not in changed_files:
                    changed_files.append(changed_file)
            continue
        for marker in ("rename from ", "rename to ", "copy from ", "copy to "):
            if line.startswith(marker):
                changed_file = _changed_file_from_extended_header(line, marker)
                if changed_file not in changed_files:
                    changed_files.append(changed_file)
                break
        normalized_line = line.rstrip()
        if normalized_line == "new file mode 100644":
            for changed_file in current_paths:
                if changed_file not in new_files:
                    new_files.append(changed_file)
        if normalized_line.endswith(" mode 120000") or (
            normalized_line.startswith("index ") and normalized_line.endswith(" 120000")
        ):
            for changed_file in current_paths:
                if changed_file not in symlink_paths:
                    symlink_paths.append(changed_file)
    for parsed_file in parsed_files:
        if parsed_file not in changed_files:
            changed_files.append(parsed_file)
    if parsed_files and not current_paths:
        raise PatchInspectionError("proposal diff must use git diff headers")
    return {
        "changed_files": changed_files,
        "files_changed": len(changed_files),
        "additions": additions,
        "deletions": deletions,
        **({"new_files": new_files} if new_files else {}),
        **({"symlink_paths": symlink_paths} if symlink_paths else {}),
    }


def _reject_unsafe_git_shapes(content: str) -> None:
    forbidden_prefixes = (
        "rename from ",
        "rename to ",
        "copy from ",
        "copy to ",
        "old mode ",
        "new mode ",
        "GIT binary patch",
        "Binary files ",
    )
    for line in content.splitlines():
        if line.startswith(forbidden_prefixes):
            raise PatchInspectionError("proposal diff contains a forbidden Git shape")
        if line.startswith(("new file mode ", "deleted file mode ")) and not line.endswith(
            " 100644"
        ):
            raise PatchInspectionError("proposal diff contains a forbidden file mode")
        if line.startswith("index ") and (line.endswith(" 120000") or line.endswith(" 160000")):
            raise PatchInspectionError("proposal diff contains a forbidden Git object mode")


def proposal_control_plane_violations(
    proposal: dict[str, object],
    *,
    repo_root: Path | None = None,
) -> list[tuple[str, str]]:
    paths = _string_items(proposal.get("changed_files"))
    violations = protected_paths(paths, repo_root=repo_root)
    violations.extend(
        (path, "symlink-path") for path in _string_items(proposal.get("symlink_paths"))
    )
    return list(dict.fromkeys(violations))


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _changed_files_from_diff_header(line: str) -> tuple[str, ...]:
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        raise PatchInspectionError("proposal diff contains an invalid diff header") from exc
    if len(parts) < 4:
        raise PatchInspectionError("proposal diff contains an invalid diff header")
    paths: list[str] = []
    for prefix, value in (("a/", parts[2]), ("b/", parts[3])):
        decoded = _decode_git_quoted_path(value)
        candidate = decoded[len(prefix) :] if decoded.startswith(prefix) else decoded
        if candidate not in paths:
            paths.append(candidate)
    return tuple(paths)


def _changed_file_from_extended_header(line: str, marker: str) -> str:
    candidate = line.removeprefix(marker).strip()
    if not candidate:
        raise PatchInspectionError("proposal diff contains an invalid extended header")
    if candidate.startswith('"'):
        try:
            parts = shlex.split(candidate)
        except ValueError as exc:
            raise PatchInspectionError("proposal diff contains an invalid extended header") from exc
        if len(parts) != 1:
            raise PatchInspectionError("proposal diff contains an invalid extended header")
        candidate = parts[0]
    return _decode_git_quoted_path(candidate)


def _decode_git_quoted_path(value: str) -> str:
    decoded = bytearray()
    index = 0
    escapes = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11}
    while index < len(value):
        character = value[index]
        if character != "\\":
            decoded.extend(character.encode("utf-8"))
            index += 1
            continue
        octal = value[index + 1 : index + 4]
        if len(octal) == 3 and all(digit in "01234567" for digit in octal):
            decoded.append(int(octal, 8))
            index += 4
            continue
        if index + 1 >= len(value) or value[index + 1] not in escapes:
            raise PatchInspectionError("proposal diff contains an unsupported path escape")
        decoded.append(escapes[value[index + 1]])
        index += 2
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchInspectionError("proposal diff contains a non-UTF-8 path") from exc


def _git_patch_stats(content: str) -> tuple[int, int, tuple[str, ...]]:
    try:
        completed = run_subprocess(
            ["git", "apply", "--numstat", "-z", "--no-index", "-"],
            check=False,
            timeout=5,
            max_output_bytes=262_144,
            input_text=content,
        )
    except ScriptSafetyError as exc:
        raise PatchInspectionError("proposal diff could not be parsed safely") from exc
    if completed.returncode != 0:
        raise PatchInspectionError("proposal diff is not a valid bounded Git patch")
    if completed.stdout.endswith(TRUNCATED_MESSAGE):
        raise PatchInspectionError("proposal diff path statistics exceeded the safe limit")
    additions = 0
    deletions = 0
    paths: list[str] = []
    for record in completed.stdout.split("\0"):
        if not record:
            continue
        fields = record.split("\t", maxsplit=2)
        if len(fields) != 3:
            raise PatchInspectionError("proposal diff returned malformed path statistics")
        added, deleted, path = fields
        if added != "-":
            additions += int(added)
        if deleted != "-":
            deletions += int(deleted)
        if path not in paths:
            paths.append(path)
    return additions, deletions, tuple(paths)
