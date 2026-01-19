# Feature Flag Activation Guide - Stage 6

**Project:** scribe_tool_output_refinement
**Stage:** 6 - DB Mode Activation
**Date:** 2026-01-03
**Status:** Ready for Activation (flags currently OFF)

---

## Overview

This guide documents how to enable DB-backed reminder tracking with session-aware hashing. The infrastructure is fully implemented and tested, but feature flags remain OFF until explicit activation.

**Key Features When Enabled:**
- DB-backed cooldown tracking (replaces file-based `data/reminder_cooldowns.json`)
- Session-aware reminder hashing (reminders reset when `session_id` changes)
- 10-minute idle timeout for session reset
- Failure-priority reminders (failures bypass cooldowns)
- <5ms query performance SLA

---

## Feature Flags

### 1. `use_db_cooldown_tracking`

**Purpose:** Switch from file-based to DB-backed reminder cooldown tracking

**Location:** `config/reminder_config.json`

**Current Value:** `false` (default)

**How to Enable:**

```json
{
  "use_db_cooldown_tracking": true,
  "cooldown_minutes": 45,
  "session_timeout_minutes": 10
}
```

**Behavior When Enabled:**
- Reminder cooldown data stored in `scribe_reminder_history` table (SQLite)
- File `data/reminder_cooldowns.json` no longer written or read
- Session isolation: Each `session_id` has independent cooldown tracking
- Automatic cleanup of old reminder records (90-day retention)

**Expected Performance:**
- `record_reminder_shown()`: <2ms average
- `check_reminder_cooldown()`: <3ms average
- `cleanup_old_reminders()`: <50ms for 10,000+ records

---

### 2. `use_session_aware_hashes`

**Purpose:** Enable session-aware reminder hash generation

**Location:** `config/reminder_config.json`

**Current Value:** `false` (default)

**How to Enable:**

```json
{
  "use_session_aware_hashes": true,
  "session_timeout_minutes": 10
}
```

**Behavior When Enabled:**
- Reminder hashes include `session_id` as input
- Different sessions get different hashes (session isolation)
- 10-minute idle timeout resets session (new `session_id` generated)
- Teaching reminders and doc hygiene reminders respect session boundaries

**Session Reset Conditions:**
1. **Idle Timeout:** No tool calls for 10 minutes (configurable)
2. **Explicit Reset:** User restarts MCP server
3. **Context Switch:** User switches projects via `set_project()`

---

## Activation Procedure

### Prerequisites

- [ ] All 35+ tests passing (Stages 1-5 foundation + failure priority)
- [ ] Performance benchmarks showing <5ms queries
- [ ] Session isolation validated via tests
- [ ] No outstanding bugs or regressions

### Step-by-Step Activation

**1. Backup Current State (5 minutes)**

```bash
# Backup file-based cooldown cache
cp data/reminder_cooldowns.json data/reminder_cooldowns.json.backup_$(date +%Y%m%d_%H%M%S)

# Backup config
cp config/reminder_config.json config/reminder_config.json.backup_$(date +%Y%m%d_%H%M%S)
```

**2. Enable Feature Flags (2 minutes)**

Edit `config/reminder_config.json`:

```json
{
  "use_db_cooldown_tracking": true,
  "use_session_aware_hashes": true,
  "cooldown_minutes": 45,
  "session_timeout_minutes": 10,
  "reminder_warning_minutes": 15,
  "teaching_reminder_limit": 3
}
```

**3. Verify Configuration (1 minute)**

```bash
# Check config syntax
python -c "import json; json.load(open('config/reminder_config.json'))"
```

**4. Run Validation Tests (10 minutes)**

```bash
# Run all activation tests
pytest tests/test_db_activation.py -v

# Run full test suite
pytest tests/ -v

# Expected: All tests pass (35+ tests)
```

**5. Performance Benchmark (5 minutes)**

```bash
# Run performance tests
pytest tests/test_db_activation.py::test_db_mode_performance_benchmark -v

# Expected: All queries <5ms p95
```

**6. Monitor Startup (2 minutes)**

```bash
# Start server and watch logs
python -m server 2>&1 | tee activation_logs_$(date +%Y%m%d_%H%M%S).log

# Expected: No errors, DB mode detected and activated
```

**7. Integration Test (5 minutes)**

```bash
# Run a few tool calls and verify DB is being used
# Check scribe_reminder_history table for new records
sqlite3 .scribe/data/scribe.db "SELECT COUNT(*) FROM scribe_reminder_history WHERE created_at > datetime('now', '-5 minutes');"

# Expected: Records appearing in DB, not in file
```

---

## Validation Checklist

After activation, verify:

- [ ] `scribe_reminder_history` table receiving new records
- [ ] `data/reminder_cooldowns.json` NOT being updated
- [ ] Session isolation working (different `session_id` = different hashes)
- [ ] Failure reminders bypass cooldowns correctly
- [ ] Success reminders respect cooldowns
- [ ] Teaching reminders limited to 3 per session
- [ ] No performance degradation (<5ms queries)
- [ ] No errors in logs

---

## Rollback Procedure

If issues are detected, rollback immediately:

### Quick Rollback (5 minutes)

**1. Disable Feature Flags**

Edit `config/reminder_config.json`:

```json
{
  "use_db_cooldown_tracking": false,
  "use_session_aware_hashes": false,
  "cooldown_minutes": 45,
  "session_timeout_minutes": 10
}
```

**2. Restore File-Based Cache (if needed)**

```bash
# Restore backup
cp data/reminder_cooldowns.json.backup_* data/reminder_cooldowns.json

# Or use most recent backup
ls -t data/reminder_cooldowns.json.backup_* | head -1 | xargs -I {} cp {} data/reminder_cooldowns.json
```

**3. Restart Server**

```bash
# Kill existing server
pkill -f "python -m server"

# Restart
python -m server
```

**4. Verify Rollback**

```bash
# Check that file is being written again
ls -lh data/reminder_cooldowns.json

# Should show recent modification time
```

---

## Performance Expectations

### Query Performance SLA

| Operation | Target | Acceptable Max |
|-----------|--------|----------------|
| `record_reminder_shown()` | <2ms | 5ms |
| `check_reminder_cooldown()` | <2ms | 5ms |
| `cleanup_old_reminders()` | <50ms | 100ms |
| Session hash generation | <1ms | 2ms |

### Memory Impact

- **DB Mode:** ~10KB overhead per 1000 reminder records
- **Session Tracking:** ~1KB per active session
- **Total Expected:** <100KB additional memory usage

### Disk Impact

- **DB Growth:** ~500 bytes per reminder record
- **Cleanup:** 90-day retention (automatic cleanup)
- **Expected DB Size:** 1-5MB for typical usage

---

## Monitoring Recommendations

### During First 48 Hours

**Monitor These Metrics:**

1. **Query Performance**
   - Check slow query logs (>5ms warnings)
   - Run `validate_db_performance()` every 6 hours
   - Alert if p95 exceeds 5ms

2. **Session Isolation**
   - Verify different sessions have different hashes
   - Run `validate_session_isolation()` daily
   - Check for hash collisions in logs

3. **Error Rates**
   - Monitor for DB errors in logs
   - Check for reminder delivery failures
   - Alert on any DB connection issues

4. **Reminder Delivery**
   - Verify reminders still showing correctly
   - Check that failures bypass cooldowns
   - Confirm teaching reminders limited properly

### Monitoring Commands

```bash
# Performance validation
python -c "from utils.reminder_monitoring import validate_db_performance; import asyncio; print(asyncio.run(validate_db_performance()))"

# Session isolation check
python -c "from utils.reminder_monitoring import validate_session_isolation; import asyncio; print(asyncio.run(validate_session_isolation()))"

# Statistics
python -c "from utils.reminder_monitoring import get_reminder_statistics; import asyncio; print(asyncio.run(get_reminder_statistics()))"
```

---

## Known Behaviors

### Session Reset Behavior

**10-Minute Idle Timeout:**
- After 10 minutes of no tool calls, session resets
- New `session_id` generated on next tool call
- All teaching reminder counters reset
- Cooldown tracking starts fresh for new session

**Implications:**
- Teaching reminders may show again after idle timeout (by design)
- Doc hygiene reminders respect new session boundaries
- Failure reminders still bypass cooldowns (not affected by session)

### Backward Compatibility

**Feature Flags OFF (default):**
- File-based cooldown tracking used
- Global (non-session-aware) hashing
- Original behavior preserved

**Feature Flags ON:**
- DB-backed tracking
- Session-aware hashing
- Enhanced isolation and performance

**Migration Path:**
- Safe to enable flags without data loss
- Safe to disable flags (rollback)
- No data migration required (dual-mode support)

---

## Troubleshooting

### Issue: Reminders Not Showing

**Symptoms:** No reminders appear in tool responses

**Diagnosis:**
1. Check `scribe_reminder_history` table for records
2. Verify `cooldown_minutes` not set too high
3. Check session isolation not blocking unexpectedly

**Fix:**
```bash
# Clear cooldown history (nuclear option)
sqlite3 .scribe/data/scribe.db "DELETE FROM scribe_reminder_history WHERE created_at < datetime('now', '-1 hour');"
```

### Issue: Performance Degradation

**Symptoms:** Queries taking >5ms consistently

**Diagnosis:**
```bash
# Run performance benchmark
pytest tests/test_db_activation.py::test_db_mode_performance_benchmark -v

# Check DB indexes
sqlite3 .scribe/data/scribe.db ".schema scribe_reminder_history"
```

**Fix:**
- Ensure indexes exist on `session_id`, `reminder_hash`, `created_at`
- Run `VACUUM` on database if fragmented
- Consider cleanup of old records

### Issue: Session Not Resetting

**Symptoms:** Teaching reminders not resetting after idle timeout

**Diagnosis:**
1. Check `session_timeout_minutes` config value
2. Verify idle detection working
3. Check session ID changing in logs

**Fix:**
- Verify config: `"session_timeout_minutes": 10`
- Check state file: `.scribe/tmp_state/state.json` for last access time
- Manually reset: Delete state file and restart

---

## Next Steps After Activation

**Immediate (First 48 Hours):**
- [ ] Monitor performance metrics continuously
- [ ] Check error logs every 6 hours
- [ ] Run validation tests daily
- [ ] Be ready for immediate rollback

**Short Term (First 2 Weeks):**
- [ ] Continue performance monitoring
- [ ] Collect user feedback on behavior
- [ ] Verify no regression in reminder utility
- [ ] Document any unexpected behaviors

**Stage 7 Preparation (After 2 Weeks):**
- [ ] Validate stable operation
- [ ] Approve cleanup of legacy file-based code
- [ ] Schedule Stage 7 (Cleanup) implementation
- [ ] Update documentation for DB-only mode

---

## References

- **Architecture:** `ARCHITECTURE_GUIDE.md` Section 9
- **Phase Plan:** `PHASE_PLAN.md` Phase 6, Stage 6
- **Tests:** `tests/test_db_activation.py`
- **Monitoring:** `utils/reminder_monitoring.py`
- **Checklist:** `ACTIVATION_CHECKLIST.md`

---

**Status:** Infrastructure ready, flags OFF, awaiting activation approval

**Confidence:** 0.95 (based on 35+ tests passing, performance benchmarks validated)
