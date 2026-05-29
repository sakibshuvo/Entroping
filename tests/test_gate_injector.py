"""Adapter tests for temporary Hurl gate injection."""

from pathlib import Path
from textwrap import dedent

import pytest

from entroping.core.gate_injector import GateInjectionError, write_injected_execution_copy
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.models.hurl import HurlMetadata, HurlTest
from entroping.models.qanstitution import Enforcement, GateRule


def _write_hurl(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")
    return path


def _gate(
    gate_id: str,
    condition: str,
    assertion: str,
    enforcement: Enforcement = "block",
) -> GateRule:
    return GateRule(
        id=gate_id,
        condition=condition,
        gate=assertion,
        enforcement=enforcement,
    )


@pytest.mark.regression
@pytest.mark.security
def test_write_injected_execution_copy_never_mutates_source_hurl(tmp_path: Path) -> None:
    source = _write_hurl(
        tmp_path / "tests" / "checkout_smoke.hurl",
        """
        # entroping: tags=smoke,checkout
        # entroping: story_id=CHK-001

        GET {{base_url}}/health
        HTTP 200
        [Asserts]
        jsonpath "$.status" == "ok"

        POST {{base_url}}/checkout
        Content-Type: application/json
        {
          "cart_id": "{{cart_id}}"
        }
        HTTP 201
        [Asserts]
        jsonpath "$.id" exists
        """,
    )
    discovered = discover_hurl_tests([source])
    source_before = source.read_text(encoding="utf-8")

    execution = write_injected_execution_copy(
        discovered[0],
        [
            _gate("global_latency", "true", "duration < 2000"),
            _gate("smoke_latency", "tags contains 'smoke'", "duration < 500", "warn"),
            _gate("post_json", "method == 'POST'", 'header "Content-Type" exists'),
            _gate("checkout_path", "path contains '/checkout'", "status < 500"),
        ],
        execution_root=tmp_path / "execution",
    )

    injected = execution.execution_path.read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == source_before
    assert execution.source_path == source.resolve()
    assert execution.execution_path.is_relative_to((tmp_path / "execution").resolve())
    assert execution.execution_path != source.resolve()
    assert [gate.rule_id for gate in execution.injected_gates] == [
        "global_latency",
        "smoke_latency",
        "post_json",
        "checkout_path",
    ]
    assert 'jsonpath "$.status" == "ok"' in injected
    assert "# entroping-gate: global_latency enforcement=block" in injected
    assert "# entroping-gate: smoke_latency enforcement=warn" in injected
    assert "# entroping-gate: post_json enforcement=block" in injected
    assert "# entroping-gate: checkout_path enforcement=block" in injected
    assert injected.count("duration < 2000") == 2
    assert injected.count("duration < 500") == 2
    assert injected.count('header "Content-Type" exists') == 1
    assert injected.count("status < 500") == 1


def test_write_injected_execution_copy_creates_asserts_block_when_missing(
    tmp_path: Path,
) -> None:
    source = _write_hurl(
        tmp_path / "tests" / "health.hurl",
        """
        # entroping: tags=smoke

        GET {{base_url}}/health
        HTTP 200
        """,
    )

    execution = write_injected_execution_copy(
        discover_hurl_tests([source])[0],
        [_gate("global_latency", "true", "duration < 2000")],
        execution_root=tmp_path / "execution",
    )

    assert (
        "HTTP 200\n"
        "[Asserts]\n"
        "# entroping-gate: global_latency enforcement=block\n"
        "duration < 2000"
    ) in execution.execution_path.read_text(encoding="utf-8")


@pytest.mark.security
def test_write_injected_execution_copy_rejects_non_hurl_source_path(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "not_hurl.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("GET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(GateInjectionError, match="Expected a .hurl file"):
        write_injected_execution_copy(
            HurlTest(path=source, metadata=HurlMetadata()),
            [_gate("global_latency", "true", "duration < 2000")],
            execution_root=tmp_path / "execution",
        )


@pytest.mark.security
def test_write_injected_execution_copy_rejects_symlinked_source_path(tmp_path: Path) -> None:
    source = _write_hurl(
        tmp_path / "real" / "health.hurl",
        """
        GET {{base_url}}/health
        HTTP 200
        """,
    )
    symlink = tmp_path / "tests" / "health.hurl"
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(source)

    with pytest.raises(GateInjectionError, match="symlinked Hurl file"):
        write_injected_execution_copy(
            HurlTest(path=symlink, metadata=HurlMetadata()),
            [_gate("global_latency", "true", "duration < 2000")],
            execution_root=tmp_path / "execution",
        )


@pytest.mark.security
def test_write_injected_execution_copy_rejects_symlinked_execution_path(tmp_path: Path) -> None:
    source = _write_hurl(
        tmp_path / "tests" / "health.hurl",
        """
        GET {{base_url}}/health
        HTTP 200
        """,
    )
    discovered = discover_hurl_tests([source])[0]
    execution_root = tmp_path / "execution"
    first_execution = write_injected_execution_copy(
        discovered,
        [_gate("global_latency", "true", "duration < 2000")],
        execution_root=execution_root,
    )
    first_execution.execution_path.unlink()
    outside_target = tmp_path / "outside.hurl"
    first_execution.execution_path.symlink_to(outside_target)

    with pytest.raises(GateInjectionError, match="symlinked execution path"):
        write_injected_execution_copy(
            discovered,
            [_gate("global_latency", "true", "duration < 2000")],
            execution_root=execution_root,
        )
    assert not outside_target.exists()
