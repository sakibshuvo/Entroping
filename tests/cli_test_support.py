"""Shared helpers and imports for CLI adapter tests."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO
from xml.etree import ElementTree

import pytest
import yaml
from typer.testing import CliRunner

import entroping.cli.commands.architect as architect_cli
import entroping.cli.commands.execution as execution_cli
import entroping.cli.commands.project as project_cli
import entroping.cli.commands.report as report_cli
import entroping.cli.main as cli_main
from entroping.brain.litellm_client import BrainProviderError, LiteLLMCompletionResult, LiteLLMUsage
from entroping.brain.prompt_builder import ArchitectPromptPackage
from entroping.bridge.openapi_to_hurl import GeneratedHurlFile
from entroping.cli.main import app
from entroping.core.hurl_runner import HurlFileResult, HurlRunOptions, HurlSuiteResult
from entroping.core.hurl_validator import HurlValidationError
from entroping.core.report_writer import ReportWriterError, write_json_report
from entroping.core.run_workflow import DependencyDriftObservationError, NoHurlTestsMatchedError
from entroping.core.traffic_proxy import MitmproxyUnavailableError, WatchConfig
from entroping.models.report import RunReport, RunReportSummary, RunTestReport
from entroping.studio.status import StudioDependencyError, render_studio_status


def _accept_architect_hurl_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "entroping.brain.architect_build.validate_hurl_content",
        lambda content, display_path: None,
    )


def _accept_openapi_hurl_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "entroping.cli.commands.architect.validate_hurl_content",
        lambda content, display_path: None,
    )


def _accept_architect_refactor_hurl_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "entroping.brain.architect_refactor.validate_hurl_content",
        lambda content, display_path: None,
    )


def _record_freeze_exchange(tmp_path: Path, *, secret: str = "freeze-secret") -> None:
    from datetime import UTC, datetime

    from entroping.core.traffic_redactor import redact_traffic_exchange
    from entroping.core.traffic_store import TrafficStore
    from entroping.models.traffic import (
        TrafficBody,
        TrafficExchange,
        TrafficRequest,
        TrafficResponse,
    )

    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method="POST",
            url=f"https://api.example.test/checkout?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=44,
                text=f'{{"cart_id":"cart-1","password":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=43,
                text='{"id":"ord_123","status":"accepted"}',
            ),
        ),
    )
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(redact_traffic_exchange(exchange))


def _record_mock_exchange(tmp_path: Path, *, secret: str = "mock-secret") -> None:
    from datetime import UTC, datetime

    from entroping.core.traffic_redactor import redact_traffic_exchange
    from entroping.core.traffic_store import TrafficStore
    from entroping.models.traffic import (
        TrafficBody,
        TrafficExchange,
        TrafficRequest,
        TrafficResponse,
    )

    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 1, tzinfo=UTC),
        duration_ms=40,
        request=TrafficRequest(
            method="POST",
            url=f"https://payments.example.test/charge?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=34,
                text=f'{{"card_token":"{secret}"}}',
            ),
        ),
        response=TrafficResponse(
            status_code=201,
            headers={
                "Content-Type": "application/json",
                "Set-Cookie": f"session={secret}",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=43,
                text=f'{{"approved":true,"token":"{secret}"}}',
            ),
        ),
    )
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(redact_traffic_exchange(exchange))

__all__ = [
    "json",
    "subprocess",
    "Path",
    "SimpleNamespace",
    "BinaryIO",
    "ElementTree",
    "pytest",
    "yaml",
    "CliRunner",
    "architect_cli",
    "execution_cli",
    "project_cli",
    "report_cli",
    "cli_main",
    "BrainProviderError",
    "LiteLLMCompletionResult",
    "LiteLLMUsage",
    "ArchitectPromptPackage",
    "GeneratedHurlFile",
    "app",
    "HurlFileResult",
    "HurlRunOptions",
    "HurlSuiteResult",
    "HurlValidationError",
    "ReportWriterError",
    "write_json_report",
    "DependencyDriftObservationError",
    "NoHurlTestsMatchedError",
    "MitmproxyUnavailableError",
    "WatchConfig",
    "RunReport",
    "RunReportSummary",
    "RunTestReport",
    "StudioDependencyError",
    "render_studio_status",
    "_accept_architect_hurl_validation",
    "_accept_openapi_hurl_validation",
    "_accept_architect_refactor_hurl_validation",
    "_record_freeze_exchange",
    "_record_mock_exchange",
]
