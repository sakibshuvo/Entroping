from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, ClassVar, Literal, Self, override

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

type AutonomyTier = Literal["tier_a", "tier_b", "tier_c"]
type BillingKind = Literal["included_quota", "metered", "subscription", "offline"]
type Capability = Literal[
    "implementation",
    "model_comparison",
    "patch_proposal",
    "private_processing",
    "queue_dispatch",
    "review",
]
type Lifecycle = Literal["candidate", "active", "deprecated", "retired"]
type QueueDefault = Literal["standard", "tier_a"]
type QueueEngine = Literal["opencode", "deepseek-api"]
type UnlistedModelPolicy = Literal["deny", "allow_non_paid"]
type UsageAccounting = Literal[
    "provider_reported",
    "quota_only",
    "unavailable",
    "not_applicable",
]

CostProviderIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
    ),
]
CostModelIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=160,
        pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*/[a-z0-9][a-z0-9._-]*$",
    ),
]

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._/-]*$",
    ),
]
EvidenceText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=160, strip_whitespace=True),
]


class StrictRegistryModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class QueueBinding(StrictRegistryModel):
    engine: QueueEngine
    profile: Identifier
    default_for: Annotated[tuple[QueueDefault, ...], Field(max_length=2)] = ()

    @model_validator(mode="after")
    def validate_defaults(self) -> Self:
        if len(set(self.default_for)) != len(self.default_for):
            raise PydanticCustomError(
                "duplicate_queue_default",
                "queue binding contains a duplicate default selector",
            )
        return self


class ProviderModel(StrictRegistryModel):
    id: Identifier
    aliases: Annotated[tuple[EvidenceText, ...], Field(max_length=16)] = ()
    lifecycle: Lifecycle
    billing_path: EvidenceText | None = None
    billing_path_aliases: Annotated[tuple[EvidenceText, ...], Field(max_length=16)] = ()
    billing_kind: BillingKind | None = None
    usage_accounting: UsageAccounting | None = None
    cost_model_id: CostModelIdentifier | None = None
    queue: QueueBinding | None = None


class ProviderLane(StrictRegistryModel):
    id: Identifier
    provider_host: EvidenceText
    provider_host_aliases: Annotated[tuple[EvidenceText, ...], Field(max_length=16)] = ()
    billing_path: EvidenceText
    billing_path_aliases: Annotated[tuple[EvidenceText, ...], Field(max_length=16)] = ()
    billing_kind: BillingKind
    capabilities: Annotated[tuple[Capability, ...], Field(min_length=1, max_length=16)]
    autonomy_ceiling: AutonomyTier
    usage_accounting: UsageAccounting
    policy_provider_id: CostProviderIdentifier | None = None
    cost_provider_id: CostProviderIdentifier | None = None
    lifecycle: Lifecycle
    unlisted_model_policy: UnlistedModelPolicy
    models: Annotated[tuple[ProviderModel, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def validate_lane(self) -> Self:
        model_names: list[str] = []
        for model in self.models:
            model_names.extend((model.id, *model.aliases))
        if len(set(model_names)) != len(model_names):
            raise PydanticCustomError(
                "duplicate_model_identifier",
                "provider lane contains a duplicate model id or alias",
            )
        if self.unlisted_model_policy == "allow_non_paid" and self.billing_kind in {
            "metered",
            "subscription",
        }:
            raise PydanticCustomError(
                "paid_unlisted_model",
                "paid provider lanes cannot allow unlisted models",
            )
        metered_models: list[ProviderModel] = []
        for model in self.models:
            effective_billing_kind = model.billing_kind or self.billing_kind
            if model.queue is not None and "queue_dispatch" not in self.capabilities:
                raise PydanticCustomError(
                    "queue_dispatch_capability",
                    "a queue binding requires the queue_dispatch capability",
                )
            if effective_billing_kind == "metered":
                metered_models.append(model)
                if self.cost_provider_id is None or model.cost_model_id is None:
                    raise PydanticCustomError(
                        "metered_cost_identity",
                        "metered models require cost_provider_id and cost_model_id",
                    )
                if model.cost_model_id.partition("/")[0] != self.cost_provider_id:
                    raise PydanticCustomError(
                        "metered_cost_provider",
                        "cost model provider does not match the lane cost provider id",
                    )
            elif model.cost_model_id is not None:
                raise PydanticCustomError(
                    "non_metered_cost_identity",
                    "non-metered models must not declare cost_model_id",
                )
        if not metered_models and self.cost_provider_id is not None:
            raise PydanticCustomError(
                "unused_cost_provider",
                "a lane without metered models must not declare cost_provider_id",
            )
        if (
            self.cost_provider_id is not None
            and self.policy_provider_id is not None
            and self.cost_provider_id != self.policy_provider_id
        ):
            raise PydanticCustomError(
                "policy_cost_provider",
                "metered cost and policy provider identities must match",
            )
        if self.billing_kind != "offline" and self.policy_provider_id is None:
            raise PydanticCustomError(
                "missing_policy_provider",
                "paid and quota-backed lanes require a policy provider identity",
            )
        if self.billing_kind == "offline" and self.policy_provider_id is not None:
            raise PydanticCustomError(
                "offline_policy_provider",
                "offline lanes must not declare a policy provider identity",
            )
        return self


class ProviderCapabilityRegistry(StrictRegistryModel):
    schema_version: Literal["entroping.provider-capability-registry.v1"]
    purpose: Literal["maintainer_workflow_only"]
    unknown_paid_route: Literal["deny"]
    lanes: Annotated[tuple[ProviderLane, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        lane_ids = tuple(lane.id for lane in self.lanes)
        if len(set(lane_ids)) != len(lane_ids):
            raise PydanticCustomError(
                "duplicate_lane_identifier",
                "provider registry contains a duplicate lane id",
            )
        queue_routes: list[tuple[str, str]] = []
        queue_model_identifiers: list[tuple[str, str]] = []
        queue_defaults: list[tuple[str, str]] = []
        for lane in self.lanes:
            for model in lane.models:
                if model.queue is None:
                    continue
                queue_routes.append((model.queue.engine, model.queue.profile))
                queue_model_identifiers.extend(
                    (model.queue.engine, identifier) for identifier in (model.id, *model.aliases)
                )
                queue_defaults.extend(
                    (model.queue.engine, selector) for selector in model.queue.default_for
                )
                if model.queue.default_for and (
                    lane.lifecycle != "active" or model.lifecycle != "active"
                ):
                    raise PydanticCustomError(
                        "inactive_queue_default",
                        "queue defaults must reference an active lane and model",
                    )
        if len(set(queue_routes)) != len(queue_routes):
            raise PydanticCustomError(
                "duplicate_queue_route",
                "provider registry contains a duplicate queue engine/profile route",
            )
        if len(set(queue_model_identifiers)) != len(queue_model_identifiers):
            raise PydanticCustomError(
                "duplicate_queue_model_identifier",
                "provider registry contains a duplicate queue model id or alias",
            )
        if len(set(queue_defaults)) != len(queue_defaults):
            raise PydanticCustomError(
                "duplicate_queue_default",
                "provider registry contains a duplicate queue default",
            )
        engines = {engine for engine, _profile in queue_routes}
        required_defaults = {
            (engine, selector) for engine in engines for selector in ("standard", "tier_a")
        }
        if set(queue_defaults) != required_defaults:
            raise PydanticCustomError(
                "missing_queue_default",
                "every queue engine needs exactly one standard and Tier A default",
            )
        return self


@dataclass
class ProviderRegistryError(Exception):
    code: str
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ProviderEvidence:
    lane_id: str
    provider_host: str
    billing_path: str
    model_id: str
    autonomy_tier: AutonomyTier


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    lane: ProviderLane
    model: ProviderModel
    queue: QueueBinding
    billing_path: str
    billing_kind: BillingKind
    usage_accounting: UsageAccounting
