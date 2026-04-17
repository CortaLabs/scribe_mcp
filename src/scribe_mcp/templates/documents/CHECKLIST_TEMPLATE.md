{% extends "documents/base_document.md" %}
{% set doc_title = "Acceptance Checklist" %}
{% set doc_icon = "✅" %}
{% set doc_version = metadata.version | default("v0.1") %}
{% set doc_status = metadata.status | default("Draft") %}
{% set summary = metadata.summary | default("Mirror the Phase Plan here. Every task should map to a checkbox with proof (commit, log entry, screenshot, etc.).") %}
{% set sections = metadata.sections or [] %}

{% block document_body %}
{% if sections %}
  {% for section_block in sections %}
    {% set checklist_items = section_block["items"] if "items" in section_block else [] %}
    {% call section(section_block.title, section_block.anchor or ("section_" ~ loop.index0)) %}
{{ checklist(checklist_items, "Add verification tasks for " ~ section_block.title ~ ".") }}
    {% endcall %}
  {% endfor %}
{% else %}
{% call section("Documentation Hygiene", "documentation_hygiene") %}
- [ ] Confirm planning docs exist and use current project scope (proof: list the exact doc references).
- [ ] Confirm each checklist item maps to a phase package or milestone (proof: include section/item IDs).
{% endcall %}

{% call section("Phase 0", "phase_0") %}
- [ ] Add package-specific acceptance item with expected verification command (proof: test output or artifact path).
- [ ] Add package-specific regression guard (proof: targeted test or inspection evidence).
{% endcall %}

{% call section("Phase 1", "phase_1") %}
- [ ] Add phase-1 acceptance item with explicit proof format.
{% endcall %}

{% call section("Phase 2", "phase_2") %}
- [ ] Add phase-2 acceptance item with explicit proof format.
{% endcall %}
{% endif %}

{% call section("Final Verification", "final_verification") %}
- [ ] All checklist items checked with proofs attached.  
- [ ] Stakeholder sign-off recorded (name + date).  
- [ ] Retro completed and lessons learned documented.
{% endcall %}
{% endblock %}
