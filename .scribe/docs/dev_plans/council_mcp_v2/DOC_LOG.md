
# 📋 Documentation Update Log — council_mcp_v2
**Maintained By:** Scribe
**Timezone:** UTC

> Track every structured documentation change. Use `log_type="doc_updates"` (or `--log doc_updates`).

---



## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: council_mcp_v2] Message text | doc=<doc_name>; section=<section_id>; action=<action_type>; [additional metadata]
```

**Required Metadata Fields:**
- `doc`: Document name (e.g., "architecture", "phase_plan", "checklist")
- `section`: Section ID being modified (e.g., "directory_structure", "phase_overview")
- `action`: Action type (`replace_section`, `append`, `status_update`, etc.)

**Optional Metadata Fields:**
- `file_path`: Full path to the Markdown file
- `changes_count`: Number of lines changed
- `review_status`: pending/approved/rejected
- `reviewer`: Reviewer name
- `jira_ticket`: Associated ticket number
- `confidence`: Confidence level for the change (0-1)
- `context`: Additional context about the change

---

## Tips for Documentation Updates
- Always specify which document section you're updating via `section=`.
- Include `action=` to indicate the type of modification.
- Reference checklist items or phases when applicable.
- Use `--dry-run` first when making structural changes.
- All documentation changes are automatically tracked and versioned.

---

## Entries will populate below
[✅] [2026-01-11 03:13:13 UTC] [Agent: Scribe] [Project: council_mcp_v2] Created review report: REVIEW_REPORT_5_2026-01-11_0313.md | action=create; agent_id=Scribe; agent_name=Scribe; doc=review_report; document_type=review_report; file_path=/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/council_mcp_v2/REVIEW_REPORT_5_2026-01-11_0313.md; file_size=2992; project_name=council_mcp_v2; project_root=/home/austin/projects/MCP_SPINE/scribe_mcp; review_type=schema_extension_investigation; section=; stage=5; timestamp=2026-01-11 03:13:13 UTC; priority=medium; log_type=doc_updates; content_type=log
[✅] [2026-01-11 06:43:00 UTC] [Agent: Scribe] [Project: council_mcp_v2] Created review report: REVIEW_REPORT_post_phase2_2026-01-11_0643.md | action=create; agent_id=Scribe; agent_name=Scribe; doc=review_report; document_type=review_report; file_path=/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/council_mcp_v2/REVIEW_REPORT_post_phase2_2026-01-11_0643.md; file_size=3012; project_name=council_mcp_v2; project_root=/home/austin/projects/MCP_SPINE/scribe_mcp; section=; stage=post_phase2; timestamp=2026-01-11 06:43:00 UTC; priority=medium; log_type=doc_updates; content_type=log
[✅] [2026-01-13 02:15:17 UTC] [Agent: Scribe] [Project: council_mcp_v2] Created review report: REVIEW_REPORT_unknown_2026-01-13_0215.md | action=create; agent_id=Scribe; agent_name=Scribe; date=2026-01-13; doc=review_report; document_type=review_report; file_path=/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/council_mcp_v2/REVIEW_REPORT_unknown_2026-01-13_0215.md; file_size=9076; overall_grade=96.1; phase=5; project_name=council_mcp_v2; project_root=/home/austin/projects/MCP_SPINE/scribe_mcp; reviewer=ReviewAgent; section=; stage=unknown; status=APPROVED; timestamp=2026-01-13 02:15:17 UTC; title=Phase 5 Comprehensive Review; priority=medium; log_type=doc_updates; content_type=log
