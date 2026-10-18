# Incident Drill

This drill demonstrates the two incident lanes while keeping one continuous Pocket Mission Control narrative.

## Lane A: Bug Case

```bash
open_bug(
  agent="scribe-doc-writer",
  title="Telemetry timestamp drift",
  symptoms="Mission event timeline appears out of order",
  category="logic"
)
```

Outcome:
- bug case is opened and documented

## Lane B: Security Case

```bash
open_security(
  agent="scribe-doc-writer",
  title="Unexpected public artifact path",
  symptoms="Generated artifact appeared outside the approved public docs boundary",
  category="security",
  customer_impact="Possible publication boundary violation"
)
```

Outcome:
- security case is opened for trust-boundary triage

## Resolution Link

```bash
link_fix(
  agent="scribe-doc-writer",
  case_id="BUG-0001",
  execution_id="exec-demo-001",
  artifact_ref="docs/examples/hello_world_scribe/publication_boundary.md:1",
  landing_status="documented"
)
```

Outcome:
- evidence chain links the fix artifact back to the case

## Drill Rule

Use this lane to teach incident flow, not to replace core onboarding. Incident tools are advanced operations by design.
