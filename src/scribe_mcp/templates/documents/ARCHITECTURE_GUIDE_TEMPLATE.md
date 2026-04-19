{% extends "documents/base_document.md" %}
{% set doc_title = "Architecture Guide" %}
{% set doc_icon = "🏗️" %}
{% set product = product_name | default(project_name or "this project") %}
{% set summary = metadata.get("summary", "Document the " ~ product ~ " system intent, constraints, configuration model, and operational expectations so contributors can implement safely.") %}
{% set problem = metadata.get("problem_statement", {}) %}
{% set requirements = metadata.get("requirements", {}) %}
{% set overview = metadata.get("architecture_overview", {}) %}
{% set components = overview.get("components") or metadata.get("components") %}
{% set data_design = metadata.get("data_storage", {}) %}
{% set testing = metadata.get("testing_strategy", {}) %}
{% set deployment = metadata.get("deployment", {}) %}
{% set questions = metadata.get("open_questions", []) %}

{% block document_body %}
{% call section("1. Problem Statement", "problem_statement") %}
- **Context:** {{ problem.context | default("Why does " ~ product ~ " exist, who benefits, and what operational problem are we solving?") }}
- **Goals:**
{{ bullet_list(problem.get("goals"), "Bullet the concrete outcomes we must achieve.") }}
- **Non-Goals:**
{{ bullet_list(problem.get("non_goals"), "Explicitly list what is out of scope.") }}
- **Success Metrics:**
{{ bullet_list(problem.get("success_metrics"), "How will we measure impact?") }}
{% endcall %}

{% call section("2. Requirements & Constraints", "requirements_constraints") %}
- **Functional Requirements:**
{{ bullet_list(requirements.get("functional"), "Capture the required capabilities, including runtime behavior, generated docs, configuration surfaces, and template override flows.") }}
- **Non-Functional Requirements:**
{{ bullet_list(requirements.get("non_functional"), "List performance, reliability, and compliance expectations.") }}
- **Assumptions:**
{{ bullet_list(requirements.get("assumptions"), "Document dependencies and environmental expectations.") }}
- **Risks & Mitigations:**
{{ bullet_list(requirements.get("risks"), "Pair each risk with a mitigation strategy.") }}
{% endcall %}

{% call section("3. Architecture Overview", "architecture_overview") %}
- **Solution Summary:** {{ overview.summary | default("Provide two to three paragraphs summarising the design, trade-offs, and desired state for " ~ product ~ ".") }}
- **Component Breakdown:**
{% if components %}
  {% for component in components %}
  - **{{ component.name | default("Component") }}:** {{ component.description | default("Describe responsibilities, inputs, and outputs.") }}
    {% if component.interfaces %}
      - Interfaces: {{ component.interfaces }}
    {% endif %}
    {% if component.notes %}
      - Notes: {{ component.notes }}
    {% endif %}
  {% endfor %}
{% else %}
- Enumerate major services/modules and explain how they collaborate, including any repo-local override or configuration boundaries that matter.
{% endif %}
- **Data Flow:** {{ overview.data_flow | default("Narrate how data moves through the system (include diagrams/links when available).") }}
- **External Integrations:** {{ overview.external_integrations | default("List APIs, queues, webhooks, or third-party systems relied upon.") }}
{% endcall %}

{% call section("4. Detailed Design", "detailed_design") %}
For each subsystem:
{% if metadata.get("subsystems") %}
  {% for subsystem in metadata.get("subsystems", []) %}
1. **{{ subsystem.name }}**
   - **Purpose:** {{ subsystem.purpose | default("Explain why this subsystem exists.") }}
   - **Interfaces:** {{ subsystem.interfaces | default("Describe inputs/outputs, schemas, events.") }}
   - **Implementation Notes:** {{ subsystem.notes | default("List algorithms, patterns, libraries, and constraints.") }}
   - **Error Handling:** {{ subsystem.error_handling | default("Document failure modes and recovery strategy.") }}
  {% endfor %}
{% else %}
1. **Purpose** – why it exists.  
2. **Interfaces** – inputs, outputs, data contracts, schemas.  
3. **Implementation Notes** – libraries, algorithms, patterns.  
4. **Error Handling** – failure modes and recovery strategy.
{% endif %}
{% endcall %}

{% call section("5. Directory Structure (Keep Updated)", "directory_structure") %}
{% if metadata.get("directory_structure") %}
```
{{ metadata.get("directory_structure") }}
```
{% else %}
{% include "fragments/directory_structure.md" %}
{% endif %}
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.
{% endcall %}

{% call section("6. Data & Storage", "data_storage") %}
- **Datastores:** {{ data_design.datastores | default("List databases/tables/collections with schema snapshots.") }}
- **Indexes & Performance:** {{ data_design.indexing | default("Outline indexing strategy, retention, archival plans.") }}
- **Migrations:** {{ data_design.migrations | default("Describe migration ordering, verification, and rollback.") }}
{% endcall %}

{% call section("7. Testing & Validation Strategy", "testing_strategy") %}
- **Unit Tests:** {{ testing.unit | default("Scope and coverage targets for core logic, config precedence, and template/rendering behavior.") }}
- **Integration Tests:** {{ testing.integration | default("Required environments, fixtures, or data sets, including real repo-root override flows where relevant.") }}
- **Manual QA:** {{ testing.manual | default("Exploratory plans or acceptance walkthroughs.") }}
- **Observability:** {{ testing.observability | default("Logging, metrics, tracing, alerting expectations.") }}
{% endcall %}

{% call section("8. Deployment & Operations", "deployment_operations") %}
- **Environments:** {{ deployment.environments | default("Describe dev/staging/prod differences.") }}
- **Release Process:** {{ deployment.release | default("Automation, approvals, rollback.") }}
- **Configuration Management:** {{ deployment.config | default("Secrets, feature flags, runtime toggles.") }}
- **Maintenance & Ownership:** {{ deployment.ownership | default("On-call rotations, SLOs, future work.") }}
{% endcall %}

{% call section("9. Open Questions & Follow-Ups", "open_questions") %}
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
{% if questions %}
  {% for item in questions %}
| {{ item.item | default(item.title | default("Describe the open question")) }} | {{ item.owner | default("TBD") }} | {{ item.status | default("TODO") }} | {{ item.notes | default("Capture decisions, blockers, or research tasks.") }} |
  {% endfor %}
{% else %}
| What decision is pending? | Owner | TODO | Capture decisions, blockers, or research tasks. |
{% endif %}
Close each question once answered and reference the relevant section above.
{% endcall %}

{% call section("10. References & Appendix", "references_appendix") %}
{{ bullet_list(metadata.get("references"), "Link to diagrams, ADRs, research notes, or external specs.") }}
{% if metadata.get("appendix") %}
{{ metadata.get("appendix") }}
{% endif %}
{% endcall %}
{% endblock %}
