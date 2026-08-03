from __future__ import annotations

QUOTA_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE quota_observations (
        id INTEGER PRIMARY KEY,
        observation_id TEXT NOT NULL UNIQUE,
        quota_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        provider_lane_id TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_revision INTEGER NOT NULL CHECK (policy_revision > 0),
        unit TEXT NOT NULL CHECK (unit IN (
            'requests', 'input_tokens', 'output_tokens', 'tokens'
        )),
        source_kind TEXT NOT NULL,
        source_id TEXT NOT NULL,
        observed_at_utc TEXT NOT NULL,
        recorded_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL,
        window_kind TEXT NOT NULL CHECK (window_kind IN (
            'rolling', 'calendar_month', 'subscription_cycle'
        )),
        window_start_utc TEXT NOT NULL,
        window_end_utc TEXT NOT NULL,
        cycle_id TEXT,
        used_units INTEGER NOT NULL CHECK (used_units >= 0),
        known INTEGER NOT NULL CHECK (known IN (0, 1)),
        evidence_digest TEXT NOT NULL CHECK (length(evidence_digest) = 64),
        inclusions_digest TEXT NOT NULL CHECK (length(inclusions_digest) = 64),
        CHECK (observed_at_utc <= recorded_at_utc),
        CHECK (recorded_at_utc < expires_at_utc),
        CHECK (window_start_utc < window_end_utc),
        CHECK ((window_kind = 'subscription_cycle' AND cycle_id IS NOT NULL)
            OR (window_kind != 'subscription_cycle' AND cycle_id IS NULL))
    ) STRICT
    """,
    (
        "CREATE INDEX quota_observations_identity_idx ON quota_observations("
        "quota_id, provider_id, provider_lane_id, policy_id, policy_revision, "
        "window_start_utc, window_end_utc, id)"
    ),
    """
    CREATE TRIGGER quota_observations_no_update
    BEFORE UPDATE ON quota_observations
    BEGIN
        SELECT RAISE(ABORT, 'quota observations are immutable');
    END
    """,
    """
    CREATE TRIGGER quota_observations_no_delete
    BEFORE DELETE ON quota_observations
    BEGIN
        SELECT RAISE(ABORT, 'quota observations are immutable');
    END
    """,
    """
    CREATE TABLE top_up_attestations (
        id INTEGER PRIMARY KEY,
        attestation_id TEXT NOT NULL UNIQUE,
        provider_id TEXT NOT NULL,
        provider_lane_id TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_revision INTEGER NOT NULL CHECK (policy_revision > 0),
        mode TEXT NOT NULL CHECK (mode = 'disabled'),
        source_kind TEXT NOT NULL,
        source_id TEXT NOT NULL,
        evidence_digest TEXT NOT NULL CHECK (length(evidence_digest) = 64),
        observed_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL,
        CHECK (observed_at_utc < expires_at_utc)
    ) STRICT
    """,
    """
    CREATE TRIGGER top_up_attestations_no_update
    BEFORE UPDATE ON top_up_attestations
    BEGIN
        SELECT RAISE(ABORT, 'top-up attestations are immutable');
    END
    """,
    """
    CREATE TRIGGER top_up_attestations_no_delete
    BEFORE DELETE ON top_up_attestations
    BEGIN
        SELECT RAISE(ABORT, 'top-up attestations are immutable');
    END
    """,
    """
    CREATE TABLE dispatch_decision_clock (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        decided_at_utc TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE dispatch_authorizations (
        id INTEGER PRIMARY KEY,
        public_id TEXT NOT NULL UNIQUE CHECK (length(public_id) = 37),
        idempotency_digest TEXT NOT NULL UNIQUE CHECK (length(idempotency_digest) = 64),
        request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
        job_id TEXT NOT NULL UNIQUE,
        provider_lane_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        cost_policy_lane_id TEXT NOT NULL,
        policy_id TEXT NOT NULL,
        policy_revision INTEGER NOT NULL CHECK (policy_revision > 0),
        billing_mode TEXT NOT NULL CHECK (billing_mode IN (
            'metered', 'included_quota', 'fixed_subscription'
        )),
        work_purpose TEXT NOT NULL CHECK (work_purpose IN ('experiment', 'essential')),
        cash_reservation_id INTEGER UNIQUE REFERENCES cost_reservations(id),
        top_up_attestation_id INTEGER NOT NULL REFERENCES top_up_attestations(id),
        decision_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN (
            'active', 'launched', 'settled', 'released', 'uncertain'
        )),
        state_changed_at_utc TEXT NOT NULL,
        settlement_digest TEXT CHECK (
            settlement_digest IS NULL OR length(settlement_digest) = 64
        ),
        reason TEXT NOT NULL,
        CHECK (decision_at_utc < expires_at_utc),
        CHECK (decision_at_utc <= state_changed_at_utc),
        CHECK ((state = 'settled' AND settlement_digest IS NOT NULL)
            OR (state != 'settled' AND settlement_digest IS NULL)),
        CHECK ((billing_mode = 'metered' AND cash_reservation_id IS NOT NULL)
            OR (billing_mode != 'metered' AND cash_reservation_id IS NULL))
    ) STRICT
    """,
    (
        "CREATE INDEX dispatch_authorizations_expiry_idx "
        "ON dispatch_authorizations(expires_at_utc, id)"
    ),
    """
    CREATE TRIGGER dispatch_authorizations_authority_no_update
    BEFORE UPDATE OF public_id, idempotency_digest, request_digest, job_id,
        provider_lane_id, provider_id, cost_policy_lane_id, policy_id,
        policy_revision, billing_mode, work_purpose, cash_reservation_id,
        top_up_attestation_id, decision_at_utc, expires_at_utc, reason
    ON dispatch_authorizations
    BEGIN
        SELECT RAISE(ABORT, 'dispatch authorization authority is immutable');
    END
    """,
    """
    CREATE TRIGGER dispatch_authorizations_settlement_digest_once
    BEFORE UPDATE OF settlement_digest ON dispatch_authorizations
    WHEN OLD.settlement_digest IS NOT NULL
    BEGIN
        SELECT RAISE(ABORT, 'dispatch authorization settlement is immutable');
    END
    """,
    """
    CREATE TRIGGER dispatch_authorizations_no_delete
    BEFORE DELETE ON dispatch_authorizations
    BEGIN
        SELECT RAISE(ABORT, 'dispatch authorizations are immutable');
    END
    """,
    """
    CREATE TABLE quota_holds (
        id INTEGER PRIMARY KEY,
        authorization_id INTEGER NOT NULL REFERENCES dispatch_authorizations(id),
        observation_id INTEGER NOT NULL REFERENCES quota_observations(id),
        quota_id TEXT NOT NULL,
        unit TEXT NOT NULL CHECK (unit IN (
            'requests', 'input_tokens', 'output_tokens', 'tokens'
        )),
        quota_limit INTEGER NOT NULL CHECK (quota_limit > 0),
        held_units INTEGER NOT NULL CHECK (held_units > 0),
        actual_units INTEGER CHECK (actual_units >= 0),
        state TEXT NOT NULL CHECK (state IN ('active', 'settled', 'released', 'uncertain')),
        UNIQUE (authorization_id, quota_id),
        CHECK ((state = 'active' AND actual_units IS NULL)
            OR (state = 'uncertain' AND actual_units IS NULL)
            OR (state IN ('settled', 'released') AND actual_units IS NOT NULL))
    ) STRICT
    """,
    "CREATE INDEX quota_holds_capacity_idx ON quota_holds(quota_id, state, id)",
    """
    CREATE TRIGGER quota_holds_authority_no_update
    BEFORE UPDATE OF authorization_id, observation_id, quota_id, unit,
        quota_limit, held_units
    ON quota_holds
    BEGIN
        SELECT RAISE(ABORT, 'quota hold authority is immutable');
    END
    """,
    """
    CREATE TRIGGER quota_holds_no_delete
    BEFORE DELETE ON quota_holds
    BEGIN
        SELECT RAISE(ABORT, 'quota holds are immutable');
    END
    """,
    """
    CREATE TABLE quota_observation_inclusions (
        id INTEGER PRIMARY KEY,
        observation_id INTEGER NOT NULL REFERENCES quota_observations(id),
        authorization_id INTEGER NOT NULL REFERENCES dispatch_authorizations(id),
        UNIQUE (observation_id, authorization_id)
    ) STRICT
    """,
    (
        "CREATE INDEX quota_observation_inclusions_authorization_idx "
        "ON quota_observation_inclusions(authorization_id, observation_id)"
    ),
    """
    CREATE TRIGGER quota_observation_inclusions_no_update
    BEFORE UPDATE ON quota_observation_inclusions
    BEGIN
        SELECT RAISE(ABORT, 'quota observation inclusions are immutable');
    END
    """,
    """
    CREATE TRIGGER quota_observation_inclusions_no_delete
    BEFORE DELETE ON quota_observation_inclusions
    BEGIN
        SELECT RAISE(ABORT, 'quota observation inclusions are immutable');
    END
    """,
)
