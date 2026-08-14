from cli_test_support import (
    CliRunner,
    GeneratedHurlFile,
    Path,
    app,
    architect_cli,
    pytest,
)

from entroping.cli.shared import safe_cli_text
from entroping.models.secrets import redact_secret_like_values


def test_architect_build_merge_strategy_requires_prompt_for_now() -> None:
    result = CliRunner().invoke(app, ["architect", "build", "--new", "--strategy", "merge"])

    assert result.exit_code == 2
    assert "--strategy merge requires --prompt" in result.output


def test_cli_helper_normalizes_supported_audit_focus() -> None:
    assert architect_cli._normalize_architect_audit_focus(" LoGiC ") == "logic"


def test_cli_helper_normalizes_supported_architect_build_agent() -> None:
    assert architect_cli._normalize_architect_build_agent(" BUILDER ") == "builder"
    assert architect_cli._normalize_architect_build_agent(" BrEaKeR ") == "breaker"


def test_configured_spec_reference_preserves_remote_and_absolute_paths(tmp_path: Path) -> None:
    remote = architect_cli._configured_spec_reference("https://example.test/openapi.yaml")
    absolute = architect_cli._configured_spec_reference(str(tmp_path / "openapi.yaml"))

    assert remote == "https://example.test/openapi.yaml"
    assert absolute == tmp_path / "openapi.yaml"


def test_safe_cli_text_replaces_all_disallowed_control_characters() -> None:
    forbidden_codes = [code for code in range(0x00, 0x20) if code not in (0x09, 0x0A)]
    forbidden_codes.append(0x7F)
    forbidden_codes.extend(range(0x80, 0xA0))
    forbidden = "".join(chr(code) for code in forbidden_codes)
    sanitized_forbidden = safe_cli_text(forbidden)
    assert sanitized_forbidden == "�" * len(forbidden_codes)
    assert len(sanitized_forbidden) == len(forbidden)
    assert all(character == "�" for character in sanitized_forbidden)

    value = (
        "🙂 status=ok\n"
        "Allowed text\tand line\n"
        "Unicode: ~ and \u00A0 keep.\n"
        "Bearer sk-proj-live-secret\n"
        f"\nforbidden={forbidden}"
    )
    redacted_first = redact_secret_like_values(value)
    sanitized = safe_cli_text(value)

    assert redacted_first == value.replace(
        "Bearer sk-proj-live-secret",
        "Bearer [REDACTED]",
    )
    assert safe_cli_text(redacted_first) == sanitized
    assert "Bearer [REDACTED]" in sanitized
    assert "sk-proj-live-secret" not in sanitized
    assert "\t" in sanitized
    assert "\n" in sanitized
    assert "~" in sanitized
    assert "\u00A0" in sanitized
    assert "🙂" in sanitized
    assert sanitized.endswith("forbidden=" + ("�" * len(forbidden)))


def test_write_generated_hurl_file_writes_openapi_generated_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    output_path = architect_cli._write_generated_hurl_file(
        GeneratedHurlFile(
            relative_path="tests/generated/health.hurl",
            content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
        )
    )

    assert output_path == (tmp_path / "tests" / "generated" / "health.hurl")
    assert output_path.read_text(encoding="utf-8") == (
        "# entroping: source=openapi\nGET /health\nHTTP 200\n"
    )


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("../escape.hurl", "must stay inside the project"),
        ("tests/manual/checkout.hurl", "must stay under tests/generated"),
    ],
)
def test_write_generated_hurl_file_rejects_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=message):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path=relative_path,
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )


def test_write_generated_hurl_file_rejects_symlinked_output_after_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "tests" / "generated" / "health.hurl"

    def allow_symlink_components(path: Path, *, root: Path) -> None:
        _ = path, root

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(self: Path) -> bool:
        if self == output_path:
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(architect_cli, "_reject_symlink_path_components", allow_symlink_components)
    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="symlinked generated Hurl file"):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )


def test_write_generated_hurl_file_rejects_existing_non_openapi_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    target.write_text("# manual\nGET /health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(ValueError, match="non-OpenAPI Hurl file"):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )


def test_write_generated_hurl_file_checks_existing_header_without_full_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    target.write_text("# manual\n" + ("GET /health\nHTTP 200\n" * 10_000), encoding="utf-8")
    original_read_text = Path.read_text

    def reject_full_target_read(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == target:
            raise AssertionError("ownership guard must not read the full target")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", reject_full_target_read)

    with pytest.raises(ValueError, match="non-OpenAPI Hurl file"):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )


def test_write_generated_hurl_file_accepts_owned_file_when_prefix_splits_utf8(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    content = "# entroping: source=openapi\n"
    if (architect_cli._OWNERSHIP_HEADER_READ_LIMIT_BYTES - len(content.encode("utf-8"))) % 2 == 0:
        content += "x"
    target.write_text(
        content
        + ("é" * architect_cli._OWNERSHIP_HEADER_READ_LIMIT_BYTES)
        + "\nGET /old-health\nHTTP 200\n",
        encoding="utf-8",
    )

    architect_cli._write_generated_hurl_file(
        GeneratedHurlFile(
            relative_path="tests/generated/health.hurl",
            content="# entroping: source=openapi\nGET /new-health\nHTTP 200\n",
        )
    )

    assert target.read_text(encoding="utf-8") == (
        "# entroping: source=openapi\nGET /new-health\nHTTP 200\n"
    )


def test_write_generated_hurl_file_rejects_truncated_utf8_marker_at_eof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    original = b"# entroping: source=openapi\xc3"
    target.write_bytes(original)

    with pytest.raises(UnicodeDecodeError):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /new-health\nHTTP 200\n",
            )
        )

    assert target.read_bytes() == original


def test_write_generated_hurl_file_rejects_sentinel_utf8_lead_byte_at_eof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    header = b"# entroping: source=openapi\n"
    padding = b"x" * (architect_cli._OWNERSHIP_HEADER_READ_LIMIT_BYTES - len(header))
    original = header + padding + b"\xc3"
    target.write_bytes(original)

    with pytest.raises(UnicodeDecodeError):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /new-health\nHTTP 200\n",
            )
        )

    assert target.read_bytes() == original


def test_write_generated_hurl_file_rejects_invalid_utf8_after_split_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    header = b"# entroping: source=openapi\n"
    if (architect_cli._OWNERSHIP_HEADER_READ_LIMIT_BYTES - len(header)) % 2 == 0:
        header += b"x"
    remaining = architect_cli._OWNERSHIP_HEADER_READ_LIMIT_BYTES - len(header)
    original = header + ("é" * (remaining // 2)).encode("utf-8") + b"\xc3x"
    target.write_bytes(original)

    with pytest.raises(UnicodeDecodeError):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /new-health\nHTTP 200\n",
            )
        )

    assert target.read_bytes() == original


def test_write_generated_hurl_file_rejects_spoofed_openapi_marker_below_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "# manual coverage\n"
        "# entroping: source=openapi\n"
        "GET /manual-health\n"
        "HTTP 200\n",
        encoding="utf-8",
    )
    original = target.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="non-OpenAPI Hurl file"):
        architect_cli._write_generated_hurl_file(
            GeneratedHurlFile(
                relative_path="tests/generated/health.hurl",
                content="# entroping: source=openapi\nGET /health\nHTTP 200\n",
            )
        )

    assert target.read_text(encoding="utf-8") == original


def test_write_generated_hurl_file_overwrites_existing_openapi_header_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "# entroping: tags=generated,smoke\n"
        "# entroping: source=openapi\n"
        "GET /old-health\n"
        "HTTP 200\n",
        encoding="utf-8",
    )

    architect_cli._write_generated_hurl_file(
        GeneratedHurlFile(
            relative_path="tests/generated/health.hurl",
            content=(
                "# entroping: tags=generated,smoke\n"
                "# entroping: source=openapi\n"
                "GET /new-health\n"
                "HTTP 200\n"
            ),
        )
    )

    assert target.read_text(encoding="utf-8") == (
        "# entroping: tags=generated,smoke\n"
        "# entroping: source=openapi\n"
        "GET /new-health\n"
        "HTTP 200\n"
    )


def test_write_generated_hurl_file_overwrites_existing_target_url_header_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tests" / "generated" / "health.hurl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "# entroping: source=target-url\n"
        "GET /old-health\n"
        "HTTP 200\n",
        encoding="utf-8",
    )

    architect_cli._write_generated_hurl_file(
        GeneratedHurlFile(
            relative_path="tests/generated/health.hurl",
            content=(
                "# entroping: source=target-url\n"
                "GET /new-health\n"
                "HTTP 200\n"
            ),
        )
    )

    assert target.read_text(encoding="utf-8") == (
        "# entroping: source=target-url\n"
        "GET /new-health\n"
        "HTTP 200\n"
    )


def test_architect_refactor_command_sanitizes_error_output(monkeypatch: pytest.MonkeyPatch) -> None:
    control_text = "refactor failure:\nBearer sk-proj-live-secret\t\x00\x1b[31m\u007F\u0080"

    def fake_load_qanstitution(_path: object) -> object:
        return object()

    def fake_run_architect_refactor(*_args: object, **_kwargs: object) -> None:
        raise ValueError(control_text)

    monkeypatch.setattr(architect_cli, "load_qanstitution", fake_load_qanstitution)
    monkeypatch.setattr(architect_cli, "run_architect_refactor", fake_run_architect_refactor)

    result = CliRunner().invoke(
        app,
        [
            "architect",
            "refactor",
            "--target",
            "tests/**/*.hurl",
            "--prompt",
            "refresh all",
        ],
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "sk-proj-live-secret" not in result.output
    assert "refactor failure:" in result.output
    assert "Bearer [REDACTED]" in result.output
    assert "\x00" not in result.output
    assert "\x1b" not in result.output
    assert "\u007f" not in result.output
    assert "\u0080" not in result.output
    assert "\r" not in result.output


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("# entroping: tags=generated\n\n# entroping: source=openapi\n", False),
        ("# entroping: tags=generated\n", False),
        ("# entroping: tags=generated\n# entroping: source=openapi\n", True),
        ("# entroping: tags=generated\n# entroping: source=target-url\n", True),
    ],
)
def test_openapi_generated_header_detection_requires_contiguous_source_header(
    content: str,
    expected: bool,
) -> None:
    assert architect_cli._has_openapi_generated_header(content) is expected
