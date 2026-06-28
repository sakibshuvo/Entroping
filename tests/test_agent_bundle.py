"""Tests for local multi-agent review bundles."""

import json
from pathlib import Path

import pytest

import entroping.core.evidence.agent_bundle as agent_bundle
from entroping.core.evidence.agent_bundle import (
    AGENT_REVIEW_BUNDLE_SCHEMA_VERSION,
    AgentBundleError,
    build_agent_bundle_report,
    render_agent_bundle_markdown,
    run_agent_bundle_report,
)
from entroping.core.safe_write import SafeWriteError


def test_agent_bundle_summarizes_roles_and_reports_output_conflicts(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder", "breaker", "auditor"))
    _write_manifest(
        tmp_path,
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
        model="openai/builder",
        provider="openai",
        persona_source="agents/builder.md",
        output_paths=("tests/generated/checkout.hurl",),
        prompt_hash="builder-prompt-hash",
    )
    _write_manifest(
        tmp_path,
        "20260604T010100Z-architect-build-breaker-b.json",
        agent="breaker",
        model="deepseek/breaker",
        persona_source="agents/breaker.md",
        output_paths=("tests/generated/checkout.hurl",),
        prompt_hash="breaker-prompt-hash",
    )
    _write_manifest(
        tmp_path,
        "20260604T010200Z-architect-audit-auditor-c.json",
        agent="auditor",
        command="architect audit",
        mode="review",
        model="anthropic/auditor",
        persona_source="agents/auditor.md",
        output_paths=(),
        hurl_validated=False,
        prompt_hash="auditor-prompt-hash",
    )

    report = build_agent_bundle_report(project_root=tmp_path)

    assert report.schema_version == AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
    assert report.summary.status == "fail"
    assert report.summary.roles == 3
    assert report.summary.manifests == 3
    assert {role.role for role in report.roles} == {"builder", "breaker", "auditor"}
    assert all(role.configured for role in report.roles)
    assert [finding.kind for finding in report.findings] == ["output_path_conflict"]
    conflict = report.findings[0]
    assert conflict.severity == "error"
    assert conflict.path == "tests/generated/checkout.hurl"
    assert "builder, breaker" in conflict.message

    payload = report.model_dump(mode="json")
    assert payload["schema_version"] == "entroping.agent-review-bundle.v1"
    assert payload["roles"][0]["manifests"]
    markdown = render_agent_bundle_markdown(report)
    assert "# Entroping Agent Review Bundle" in markdown
    assert "tests/generated/checkout.hurl" in markdown
    assert "builder-prompt-hash" not in markdown
    assert "breaker-prompt-hash" not in markdown


def test_agent_bundle_reports_missing_role_config_and_invalid_provider_output(
    tmp_path: Path,
) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    _write_manifest(
        tmp_path,
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
        validation_status="failed",
        structured_output_validated=False,
        hurl_validated=False,
    )

    report = build_agent_bundle_report(project_root=tmp_path, roles=("builder", "breaker"))

    assert report.summary.status == "fail"
    assert [finding.kind for finding in report.findings] == [
        "missing_role_config",
        "invalid_provider_output",
        "unvalidated_hurl",
    ]
    assert report.findings[0].role == "breaker"
    assert "not configured" in report.findings[0].message
    assert "structured output" in report.findings[1].message
    assert "Hurl validation" in report.findings[2].message


def test_agent_bundle_role_selection_filters_manifest_evidence(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder", "breaker", "auditor"))
    _write_manifest(
        tmp_path,
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
    )
    _write_manifest(
        tmp_path,
        "20260604T010100Z-architect-build-breaker-b.json",
        agent="breaker",
    )

    report = build_agent_bundle_report(project_root=tmp_path, roles=("builder",))

    assert report.summary.status == "pass"
    assert [role.role for role in report.roles] == ["builder"]
    assert report.roles[0].manifests[0].agent == "builder"
    markdown = render_agent_bundle_markdown(report)
    assert "No agent-bundle findings." in markdown


def test_agent_bundle_rejects_unsupported_core_role(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))

    with pytest.raises(AgentBundleError, match="Unsupported agent-bundle role"):
        build_agent_bundle_report(project_root=tmp_path, roles=("planner",))


def test_agent_bundle_scope_filters_by_output_paths(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder", "breaker"))
    _write_manifest(
        tmp_path,
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
        output_paths=("tests/generated/checkout.hurl",),
    )
    _write_manifest(
        tmp_path,
        "20260604T010100Z-architect-build-breaker-b.json",
        agent="breaker",
        output_paths=("tests/generated/refund.hurl",),
    )

    report = build_agent_bundle_report(
        project_root=tmp_path,
        scope=Path("tests/generated/checkout.hurl"),
    )

    assert report.scope == "tests/generated/checkout.hurl"
    assert [role.role for role in report.roles] == ["builder", "breaker"]
    assert len(report.roles[0].manifests) == 1
    assert report.roles[1].manifests == ()
    assert report.findings[0].kind == "missing_manifest"
    assert report.findings[0].role == "breaker"


def test_agent_bundle_reports_source_evidence_and_scope_matches_preview_sources(
    tmp_path: Path,
) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    _write_manifest(
        tmp_path,
        "20260604T010000Z-architect-refactor-builder-a.json",
        agent="builder",
        command="architect refactor",
        mode="refactor",
        output_paths=(),
        source_evidence=(
            {
                "kind": "explicit_prompt",
                "reference": "prompt_intent",
                "sha256": "a" * 64,
            },
            {
                "kind": "selected_hurl_target",
                "reference": "tests/generated/checkout.hurl",
                "sha256": "b" * 64,
            },
        ),
    )

    report = build_agent_bundle_report(
        project_root=tmp_path,
        scope=Path("tests/generated/checkout.hurl"),
    )

    assert report.summary.status == "pass"
    manifest = report.roles[0].manifests[0]
    assert manifest.output_paths == ()
    assert [source.kind for source in manifest.source_evidence] == [
        "explicit_prompt",
        "selected_hurl_target",
    ]
    assert manifest.source_evidence[1].reference == "tests/generated/checkout.hurl"
    markdown = render_agent_bundle_markdown(report)
    assert "selected_hurl_target: tests/generated/checkout.hurl" in markdown
    assert "a" * 64 not in markdown
    assert "b" * 64 not in markdown


def test_agent_bundle_accepts_source_evidence_without_hash(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    _write_manifest(
        tmp_path,
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
        source_evidence=(
            {
                "kind": "drift_report",
                "reference": "reports/drift.json",
                "sha256": None,
            },
        ),
    )

    report = build_agent_bundle_report(project_root=tmp_path)

    assert report.summary.status == "pass"
    assert report.roles[0].manifests[0].source_evidence[0].sha256 is None


def test_agent_bundle_rejects_invalid_source_evidence_hash(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    _write_manifest(
        tmp_path,
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
        source_evidence=(
            {
                "kind": "drift_report",
                "reference": "reports/drift.json",
                "sha256": "not-a-sha",
            },
        ),
    )

    report = build_agent_bundle_report(project_root=tmp_path)

    assert report.summary.status == "fail"
    assert report.findings[0].kind == "invalid_manifest"


def test_agent_bundle_rejects_secret_like_manifest_without_leaking(
    tmp_path: Path,
) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    manifest_dir = tmp_path / ".entroping" / "agent-runs"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "20260604T010000Z-architect-build-builder-a.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.agent-run-manifest.v1",
                "agent": "builder",
                "raw_prompt": "secret=live-agent-secret",
            }
        ),
        encoding="utf-8",
    )

    report = build_agent_bundle_report(project_root=tmp_path)

    assert report.summary.status == "fail"
    assert report.findings[0].kind == "unsafe_manifest"
    assert "live-agent-secret" not in report.model_dump_json()
    assert "live-agent-secret" not in render_agent_bundle_markdown(report)


def test_agent_bundle_rejects_unsafe_scope(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))

    with pytest.raises(AgentBundleError, match="scope must stay inside"):
        build_agent_bundle_report(project_root=tmp_path, scope=Path("../outside"))


def test_agent_bundle_reports_missing_qanstitution(tmp_path: Path) -> None:
    with pytest.raises(AgentBundleError, match="QAnstitution file not found"):
        build_agent_bundle_report(project_root=tmp_path)


def test_agent_bundle_reports_missing_manifest_directory(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))

    report = build_agent_bundle_report(project_root=tmp_path)

    assert report.summary.status == "attention"
    assert report.summary.manifests == 0
    assert report.findings[0].kind == "missing_manifest"
    assert "No matching agent-run manifests were found." in render_agent_bundle_markdown(report)


def test_agent_bundle_reports_malformed_unreadable_and_invalid_timestamp_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    manifest_dir = tmp_path / ".entroping" / "agent-runs"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "malformed.json").write_text("{", encoding="utf-8")
    _write_manifest(
        tmp_path,
        "bad-timestamp.json",
        agent="builder",
        generated_at="not-a-date",
    )
    (manifest_dir / "unreadable.json").write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.name == "unreadable.json":
            raise OSError("permission denied")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    report = build_agent_bundle_report(project_root=tmp_path)

    assert report.summary.status == "fail"
    kinds = [finding.kind for finding in report.findings]
    assert kinds.count("invalid_manifest") == 3
    assert "missing_manifest" in kinds
    assert any("permission denied" in finding.message for finding in report.findings)


def test_agent_bundle_reports_symlinked_manifest_and_unsafe_output_paths(
    tmp_path: Path,
) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    outside_manifest = tmp_path.parent / "outside-agent-manifest.json"
    outside_manifest.write_text("{}", encoding="utf-8")
    manifest_dir = tmp_path / ".entroping" / "agent-runs"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "symlink.json").symlink_to(outside_manifest)
    _write_manifest(
        tmp_path,
        "absolute-output.json",
        agent="builder",
        output_paths=("/tmp/out.hurl",),
    )
    _write_manifest(
        tmp_path,
        "escaped-output.json",
        agent="builder",
        output_paths=("../outside.hurl",),
    )
    real_dir = tmp_path / "real-output"
    real_dir.mkdir()
    (tmp_path / "linked-output").symlink_to(real_dir)
    _write_manifest(
        tmp_path,
        "symlink-output.json",
        agent="builder",
        output_paths=("linked-output/generated.hurl",),
    )

    report = build_agent_bundle_report(project_root=tmp_path)

    assert report.summary.status == "fail"
    kinds = [finding.kind for finding in report.findings]
    assert kinds.count("invalid_manifest") == 4
    assert "missing_manifest" in kinds


def test_agent_bundle_rejects_symlinked_scope(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    real_scope = tmp_path / "real-scope"
    real_scope.mkdir()
    (tmp_path / "scope-link").symlink_to(real_scope)

    with pytest.raises(AgentBundleError, match="scope must not use symlinks"):
        build_agent_bundle_report(project_root=tmp_path, scope=Path("scope-link"))


def test_run_agent_bundle_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    _write_manifest(tmp_path, "builder.json", agent="builder")

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("write failed")

    monkeypatch.setattr(agent_bundle, "safe_write_text", fail_safe_write)

    with pytest.raises(AgentBundleError, match="write failed"):
        run_agent_bundle_report(project_root=tmp_path, output="md")


def test_run_agent_bundle_report_writes_json(tmp_path: Path) -> None:
    _write_qanstitution(tmp_path, roles=("builder",))
    _write_manifest(tmp_path, "builder.json", agent="builder")

    result = run_agent_bundle_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "agent-bundle.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.agent-review-bundle.v1"


def test_agent_bundle_text_and_display_helpers_redact_and_validate(tmp_path: Path) -> None:
    assert agent_bundle._display_project_path(tmp_path.parent / "outside", root=tmp_path)

    with pytest.raises(ValueError, match="must not be empty"):
        agent_bundle._validate_manifest_text("")
    with pytest.raises(ValueError, match="control characters"):
        agent_bundle._validate_manifest_text("bad\u0001value")
    with pytest.raises(ValueError, match="secret-like"):
        agent_bundle._validate_manifest_text("token=live-agent-secret")


def _write_qanstitution(tmp_path: Path, *, roles: tuple[str, ...]) -> None:
    agent_lines: list[str] = []
    for role in roles:
        agent_lines.extend(
            [
                f"  {role}:",
                f"    source: agents/{role}.md",
                f"    model: openai/{role}",
            ]
        )
    agents = "\n".join(agent_lines)
    tmp_path.joinpath("qanstitution.yaml").write_text(
        f"""
project: checkout-api
agents:
{agents}
gates: []
""".lstrip(),
        encoding="utf-8",
    )


def _write_manifest(
    tmp_path: Path,
    name: str,
    *,
    agent: str,
    command: str = "architect build",
    mode: str = "create",
    model: str = "openai/builder",
    persona_source: str = "agents/builder.md",
    output_paths: tuple[str, ...] = ("tests/generated/checkout.hurl",),
    validation_status: str = "passed",
    structured_output_validated: bool = True,
    hurl_validated: bool = True,
    prompt_hash: str = "prompt-hash",
    provider: str | None = None,
    generated_at: str = "2026-06-04T01:00:00+00:00",
    source_evidence: tuple[dict[str, object], ...] = (),
) -> None:
    manifest_dir = tmp_path / ".entroping" / "agent-runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "entroping.agent-run-manifest.v1",
        "generated_at": generated_at,
        "command": command,
        "mode": mode,
        "agent": agent,
        "model": model,
        "provider": provider,
        "persona": {
            "source_path": persona_source,
            "sha256": "persona-sha",
        },
        "prompt": {
            "intent_sha256": prompt_hash,
            "package_sha256": f"{prompt_hash}-package",
        },
        "output_paths": list(output_paths),
        "tags": [],
        "validation": {
            "status": validation_status,
            "structured_output_validated": structured_output_validated,
            "hurl_validated": hurl_validated,
        },
        "latency_ms": 42,
        "cost": {
            "estimated_usd": None,
            "input_cost_per_1m_tokens_usd": None,
            "output_cost_per_1m_tokens_usd": None,
        },
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }
    if source_evidence:
        payload["source_evidence"] = list(source_evidence)
    (manifest_dir / name).write_text(json.dumps(payload), encoding="utf-8")
