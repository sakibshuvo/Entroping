from __future__ import annotations

RESERVATION_SCHEMA_STATEMENTS = (
    """
    ALTER TABLE budget_periods
    ADD COLUMN active_reserved_microcents INTEGER NOT NULL DEFAULT 0
        CHECK (active_reserved_microcents >= 0)
    """,
    """
    CREATE TABLE cost_reservations (
        id INTEGER PRIMARY KEY,
        public_id TEXT NOT NULL UNIQUE CHECK (length(public_id) = 36),
        idempotency_digest TEXT NOT NULL UNIQUE
            CHECK (length(idempotency_digest) = 64),
        period_id INTEGER NOT NULL REFERENCES budget_periods(id) ON DELETE RESTRICT,
        job_id TEXT NOT NULL UNIQUE,
        provider_lane_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        requested_model TEXT NOT NULL,
        cost_policy_lane_id TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_revision INTEGER NOT NULL CHECK (policy_revision > 0),
        pricing_digest TEXT NOT NULL CHECK (length(pricing_digest) = 64),
        held_microcents INTEGER NOT NULL CHECK (held_microcents > 0),
        max_requests INTEGER NOT NULL CHECK (max_requests >= 0),
        max_input_tokens INTEGER NOT NULL CHECK (max_input_tokens >= 0),
        max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens >= 0),
        max_minutes INTEGER NOT NULL CHECK (max_minutes >= 0),
        actual_microcents INTEGER CHECK (actual_microcents >= 0),
        state TEXT NOT NULL CHECK (state IN (
            'dispatching', 'uncertain', 'settled', 'reconciled'
        )),
        reason TEXT,
        provider_session_digest TEXT UNIQUE CHECK (
            provider_session_digest IS NULL OR length(provider_session_digest) = 64
        ),
        settlement_entry_id INTEGER UNIQUE
            REFERENCES ledger_entries(id) ON DELETE RESTRICT,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        CHECK (
            (state = 'dispatching' AND actual_microcents IS NULL
                AND reason IS NULL AND settlement_entry_id IS NULL)
            OR (state = 'uncertain' AND actual_microcents IS NULL
                AND reason IS NOT NULL AND settlement_entry_id IS NULL)
            OR (state = 'settled' AND actual_microcents > 0
                AND reason = 'complete' AND provider_session_digest IS NOT NULL
                AND settlement_entry_id IS NOT NULL)
            OR (state = 'reconciled' AND actual_microcents IS NOT NULL
                AND reason IS NOT NULL
                AND ((actual_microcents = 0 AND settlement_entry_id IS NULL)
                    OR (actual_microcents > 0 AND settlement_entry_id IS NOT NULL)))
        )
    ) STRICT
    """,
    "CREATE INDEX cost_reservations_period_idx ON cost_reservations(period_id, id)",
    "CREATE INDEX cost_reservations_state_idx ON cost_reservations(state, id)",
    """
    CREATE TRIGGER cost_reservations_authority_no_update
    BEFORE UPDATE OF
        id,
        public_id,
        idempotency_digest,
        period_id,
        job_id,
        provider_lane_id,
        provider_id,
        model_id,
        requested_model,
        cost_policy_lane_id,
        policy_id,
        policy_revision,
        pricing_digest,
        held_microcents,
        max_requests,
        max_input_tokens,
        max_output_tokens,
        max_minutes,
        created_at_utc
    ON cost_reservations
    BEGIN
        SELECT RAISE(ABORT, 'cost reservation authority is immutable');
    END
    """,
    """
    CREATE TRIGGER cost_reservations_no_delete
    BEFORE DELETE ON cost_reservations
    BEGIN
        SELECT RAISE(ABORT, 'cost reservations are immutable');
    END
    """,
    """
    CREATE TABLE cost_reservation_prices (
        id INTEGER PRIMARY KEY,
        reservation_id INTEGER NOT NULL
            REFERENCES cost_reservations(id) ON DELETE RESTRICT,
        snapshot_id TEXT NOT NULL,
        unit TEXT NOT NULL CHECK (unit IN (
            'request', 'input_token', 'output_token', 'minute'
        )),
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        price_microcents INTEGER NOT NULL CHECK (price_microcents > 0),
        observed_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL,
        UNIQUE (reservation_id, snapshot_id),
        UNIQUE (reservation_id, unit),
        CHECK (observed_at_utc < expires_at_utc)
    ) STRICT
    """,
    """
    CREATE TRIGGER cost_reservation_prices_no_update
    BEFORE UPDATE ON cost_reservation_prices
    BEGIN
        SELECT RAISE(ABORT, 'cost reservation prices are immutable');
    END
    """,
    """
    CREATE TRIGGER cost_reservation_prices_no_delete
    BEFORE DELETE ON cost_reservation_prices
    BEGIN
        SELECT RAISE(ABORT, 'cost reservation prices are immutable');
    END
    """,
    """
    CREATE TABLE cost_reservation_events (
        id INTEGER PRIMARY KEY,
        reservation_id INTEGER NOT NULL
            REFERENCES cost_reservations(id) ON DELETE RESTRICT,
        idempotency_digest TEXT NOT NULL UNIQUE
            CHECK (length(idempotency_digest) = 64),
        event_type TEXT NOT NULL CHECK (event_type IN (
            'dispatch_reserved', 'receipt_rejected', 'settled',
            'reconciled_no_charge', 'reconciled_manual_debit'
        )),
        resulting_state TEXT NOT NULL CHECK (resulting_state IN (
            'dispatching', 'uncertain', 'settled', 'reconciled'
        )),
        occurred_at_utc TEXT NOT NULL,
        reason TEXT,
        evidence_digest TEXT CHECK (
            evidence_digest IS NULL OR length(evidence_digest) = 64
        ),
        receipt_digest TEXT CHECK (
            receipt_digest IS NULL OR length(receipt_digest) = 64
        )
    ) STRICT
    """,
    (
        "CREATE INDEX cost_reservation_events_reservation_idx "
        "ON cost_reservation_events(reservation_id, id)"
    ),
    """
    CREATE TRIGGER cost_reservation_events_no_update
    BEFORE UPDATE ON cost_reservation_events
    BEGIN
        SELECT RAISE(ABORT, 'cost reservation events are immutable');
    END
    """,
    """
    CREATE TRIGGER cost_reservation_events_no_delete
    BEFORE DELETE ON cost_reservation_events
    BEGIN
        SELECT RAISE(ABORT, 'cost reservation events are immutable');
    END
    """,
)
