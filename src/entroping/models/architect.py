"""Domain models for Architect-generated edits."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ArchitectEdit(BaseModel):
    """One proposed Hurl file edit from an Architect role."""

    model_config = ConfigDict(extra="forbid")

    path: str
    content: str
    rationale: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Keep generated edits inside reviewable Hurl test paths."""

        path = value.strip()
        if not path:
            msg = "path must not be empty"
            raise ValueError(msg)
        if _has_path_control(path):
            msg = "path must not contain control characters"
            raise ValueError(msg)
        if "\\" in path:
            msg = "path must use POSIX separators"
            raise ValueError(msg)
        parsed = PurePosixPath(path)
        if parsed.is_absolute():
            msg = "path must be relative"
            raise ValueError(msg)
        if ".." in parsed.parts:
            msg = "path must not contain parent traversal"
            raise ValueError(msg)
        if not parsed.parts or parsed.parts[0] != "tests":
            msg = "path must stay under tests/"
            raise ValueError(msg)
        if parsed.suffix != ".hurl":
            msg = "path must end with .hurl"
            raise ValueError(msg)
        return path

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Reject empty or binary-like generated Hurl content."""

        if not value.strip():
            msg = "content must not be empty"
            raise ValueError(msg)
        if _has_disallowed_control(value):
            msg = "content must not contain control characters"
            raise ValueError(msg)
        return value


class ArchitectEditSet(BaseModel):
    """Structured Architect output parsed before writing files."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    edits: list[ArchitectEdit] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_edit_paths(self) -> "ArchitectEditSet":
        """Reject contradictory provider edits for the same target path."""

        seen: set[str] = set()
        for edit in self.edits:
            if edit.path in seen:
                msg = f"duplicate Architect edit path: {edit.path}"
                raise ValueError(msg)
            seen.add(edit.path)
        return self

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        """Require a human-readable summary for review."""

        summary = value.strip()
        if not summary:
            msg = "summary must not be empty"
            raise ValueError(msg)
        if _has_disallowed_control(summary):
            msg = "summary must not contain control characters"
            raise ValueError(msg)
        return summary

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, value: list[str]) -> list[str]:
        """Reject binary-like warning text."""

        for warning in value:
            if _has_disallowed_control(warning):
                msg = "warning must not contain control characters"
                raise ValueError(msg)
        return value


class ArchitectAuditReviewFinding(BaseModel):
    """One actionable Auditor finding parsed from provider output."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["info", "warn", "error"]
    title: str
    detail: str
    recommendation: str
    evidence: list[str] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        """Require stable machine-readable finding codes."""

        code = value.strip()
        if not code:
            msg = "code must not be empty"
            raise ValueError(msg)
        if _has_disallowed_control(code):
            msg = "code must not contain control characters"
            raise ValueError(msg)
        return code

    @field_validator("title", "detail", "recommendation")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject empty or binary-like review text."""

        text = value.strip()
        if not text:
            msg = "text must not be empty"
            raise ValueError(msg)
        if _has_disallowed_control(text):
            msg = "text must not contain control characters"
            raise ValueError(msg)
        return text

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: list[str]) -> list[str]:
        """Reject binary-like evidence labels."""

        clean: list[str] = []
        for item in value:
            evidence = item.strip()
            if not evidence:
                msg = "evidence must not be empty"
                raise ValueError(msg)
            if _has_disallowed_control(evidence):
                msg = "evidence must not contain control characters"
                raise ValueError(msg)
            clean.append(evidence)
        return clean


class ArchitectAuditReview(BaseModel):
    """Structured Auditor review output parsed before display."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    findings: list[ArchitectAuditReviewFinding]
    warnings: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Return true when the Auditor found no blocking issues."""

        return all(finding.severity != "error" for finding in self.findings)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        """Require a human-readable review summary."""

        summary = value.strip()
        if not summary:
            msg = "summary must not be empty"
            raise ValueError(msg)
        if _has_disallowed_control(summary):
            msg = "summary must not contain control characters"
            raise ValueError(msg)
        return summary

    @field_validator("warnings")
    @classmethod
    def validate_review_warnings(cls, value: list[str]) -> list[str]:
        """Reject binary-like warning text."""

        for warning in value:
            if _has_disallowed_control(warning):
                msg = "warning must not contain control characters"
                raise ValueError(msg)
        return value


def _has_disallowed_control(value: str) -> bool:
    allowed = {"\n", "\r", "\t"}
    return any(character not in allowed and ord(character) < 32 for character in value)


def _has_path_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
