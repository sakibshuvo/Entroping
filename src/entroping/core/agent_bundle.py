"""Local multi-agent review bundles from sanitized agent-run manifests."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.qanstitution import AgentRole
from entroping.models.secrets import (
    contains_secret_like_value,
    has_disallowed_control,
    redact_secret_like_values,
)

AGENT_REVIEW_BUNDLE_SCHEMA_VERSION: Final = "entroping.agent-review-bundle.v1"
AGENT_BUNDLE_ROLES: Final[tuple[AgentRole, ...]] = ("builder", "breaker", "auditor")

AgentBundleOutput = Literal["md", "json"]
AgentBundleStatus = Literal["pass", "attention", "fail"]
AgentBundleSeverity = Literal["error", "warning", "notice"]
AgentBundleFindingKind = Literal[
    "missing_role_config",
    "missing_manifest",
    "invalid_manifest",
    "unsafe_manifest",
    "invalid_provider_output",
    "unvalidated_hurl",
    "output_path_conflict",
]


class AgentBundleError(ValueError):
    """Raised when an agent review bundle cannot be generated."""


class AgentBundleFinding(BaseModel):
    """One review finding from local agent evidence."""

    model_config = ConfigDict(extra="forbid")

    kind: AgentBundleFindingKind
    severity: AgentBundleSeverity
    message: str
    role: AgentRole | None = None
    manifest_path: str | None = None
    path: str | None = None


class AgentBundleManifestEvidence(BaseModel):
    """Safe manifest evidence rendered into the bundle."""

    model_config = ConfigDict(extra="forbid")

    manifest_path: str
    generated_at: str
    command: str
    mode: str
    agent: AgentRole
    model: str
    provider: str | None
    persona_source_path: str
    persona_sha256: str
    output_paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    validation_status: Literal["passed", "failed"]
    structured_output_validated: bool
    hurl_validated: bool
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None


class AgentBundleRoleEvidence(BaseModel):
    """Configured role plus matching local manifest evidence."""

    model_config = ConfigDict(extra="forbid")

    role: AgentRole
    configured: bool
    configured_model: str | None = None
    configured_persona_source: str | None = None
    manifests: tuple[AgentBundleManifestEvidence, ...] = ()


class AgentBundleSummary(BaseModel):
    """Aggregate bundle status."""

    model_config = ConfigDict(extra="forbid")

    status: AgentBundleStatus
    roles: int = Field(ge=0)
    configured_roles: int = Field(ge=0)
    manifests: int = Field(ge=0)
    findings: int = Field(ge=0)


class AgentBundleReport(BaseModel):
    """Versioned local multi-agent review bundle."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.agent-review-bundle.v1"] = (
        AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
    )
    scope: str
    summary: AgentBundleSummary
    roles: tuple[AgentBundleRoleEvidence, ...]
    findings: tuple[AgentBundleFinding, ...]


@dataclass(frozen=True, slots=True)
class AgentBundleReportResult:
    """Result of writing one agent review bundle artifact."""

    output_path: Path
    report: AgentBundleReport


class _ManifestPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    sha256: str

    @field_validator("source_path", "sha256")
    @classmethod
    def validate_safe_text(cls, value: str) -> str:
        return _validate_manifest_text(value)


class _ManifestPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_sha256: str
    package_sha256: str

    @field_validator("intent_sha256", "package_sha256")
    @classmethod
    def validate_safe_text(cls, value: str) -> str:
        return _validate_manifest_text(value)


class _ManifestValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "failed"]
    structured_output_validated: bool
    hurl_validated: bool


class _ManifestCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_usd: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    input_cost_per_1m_tokens_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    output_cost_per_1m_tokens_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )


class _ManifestUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class _AgentRunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.agent-run-manifest.v1"]
    generated_at: str
    command: Literal["architect build", "architect refactor", "architect audit"]
    mode: Literal["create", "merge", "refactor", "review"]
    agent: AgentRole
    model: str
    provider: str | None
    persona: _ManifestPersona
    prompt: _ManifestPrompt
    output_paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    validation: _ManifestValidation
    latency_ms: int = Field(ge=0)
    cost: _ManifestCost
    usage: _ManifestUsage

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: str) -> str:
        text = _validate_manifest_text(value)
        try:
            datetime.fromisoformat(text)
        except ValueError as exc:
            msg = "generated_at must be an ISO 8601 timestamp"
            raise ValueError(msg) from exc
        return text

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return _validate_manifest_text(value)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_manifest_text(value)

    @field_validator("output_paths", "tags")
    @classmethod
    def validate_text_tuple(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validate_manifest_text(item) for item in value)


def run_agent_bundle_report(
    *,
    project_root: Path,
    output: AgentBundleOutput,
    roles: Sequence[str] | None = None,
    scope: str | Path = Path("."),
) -> AgentBundleReportResult:
    """Build and write a local multi-agent review bundle."""

    root = project_root.expanduser().resolve()
    report = build_agent_bundle_report(project_root=root, roles=roles, scope=scope)
    content = _render_report(report, output)
    output_path = root / "reports" / f"agent-bundle.{output}"
    try:
        written = safe_write_text(
            output_path,
            content,
            artifact="agent review bundle",
            root=root,
        )
    except SafeWriteError as exc:
        raise AgentBundleError(str(exc)) from exc
    return AgentBundleReportResult(output_path=written, report=report)


def build_agent_bundle_report(
    *,
    project_root: Path,
    roles: Sequence[str] | None = None,
    scope: str | Path = Path("."),
) -> AgentBundleReport:
    """Summarize Builder, Breaker, and Auditor evidence without provider calls."""

    root = project_root.expanduser().resolve()
    normalized_scope = _normalize_scope(scope, root=root)
    try:
        law = load_qanstitution(root / "qanstitution.yaml")
    except QanstitutionLoadError as exc:
        raise AgentBundleError(str(exc)) from exc
    selected_roles = _normalize_roles(roles, configured_roles=tuple(law.agents))

    manifests, findings = _load_manifests(root)
    selected_manifests = tuple(
        manifest
        for manifest in manifests
        if manifest.agent in selected_roles
        and _manifest_matches_scope(manifest, scope=normalized_scope)
    )

    role_evidence: list[AgentBundleRoleEvidence] = []
    for role in selected_roles:
        config = law.agents.get(role)
        role_manifests = tuple(
            manifest for manifest in selected_manifests if manifest.agent == role
        )
        if config is None:
            findings.append(
                _finding(
                    kind="missing_role_config",
                    severity="error",
                    role=role,
                    message=f"Agent role {role} is not configured in qanstitution.yaml.",
                )
            )
        elif not role_manifests:
            findings.append(
                _finding(
                    kind="missing_manifest",
                    severity="warning",
                    role=role,
                    message=f"No local agent-run manifest matched role {role} for this scope.",
                )
            )
        role_evidence.append(
            AgentBundleRoleEvidence(
                role=role,
                configured=config is not None,
                configured_model=None if config is None else config.model,
                configured_persona_source=None if config is None else config.source,
                manifests=role_manifests,
            )
        )

    findings.extend(_validation_findings(selected_manifests))
    findings.extend(_conflict_findings(selected_manifests))
    status = _status(findings)
    return AgentBundleReport(
        scope=normalized_scope,
        summary=AgentBundleSummary(
            status=status,
            roles=len(role_evidence),
            configured_roles=sum(1 for role in role_evidence if role.configured),
            manifests=len(selected_manifests),
            findings=len(findings),
        ),
        roles=tuple(role_evidence),
        findings=tuple(findings),
    )


def render_agent_bundle_markdown(report: AgentBundleReport) -> str:
    """Render a safe Markdown bundle for human review."""

    lines = [
        "# Entroping Agent Review Bundle",
        "",
        f"- Status: `{report.summary.status}`",
        f"- Scope: `{_inline_code(report.scope)}`",
        f"- Roles: `{report.summary.roles}`",
        f"- Configured roles: `{report.summary.configured_roles}`",
        f"- Manifests: `{report.summary.manifests}`",
        f"- Findings: `{report.summary.findings}`",
        "",
        "## Roles",
        "",
        "| Role | Configured | Model | Persona | Manifests |",
        "| --- | --- | --- | --- | --- |",
    ]
    for role in report.roles:
        lines.append(
            "| "
            f"{_markdown_cell(role.role)} | "
            f"{_markdown_cell('yes' if role.configured else 'no')} | "
            f"{_markdown_cell(role.configured_model or 'n/a')} | "
            f"{_markdown_cell(role.configured_persona_source or 'n/a')} | "
            f"{len(role.manifests)} |"
        )

    lines.extend(["", "## Manifest Evidence", ""])
    manifests = [manifest for role in report.roles for manifest in role.manifests]
    if not manifests:
        lines.append("No matching agent-run manifests were found.")
    else:
        lines.extend(
            [
                "| Role | Manifest | Command | Model | Provider | Outputs | Validation |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for manifest in manifests:
            validation = (
                f"{manifest.validation_status}; "
                f"structured={manifest.structured_output_validated}; "
                f"hurl={manifest.hurl_validated}"
            )
            outputs = ", ".join(manifest.output_paths) if manifest.output_paths else "n/a"
            lines.append(
                "| "
                f"{_markdown_cell(manifest.agent)} | "
                f"{_markdown_cell(manifest.manifest_path)} | "
                f"{_markdown_cell(manifest.command)} | "
                f"{_markdown_cell(manifest.model)} | "
                f"{_markdown_cell(manifest.provider or 'unknown')} | "
                f"{_markdown_cell(outputs)} | "
                f"{_markdown_cell(validation)} |"
            )

    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No agent-bundle findings.")
    else:
        lines.extend(
            [
                "| Severity | Kind | Role | Path | Message |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for finding in report.findings:
            lines.append(
                "| "
                f"{_markdown_cell(finding.severity)} | "
                f"{_markdown_cell(finding.kind)} | "
                f"{_markdown_cell(finding.role or 'n/a')} | "
                f"{_markdown_cell(finding.path or finding.manifest_path or 'n/a')} | "
                f"{_markdown_cell(finding.message)} |"
            )
    return "\n".join(lines) + "\n"


def _render_report(report: AgentBundleReport, output: AgentBundleOutput) -> str:
    if output == "md":
        return render_agent_bundle_markdown(report)
    return report.model_dump_json(indent=2) + "\n"


def _normalize_roles(
    roles: Sequence[str] | None,
    *,
    configured_roles: Sequence[str] = (),
) -> tuple[AgentRole, ...]:
    if roles is None or len(roles) == 0:
        selected = tuple(role for role in AGENT_BUNDLE_ROLES if role in configured_roles)
        return selected or AGENT_BUNDLE_ROLES

    normalized: list[AgentRole] = []
    for role in roles:
        role_name = role.strip().lower()
        if role_name not in AGENT_BUNDLE_ROLES:
            msg = (
                "Unsupported agent-bundle role "
                f"{role!r}; expected builder, breaker, or auditor."
            )
            raise AgentBundleError(msg)
        typed_role: AgentRole = role_name
        if typed_role not in normalized:
            normalized.append(typed_role)
    return tuple(normalized)


def _normalize_scope(scope: str | Path, *, root: Path) -> str:
    raw_scope = Path(scope)
    candidate = raw_scope.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        msg = f"agent-bundle scope must stay inside {root}: {scope}"
        raise AgentBundleError(msg) from exc
    if candidate.is_relative_to(root):
        symlink_component = first_symlink_path_component(candidate, root=root)
        if symlink_component is not None:
            msg = f"agent-bundle scope must not use symlinks: {symlink_component}"
            raise AgentBundleError(msg)
    scope_text = relative.as_posix()
    return "." if scope_text == "." else scope_text


def _load_manifests(
    root: Path,
) -> tuple[tuple[AgentBundleManifestEvidence, ...], list[AgentBundleFinding]]:
    manifest_dir = root / ".entroping" / "agent-runs"
    if not manifest_dir.exists():
        return (), []

    findings: list[AgentBundleFinding] = []
    manifests: list[AgentBundleManifestEvidence] = []
    for path in sorted(manifest_dir.glob("*.json")):
        display_path = _display_project_path(path, root=root)
        symlink_component = first_symlink_path_component(path, root=root)
        if symlink_component is not None:
            findings.append(
                _finding(
                    kind="invalid_manifest",
                    severity="error",
                    manifest_path=display_path,
                    message="Agent-run manifest path uses a symlink component.",
                )
            )
            continue

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                _finding(
                    kind="invalid_manifest",
                    severity="error",
                    manifest_path=display_path,
                    message=f"Could not read agent-run manifest: {exc}",
                )
            )
            continue
        if contains_secret_like_value(raw):
            findings.append(
                _finding(
                    kind="unsafe_manifest",
                    severity="error",
                    manifest_path=display_path,
                    message="Agent-run manifest contains secret-like text and was skipped.",
                )
            )
            continue

        try:
            manifest = _AgentRunManifest.model_validate_json(raw)
            manifests.append(_manifest_evidence(manifest, path=path, root=root))
        except (AgentBundleError, ValidationError, json.JSONDecodeError, UnicodeError):
            findings.append(
                _finding(
                    kind="invalid_manifest",
                    severity="error",
                    manifest_path=display_path,
                    message="Agent-run manifest failed schema or safety validation.",
                )
            )
    sorted_manifests = tuple(
        sorted(manifests, key=lambda item: (item.generated_at, item.manifest_path))
    )
    return sorted_manifests, findings


def _manifest_evidence(
    manifest: _AgentRunManifest,
    *,
    path: Path,
    root: Path,
) -> AgentBundleManifestEvidence:
    output_paths = tuple(
        _normalize_manifest_output_path(item, root=root) for item in manifest.output_paths
    )
    return AgentBundleManifestEvidence(
        manifest_path=_display_project_path(path, root=root),
        generated_at=manifest.generated_at,
        command=manifest.command,
        mode=manifest.mode,
        agent=manifest.agent,
        model=manifest.model,
        provider=manifest.provider,
        persona_source_path=manifest.persona.source_path,
        persona_sha256=manifest.persona.sha256,
        output_paths=output_paths,
        tags=tuple(sorted(manifest.tags)),
        validation_status=manifest.validation.status,
        structured_output_validated=manifest.validation.structured_output_validated,
        hurl_validated=manifest.validation.hurl_validated,
        latency_ms=manifest.latency_ms,
        prompt_tokens=manifest.usage.prompt_tokens,
        completion_tokens=manifest.usage.completion_tokens,
        total_tokens=manifest.usage.total_tokens,
        estimated_cost_usd=manifest.cost.estimated_usd,
    )


def _normalize_manifest_output_path(path: str, *, root: Path) -> str:
    raw_path = Path(path)
    if raw_path.is_absolute():
        msg = "agent-run output paths must be relative"
        raise AgentBundleError(msg)
    candidate = root / raw_path
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        msg = "agent-run output paths must stay inside the project"
        raise AgentBundleError(msg) from exc
    if candidate.is_relative_to(root):
        symlink_component = first_symlink_path_component(candidate, root=root)
        if symlink_component is not None:
            msg = "agent-run output paths must not use symlinks"
            raise AgentBundleError(msg)
    return relative.as_posix()


def _manifest_matches_scope(
    manifest: AgentBundleManifestEvidence,
    *,
    scope: str,
) -> bool:
    if scope == ".":
        return True
    scope_prefix = f"{scope.rstrip('/')}/"
    return any(path == scope or path.startswith(scope_prefix) for path in manifest.output_paths)


def _validation_findings(
    manifests: Sequence[AgentBundleManifestEvidence],
) -> tuple[AgentBundleFinding, ...]:
    findings: list[AgentBundleFinding] = []
    for manifest in manifests:
        if manifest.validation_status != "passed" or not manifest.structured_output_validated:
            findings.append(
                _finding(
                    kind="invalid_provider_output",
                    severity="error",
                    role=manifest.agent,
                    manifest_path=manifest.manifest_path,
                    message=(
                        "Provider output did not pass structured output validation "
                        "before bundle review."
                    ),
                )
            )
        if (
            manifest.command in {"architect build", "architect refactor"}
            and manifest.output_paths
            and not manifest.hurl_validated
        ):
            findings.append(
                _finding(
                    kind="unvalidated_hurl",
                    severity="error",
                    role=manifest.agent,
                    manifest_path=manifest.manifest_path,
                    message=(
                        "Generated or refactored Hurl evidence is missing parser-backed "
                        "Hurl validation."
                    ),
                )
            )
    return tuple(findings)


def _conflict_findings(
    manifests: Sequence[AgentBundleManifestEvidence],
) -> tuple[AgentBundleFinding, ...]:
    by_output_path: dict[str, list[AgentBundleManifestEvidence]] = defaultdict(list)
    for manifest in manifests:
        for output_path in manifest.output_paths:
            by_output_path[output_path].append(manifest)

    findings: list[AgentBundleFinding] = []
    for output_path, path_manifests in sorted(by_output_path.items()):
        roles = [
            role
            for role in AGENT_BUNDLE_ROLES
            if any(manifest.agent == role for manifest in path_manifests)
        ]
        if len(roles) < 2:
            continue
        findings.append(
            _finding(
                kind="output_path_conflict",
                severity="error",
                path=output_path,
                message=(
                    "Multiple agent roles produced evidence for the same output path: "
                    f"{', '.join(roles)}."
                ),
            )
        )
    return tuple(findings)


def _status(findings: Sequence[AgentBundleFinding]) -> AgentBundleStatus:
    if any(finding.severity == "error" for finding in findings):
        return "fail"
    if findings:
        return "attention"
    return "pass"


def _finding(
    *,
    kind: AgentBundleFindingKind,
    severity: AgentBundleSeverity,
    message: str,
    role: AgentRole | None = None,
    manifest_path: str | None = None,
    path: str | None = None,
) -> AgentBundleFinding:
    return AgentBundleFinding(
        kind=kind,
        severity=severity,
        message=redact_secret_like_values(message),
        role=role,
        manifest_path=manifest_path,
        path=path,
    )


def _display_project_path(path: Path, *, root: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return redact_secret_like_values(str(path))


def _validate_manifest_text(value: str) -> str:
    text = value.strip()
    if not text:
        msg = "manifest text field must not be empty"
        raise ValueError(msg)
    if has_disallowed_control(text):
        msg = "manifest text field must not contain control characters"
        raise ValueError(msg)
    if contains_secret_like_value(text):
        msg = "manifest text field must not contain secret-like values"
        raise ValueError(msg)
    return text


def _markdown_cell(value: object) -> str:
    text = _markdown_text(str(value))
    return text.replace("|", "\\|").replace("\n", " ")


def _markdown_text(value: str) -> str:
    return redact_secret_like_values(value).replace("\r", " ").replace("\n", " ")


def _inline_code(value: str) -> str:
    return redact_secret_like_values(value).replace("`", "'")
