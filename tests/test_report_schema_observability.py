"""Versioned report schema contract tests."""

import json
from pathlib import Path

from entroping.core.evidence.observability_packet import (
    OBSERVABILITY_PACKET_SCHEMA_VERSION,
    ObservabilityComponentSummary,
    ObservabilityEventSummary,
    ObservabilityMessage,
    ObservabilityPacket,
    ObservabilityRuntimeSummary,
    ObservabilitySource,
    ObservabilitySummary,
)
from entroping.core.evidence.otel_mapping import (
    OTEL_MAPPING_SCHEMA_VERSION,
    OtelAttributeMapping,
    OtelBoundaryControl,
    OtelMappingNextAction,
    OtelMappingPacket,
    OtelMappingSource,
    OtelMappingSummary,
)
from entroping.core.evidence.otlp_preview import (
    OTLP_PREVIEW_SCHEMA_VERSION,
    OtlpPreviewAttribute,
    OtlpPreviewBoundaryControl,
    OtlpPreviewFixture,
    OtlpPreviewLogRecord,
    OtlpPreviewMetric,
    OtlpPreviewNextAction,
    OtlpPreviewPacket,
    OtlpPreviewSource,
    OtlpPreviewSpan,
    OtlpPreviewSummary,
)
from entroping.core.readiness.observability_adapter_readiness import (
    OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION,
    ObservabilityAdapterBoundaryControl,
    ObservabilityAdapterNextAction,
    ObservabilityAdapterReadinessPacket,
    ObservabilityAdapterReadinessRow,
    ObservabilityAdapterReadinessSource,
    ObservabilityAdapterReadinessSummary,
)
from entroping.core.structured_diagnostics import (
    STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
    StructuredDiagnosticAttribute,
    StructuredDiagnosticEvent,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "docs" / "technical" / "report-schemas"


def test_structured_diagnostics_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "diagnostics.v1.schema.json").read_text())
    event = StructuredDiagnosticEvent(
        timestamp="2026-06-19T00:00:00+00:00",
        component="run",
        operation="hurl.timeout",
        severity="warning",
        code="hurl_timeout",
        summary="Hurl subprocess timed out.",
        attributes=(
            StructuredDiagnosticAttribute(name="duration_ms", value=125),
            StructuredDiagnosticAttribute(name="artifact_path", value="reports/run-latest.json"),
        ),
    )

    payload = event.model_dump(mode="json")

    assert payload == {
        "schema_version": "entroping.diagnostics.v1",
        "timestamp": "2026-06-19T00:00:00+00:00",
        "component": "run",
        "operation": "hurl.timeout",
        "severity": "warning",
        "code": "hurl_timeout",
        "summary": "Hurl subprocess timed out.",
        "attributes": [
            {"name": "duration_ms", "value": 125},
            {"name": "artifact_path", "value": "reports/run-latest.json"},
        ],
    }
    assert STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION == "entroping.diagnostics.v1"
    assert schema["properties"]["schema_version"]["const"] == (
        STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION
    )
    assert schema["properties"]["severity"]["enum"] == [
        "debug",
        "info",
        "warning",
        "error",
    ]
    assert schema["$defs"]["attribute"]["properties"]["value"]["type"] == [
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    ]


def test_observability_packet_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "observability-packet.v1.schema.json").read_text())
    packet = ObservabilityPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=ObservabilitySummary(
            status="ready",
            severity="blocker",
            sources_total=2,
            sources_present=2,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            events_total=1,
            debug_events=0,
            info_events=0,
            warning_events=0,
            error_events=1,
        ),
        runtime=ObservabilityRuntimeSummary(
            status="attention",
            findings=2,
            evidence_links=3,
            failed_gate_ids=1,
        ),
        sources=(
            ObservabilitySource(
                id="diagnostics",
                label="Structured diagnostics",
                path=".entroping/latest-diagnostics.jsonl",
                state="present",
                schema_version="entroping.diagnostics.v1",
                sha256="a" * 64,
                summary="1 diagnostic events.",
            ),
            ObservabilitySource(
                id="runtime_card",
                label="Runtime card",
                path="reports/runtime-card.json",
                state="present",
                schema_version="entroping.runtime-card.v1",
                sha256="b" * 64,
                summary="attention runtime evidence",
            ),
        ),
        events=(
            ObservabilityEventSummary(
                component="run",
                operation="execute",
                severity="error",
                code="hurl.timeout",
                summary="Hurl timeout recorded.",
            ),
        ),
        components=(
            ObservabilityComponentSummary(
                component="run",
                events_total=1,
                debug_events=0,
                info_events=0,
                warning_events=0,
                error_events=1,
                operations=("execute",),
                codes=("hurl.timeout",),
            ),
        ),
        messages=(
            ObservabilityMessage(
                surface="opentelemetry",
                label="OpenTelemetry",
                severity="blocker",
                title="Entroping observability signals need attention",
                body=(
                    "Runtime status attention; 1 diagnostic events; "
                    "1 errors; 0 warnings; 2/2 sources present."
                ),
                next_action="Use this packet as value-free OTLP adapter input.",
                artifact_paths=(
                    "reports/observability-packet.json",
                    ".entroping/latest-diagnostics.jsonl",
                    "reports/runtime-card.json",
                ),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert OBSERVABILITY_PACKET_SCHEMA_VERSION == "entroping.observability-packet.v1"
    assert payload == {
        "schema_version": "entroping.observability-packet.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "severity": "blocker",
            "sources_total": 2,
            "sources_present": 2,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "events_total": 1,
            "debug_events": 0,
            "info_events": 0,
            "warning_events": 0,
            "error_events": 1,
        },
        "runtime": {
            "status": "attention",
            "findings": 2,
            "evidence_links": 3,
            "failed_gate_ids": 1,
        },
        "sources": [
            {
                "id": "diagnostics",
                "label": "Structured diagnostics",
                "path": ".entroping/latest-diagnostics.jsonl",
                "state": "present",
                "schema_version": "entroping.diagnostics.v1",
                "sha256": "a" * 64,
                "summary": "1 diagnostic events.",
            },
            {
                "id": "runtime_card",
                "label": "Runtime card",
                "path": "reports/runtime-card.json",
                "state": "present",
                "schema_version": "entroping.runtime-card.v1",
                "sha256": "b" * 64,
                "summary": "attention runtime evidence",
            },
        ],
        "events": [
            {
                "component": "run",
                "operation": "execute",
                "severity": "error",
                "code": "hurl.timeout",
                "summary": "Hurl timeout recorded.",
            }
        ],
        "components": [
            {
                "component": "run",
                "events_total": 1,
                "debug_events": 0,
                "info_events": 0,
                "warning_events": 0,
                "error_events": 1,
                "operations": ["execute"],
                "codes": ["hurl.timeout"],
            }
        ],
        "messages": [
            {
                "surface": "opentelemetry",
                "label": "OpenTelemetry",
                "severity": "blocker",
                "title": "Entroping observability signals need attention",
                "body": (
                    "Runtime status attention; 1 diagnostic events; "
                    "1 errors; 0 warnings; 2/2 sources present."
                ),
                "next_action": "Use this packet as value-free OTLP adapter input.",
                "artifact_paths": [
                    "reports/observability-packet.json",
                    ".entroping/latest-diagnostics.jsonl",
                    "reports/runtime-card.json",
                ],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.observability-packet.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["summary"]["properties"]["severity"]["enum"] == [
        "info",
        "attention",
        "blocker",
    ]
    assert schema["$defs"]["message"]["properties"]["surface"]["enum"] == [
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic",
    ]


def test_otel_mapping_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "otel-mapping.v1.schema.json").read_text())
    packet = OtelMappingPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=OtelMappingSummary(
            status="ready",
            severity="attention",
            sources_total=4,
            sources_present=4,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            mappings_total=1,
            resource_mappings=1,
            log_mappings=0,
            metric_mappings=0,
            trace_mappings=0,
            boundary_controls=1,
        ),
        sources=(
            OtelMappingSource(
                id="observability_packet",
                label="Observability packet",
                path="reports/observability-packet.json",
                state="present",
                schema_version="entroping.observability-packet.v1",
                sha256="a" * 64,
                summary="ready observability, attention severity, 3 events",
            ),
        ),
        mappings=(
            OtelAttributeMapping(
                signal="resource",
                attribute="service.name",
                requirement="required",
                value_kind="identifier",
                source_ids=("observability_packet", "runtime_card"),
                summary="Future OTLP resources can identify the sanitized project/service name.",
                forbidden_fields=("raw_urls", "headers"),
            ),
        ),
        boundary_controls=(
            OtelBoundaryControl(
                id="no_otlp_export",
                state="active",
                summary="This command writes local mapping evidence only; it does not export OTLP.",
            ),
        ),
        next_actions=(
            OtelMappingNextAction(
                priority="low",
                action="Use this packet as the value-free contract for a future OTLP adapter.",
                source_ids=("observability_packet", "runtime_card"),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert OTEL_MAPPING_SCHEMA_VERSION == "entroping.otel-mapping.v1"
    assert payload == {
        "schema_version": "entroping.otel-mapping.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "severity": "attention",
            "sources_total": 4,
            "sources_present": 4,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "mappings_total": 1,
            "resource_mappings": 1,
            "log_mappings": 0,
            "metric_mappings": 0,
            "trace_mappings": 0,
            "boundary_controls": 1,
        },
        "sources": [
            {
                "id": "observability_packet",
                "label": "Observability packet",
                "path": "reports/observability-packet.json",
                "state": "present",
                "schema_version": "entroping.observability-packet.v1",
                "sha256": "a" * 64,
                "summary": "ready observability, attention severity, 3 events",
            }
        ],
        "mappings": [
            {
                "signal": "resource",
                "attribute": "service.name",
                "requirement": "required",
                "value_kind": "identifier",
                "source_ids": ["observability_packet", "runtime_card"],
                "summary": (
                    "Future OTLP resources can identify the sanitized project/service name."
                ),
                "forbidden_fields": ["raw_urls", "headers"],
            }
        ],
        "boundary_controls": [
            {
                "id": "no_otlp_export",
                "state": "active",
                "summary": (
                    "This command writes local mapping evidence only; it does not export OTLP."
                ),
            }
        ],
        "next_actions": [
            {
                "priority": "low",
                "action": (
                    "Use this packet as the value-free contract for a future OTLP adapter."
                ),
                "source_ids": ["observability_packet", "runtime_card"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.otel-mapping.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "observability_packet",
        "runtime_card",
        "test_pyramid",
        "external_test_evidence",
    ]
    assert schema["$defs"]["signal"]["enum"] == ["resource", "log", "metric", "trace"]


def test_otlp_preview_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "otlp-preview.v1.schema.json").read_text())
    packet = OtlpPreviewPacket(
        generated_at="2026-07-04T00:00:00+00:00",
        summary=OtlpPreviewSummary(
            status="partial",
            severity="attention",
            sources_total=3,
            sources_present=1,
            sources_missing=2,
            sources_invalid=0,
            sources_unsafe=0,
            resource_attributes_total=1,
            log_records_total=1,
            metrics_total=1,
            spans_total=1,
        ),
        sources=(
            OtlpPreviewSource(
                id="run_report",
                label="Run report",
                path="reports/run-latest.json",
                state="present",
                schema_version="entroping.run-report.v1",
                sha256="a" * 64,
                summary="fail run, 2 total, 1 passed, 1 failed",
            ),
        ),
        fixture=OtlpPreviewFixture(
            resource_attributes=(
                OtlpPreviewAttribute(
                    key="service.name",
                    value_kind="string",
                    value="entroping-local-preview",
                    source_ids=("run_report",),
                ),
            ),
            log_records=(
                OtlpPreviewLogRecord(
                    name="entroping.run.summary",
                    severity_text="attention",
                    attributes=(),
                ),
            ),
            metrics=(
                OtlpPreviewMetric(
                    name="entroping.tests.total",
                    unit="1",
                    value_kind="sum",
                    value=2,
                ),
            ),
            spans=(
                OtlpPreviewSpan(
                    name="entroping.run",
                    status_code="ERROR",
                    attributes=(),
                ),
            ),
        ),
        boundary_controls=(
            OtlpPreviewBoundaryControl(
                id="local-only",
                summary="Writes a local preview file only.",
            ),
        ),
        next_actions=(
            OtlpPreviewNextAction(
                priority="medium",
                action="Generate reports/otel-mapping.json.",
                source_ids=("otel_mapping",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert OTLP_PREVIEW_SCHEMA_VERSION == "entroping.otlp-preview.v1"
    assert payload == {
        "schema_version": "entroping.otlp-preview.v1",
        "generated_at": "2026-07-04T00:00:00+00:00",
        "summary": {
            "status": "partial",
            "severity": "attention",
            "sources_total": 3,
            "sources_present": 1,
            "sources_missing": 2,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "resource_attributes_total": 1,
            "log_records_total": 1,
            "metrics_total": 1,
            "spans_total": 1,
        },
        "sources": [
            {
                "id": "run_report",
                "label": "Run report",
                "path": "reports/run-latest.json",
                "state": "present",
                "schema_version": "entroping.run-report.v1",
                "sha256": "a" * 64,
                "summary": "fail run, 2 total, 1 passed, 1 failed",
            }
        ],
        "fixture": {
            "transport": "otlp-json-preview",
            "network_policy": "local-only-no-export",
            "resource_attributes": [
                {
                    "key": "service.name",
                    "value_kind": "string",
                    "value": "entroping-local-preview",
                    "source_ids": ["run_report"],
                }
            ],
            "log_records": [
                {
                    "name": "entroping.run.summary",
                    "severity_text": "attention",
                    "attributes": [],
                }
            ],
            "metrics": [
                {
                    "name": "entroping.tests.total",
                    "unit": "1",
                    "value_kind": "sum",
                    "value": 2,
                    "attributes": [],
                }
            ],
            "spans": [
                {
                    "name": "entroping.run",
                    "status_code": "ERROR",
                    "attributes": [],
                }
            ],
        },
        "boundary_controls": [
            {
                "id": "local-only",
                "summary": "Writes a local preview file only.",
            }
        ],
        "next_actions": [
            {
                "priority": "medium",
                "action": "Generate reports/otel-mapping.json.",
                "source_ids": ["otel_mapping"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.otlp-preview.v1"
    assert schema["properties"]["fixture"]["$ref"] == "#/$defs/OtlpPreviewFixture"
    assert schema["$defs"]["OtlpPreviewSummary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["OtlpPreviewSource"]["properties"]["state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert (
        schema["$defs"]["OtlpPreviewFixture"]["properties"]["network_policy"]["const"]
        == "local-only-no-export"
    )


def test_observability_adapter_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads(
        (SCHEMA_DIR / "observability-adapter-readiness.v1.schema.json").read_text()
    )
    packet = ObservabilityAdapterReadinessPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=ObservabilityAdapterReadinessSummary(
            status="ready",
            severity="attention",
            sources_total=4,
            sources_present=4,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            adapters_total=1,
            adapters_ready=1,
            adapters_attention=0,
            adapters_blocked=0,
            boundary_controls=1,
        ),
        sources=(
            ObservabilityAdapterReadinessSource(
                id="observability_packet",
                label="Observability packet",
                path="reports/observability-packet.json",
                state="present",
                schema_version="entroping.observability-packet.v1",
                sha256="a" * 64,
                summary="ready observability, attention severity, 3 events",
            ),
        ),
        adapters=(
            ObservabilityAdapterReadinessRow(
                id="opentelemetry",
                label="OpenTelemetry",
                status="ready",
                required_source_ids=("observability_packet", "otel_mapping"),
                optional_source_ids=("evidence_index", "runtime_card"),
                summary="Required value-free evidence is present for adapter design.",
                next_action=(
                    "Use the mapping packet as the value-free contract for an OTLP adapter."
                ),
                forbidden_fields=("raw_urls", "dashboard_payloads"),
            ),
        ),
        boundary_controls=(
            ObservabilityAdapterBoundaryControl(
                id="no_vendor_api",
                state="active",
                summary="This command does not call vendor APIs.",
            ),
        ),
        next_actions=(
            ObservabilityAdapterNextAction(
                priority="low",
                action="Use this packet as the local value-free adapter readiness contract.",
                source_ids=("observability_packet", "otel_mapping"),
                adapter_ids=("opentelemetry",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert OBSERVABILITY_ADAPTER_READINESS_SCHEMA_VERSION == (
        "entroping.observability-adapter-readiness.v1"
    )
    assert payload == {
        "schema_version": "entroping.observability-adapter-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "severity": "attention",
            "sources_total": 4,
            "sources_present": 4,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "adapters_total": 1,
            "adapters_ready": 1,
            "adapters_attention": 0,
            "adapters_blocked": 0,
            "boundary_controls": 1,
        },
        "sources": [
            {
                "id": "observability_packet",
                "label": "Observability packet",
                "path": "reports/observability-packet.json",
                "state": "present",
                "schema_version": "entroping.observability-packet.v1",
                "sha256": "a" * 64,
                "summary": "ready observability, attention severity, 3 events",
            }
        ],
        "adapters": [
            {
                "id": "opentelemetry",
                "label": "OpenTelemetry",
                "status": "ready",
                "required_source_ids": ["observability_packet", "otel_mapping"],
                "optional_source_ids": ["evidence_index", "runtime_card"],
                "summary": "Required value-free evidence is present for adapter design.",
                "next_action": (
                    "Use the mapping packet as the value-free contract for an OTLP adapter."
                ),
                "forbidden_fields": ["raw_urls", "dashboard_payloads"],
            }
        ],
        "boundary_controls": [
            {
                "id": "no_vendor_api",
                "state": "active",
                "summary": "This command does not call vendor APIs.",
            }
        ],
        "next_actions": [
            {
                "priority": "low",
                "action": (
                    "Use this packet as the local value-free adapter readiness contract."
                ),
                "source_ids": ["observability_packet", "otel_mapping"],
                "adapter_ids": ["opentelemetry"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.observability-adapter-readiness.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["source_id"]["enum"] == [
        "observability_packet",
        "otel_mapping",
        "evidence_index",
        "runtime_card",
    ]
    assert schema["$defs"]["adapter_id"]["enum"] == [
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic",
    ]
