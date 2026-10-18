● 📋 Scribe MCP Enhancement Plan - Remaining Phases

  Current Status (as of 2025-10-31)

  ✅ Completed: Phases 1-3🔄 Next: Phase 2.1 (Global Log Testing)📋 Total: 6 phases remaining

  ---
  🎯 Phase 2.1: Test Global Log After MCP Restart

  Priority: IMMEDIATEGoal: Verify global log works with new template after MCP restart

  Tasks:

  1. Restart MCP server to load new GLOBAL_PROGRESS_LOG_TEMPLATE.md
  2. Test global log entry to verify proper spacing works
  3. Verify template generation works if log needs to be recreated
  4. Confirm metadata validation still functions correctly

  Expected Results:

  - ✅ Global log entries properly spaced
  - ✅ Template structure maintained
  - ✅ entry_type metadata validation working
  - ✅ File path: docs/GLOBAL_PROGRESS_LOG.md

  ---
  🔍 Phase 4: Enhanced Search & Query Capabilities

  Priority: HIGHGoal: Enable subagents to search across all logs, research docs, and bug reports

  Core Features to Implement:

  4.1 Enhanced query_entries Tool

  # New parameters to add:
  await query_entries(
      search_scope="all_projects",     # project|global|all_projects|research|bugs|all
      document_types=["progress", "research", "architecture"],
      include_outdated=True,           # With warnings for stale info
      verify_code_references=True,     # Check if mentioned code still exists
      time_range="last_30d",          # Date range filtering
      relevance_threshold=0.7,         # Relevance scoring
      max_results=50
  )

  4.2 Cross-Project Search

  - Search across all project logs simultaneously
  - Aggregate results by relevance and date
  - Include global log entries in search scope
  - Maintain project context for each result

  4.3 Document Type Filtering

  - Research Documents: Search research/RESEARCH_*.md files
  - Bug Reports: Search bugs/*/*/report.md files
  - Architecture Docs: Search ARCHITECTURE_GUIDE.md files
  - Global Log: Search GLOBAL_PROGRESS_LOG.md

  4.4 Code Reference Verification

  - Parse entries for file path references
  - Check if referenced files still exist in codebase
  - Add warnings for outdated/broken references
  - Suggest alternative locations for moved files

  4.5 Temporal Search

  - Date range filtering (last X days, specific dates)
  - Chronological result ordering
  - Time-based relevance scoring

  Files to Modify:

  - tools/query_entries.py - Add new parameters and search logic
  - tools/read_recent.py - Add global log reading
  - storage/ - Add document tracking tables
  - Database schema - Document relationships

  Implementation Priority:

  1. Core search expansion (2-3 days)
  2. Document type filtering (1-2 days)
  3. Code reference verification (2-3 days)
  4. Temporal search features (1 day)

  ---
  📝 Phase 5: Fix Subagent Prompts for Proper Document Structure

  Priority: HIGHGoal: Update all 5 subagent prompts to use enhanced tools correctly

  Files to Update:

  - Scribe project configuration
  - Source-owned authoring templates
  - Required-reading template source
  - Session protocol template source
  - Regenerate local agent outputs only after the source lanes above are corrected

  Key Fixes Needed:

  5.1 Research Agent (scribe-research-analyst.md)

  Current Issue: Overwrites templates instead of creating research docs
  Fixes:
  - Clear instructions: "Use manage_docs with action=create_research_doc"
  - Proper file structure: research/RESEARCH_<topic>_<timestamp>.md
  - Search scope guidelines: "Search current project first, then research across projects"
  - Verification: "Always verify code references exist in current codebase"

  5.2 Architect Agent (scribe-architect.md)

  Fixes:
  - Enhanced search usage examples
  - Global milestone logging instructions
  - Cross-project research review guidance

  5.3 Coder Agent (scribe-coder.md)

  Fixes:
  - Enhanced search for implementation reference
  - Bug report creation workflow
  - Global milestone logging guidance

  5.4 Review Agent (scribe-review-agent.md)

  Fixes:
  - Cross-project document review capabilities
  - Enhanced search for validation
  - Security audit procedures outside specific projects

  5.5 Bug Hunter (scribe-bug-hunter.md)

  Fixes:
  - Proper bug report creation workflow
  - manage_docs create_bug_report usage
  - Category-based organization

  Implementation Timeline: 1-2 days

  ---
  🧪 Phase 6: Complete Protocol Workflow Testing

  Priority: CRITICALGoal: End-to-end test of enhanced Scribe Protocol

  Test Scenarios:

  6.1 Full Research Phase Test

  Scenario: Research Agent investigates new feature
  1. Deploy Research Agent with investigation task
  2. Verify research document created in research/ subdirectory
  3. Check INDEX.md auto-generation
  4. Validate document structure and content

  6.2 Enhanced Search Test

  Scenario: Architect uses enhanced search capabilities
  1. Architect searches across all projects for similar patterns
  2. Tests document type filtering (research only)
  3. Verifies code reference verification
  4. Tests temporal search (last 30 days)

  6.3 Implementation Phase Test

  Scenario: Coder implements approved architecture
  1. Coder uses enhanced search for implementation reference
  2. Tests bug report creation if issues found
  3. Verifies global milestone logging

  6.4 Review Phase Test

  Scenario: Review Agent cross-references all documents
  1. Review Agent searches across all document types
  2. Tests cross-project validation
  3. Verifies enhanced search results

  6.5 Bug Hunt Test

  Scenario: Bug Hunter creates structured bug reports
  1. Bug Hunter investigates protocol violation
  2. Creates bug report with proper structure
  3. Verifies automatic INDEX.md management
  4. Tests category-based organization

  6.6 Global Log Integration Test

  Scenario: Automatic milestone tracking
  1. Test project creation events
  2. Test phase transition logging
  3. Test manual milestone logging
  4. Verify proper spacing and structure

  Success Criteria:

  - ✅ All subagents use enhanced tools correctly
  - ✅ Research documents created in proper structure
  - ✅ Enhanced search returns relevant results
  - ✅ Bug reports properly categorized and indexed
  - ✅ Global log automatically tracks milestones
  - ✅ No template overwriting issues
  - ✅ All ≥93% quality gates passed

  Implementation Timeline: 2-3 days

  ---
  🚀 Next Steps Summary

  Immediate (After MCP Restart):

  1. Phase 2.1: Test global log template functionality
  2. Phase 4: Begin enhanced search implementation
  3. Phase 5: Update subagent prompts
  4. Phase 6: Complete end-to-end testing

  Expected Timeline:

  - Phase 2.1: 30 minutes
  - Phase 4: 4-6 days
  - Phase 5: 1-2 days
  - Phase 6: 2-3 days
  - Total Remaining: ~1 week

  This comprehensive enhancement will transform Scribe MCP from a single-project tool into a powerful, cross-project development
  orchestration platform while maintaining all existing functionality and backward compatibility.

  Ready to proceed with Phase 2.1 after MCP restart!
