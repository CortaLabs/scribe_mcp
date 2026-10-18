# Review Report: {{ (stage | default(metadata.stage | default("stage_unspecified"))).replace('_', ' ').title() }} Stage

{% set stage_value = stage | default(metadata.stage | default("stage_unspecified")) %}
{% set review_timestamp = timestamp | default(date_utc | default("1970-01-01 00:00:00 UTC")) %}
{% set reviewer_name = agent_id | default(author | default("Scribe Reviewer")) %}
{% set review_project = project_name | default(PROJECT_NAME | default("Unknown Project")) %}
**Review Date:** {{ review_timestamp }}
**Reviewer:** {{ reviewer_name }}
**Project:** {{ review_project }}
**Stage:** {{ stage_value }}
{% set review_type = "Pre-Implementation" if stage_value.startswith("Stage") else "Post-Implementation" %}
**Review Type:** {{ review_type }}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Decision:** {{ overall_decision | default(metadata.overall_decision | default('REQUIRES_REVISION')) }}

**Confidence Level:** {{ confidence_level | default(metadata.confidence_level | default('Medium')) }}

**Key Findings:**
- [ ] {{ key_finding_1 | default('Finding 1') }}
- [ ] {{ key_finding_2 | default('Finding 2') }}
- [ ] {{ key_finding_3 | default('Finding 3') }}

---

<!-- ID: phase_review_results -->
## Phase Review Results

### Research Phase Review
**Grade:** {{ research_grade | default('Not graded') }}
**Status:** {{ research_status | default('CONDITIONAL') }}

**Findings:**
- [ ] {{ research_finding_1 | default('Research completeness assessment') }}
- [ ] {{ research_finding_2 | default('Technical accuracy validation') }}
- [ ] {{ research_finding_3 | default('Evidence quality evaluation') }}
- [ ] {{ research_finding_4 | default('Cross-project validation results') }}

### Architecture Phase Review
**Grade:** {{ architecture_grade | default('Not graded') }}
**Status:** {{ architecture_status | default('CONDITIONAL') }}

**Findings:**
- [ ] {{ architecture_finding_1 | default('Design feasibility assessment') }}
- [ ] {{ architecture_finding_2 | default('Implementation readiness evaluation') }}
- [ ] {{ architecture_finding_3 | default('Risk management review') }}
- [ ] {{ architecture_finding_4 | default('Plan completeness validation') }}

---

<!-- ID: detailed_analysis -->
## Detailed Analysis

### Technical Validation
- [ ] {{ technical_validation_1 | default('Architecture decisions are sound and implementable') }}
- [ ] {{ technical_validation_2 | default('Implementation approach follows established patterns') }}
- [ ] {{ technical_validation_3 | default('Dependencies and constraints are properly addressed') }}
- [ ] {{ technical_validation_4 | default('Performance and scalability considerations') }}

### Quality Assurance
- [ ] {{ quality_assurance_1 | default('Documentation completeness and accuracy') }}
- [ ] {{ quality_assurance_2 | default('Testing strategy adequacy') }}
- [ ] {{ quality_assurance_3 | default('Error handling and edge cases') }}
- [ ] {{ quality_assurance_4 | default('Code quality and maintainability') }}

### Risk Assessment
- [ ] {{ risk_assessment_1 | default('Technical risks identified and mitigated') }}
- [ ] {{ risk_assessment_2 | default('Implementation timeline feasibility') }}
- [ ] {{ risk_assessment_3 | default('Resource requirements validation') }}
- [ ] {{ risk_assessment_4 | default('Rollback and contingency planning') }}

---

<!-- ID: recommendations -->
## Recommendations

### Immediate Actions
- [ ] {{ immediate_action_1 | default('Capture reviewer-approved remediation tasks.') }}
- [ ] {{ immediate_action_2 | default('Assign owners and due dates for each remediation task.') }}

### Implementation Requirements
- [ ] {{ implementation_requirement_1 | default('Define verification commands and expected results.') }}
- [ ] {{ implementation_requirement_2 | default('Confirm bounded scope and dependency ownership.') }}

### Next Steps
- [ ] {{ next_step_1 | default('Proceed to implementation (if approved)') }}
- [ ] {{ next_step_2 | default('Address identified issues (if rejected)') }}
- [ ] {{ next_step_3 | default('Additional validation (if conditional)') }}

---

<!-- ID: agent_performance_assessment -->
## Agent Performance Assessment

| Agent | Role | Grade | Comments |
|-------|------|-------|----------|
| Research Analyst | Research | {{ research_agent_grade | default('Not graded') }} | {{ research_agent_comments | default('No research-specific grading recorded in this report.') }} |
| Architect | Architecture | {{ architect_agent_grade | default('Not graded') }} | {{ architect_agent_comments | default('No architecture-specific grading recorded in this report.') }} |
| Coder | Implementation | {{ coder_agent_grade | default('Not graded') }} | {{ coder_agent_comments | default('Implementation grading deferred or not applicable.') }} |
| Reviewer | Review | {{ reviewer_agent_grade | default('Not graded') }} | {{ reviewer_agent_comments | default('Reviewer self-assessment not provided.') }} |

---

<!-- ID: compliance_verification -->
## Compliance Verification

**Scribe Protocol Compliance:** {{ protocol_compliance | default('PARTIALLY_COMPLIANT') }}

- [ ] {{ compliance_check_1 | default('Minimum logging requirements met') }}
- [ ] {{ compliance_check_2 | default('Documentation standards followed') }}
- [ ] {{ compliance_check_3 | default('Quality gate procedures completed') }}
- [ ] {{ compliance_check_4 | default('Cross-project validation performed') }}

---

<!-- ID: final_decision -->
## Final Decision

**{{ final_decision | default('REQUIRES_REVISION') }}**

**Rationale:** {{ rationale | default('Decision rationale should reference concrete evidence from findings and verification.') }}

**Conditions for Proceeding:**
- [ ] {{ condition_1 | default('Complete required remediation tasks and capture verification evidence.') }}
- [ ] {{ condition_2 | default('Re-run applicable validation and document outcome in the managed report.') }}

**Expected Timeline:** {{ expected_timeline | default('To be confirmed by owner after remediation scope review.') }}

---

*This review report is part of the quality assurance process for {{ project_name }}.*
