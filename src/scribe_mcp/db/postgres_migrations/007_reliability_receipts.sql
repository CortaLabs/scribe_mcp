-- Reliability schema upgrade for durable session bindings and background receipts.
-- The numbered migration runner owns the corresponding scribe_migrations row.

ALTER TABLE session_projects
    ADD COLUMN IF NOT EXISTS project_key TEXT,
    ADD COLUMN IF NOT EXISTS binding_generation BIGINT;

DO $$
DECLARE
    unresolved RECORD;
BEGIN
    SELECT
        sp.session_id,
        sp.project_name,
        COUNT(p.id) AS match_count,
        COUNT(p.project_key) FILTER (WHERE NULLIF(BTRIM(p.project_key), '') IS NOT NULL)
            AS usable_key_count
    INTO unresolved
    FROM session_projects AS sp
    JOIN scribe_sessions AS ss
      ON ss.session_id = sp.session_id
    LEFT JOIN scribe_projects AS p
      ON p.repo_root = ss.repo_root
     AND p.name = sp.project_name
    WHERE NULLIF(BTRIM(sp.project_key), '') IS NULL
       OR sp.binding_generation IS NULL
    GROUP BY sp.session_id, sp.project_name
    HAVING COUNT(p.id) <> 1
        OR COUNT(p.project_key) FILTER (
            WHERE NULLIF(BTRIM(p.project_key), '') IS NOT NULL
        ) <> 1
    LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'session binding % has % project identity matches (% usable project keys)',
            unresolved.session_id,
            unresolved.match_count,
            unresolved.usable_key_count;
    END IF;
END
$$;

UPDATE session_projects AS sp
SET project_key = resolved.project_key,
    binding_generation = 1
FROM (
    SELECT
        sp_inner.session_id,
        MIN(p.project_key) AS project_key
    FROM session_projects AS sp_inner
    JOIN scribe_sessions AS ss
      ON ss.session_id = sp_inner.session_id
    JOIN scribe_projects AS p
      ON p.repo_root = ss.repo_root
     AND p.name = sp_inner.project_name
    WHERE NULLIF(BTRIM(sp_inner.project_key), '') IS NULL
       OR sp_inner.binding_generation IS NULL
    GROUP BY sp_inner.session_id
    HAVING COUNT(p.id) = 1
       AND COUNT(p.project_key) FILTER (
           WHERE NULLIF(BTRIM(p.project_key), '') IS NOT NULL
       ) = 1
) AS resolved
WHERE sp.session_id = resolved.session_id;

ALTER TABLE session_projects
    ALTER COLUMN project_key SET NOT NULL,
    ALTER COLUMN binding_generation SET NOT NULL,
    ALTER COLUMN binding_generation SET DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'session_projects'::regclass
          AND conname = 'session_projects_project_key_nonempty'
    ) THEN
        ALTER TABLE session_projects
            ADD CONSTRAINT session_projects_project_key_nonempty
            CHECK (BTRIM(project_key) <> '');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'session_projects'::regclass
          AND conname = 'session_projects_binding_generation_positive'
    ) THEN
        ALTER TABLE session_projects
            ADD CONSTRAINT session_projects_binding_generation_positive
            CHECK (binding_generation >= 1);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS background_receipts (
    operation_id TEXT PRIMARY KEY
        CHECK (BTRIM(operation_id) <> ''),
    canonical_project_key TEXT NOT NULL
        CHECK (BTRIM(canonical_project_key) <> ''),
    lane TEXT NOT NULL
        CHECK (lane IN ('control', 'durable', 'heavy')),
    idempotency_key TEXT NOT NULL
        CHECK (BTRIM(idempotency_key) <> ''),
    payload_digest TEXT NOT NULL
        CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    payload_bytes BIGINT NOT NULL
        CHECK (payload_bytes >= 0),
    durability_class TEXT NOT NULL
        CHECK (BTRIM(durability_class) <> ''),
    state TEXT NOT NULL
        CHECK (state IN (
            'accepted',
            'ready',
            'leased',
            'retry_wait',
            'succeeded',
            'failed_terminal',
            'cancelled'
        )),
    state_version BIGINT NOT NULL DEFAULT 1
        CHECK (state_version >= 1),
    attempt_count BIGINT NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    fencing_token BIGINT NOT NULL DEFAULT 0
        CHECK (fencing_token >= 0),
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    result_ref TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (canonical_project_key, idempotency_key),
    CHECK (updated_at >= created_at),
    CHECK (attempt_count = fencing_token),
    CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
    CHECK (lease_owner IS NULL OR BTRIM(lease_owner) <> ''),
    CHECK (result_ref IS NULL OR BTRIM(result_ref) <> ''),
    CHECK (error_code IS NULL OR BTRIM(error_code) <> ''),
    CHECK (
        (
            state = 'accepted'
            AND state_version = 1
            AND attempt_count = 0
            AND fencing_token = 0
            AND cancel_requested = FALSE
            AND next_attempt_at IS NULL
            AND lease_owner IS NULL
            AND result_ref IS NULL
            AND error_code IS NULL
        )
        OR (
            state = 'ready'
            AND state_version >= 2
            AND attempt_count = 0
            AND fencing_token = 0
            AND cancel_requested = FALSE
            AND next_attempt_at IS NULL
            AND lease_owner IS NULL
            AND result_ref IS NULL
            AND error_code IS NULL
        )
        OR (
            state = 'leased'
            AND state_version >= 3
            AND attempt_count >= 1
            AND fencing_token >= 1
            AND next_attempt_at IS NULL
            AND lease_owner IS NOT NULL
            AND result_ref IS NULL
            AND error_code IS NULL
        )
        OR (
            state = 'retry_wait'
            AND state_version >= 4
            AND attempt_count >= 1
            AND fencing_token >= 1
            AND next_attempt_at IS NOT NULL
            AND lease_owner IS NULL
            AND result_ref IS NULL
            AND error_code IS NULL
        )
        OR (
            state = 'succeeded'
            AND state_version >= 4
            AND attempt_count >= 1
            AND fencing_token >= 1
            AND next_attempt_at IS NULL
            AND lease_owner IS NULL
            AND result_ref IS NOT NULL
            AND error_code IS NULL
        )
        OR (
            state = 'failed_terminal'
            AND state_version >= 4
            AND attempt_count >= 1
            AND fencing_token >= 1
            AND next_attempt_at IS NULL
            AND lease_owner IS NULL
            AND result_ref IS NULL
            AND error_code IS NOT NULL
        )
        OR (
            state = 'cancelled'
            AND state_version >= 2
            AND next_attempt_at IS NULL
            AND lease_owner IS NULL
            AND result_ref IS NULL
            AND error_code IS NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_background_receipts_claim
    ON background_receipts (
        canonical_project_key,
        lane,
        state,
        next_attempt_at,
        created_at
    );

CREATE INDEX IF NOT EXISTS idx_background_receipts_state_lease
    ON background_receipts (state, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_background_receipts_project_state
    ON background_receipts (canonical_project_key, state)
    INCLUDE (payload_bytes);

CREATE TABLE IF NOT EXISTS scribe_schema_readiness (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE
        CHECK (singleton),
    schema_fingerprint TEXT NOT NULL
        CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$'),
    migration_version TEXT NOT NULL
        CHECK (BTRIM(migration_version) <> ''),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
