CREATE TABLE IF NOT EXISTS apply_preview_receipts (
    token_sha256 TEXT PRIMARY KEY
        CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    receipt_version INTEGER NOT NULL
        CHECK (receipt_version >= 1),
    state TEXT NOT NULL
        CHECK (state IN ('issued', 'applying', 'applied', 'failed_terminal')),
    principal_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    project_key TEXT NOT NULL,
    repo_id TEXT NOT NULL,
    action TEXT NOT NULL,
    normalized_intent_json JSONB NOT NULL,
    target_binding_json JSONB NOT NULL,
    precondition_json JSONB NOT NULL,
    predicted_after_json JSONB NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    fence BIGINT NOT NULL DEFAULT 0
        CHECK (fence >= 0),
    apply_lease_expires_at TIMESTAMPTZ,
    terminal_result_code TEXT
        CHECK (
            terminal_result_code IS NULL
            OR terminal_result_code IN (
                'APPLY_RECEIPT_APPLIED',
                'APPLY_RECEIPT_REPLAYED',
                'APPLY_RECEIPT_INVALID',
                'APPLY_RECEIPT_EXPIRED',
                'APPLY_RECEIPT_SCOPE_MISMATCH',
                'APPLY_RECEIPT_INAPPLICABLE',
                'APPLY_RECEIPT_POLICY_DENIED',
                'APPLY_RECEIPT_TARGET_DRIFT',
                'APPLY_RECEIPT_BUSY',
                'APPLY_RECEIPT_RECOVERY_REQUIRED',
                'APPLY_RECEIPT_STORAGE_UNAVAILABLE'
            )
        ),
    terminal_result_json JSONB,
    terminal_at TIMESTAMPTZ,
    audit_correlation_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > issued_at),
    CHECK (updated_at >= issued_at),
    CHECK (
        (
            state = 'issued'
            AND fence = 0
            AND apply_lease_expires_at IS NULL
            AND terminal_result_code IS NULL
            AND terminal_result_json IS NULL
            AND terminal_at IS NULL
        )
        OR (
            state = 'applying'
            AND fence >= 1
            AND apply_lease_expires_at IS NOT NULL
            AND terminal_result_code IS NULL
            AND terminal_result_json IS NULL
            AND terminal_at IS NULL
        )
        OR (
            state IN ('applied', 'failed_terminal')
            AND fence >= 1
            AND apply_lease_expires_at IS NULL
            AND terminal_result_code IS NOT NULL
            AND terminal_result_json IS NOT NULL
            AND terminal_at IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_apply_preview_receipts_expires_at
    ON apply_preview_receipts (expires_at);

CREATE INDEX IF NOT EXISTS idx_apply_preview_receipts_state_lease
    ON apply_preview_receipts (state, apply_lease_expires_at);
