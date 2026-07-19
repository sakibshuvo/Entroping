"""Versioned report schema contract tests."""

import json
from pathlib import Path

from entroping.core.evidence.api_inventory import (
    API_INVENTORY_SCHEMA_VERSION,
    ApiInventoryPacket,
    ApiInventorySource,
    ApiInventoryStyleSummary,
    ApiInventorySummary,
)
from entroping.core.evidence.evidence_index_report import (
    EVIDENCE_INDEX_SCHEMA_VERSION,
    EvidenceIndexArtifact,
    EvidenceIndexPacket,
    EvidenceIndexSummary,
)
from entroping.core.plan.qa_brain_eval_plan import (
    QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION,
    QaBrainEvalCase,
    QaBrainEvalPlanNextAction,
    QaBrainEvalPlanPacket,
    QaBrainEvalPlanSummary,
)
from entroping.core.plan.qa_brain_fine_tune_readiness import (
    QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION,
    QaBrainFineTuneReadinessNextAction,
    QaBrainFineTuneReadinessPacket,
    QaBrainFineTuneReadinessRow,
    QaBrainFineTuneReadinessSummary,
)
from entroping.core.plan.qa_brain_model_packaging_plan import (
    QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION,
    QaBrainModelPackagingPlanNextAction,
    QaBrainModelPackagingPlanPacket,
    QaBrainModelPackagingPlanRow,
    QaBrainModelPackagingPlanSummary,
)
from entroping.core.plan.qa_brain_prompt_plan import (
    QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION,
    QaBrainPromptPlanNextAction,
    QaBrainPromptPlanPacket,
    QaBrainPromptPlanRow,
    QaBrainPromptPlanSummary,
)
from entroping.core.plan.qa_brain_repair_plan import (
    QA_BRAIN_REPAIR_PLAN_SCHEMA_VERSION,
    QaBrainRepairPlanNextAction,
    QaBrainRepairPlanPacket,
    QaBrainRepairPlanRow,
    QaBrainRepairPlanSource,
    QaBrainRepairPlanSummary,
    QaBrainRepairProposalDryRunArtifactStatus,
    QaBrainRepairProposalDryRunChecklistItem,
)
from entroping.core.plan.qa_brain_retrieval_plan import (
    QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
    QaBrainRetrievalPlanNextAction,
    QaBrainRetrievalPlanPacket,
    QaBrainRetrievalPlanRow,
    QaBrainRetrievalPlanSummary,
)
from entroping.core.plan.qa_brain_routing_plan import (
    QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION,
    QaBrainRepairAcceptanceGate,
    QaBrainRoutingPlanNextAction,
    QaBrainRoutingPlanPacket,
    QaBrainRoutingPlanRow,
    QaBrainRoutingPlanSummary,
)
from entroping.core.plan.qa_brain_seed import (
    QA_BRAIN_SEED_SCHEMA_VERSION,
    QaBrainEvalSlice,
    QaBrainNextAction,
    QaBrainSeedPacket,
    QaBrainSeedSource,
    QaBrainSeedSummary,
)
from entroping.core.readiness.mutation_readiness import (
    MUTATION_READINESS_SCHEMA_VERSION,
    MutationReadinessCandidate,
    MutationReadinessPacket,
    MutationReadinessSeededFuzzCandidate,
    MutationReadinessSource,
    MutationReadinessSummary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "docs" / "technical" / "report-schemas"


def test_api_inventory_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "api-inventory.v1.schema.json").read_text())
    packet = ApiInventoryPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=ApiInventorySummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            styles_total=1,
            hurl_tests_total=0,
            operations_total=2,
        ),
        sources=(
            ApiInventorySource(
                kind="configured_openapi",
                style="rest_openapi",
                path="openapi.yaml",
                state="present",
                sha256="a" * 64,
                tags=(),
                operations=2,
                summary="2 OpenAPI operations.",
            ),
        ),
        styles=(
            ApiInventoryStyleSummary(
                style="rest_openapi",
                label="REST/OpenAPI",
                sources=1,
                hurl_tests=0,
                operations=2,
                tags=(),
                source_paths=("openapi.yaml",),
                next_action="Use Architect OpenAPI generation and audit reports.",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert API_INVENTORY_SCHEMA_VERSION == "entroping.api-inventory.v1"
    assert payload == {
        "schema_version": "entroping.api-inventory.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "styles_total": 1,
            "hurl_tests_total": 0,
            "operations_total": 2,
        },
        "sources": [
            {
                "kind": "configured_openapi",
                "style": "rest_openapi",
                "path": "openapi.yaml",
                "state": "present",
                "sha256": "a" * 64,
                "tags": [],
                "operations": 2,
                "summary": "2 OpenAPI operations.",
            }
        ],
        "styles": [
            {
                "style": "rest_openapi",
                "label": "REST/OpenAPI",
                "sources": 1,
                "hurl_tests": 0,
                "operations": 2,
                "tags": [],
                "source_paths": ["openapi.yaml"],
                "next_action": "Use Architect OpenAPI generation and audit reports.",
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.api-inventory.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["api_style"]["enum"] == [
        "rest_openapi",
        "graphql",
        "soap_xml",
        "grpc_proto",
        "asyncapi",
        "webhook_event",
        "websocket_realtime",
        "bruno_collection",
        "unknown_http",
    ]


def test_mutation_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "mutation-readiness.v1.schema.json").read_text())
    packet = MutationReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=MutationReadinessSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            generated_tests=1,
            negative_tests=1,
            security_tests=1,
            assertions_total=2,
            seed_metadata_tests=1,
            candidate_categories_total=1,
            seeded_fuzz_candidates_total=1,
            optional_reports_present=0,
            optional_reports_invalid=0,
            optional_reports_unsafe=0,
        ),
        sources=(
            MutationReadinessSource(
                kind="generated_hurl",
                path="tests/generated/security/auth.hurl",
                state="present",
                schema_version=None,
                tags=("generated", "security"),
                candidate_categories=("auth",),
                assertions=2,
                seed_metadata=True,
                summary="1 generated Hurl exchanges.",
            ),
        ),
        candidates=(
            MutationReadinessCandidate(
                category="auth",
                label="Auth/security mutation",
                tests=1,
                source_paths=("tests/generated/security/auth.hurl",),
                next_action="Keep auth/security cases explicit before future mutation execution.",
            ),
        ),
        seeded_fuzz_candidates=(
            MutationReadinessSeededFuzzCandidate(
                id="seeded-fuzz:auth:tests/generated/security/auth.hurl",
                category="auth",
                source_path="tests/generated/security/auth.hurl",
                assertions=2,
                seed_metadata=True,
                next_action=(
                    "Review auth/security mutation candidate before future seeded "
                    "fuzz execution."
                ),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert MUTATION_READINESS_SCHEMA_VERSION == "entroping.mutation-readiness.v1"
    assert payload == {
        "schema_version": "entroping.mutation-readiness.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "generated_tests": 1,
            "negative_tests": 1,
            "security_tests": 1,
            "assertions_total": 2,
            "seed_metadata_tests": 1,
            "candidate_categories_total": 1,
            "seeded_fuzz_candidates_total": 1,
            "category_coverage": [],
            "optional_reports_present": 0,
            "optional_reports_invalid": 0,
            "optional_reports_unsafe": 0,
        },
        "sources": [
            {
                "kind": "generated_hurl",
                "path": "tests/generated/security/auth.hurl",
                "state": "present",
                "schema_version": None,
                "tags": ["generated", "security"],
                "candidate_categories": ["auth"],
                "assertions": 2,
                "seed_metadata": True,
                "summary": "1 generated Hurl exchanges.",
            }
        ],
        "candidates": [
            {
                "category": "auth",
                "label": "Auth/security mutation",
                "tests": 1,
                "source_paths": ["tests/generated/security/auth.hurl"],
                "next_action": (
                    "Keep auth/security cases explicit before future mutation execution."
                ),
            }
        ],
        "seeded_fuzz_candidates": [
            {
                "id": "seeded-fuzz:auth:tests/generated/security/auth.hurl",
                "category": "auth",
                "source_path": "tests/generated/security/auth.hurl",
                "assertions": 2,
                "seed_metadata": True,
                "next_action": (
                    "Review auth/security mutation candidate before future seeded "
                    "fuzz execution."
                ),
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.mutation-readiness.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["seeded_fuzz_candidates"]["items"]["$ref"] == (
        "#/$defs/seeded_fuzz_candidate"
    )
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["summary"]["properties"]["category_coverage"] == {
        "type": "array",
        "items": {"$ref": "#/$defs/category_coverage"},
    }
    assert schema["$defs"]["category_coverage"]["required"] == [
        "category",
        "label",
        "candidate_tests",
        "seeded_tests",
        "missing_seed_tests",
    ]
    assert schema["$defs"]["candidate_category"]["enum"] == [
        "status_code",
        "schema",
        "auth",
        "latency",
        "request_shape",
        "response_shape",
    ]


def test_evidence_index_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "evidence-index.v1.schema.json").read_text())
    packet = EvidenceIndexPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=EvidenceIndexSummary(
            status="partial",
            artifacts_total=2,
            artifacts_present=1,
            artifacts_missing=0,
            artifacts_invalid=1,
            artifacts_unsafe=0,
        ),
        artifacts=(
            EvidenceIndexArtifact(
                id="run-json",
                label="Run JSON",
                path="reports/run-latest.json",
                state="present",
                schema_version="entroping.run-report.v1",
                summary="1 total, 1 passed, 0 failed",
            ),
            EvidenceIndexArtifact(
                id="drift-json",
                label="Drift JSON",
                path="reports/drift.json",
                state="invalid",
                schema_version=None,
                summary="invalid JSON",
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert EVIDENCE_INDEX_SCHEMA_VERSION == "entroping.evidence-index.v1"
    assert payload == {
        "schema_version": "entroping.evidence-index.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "artifacts_total": 2,
            "artifacts_present": 1,
            "artifacts_missing": 0,
            "artifacts_invalid": 1,
            "artifacts_unsafe": 0,
        },
        "artifacts": [
            {
                "id": "run-json",
                "label": "Run JSON",
                "path": "reports/run-latest.json",
                "state": "present",
                "schema_version": "entroping.run-report.v1",
                "summary": "1 total, 1 passed, 0 failed",
            },
            {
                "id": "drift-json",
                "label": "Drift JSON",
                "path": "reports/drift.json",
                "state": "invalid",
                "schema_version": None,
                "summary": "invalid JSON",
            },
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.evidence-index.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["summary"]["properties"]["status"]["enum"] == [
        "ready",
        "partial",
        "insufficient",
    ]
    assert schema["$defs"]["artifact_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]


def test_qa_brain_seed_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-seed.v1.schema.json").read_text())
    packet = QaBrainSeedPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        summary=QaBrainSeedSummary(
            status="partial",
            sources_total=2,
            sources_present=1,
            sources_missing=0,
            sources_invalid=1,
            sources_unsafe=0,
            eval_slices_total=1,
            eval_slices_ready=0,
            next_actions_total=1,
        ),
        sources=(
            QaBrainSeedSource(
                id="test-quality-json",
                label="Generated-Test Quality JSON",
                path="reports/test-quality.json",
                state="present",
                schema_version="entroping.test-quality-report.v1",
                category="generated_test_quality",
                eval_slices=("weak_test_detection", "unsafe_generated_hurl"),
                summary="warn, score 80, 2 generated, 1 findings",
            ),
            QaBrainSeedSource(
                id="drift-json",
                label="Drift JSON",
                path="reports/drift.json",
                state="invalid",
                schema_version=None,
                category="api_inventory",
                eval_slices=("api_drift_reasoning", "bogus_evidence"),
                summary="invalid JSON",
            ),
        ),
        eval_slices=(
            QaBrainEvalSlice(
                id="weak_test_detection",
                label="Weak-test detection",
                status="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                next_action="Review generated-test quality evidence before QA-brain evals.",
            ),
        ),
        next_actions=(
            QaBrainNextAction(
                priority="medium",
                action="Add or repair value-free local evidence for weak-test detection.",
                source_ids=("test-quality-json",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_SEED_SCHEMA_VERSION == "entroping.qa-brain-seed.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-seed.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "sources_total": 2,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 1,
            "sources_unsafe": 0,
            "eval_slices_total": 1,
            "eval_slices_ready": 0,
            "next_actions_total": 1,
        },
        "sources": [
            {
                "id": "test-quality-json",
                "label": "Generated-Test Quality JSON",
                "path": "reports/test-quality.json",
                "state": "present",
                "schema_version": "entroping.test-quality-report.v1",
                "category": "generated_test_quality",
                "eval_slices": ["weak_test_detection", "unsafe_generated_hurl"],
                "summary": "warn, score 80, 2 generated, 1 findings",
            },
            {
                "id": "drift-json",
                "label": "Drift JSON",
                "path": "reports/drift.json",
                "state": "invalid",
                "schema_version": None,
                "category": "api_inventory",
                "eval_slices": ["api_drift_reasoning", "bogus_evidence"],
                "summary": "invalid JSON",
            },
        ],
        "eval_slices": [
            {
                "id": "weak_test_detection",
                "label": "Weak-test detection",
                "status": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "next_action": "Review generated-test quality evidence before QA-brain evals.",
            }
        ],
        "next_actions": [
            {
                "priority": "medium",
                "action": "Add or repair value-free local evidence for weak-test detection.",
                "source_ids": ["test-quality-json"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == "entroping.qa-brain-seed.v1"
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["seed_category"]["enum"] == [
        "runtime_governance",
        "policy_governance",
        "generated_test_quality",
        "test_pyramid",
        "api_inventory",
        "mutation_fuzz",
        "redaction_safety",
        "cross_surface_handoff",
        "agent_review",
        "review_signal",
        "generic_evidence",
    ]
    assert schema["$defs"]["eval_slice_id"]["enum"] == [
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    ]


def test_qa_brain_eval_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-eval-plan.v1.schema.json").read_text())
    packet = QaBrainEvalPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        seed_schema_version="entroping.qa-brain-seed.v1",
        summary=QaBrainEvalPlanSummary(
            status="partial",
            cases_total=1,
            cases_ready=0,
            cases_missing=0,
            cases_attention=1,
            next_actions_total=1,
        ),
        cases=(
            QaBrainEvalCase(
                id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                input_contract="Value-free generated-test quality evidence rows.",
                output_contract="schema-valid QA critique result",
                acceptance_signal="Detect weak tests without using raw report contents.",
                negative_controls=("Do not reward generic confidence.",),
                next_action="Review invalid evidence before eval execution.",
            ),
        ),
        next_actions=(
            QaBrainEvalPlanNextAction(
                priority="high",
                action="Repair evidence before weak-test detection evals.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION == "entroping.qa-brain-eval-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-eval-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "seed_schema_version": "entroping.qa-brain-seed.v1",
        "summary": {
            "status": "partial",
            "cases_total": 1,
            "cases_ready": 0,
            "cases_missing": 0,
            "cases_attention": 1,
            "next_actions_total": 1,
        },
        "cases": [
            {
                "id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "input_contract": "Value-free generated-test quality evidence rows.",
                "output_contract": "schema-valid QA critique result",
                "acceptance_signal": "Detect weak tests without using raw report contents.",
                "negative_controls": ["Do not reward generic confidence."],
                "next_action": "Review invalid evidence before eval execution.",
                "evidence_catalog": {
                    "expected_sources_total": 0,
                    "sources_present": 0,
                    "sources_missing": 0,
                    "sources_invalid": 0,
                    "sources_unsafe": 0,
                    "categories": [],
                    "missing_reasons": [],
                    "sources": [],
                },
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair evidence before weak-test detection evals.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.qa-brain-eval-plan.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["eval_case"]["properties"]["evidence_catalog"]["$ref"] == (
        "#/$defs/evidence_catalog"
    )
    assert schema["$defs"]["catalog_source_state"]["enum"] == [
        "present",
        "missing",
        "invalid",
        "unsafe",
    ]
    assert schema["$defs"]["missing_reason"]["enum"] == [
        "artifact_missing",
        "artifact_invalid",
        "artifact_unsafe",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]
    assert schema["$defs"]["eval_slice_id"]["enum"] == [
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    ]


def test_qa_brain_retrieval_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-retrieval-plan.v1.schema.json").read_text())
    packet = QaBrainRetrievalPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
        summary=QaBrainRetrievalPlanSummary(
            status="partial",
            plans_total=1,
            plans_ready=0,
            plans_missing=0,
            plans_attention=1,
            next_actions_total=1,
        ),
        retrieval_plans=(
            QaBrainRetrievalPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                retrieval_category="test_quality",
                retrieval_intent="Find weak generated-test evidence by stable IDs.",
                allowed_fields=("schema_version", "artifact_id"),
                forbidden_fields=("request_body", "response_body"),
                query_hints=("Find weak-test evidence using test-quality-json.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Repair local evidence before retrieval indexing.",
            ),
        ),
        next_actions=(
            QaBrainRetrievalPlanNextAction(
                priority="high",
                action="Repair retrieval evidence before weak-test detection indexing.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION == "entroping.qa-brain-retrieval-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-retrieval-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "eval_plan_schema_version": "entroping.qa-brain-eval-plan.v1",
        "summary": {
            "status": "partial",
            "plans_total": 1,
            "plans_ready": 0,
            "plans_missing": 0,
            "plans_attention": 1,
            "next_actions_total": 1,
        },
        "retrieval_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "retrieval_category": "test_quality",
                "retrieval_intent": "Find weak generated-test evidence by stable IDs.",
                "allowed_fields": ["schema_version", "artifact_id"],
                "forbidden_fields": ["request_body", "response_body"],
                "query_hints": ["Find weak-test evidence using test-quality-json."],
                "safety_notes": ["Use value-free local metadata only."],
                "next_action": "Repair local evidence before retrieval indexing.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair retrieval evidence before weak-test detection indexing.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.qa-brain-retrieval-plan.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["retrieval_category"]["enum"] == [
        "test_quality",
        "policy_governance",
        "generated_hurl_safety",
        "evidence_integrity",
        "redaction_safety",
        "api_drift",
        "mutation_fuzz",
        "cross_surface_handoff",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_prompt_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-prompt-plan.v1.schema.json").read_text())
    packet = QaBrainPromptPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        retrieval_plan_schema_version="entroping.qa-brain-retrieval-plan.v1",
        summary=QaBrainPromptPlanSummary(
            status="partial",
            prompts_total=1,
            prompts_ready=0,
            prompts_missing=0,
            prompts_attention=1,
            next_actions_total=1,
        ),
        prompt_plans=(
            QaBrainPromptPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                retrieval_category="test_quality",
                prompt_objective="Critique generated-test quality using stable IDs.",
                prompt_inputs_allowed=("case_id", "artifact_id"),
                prompt_inputs_forbidden=("request_body", "response_body"),
                expected_output_fields=("case_id", "risk_level"),
                deterministic_acceptance_signals=("Evidence IDs are present.",),
                negative_controls=("Do not reward generic confidence.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Repair local evidence before prompt design.",
            ),
        ),
        next_actions=(
            QaBrainPromptPlanNextAction(
                priority="high",
                action="Repair prompt-plan evidence before weak-test detection prompts.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION == "entroping.qa-brain-prompt-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-prompt-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "retrieval_plan_schema_version": "entroping.qa-brain-retrieval-plan.v1",
        "summary": {
            "status": "partial",
            "prompts_total": 1,
            "prompts_ready": 0,
            "prompts_missing": 0,
            "prompts_attention": 1,
            "next_actions_total": 1,
        },
        "prompt_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "retrieval_category": "test_quality",
                "prompt_objective": "Critique generated-test quality using stable IDs.",
                "prompt_inputs_allowed": ["case_id", "artifact_id"],
                "prompt_inputs_forbidden": ["request_body", "response_body"],
                "expected_output_fields": ["case_id", "risk_level"],
                "deterministic_acceptance_signals": ["Evidence IDs are present."],
                "negative_controls": ["Do not reward generic confidence."],
                "safety_notes": ["Use value-free local metadata only."],
                "next_action": "Repair local evidence before prompt design.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair prompt-plan evidence before weak-test detection prompts.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.qa-brain-prompt-plan.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["$defs"]["retrieval_category"]["enum"] == [
        "test_quality",
        "policy_governance",
        "generated_hurl_safety",
        "evidence_integrity",
        "redaction_safety",
        "api_drift",
        "mutation_fuzz",
        "cross_surface_handoff",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_fine_tune_readiness_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-fine-tune-readiness.v1.schema.json").read_text())
    packet = QaBrainFineTuneReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        prompt_plan_schema_version="entroping.qa-brain-prompt-plan.v1",
        summary=QaBrainFineTuneReadinessSummary(
            status="partial",
            readiness_total=1,
            readiness_ready=0,
            readiness_missing=0,
            readiness_attention=1,
            blockers_total=1,
            next_actions_total=1,
        ),
        readiness_rows=(
            QaBrainFineTuneReadinessRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                readiness_stage="needs_repair",
                evidence_coverage="Repair source evidence before dataset design.",
                prompt_plan_completeness="Prompt-plan metadata is complete.",
                safety_boundary="Provider-free metadata only.",
                eval_case_coverage="Covers weak-test detection.",
                redaction_boundary="No secrets, headers, cookies, tokens, or bodies.",
                deterministic_acceptance="Evidence IDs are present.",
                blockers=("Repair invalid or unsafe prompt-plan evidence.",),
                next_action="Repair prompt-plan evidence before fine-tune design.",
            ),
        ),
        next_actions=(
            QaBrainFineTuneReadinessNextAction(
                priority="high",
                action="Repair fine-tune readiness evidence before weak-test detection.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert (
        QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION == "entroping.qa-brain-fine-tune-readiness.v1"
    )
    assert payload == {
        "schema_version": "entroping.qa-brain-fine-tune-readiness.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "prompt_plan_schema_version": "entroping.qa-brain-prompt-plan.v1",
        "summary": {
            "status": "partial",
            "readiness_total": 1,
            "readiness_ready": 0,
            "readiness_missing": 0,
            "readiness_attention": 1,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "readiness_rows": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "readiness_stage": "needs_repair",
                "evidence_coverage": "Repair source evidence before dataset design.",
                "prompt_plan_completeness": "Prompt-plan metadata is complete.",
                "safety_boundary": "Provider-free metadata only.",
                "eval_case_coverage": "Covers weak-test detection.",
                "redaction_boundary": "No secrets, headers, cookies, tokens, or bodies.",
                "deterministic_acceptance": "Evidence IDs are present.",
                "blockers": ["Repair invalid or unsafe prompt-plan evidence."],
                "next_action": "Repair prompt-plan evidence before fine-tune design.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair fine-tune readiness evidence before weak-test detection.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.qa-brain-fine-tune-readiness.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["prompt_plan_schema_version"]["const"] == (
        "entroping.qa-brain-prompt-plan.v1"
    )
    assert schema["$defs"]["readiness_stage"]["enum"] == [
        "metadata_ready",
        "needs_evidence",
        "needs_repair",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_model_packaging_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-model-packaging-plan.v1.schema.json").read_text())
    packet = QaBrainModelPackagingPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        fine_tune_readiness_schema_version=("entroping.qa-brain-fine-tune-readiness.v1"),
        summary=QaBrainModelPackagingPlanSummary(
            status="partial",
            plans_total=1,
            plans_ready=0,
            plans_missing=0,
            plans_attention=1,
            blockers_total=1,
            next_actions_total=1,
        ),
        packaging_plans=(
            QaBrainModelPackagingPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                packaging_stage="needs_boundary_repair",
                endpoint_boundary="OpenAI-compatible endpoint planning only.",
                litellm_routing_boundary="Route through LiteLLM later.",
                deployment_modes=("hosted", "local", "enterprise"),
                artifact_boundary="No model artifacts are produced.",
                access_control_audit="Access control design is required.",
                blockers=("Repair readiness evidence before packaging design.",),
                next_action="Repair readiness evidence before model packaging design.",
            ),
        ),
        next_actions=(
            QaBrainModelPackagingPlanNextAction(
                priority="high",
                action="Repair model packaging readiness evidence.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert (
        QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION == "entroping.qa-brain-model-packaging-plan.v1"
    )
    assert payload == {
        "schema_version": "entroping.qa-brain-model-packaging-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "fine_tune_readiness_schema_version": ("entroping.qa-brain-fine-tune-readiness.v1"),
        "summary": {
            "status": "partial",
            "plans_total": 1,
            "plans_ready": 0,
            "plans_missing": 0,
            "plans_attention": 1,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "packaging_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "packaging_stage": "needs_boundary_repair",
                "endpoint_boundary": "OpenAI-compatible endpoint planning only.",
                "litellm_routing_boundary": "Route through LiteLLM later.",
                "deployment_modes": ["hosted", "local", "enterprise"],
                "artifact_boundary": "No model artifacts are produced.",
                "access_control_audit": "Access control design is required.",
                "blockers": ["Repair readiness evidence before packaging design."],
                "next_action": "Repair readiness evidence before model packaging design.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair model packaging readiness evidence.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.qa-brain-model-packaging-plan.v1"
    )
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["fine_tune_readiness_schema_version"]["const"] == (
        "entroping.qa-brain-fine-tune-readiness.v1"
    )
    assert schema["$defs"]["packaging_stage"]["enum"] == [
        "packaging_ready",
        "needs_readiness_evidence",
        "needs_boundary_repair",
    ]
    assert schema["$defs"]["case_readiness"]["enum"] == [
        "ready",
        "missing",
        "attention",
    ]


def test_qa_brain_routing_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-routing-plan.v1.schema.json").read_text())
    packet = QaBrainRoutingPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="checkout-api",
        model_packaging_plan_schema_version=("entroping.qa-brain-model-packaging-plan.v1"),
        summary=QaBrainRoutingPlanSummary(
            status="partial",
            routes_total=1,
            routes_ready=0,
            routes_missing=0,
            routes_attention=1,
            blockers_total=1,
            next_actions_total=1,
        ),
        routing_plans=(
            QaBrainRoutingPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="attention",
                packaging_stage="needs_boundary_repair",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                routing_stage="needs_boundary_repair",
                litellm_boundary="Route through LiteLLM later.",
                endpoint_boundary="OpenAI-compatible endpoint planning only.",
                deployment_modes=("hosted", "local", "enterprise"),
                allowed_use_cases=(
                    "critique",
                    "generation",
                    "prioritization",
                    "repair_proposals",
                ),
                repair_acceptance_gates=(
                    QaBrainRepairAcceptanceGate(
                        id="parser_validation",
                        label="Parser validation",
                        required=True,
                        summary="Parse proposed Hurl and policy changes before review.",
                    ),
                ),
                forbidden_authority="Hurl/QAnstitution remains authority.",
                access_control_audit="Access control design is required.",
                blockers=("Repair packaging boundaries before routing design.",),
                next_action="Repair routing readiness evidence.",
            ),
        ),
        next_actions=(
            QaBrainRoutingPlanNextAction(
                priority="high",
                action="Repair routing readiness evidence.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION == "entroping.qa-brain-routing-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-routing-plan.v1",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "project": "checkout-api",
        "model_packaging_plan_schema_version": ("entroping.qa-brain-model-packaging-plan.v1"),
        "summary": {
            "status": "partial",
            "routes_total": 1,
            "routes_ready": 0,
            "routes_missing": 0,
            "routes_attention": 1,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "routing_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "attention",
                "packaging_stage": "needs_boundary_repair",
                "source_ids": ["test-quality-json"],
                "source_paths": ["reports/test-quality.json"],
                "routing_stage": "needs_boundary_repair",
                "litellm_boundary": "Route through LiteLLM later.",
                "endpoint_boundary": "OpenAI-compatible endpoint planning only.",
                "deployment_modes": ["hosted", "local", "enterprise"],
                "allowed_use_cases": [
                    "critique",
                    "generation",
                    "prioritization",
                    "repair_proposals",
                ],
                "repair_acceptance_gates": [
                    {
                        "id": "parser_validation",
                        "label": "Parser validation",
                        "required": True,
                        "summary": "Parse proposed Hurl and policy changes before review.",
                    }
                ],
                "forbidden_authority": "Hurl/QAnstitution remains authority.",
                "access_control_audit": "Access control design is required.",
                "blockers": ["Repair packaging boundaries before routing design."],
                "next_action": "Repair routing readiness evidence.",
            }
        ],
        "next_actions": [
            {
                "priority": "high",
                "action": "Repair routing readiness evidence.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == ("entroping.qa-brain-routing-plan.v1")
    assert schema["properties"]["summary"]["$ref"] == "#/$defs/summary"
    assert schema["properties"]["model_packaging_plan_schema_version"]["const"] == (
        "entroping.qa-brain-model-packaging-plan.v1"
    )
    assert schema["$defs"]["routing_stage"]["enum"] == [
        "routing_design_ready",
        "needs_packaging_evidence",
        "needs_boundary_repair",
    ]
    assert schema["$defs"]["allowed_use_case"]["enum"] == [
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    ]
    assert "repair_acceptance_gates" in schema["$defs"]["routing_plan"]["required"]
    assert schema["$defs"]["routing_plan"]["properties"]["repair_acceptance_gates"] == {
        "type": "array",
        "items": {"$ref": "#/$defs/repair_acceptance_gate"},
    }
    assert schema["$defs"]["repair_acceptance_gate"]["required"] == [
        "id",
        "label",
        "required",
        "summary",
    ]
    assert schema["$defs"]["repair_acceptance_gate_id"]["enum"] == [
        "parser_validation",
        "hurl_execution",
        "qanstitution_governance",
        "deterministic_evidence",
        "secret_redaction",
        "codex_human_review",
    ]


def test_qa_brain_repair_plan_v1_schema_contract_is_versioned_and_stable() -> None:
    schema = json.loads((SCHEMA_DIR / "qa-brain-repair-plan.v1.schema.json").read_text())
    packet = QaBrainRepairPlanPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        routing_plan_schema_version="entroping.qa-brain-routing-plan.v1",
        summary=QaBrainRepairPlanSummary(
            status="partial",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            repair_plans_total=1,
            repair_plans_ready=0,
            repair_plans_missing=1,
            repair_plans_attention=0,
            blockers_total=1,
            next_actions_total=1,
        ),
        sources=(
            QaBrainRepairPlanSource(
                id="qa-brain-routing-plan-json",
                label="QA Brain Routing Plan JSON",
                path="reports/qa-brain-routing-plan.json",
                state="present",
                schema_version="entroping.qa-brain-routing-plan.v1",
                summary="ready routing plan",
            ),
        ),
        repair_plans=(
            QaBrainRepairPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="missing",
                repair_intent="review",
                source_ids=("qa-brain-routing-plan-json",),
                source_paths=("reports/qa-brain-routing-plan.json",),
                acceptance_gate_ids=("parser_validation",),
                blockers=("Add value-free local evidence before repair proposals.",),
                next_action="Add evidence before future QA Brain repair proposals.",
            ),
        ),
        repair_proposal_dry_run_checklist=(
            QaBrainRepairProposalDryRunChecklistItem(
                case_id="weak_test_detection",
                prerequisite_status="partial",
                readiness="missing",
                artifact_statuses=(
                    QaBrainRepairProposalDryRunArtifactStatus(
                        source_id="qa-brain-routing-plan-json",
                        status="present",
                    ),
                ),
                acceptance_gate_status="ready",
                next_action_label="add-value-free-evidence",
            ),
        ),
        next_actions=(
            QaBrainRepairPlanNextAction(
                priority="medium",
                action="Add evidence before future QA Brain repair proposals.",
                case_ids=("weak_test_detection",),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")

    assert QA_BRAIN_REPAIR_PLAN_SCHEMA_VERSION == "entroping.qa-brain-repair-plan.v1"
    assert payload == {
        "schema_version": "entroping.qa-brain-repair-plan.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "routing_plan_schema_version": "entroping.qa-brain-routing-plan.v1",
        "summary": {
            "status": "partial",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "repair_plans_total": 1,
            "repair_plans_ready": 0,
            "repair_plans_missing": 1,
            "repair_plans_attention": 0,
            "blockers_total": 1,
            "next_actions_total": 1,
        },
        "sources": [
            {
                "id": "qa-brain-routing-plan-json",
                "label": "QA Brain Routing Plan JSON",
                "path": "reports/qa-brain-routing-plan.json",
                "state": "present",
                "schema_version": "entroping.qa-brain-routing-plan.v1",
                "summary": "ready routing plan",
            }
        ],
        "repair_plans": [
            {
                "case_id": "weak_test_detection",
                "label": "Weak-test detection",
                "readiness": "missing",
                "repair_intent": "review",
                "source_ids": ["qa-brain-routing-plan-json"],
                "source_paths": ["reports/qa-brain-routing-plan.json"],
                "acceptance_gate_ids": ["parser_validation"],
                "blockers": ["Add value-free local evidence before repair proposals."],
                "next_action": "Add evidence before future QA Brain repair proposals.",
            }
        ],
        "repair_proposal_dry_run_checklist": [
            {
                "case_id": "weak_test_detection",
                "prerequisite_status": "partial",
                "readiness": "missing",
                "artifact_statuses": [
                    {
                        "source_id": "qa-brain-routing-plan-json",
                        "status": "present",
                    }
                ],
                "acceptance_gate_status": "ready",
                "next_action_label": "add-value-free-evidence",
            }
        ],
        "repair_acceptance_checklist": [],
        "next_actions": [
            {
                "priority": "medium",
                "action": "Add evidence before future QA Brain repair proposals.",
                "case_ids": ["weak_test_detection"],
            }
        ],
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "entroping.qa-brain-repair-plan.v1"
    )
    assert schema["properties"]["routing_plan_schema_version"]["const"] == (
        "entroping.qa-brain-routing-plan.v1"
    )
    assert schema["$defs"]["source_id"]["enum"] == [
        "test-quality-json",
        "mutation-readiness-json",
        "evidence-action-plan-json",
        "qa-brain-routing-plan-json",
        "evidence-index-json",
    ]
    assert schema["$defs"]["repair_intent"]["enum"] == ["generate", "repair", "review"]
    assert schema["$defs"]["prerequisite_status"]["enum"] == [
        "ready",
        "partial",
        "missing",
    ]
    assert schema["$defs"]["acceptance_gate_status"]["enum"] == ["ready", "missing"]
    assert schema["properties"]["repair_acceptance_checklist"]["items"]["$ref"] == (
        "#/$defs/repair_acceptance_checklist_item"
    )
    assert schema["$defs"]["repair_acceptance_checklist_item"]["required"] == [
        "case_id",
        "gate_id",
        "gate_family",
        "source_evidence_ids",
        "required_reviewer",
        "forbidden_shortcut_notes",
    ]
    assert schema["$defs"]["acceptance_gate_family"]["enum"] == [
        "parser",
        "hurl",
        "policy",
        "evidence",
        "redaction",
        "review",
    ]
    assert schema["$defs"]["acceptance_reviewer"]["enum"] == ["codex_or_human"]
    assert schema["$defs"]["acceptance_gate_id"]["enum"] == [
        "parser_validation",
        "hurl_execution",
        "qanstitution_governance",
        "deterministic_evidence",
        "secret_redaction",
        "codex_human_review",
    ]
