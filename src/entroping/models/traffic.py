"""Domain models for redacted Eye traffic state."""

from datetime import datetime
from typing import Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TrafficBody(BaseModel):
    """Bounded body summary captured from HTTP traffic."""

    model_config = ConfigDict(extra="forbid")

    content_type: str | None = None
    size_bytes: int = Field(ge=0)
    text: str | None = None
    truncated: bool = False

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str | None) -> str | None:
        if value is not None and _contains_control(value):
            msg = "content type must not contain control characters"
            raise ValueError(msg)
        return value


class TrafficRequest(BaseModel):
    """Captured HTTP request metadata and bounded body summary."""

    model_config = ConfigDict(extra="forbid")

    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: TrafficBody | None = None

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        method = value.upper().strip()
        if not method or _contains_control(method) or not method.replace("-", "").isalpha():
            msg = "HTTP method must be a token without control characters"
            raise ValueError(msg)
        return method

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if _contains_control(value):
            msg = "URL must not contain control characters"
            raise ValueError(msg)
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            msg = "URL must be an absolute http or https URL"
            raise ValueError(msg)
        return value

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_headers(value)

    @property
    def host(self) -> str:
        """Return the request host for indexed local state."""

        return urlsplit(self.url).netloc

    @property
    def path(self) -> str:
        """Return the request path for indexed local state."""

        return urlsplit(self.url).path or "/"


class TrafficResponse(BaseModel):
    """Captured HTTP response metadata and bounded body summary."""

    model_config = ConfigDict(extra="forbid")

    status_code: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: TrafficBody | None = None

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_headers(value)


class TrafficExchange(BaseModel):
    """One request/response exchange safe for local Eye storage after redaction."""

    model_config = ConfigDict(extra="forbid")

    captured_at: datetime
    duration_ms: int | None = Field(default=None, ge=0)
    request: TrafficRequest
    response: TrafficResponse | None = None
    redacted: bool = False

    @model_validator(mode="after")
    def require_timezone(self) -> Self:
        if self.captured_at.tzinfo is None:
            msg = "captured_at must be timezone-aware"
            raise ValueError(msg)
        return self


def _validate_headers(headers: dict[str, str]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for name, value in headers.items():
        if not name or _contains_control(name) or ":" in name:
            msg = "header names must be non-empty tokens without control characters"
            raise ValueError(msg)
        if _contains_control(value, allow_tab=True):
            msg = f"header value for {name!r} must not contain control characters"
            raise ValueError(msg)
        validated[name] = value
    return validated


def _contains_control(value: str, *, allow_tab: bool = False) -> bool:
    for character in value:
        codepoint = ord(character)
        if allow_tab and character == "\t":
            continue
        if codepoint < 32 or codepoint == 127:
            return True
    return False
