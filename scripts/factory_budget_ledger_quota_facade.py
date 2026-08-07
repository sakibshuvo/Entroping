from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path

from .factory_budget_ledger_models import canonical_occurred_at
from .factory_budget_ledger_storage import readonly_connection, writable_connection
from .factory_budget_reservation_models import UsageEnvelope
from .factory_quota_authorization import (
    authorize_dispatch,
    consume_authorization_for_launch,
    validate_authorization,
)
from .factory_quota_models import (
    DispatchAuthorizationReceipt,
    DispatchAuthorizationRequest,
)
from .factory_quota_settlement import (
    QuotaSettlementOutcome,
    mark_quota_authorization_uncertain,
    release_quota_authorization,
    settle_quota_authorization,
)
from .factory_quota_store import (
    QuotaAuthorizationState,
    authorization_by_job,
    quota_authorization_state,
)
from .factory_scheduler_ledger_handoff import authorization_handoff


class FactoryQuotaLedgerFacade:
    project_root: Path

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def authorize_dispatch(
        self,
        request: DispatchAuthorizationRequest,
    ) -> DispatchAuthorizationReceipt:
        with writable_connection(self.project_root) as connection:
            return authorize_dispatch(connection, request)

    def authorization_for_job(
        self,
        job_id: str,
    ) -> DispatchAuthorizationReceipt | None:
        with readonly_connection(self.project_root) as connection:
            return authorization_by_job(connection, job_id)

    def quota_authorization_state(
        self,
        authorization_id: str,
    ) -> QuotaAuthorizationState | None:
        with readonly_connection(self.project_root) as connection:
            return quota_authorization_state(connection, authorization_id)

    def validate_dispatch_authorization(self, job_id: str, *, as_of: datetime) -> bool:
        with readonly_connection(self.project_root) as connection:
            return validate_authorization(
                connection,
                job_id,
                as_of=canonical_occurred_at(as_of),
            )

    def consume_dispatch_authorization_for_launch(
        self,
        job_id: str,
        *,
        as_of: datetime,
    ) -> bool:
        with writable_connection(self.project_root) as connection:
            return consume_authorization_for_launch(
                connection,
                job_id,
                as_of=canonical_occurred_at(as_of),
            )

    def settle_quota_authorization(
        self,
        authorization_id: str,
        usage: UsageEnvelope,
        *,
        occurred_at: datetime,
    ) -> QuotaSettlementOutcome:
        with writable_connection(self.project_root) as connection:
            return settle_quota_authorization(
                connection,
                authorization_id=authorization_id,
                usage=usage,
                occurred_at=canonical_occurred_at(occurred_at),
            )

    def release_quota_authorization(
        self,
        authorization_id: str,
        *,
        occurred_at: datetime,
    ) -> QuotaSettlementOutcome:
        with writable_connection(self.project_root) as connection:
            return release_quota_authorization(
                connection,
                authorization_id=authorization_id,
                occurred_at=canonical_occurred_at(occurred_at),
            )

    def mark_quota_authorization_uncertain(
        self,
        authorization_id: str,
        *,
        occurred_at: datetime,
    ) -> QuotaSettlementOutcome:
        with writable_connection(self.project_root) as connection:
            return mark_quota_authorization_uncertain(
                connection,
                authorization_id=authorization_id,
                occurred_at=canonical_occurred_at(occurred_at),
            )

    @classmethod
    def authorization_for_scheduler_handoff(
        cls,
        project_root: Path,
        job_id: str,
        *,
        as_of: datetime,
    ) -> AbstractContextManager[DispatchAuthorizationReceipt | None]:
        return authorization_handoff(project_root, job_id, as_of=as_of)
