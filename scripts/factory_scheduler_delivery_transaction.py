"""Under-lock scheduler delivery admission revalidation."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from scripts.factory_delivery_admission import (
    _DeliveryAdmission,
    _revalidate_delivery_admission,
)
from scripts.factory_scheduler_models import AssignmentRequest, DecisionReceipt
from scripts.factory_scheduler_transaction_control import blocked_receipt


def _delivery_admission_block(
    connection: sqlite3.Connection,
    root: Path | None,
    request: AssignmentRequest,
    admission: _DeliveryAdmission | None,
    *,
    observed_at: datetime,
    plan_only: bool,
) -> DecisionReceipt | None:
    requires_live_selection = (
        request.worker_class == "free-local" and request.access_mode == "write"
    )
    if not requires_live_selection and admission is None:
        return None
    if (
        not requires_live_selection
        or admission is None
    ):
        return blocked_receipt(
            connection,
            request=request,
            observed_at=observed_at,
            reason="selection-required",
            authoritative=not plan_only,
        )
    if root is not None and _revalidate_delivery_admission(
        connection,
        root,
        request,
        admission,
        as_of=observed_at,
    ):
        return None
    return blocked_receipt(
        connection,
        request=request,
        observed_at=observed_at,
        reason="selection-changed",
        authoritative=not plan_only,
    )
