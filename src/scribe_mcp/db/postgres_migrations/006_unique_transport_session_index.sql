-- One-time conversion of idx_scribe_sessions_transport to a partial UNIQUE index.
--
-- This used to run from init.sql on EVERY server start: it nulled duplicate
-- transport_session_id values, dropped the index and re-created it. Codex starts
-- one scribe-server per subagent thread, and two concurrent starts raced the
-- DROP/CREATE pair; the loser exited 1 before MCP initialize and its thread ran
-- with no Scribe tools (BUG-2026-09-13-0002). It also rebuilt a unique index
-- under live session traffic on every start. The conversion is a migration now,
-- recorded in scribe_migrations and applied once under the bootstrap lock.
WITH ranked AS (
    SELECT
        ctid,
        ROW_NUMBER() OVER (
            PARTITION BY transport_session_id
            ORDER BY last_active_at DESC NULLS LAST, started_at DESC NULLS LAST, session_id DESC
        ) AS rn
    FROM scribe_sessions
    WHERE transport_session_id IS NOT NULL
)
UPDATE scribe_sessions AS s
SET transport_session_id = NULL
FROM ranked
WHERE s.ctid = ranked.ctid
  AND ranked.rn > 1;

DROP INDEX IF EXISTS idx_scribe_sessions_transport;
CREATE UNIQUE INDEX IF NOT EXISTS idx_scribe_sessions_transport
    ON scribe_sessions (transport_session_id)
    WHERE transport_session_id IS NOT NULL;
