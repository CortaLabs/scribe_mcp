{% extends "documents/base_document.md" %}
{% set doc_title = "Phase Plan" %}
{% set doc_icon = "⚙️" %}
{% set summary = metadata.summary | default("Break the architecture into reviewable execution phases tied to checklist items and measurable outcomes.") %}
{% set phases = metadata.phases or [] %}
{% set milestones = metadata.milestones or [] %}

{% block document_body %}
{% call section("Phase Overview", "phase_overview") %}
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
{% if phases %}
  {% for phase in phases %}
| {{ phase.name | default("Phase " ~ loop.index0) }} | {{ phase.goal | default("State the objective for this phase.") }} | {{ (phase.deliverables or []) | join(", ") | default("List the tangible outputs.") }} | {{ "%.2f"|format(phase.confidence | default(0.7)) }} |
  {% endfor %}
{% else %}
| Phase N | Define scoped objective | List the concrete deliverables for this phase | 0.70 |
| Next Phase | Define scoped objective | List the concrete deliverables for this phase | 0.70 |
{% endif %}
Update this table as the project evolves. Confidence values should change as knowledge increases.
{% endcall %}

{% if phases %}
  {% for phase in phases %}
    {% set anchor = phase.anchor or ("phase_" ~ loop.index0) %}
    {% call section("Phase " ~ loop.index0 ~ " — " ~ (phase.name | default("Name Me")), anchor) %}
**Objective:** {{ phase.goal | default("Summarise the measurable outcome.") }}

**Key Tasks:**
{{ bullet_list(phase.tasks, "List actionable tasks for this phase.") }}

**Deliverables:**
{{ bullet_list(phase.deliverables, "Describe the artifacts that will be produced.") }}

**Acceptance Criteria:**
{{ checklist(phase.acceptance, "Spell out the checks that prove the phase succeeded.") }}

**Dependencies:** {{ phase.dependencies | default("List upstream teams, systems, or sequencing constraints.") }}

**Notes:** {{ phase.notes | default("Capture risks, blockers, or decisions specific to this phase.") }}
    {% endcall %}
  {% endfor %}
{% else %}
{% call section("Phase 0 — Define First Implementation Slice", "phase_0") %}
**Objective:** Describe the first bounded outcome this project must deliver.

**Key Tasks:**
- [ ] Add concrete task 1 with a measurable result.
- [ ] Add concrete task 2 with a measurable result.
- [ ] Add concrete task 3 with a measurable result.

**Deliverables:**
- Artifact or behavior shipped for this phase.
- Verification evidence linked to tests/logs/commits.

**Acceptance Criteria:**
- [ ] Criteria 1 states how success is proven.
- [ ] Criteria 2 states what evidence is required.

**Dependencies:** List any upstream constraints or prerequisites.  
**Notes:** Capture decisions, assumptions, or risks for this phase.
{% endcall %}

{% call section("Phase 1 — Next Bounded Slice", "phase_1") %}
Reuse the structure above for additional phases. Keep each phase independently verifiable.
{% endcall %}
{% endif %}

{% call section("Milestone Tracking", "milestone_tracking") %}
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
{% if milestones %}
  {% for m in milestones %}
| {{ m.name | default("Milestone") }} | {{ m.target | default("YYYY-MM-DD") }} | {{ m.owner | default("Owner") }} | {{ m.status | default("⏳ Planned") }} | {{ m.evidence | default("Link to PROGRESS_LOG entry or commit") }} |
  {% endfor %}
{% else %}
| Milestone name | YYYY-MM-DD | Owner | ⏳ Planned | Link to proof artifact |
{% endif %}
Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.
{% endcall %}

{% call section("Retro Notes & Adjustments", "retro_notes") %}
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.
{% endcall %}
{% endblock %}
