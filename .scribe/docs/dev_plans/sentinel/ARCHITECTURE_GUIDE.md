
# 🏗️ Architecture Guide — sentinel
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-03 09:14:29 UTC

> Architecture guide for sentinel.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** sentinel needs a reliable documentation system.
- **Goals:**
- Eliminate silent failures- Improve template flexibility
- **Non-Goals:**
- Define UI/UX beyond documentation
- **Success Metrics:**
- All manage_docs operations verified- Templates easy to customize


---
## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
- Atomic document updates- Jinja2 templates with inheritance
- **Non-Functional Requirements:**
- Backwards-compatible file layout- Sandboxed template rendering
- **Assumptions:**
- Filesystem read/write access- Python runtime available
- **Risks & Mitigations:**
- User edits outside manage_docs- Template misuse causing errors


---
## 3. Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Document manager orchestrates template rendering and writes.
- **Component Breakdown:**
  - **Doc Manager:** Validates sections and applies atomic writes.
      - Interfaces: manage_docs tool
      - Notes: Provides verification and logging.
  - **Template Engine:** Renders templates via Jinja2 with sandboxing.
      - Interfaces: Jinja2 environment
      - Notes: Supports project/local overrides.
- **Data Flow:** User -> manage_docs -> template engine -> filesystem/database.
- **External Integrations:** SQLite mirror, git history.


---
## 4. Detailed Design
<!-- ID: detailed_design -->
For each subsystem:
1. **Doc Change Pipeline**
   - **Purpose:** Coordinate apply/verify steps.
   - **Interfaces:** Atomic writer, storage backend
   - **Implementation Notes:** Async aware
   - **Error Handling:** Rollback on verification failure


---
## 5. Directory Structure (Keep Updated)
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/sentinel
```
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.


---
## 6. Data & Storage
<!-- ID: data_storage -->
- **Datastores:** ['Filesystem markdown', 'SQLite mirror']
- **Indexes & Performance:** FTS for sections
- **Migrations:** Sequential migrations tracked in storage layer


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Unit Tests:** Template rendering + doc ops
- **Integration Tests:** manage_docs tool exercises real files
- **Manual QA:** Project review after each release
- **Observability:** Structured logging via doc_updates log


---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md- ARCHITECTURE_GUIDE.md
Generated via generate_doc_templates.


---