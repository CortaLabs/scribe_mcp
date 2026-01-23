---
id: scribe_codebase_audit-research-security-audit-20260123
title: "\U0001F52C Research Security Audit 20260123 \u2014 scribe_codebase_audit"
doc_name: RESEARCH_SECURITY_AUDIT_20260123
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-23'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Security Audit 20260123 — scribe_codebase_audit
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-23 05:16:33 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Overall Risk Rating: MEDIUM-HIGH**

The Scribe MCP codebase demonstrates security-conscious design in several areas (parameterized SQL queries, confirmation requirements for destructive operations, sandbox module with robust protections). However, a **critical architectural gap** exists: the robust security sandbox (`security/sandbox.py`) is NOT integrated with the `read_file` tool, which uses a weaker custom path policy that lacks protections against symlink attacks, null byte injection, and URL-encoded path traversal.

**Primary Objective:** Comprehensive security audit of Scribe MCP codebase

**Key Takeaways:**
- CRITICAL: read_file.py bypasses security/sandbox.py module entirely
- HIGH: Jinja2 autoescape disabled by default
- MEDIUM: Unpinned dependency versions, unrestricted template mode default
- GOOD: SQL injection protection via parameterized queries
- GOOD: Proper confirmation requirements for destructive operations
- GOOD: Session isolation with proper database schema

| Category | Risk Level | Status |
|----------|------------|--------|
| SQL Injection | LOW | Parameterized queries used throughout |
| Path Traversal | **CRITICAL** | read_file.py bypasses security sandbox |
| Input Validation | LOW | JSON parsing has proper error handling |
| Session Handling | LOW | Proper isolation, self-declared agent IDs |
| Sensitive Data | LOW | No credentials in logs found |
| Dependencies | MEDIUM | Unpinned versions, Jinja2 autoescape off |
| Template Injection | MEDIUM | Sandbox modes available but not default |
<!-- ID: research_scope -->
**Research Lead:** Scribe

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
### Finding 1: [CRITICAL] read_file.py Does Not Use Security Sandbox

**Location:** `tools/read_file.py` lines 106-136, 1730-1734, 1797

**Summary:** The `read_file` tool implements its own `_enforce_path_policy()` function instead of using the robust `security/sandbox.py` module. This creates a significant security gap.

**Missing Protections in read_file.py:**
- No symlink blocking (sandbox.py blocks ALL symlinks at line 82-83)
- No null byte injection check (sandbox.py checks at line 64)
- No URL-encoded traversal pattern detection (sandbox.py checks at line 74)
- Uses `.resolve()` which follows symlinks BEFORE policy check

**Evidence:** Grep search for sandbox imports in read_file.py returned no matches. Code review confirmed `_enforce_path_policy` lacks protections present in `PathSandbox.is_allowed()`.

**Attack Vector:**
1. Attacker creates symlink inside repo pointing to `/etc/passwd` or `~/.ssh/id_rsa`
2. `read_file` resolves the symlink to target file
3. If `allow_outside_repo=True` or target matches allowlist, access is granted

**Confidence:** HIGH (0.95)
**Severity:** CRITICAL
**CVSS Estimate:** 7.5

---

### Finding 2: [HIGH] Jinja2 Template Engine - Autoescape Disabled

**Location:** `template_engine/engine.py` line 224

**Summary:** Default configuration has `autoescape=False`. If user-controlled input is rendered through templates, this enables XSS attacks.

**Evidence:**
```python
common_kwargs = dict(
    loader=FileSystemLoader([str(d) for d in self.template_dirs]),
    autoescape=False,  # <-- XSS RISK
    ...
)
```

**Mitigating Factors:**
- Templates are primarily for Markdown documentation, not HTML
- `include_file()` function has proper path traversal protection (lines 282-284)
- Sandbox modes (`sandbox`, `immutable`) are available

**Confidence:** HIGH (0.85)
**Severity:** HIGH (if HTML output) / MEDIUM (current Markdown-only use)

---

### Finding 3: [MEDIUM] Unpinned Dependency Versions

**Location:** `requirements.txt`

**Summary:** All dependencies use minimum version constraints (`>=`) rather than pinned versions, creating supply chain risk.

**Evidence:**
```
asyncpg>=0.29
jinja2>=3.1.0
faiss-cpu>=1.7.0
```

**Confidence:** HIGH (0.8)
**Severity:** MEDIUM

---

### Finding 4: [LOW] delete_project archive_path User-Controlled

**Location:** `tools/delete_project.py` line 146-147

**Summary:** The `archive_path` parameter is user-controlled and used as destination without validation.

**Mitigating Factors:**
- Requires `confirm=True` to proceed
- Only writes archives, doesn't read/execute
- Root validation exists for deletion source

**Confidence:** HIGH (0.9)
**Severity:** LOW

---

### Positive Findings

**SQL Injection Protection - GOOD:**
All database queries in `storage/sqlite.py`, `storage/postgres.py`, and `db/ops.py` use parameterized queries with `?` or `$1` placeholders.

**Security Sandbox Module - GOOD (but underutilized):**
`security/sandbox.py` has robust protections: null byte blocking, URL-encoded traversal blocking, symlink blocking, deny-by-default. Problem: Not integrated with read_file.py.

**Confirmation Requirements - GOOD:**
`delete_project` requires explicit `confirm=True` and validates root path against project record.
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps (Critical)

- [ ] **Integrate security/sandbox.py into read_file.py** - Replace `_enforce_path_policy` with `PathSandbox.is_allowed()`. The module exists and works, it just needs to be imported and used.

**Recommended Code Change:**
```python
# In read_file.py, replace _enforce_path_policy with:
from scribe_mcp.security.sandbox import get_safety_instance

sandbox = get_safety_instance().get_sandbox(repo_root)
if not sandbox.is_allowed(target):
    return {"ok": False, "error": "Access denied by security sandbox"}
```

### Short-Term (High Priority)

- [ ] Pin dependency versions in requirements.txt or create requirements.lock
- [ ] Change default template security_mode from "none" to "sandbox"
- [ ] Enable autoescape if HTML output is ever added to templates
- [ ] Validate archive_path in delete_project stays within repo boundaries

### Long-Term Opportunities

- Implement dependency scanning in CI/CD pipeline
- Document security modes for operators in user-facing docs
- Security audit of plugin system (plugins can execute arbitrary code)
- Consider agent token signing if cross-agent security becomes important
- Regular penetration testing schedule
<!-- ID: appendix -->
### Files Examined

| File | Lines | Security Relevance |
|------|-------|-------------------|
| storage/sqlite.py | 2666 | SQL queries, session management |
| storage/postgres.py | 260 | SQL queries |
| db/ops.py | 435 | PostgreSQL query construction |
| tools/read_file.py | 2299 | Path traversal, file access |
| security/sandbox.py | 364 | Security controls (NOT INTEGRATED) |
| tools/delete_project.py | 236 | Destructive operations |
| template_engine/engine.py | 594 | Jinja2 security modes |
| requirements.txt | 16 | Dependencies |
| tests/test_sandbox_bypass.py | 259 | Security test coverage |
| tools/agent_project_utils.py | 192 | Session isolation |

### Handoff Notes for Architect/Coder

1. **Priority 1:** The security sandbox integration is a straightforward fix - the module exists and works, it just needs to be imported and used in read_file.py.

2. **Test Coverage:** The test_sandbox_bypass.py file shows the team is security-conscious. Ensure any fixes include test updates.

3. **Backward Compatibility:** The `allow_outside_repo` parameter should still work but must go through sandbox validation first.

4. **Template Security:** If changing default security_mode, ensure existing templates still work (may need mode override in config).

### References

- Progress Log entries from this audit session
- security/sandbox.py - Reference implementation for path security
- tests/test_sandbox_bypass.py - Existing security test patterns

---

*This audit was conducted by ResearchAgent-Security as part of the scribe_codebase_audit project on 2026-01-23.*
