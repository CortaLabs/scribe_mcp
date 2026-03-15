{% extends "documents/base_document.md" %}
{% set doc_title = metadata.title | default("Security Report") %}
{% set doc_icon = metadata.icon | default("🔒") %}
{% set doc_status = metadata.status | default("Investigating") %}
{% set doc_version = metadata.version | default("v0.1") %}
{% set doc_summary = metadata.summary | default("Document the discovery, analysis, and remediation plan for the reported security issue.") %}

{% block document_body %}
{% call section("Security Overview", "security_overview") %}
{% set slug = metadata.get("slug", "sec_" + (timestamp | replace(" ", "_"))) %}
**Case ID:** {{ slug }}

**Reported By:** {{ metadata.get("reporter", agent_id | default("Unknown Reporter")) }}

**Date Reported:** {{ metadata.get("reported_at", timestamp) }}

**Severity:** {{ metadata.get("severity", "high") | upper }}

**Status:** {{ metadata.get("status", "INVESTIGATING") | upper }}

**Component:** {{ metadata.get("component", "[Component or subsystem]") }}

**Environment:** {{ metadata.get("environment", "[local/staging/production]") }}

**Customer Impact:** {{ metadata.get("customer_impact", "[Describe impact or 'None']") }}

**CVE ID:** {{ metadata.get("cve_id", "[CVE-YYYY-NNNNN or N/A]") }}

**CVSS Score:** {{ metadata.get("cvss_score", "[0.0-10.0 or N/A]") }}
{% endcall %}

{% call section("Description", "description") %}
### Summary
{{ metadata.get("summary_long", "[Brief description of the security issue]") }}

### Expected Behaviour
{{ metadata.get("expected_behavior", "[What should happen]") }}

### Actual Behaviour
{{ metadata.get("actual_behavior", "[What actually happens — how is security violated]") }}

### Steps to Reproduce
{{ checklist(metadata.get("reproduction_steps"), "List reproducible steps for the security team.") }}
{% endcall %}

{% call section("Affected Systems", "affected_systems") %}
**Affected Areas:**
{{ bullet_list(metadata.get("affected_areas"), "List impacted services, components, or files.") }}

**Trust Boundary Violations:**
{{ metadata.get("trust_boundary", "[Describe which trust boundaries are crossed or violated]") }}

**Attack Vector:**
{{ metadata.get("attack_vector", "[local/network/adjacent — CVSS AV metric]") }}
{% endcall %}

{% call section("Investigation", "investigation") %}
**Root Cause Analysis:**
{{ metadata.get("root_cause", "[Describe suspected or confirmed root cause]") }}

**Related Issues:**
{{ bullet_list(metadata.get("related_issues"), "Link to related bugs, CVEs, or documentation.") }}

**Compliance Impact:**
{{ metadata.get("compliance_impact", "[GDPR, SOC2, PCI-DSS, HIPAA — list applicable frameworks]") }}
{% endcall %}

{% call section("Resolution Plan", "resolution_plan") %}
### Immediate Actions
{{ checklist(metadata.get("immediate_actions"), "Track urgent steps needed to mitigate the issue.") }}

### Mitigation Status
{{ metadata.get("mitigation_status", "[not-started/in-progress/mitigated/resolved]") }}

### Long-Term Fixes
{{ checklist(metadata.get("long_term_fixes"), "Outline long-term remedial work or hardening.") }}

### Testing Strategy
{{ checklist(metadata.get("testing_strategy"), "Define validation steps for the fix (security scan, pen test, regression).") }}
{% endcall %}

{% call section("Timeline & Ownership", "timeline") %}
| Phase | Owner | Target Date | Notes |
| --- | --- | --- | --- |
| Investigation | {{ metadata.get("owners", {}).get("investigation", "[Name]") }} | {{ metadata.get("timeline", {}).get("investigation", "[Date]") }} | {{ metadata.get("notes", {}).get("investigation", "[Details]") }} |
| Fix Development | {{ metadata.get("owners", {}).get("fix", "[Name]") }} | {{ metadata.get("timeline", {}).get("fix", "[Date]") }} | {{ metadata.get("notes", {}).get("fix", "[Details]") }} |
| Testing | {{ metadata.get("owners", {}).get("testing", "[Name]") }} | {{ metadata.get("timeline", {}).get("testing", "[Date]") }} | {{ metadata.get("notes", {}).get("testing", "[Details]") }} |
| Deployment | {{ metadata.get("owners", {}).get("deployment", "[Name]") }} | {{ metadata.get("timeline", {}).get("deployment", "[Date]") }} | {{ metadata.get("notes", {}).get("deployment", "[Details]") }} |
{% endcall %}

{% call section("Appendix", "appendix") %}
- **Logs & Evidence:** {{ metadata.get("logs", "[Link to relevant logs, traces, screenshots]") }}
- **Fix References:** {{ metadata.get("fix_references", "[Git commits, PRs, or documentation]") }}
- **Open Questions:** {{ metadata.get("open_questions", "[List unresolved unknowns or next investigations]") }}
{% endcall %}
{% endblock %}
