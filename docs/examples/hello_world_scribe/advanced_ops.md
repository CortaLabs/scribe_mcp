# Advanced Ops

Mission state has graduated from launch to operations.

## Ops Check 1: Reminder Intelligence

```bash
query_reminders(agent="scribe-doc-writer", project="hello_world_scribe_20260418")
```

Purpose:
- observe pending/history reminder behavior without reconfiguring policy

Why configuration is deferred:
- `configure_reminders` and `reset_reminders` are admin controls and live in appendix coverage.

## Ops Check 2: Environment And Runtime Diagnostics

```bash
scribe_doctor(agent="scribe-doc-writer")
```

Purpose:
- inspect health, runtime configuration, and tooling status before incidents

## Ops Posture

At this point, Pocket Mission Control can:
- observe schedule pressure via reminders
- validate platform condition with doctor diagnostics
- move into formal incident drill workflows when needed
