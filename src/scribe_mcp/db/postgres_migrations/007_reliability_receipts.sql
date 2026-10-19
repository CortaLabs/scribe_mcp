-- Reliability schema upgrade for durable session bindings and background receipts.
-- The numbered migration runner owns the corresponding scribe_migrations row.
--
-- Numbered migrations run at scribe-server startup, so nothing here may refuse
-- the server over legacy data. A legacy binding whose (repo_root, project_name)
-- matches zero or several projects is classified 'unresolved' with a reason and
-- keeps a NULL project_key: it is never assigned a guessed project and never
-- deleted. One trigger owns classification for the backfill below and for
-- every later write, including writers that still send project_name only.

ALTER TABLE session_projects
    ADD COLUMN IF NOT EXISTS project_key TEXT,
    ADD COLUMN IF NOT EXISTS binding_generation BIGINT,
    ADD COLUMN IF NOT EXISTS binding_state TEXT,
    ADD COLUMN IF NOT EXISTS binding_state_reason TEXT;

CREATE OR REPLACE FUNCTION session_projects_classify_binding()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    session_repo_root TEXT;
    session_found BOOLEAN;
    match_count BIGINT;
    usable_key_count BIGINT;
    usable_key TEXT;
    supplied_key TEXT;
BEGIN
    supplied_key := NULLIF(BTRIM(NEW.project_key), '');

    IF TG_OP = 'UPDATE' THEN
        NEW.binding_generation := OLD.binding_generation;
        IF NEW.binding_generation IS NULL THEN
            NEW.binding_generation := 1;
        END IF;

        -- An unchanged key is merely the stored value when a legacy writer
        -- rebinds by project_name. Derive the new canonical key in that case.
        IF NEW.project_name IS DISTINCT FROM OLD.project_name
           AND NEW.project_key IS NOT DISTINCT FROM OLD.project_key THEN
            supplied_key := NULL;
        END IF;
    ELSE
        NEW.binding_generation := 1;
    END IF;

    -- Classification always starts unresolved. A caller-supplied key is only
    -- accepted after it agrees with the canonical project selected by the
    -- session's repository and project name.
    NEW.project_key := NULL;
    NEW.binding_state := 'unresolved';

    SELECT ss.repo_root, TRUE
    INTO session_repo_root, session_found
    FROM scribe_sessions AS ss
    WHERE ss.session_id = NEW.session_id;

    IF NEW.project_name IS NULL THEN
        NEW.binding_state_reason := 'project_name_absent';
    ELSIF session_found IS NOT TRUE THEN
        NEW.binding_state_reason := 'session_missing';
    ELSE
        SELECT
            COUNT(*),
            COUNT(*) FILTER (WHERE NULLIF(BTRIM(p.project_key), '') IS NOT NULL),
            MIN(p.project_key) FILTER (WHERE NULLIF(BTRIM(p.project_key), '') IS NOT NULL)
        INTO match_count, usable_key_count, usable_key
        FROM scribe_projects AS p
        WHERE p.repo_root = session_repo_root
          AND p.name = NEW.project_name;

        IF match_count = 0 THEN
            NEW.binding_state_reason := 'project_identity_zero_matches';
        ELSIF match_count > 1 THEN
            NEW.binding_state_reason := 'project_identity_ambiguous';
        ELSIF usable_key_count <> 1 THEN
            NEW.binding_state_reason := 'project_key_missing';
        ELSIF supplied_key IS NOT NULL AND supplied_key IS DISTINCT FROM usable_key THEN
            NEW.binding_state_reason := 'project_key_mismatch';
        ELSE
            NEW.project_key := usable_key;
            NEW.binding_state := 'resolved';
            NEW.binding_state_reason := NULL;
        END IF;
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.binding_state IS NOT NULL
       AND (
           NEW.project_name IS DISTINCT FROM OLD.project_name
           OR NEW.project_key IS DISTINCT FROM OLD.project_key
           OR NEW.binding_state IS DISTINCT FROM OLD.binding_state
           OR NEW.binding_state_reason IS DISTINCT FROM OLD.binding_state_reason
       ) THEN
        NEW.binding_generation := OLD.binding_generation + 1;
    END IF;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS session_projects_classify_binding ON session_projects;
CREATE TRIGGER session_projects_classify_binding
    BEFORE INSERT OR UPDATE ON session_projects
    FOR EACH ROW
    EXECUTE FUNCTION session_projects_classify_binding();

-- Backfill: the trigger classifies every legacy row in place. updated_at and
-- project_name are left untouched.
UPDATE session_projects
SET binding_state = NULL
WHERE binding_state IS NULL;

ALTER TABLE session_projects
    ALTER COLUMN binding_generation SET DEFAULT 1,
    ALTER COLUMN binding_generation SET NOT NULL,
    ALTER COLUMN binding_state SET NOT NULL;

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

    -- Only a resolved binding carries a project key; an unresolved one carries
    -- a reason instead and is unusable for project-keyed writes.
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'session_projects'::regclass
          AND conname = 'session_projects_binding_state_consistent'
    ) THEN
        ALTER TABLE session_projects
            ADD CONSTRAINT session_projects_binding_state_consistent
            CHECK (
                (
                    binding_state = 'resolved'
                    AND project_key IS NOT NULL
                    AND binding_state_reason IS NULL
                )
                OR (
                    binding_state = 'unresolved'
                    AND project_key IS NULL
                    AND BTRIM(COALESCE(binding_state_reason, '')) <> ''
                )
            );
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
