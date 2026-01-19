#!/usr/bin/env python3
"""Token measurement for query_entries output analysis."""

import json
import tiktoken
from typing import Dict, List

# Initialize tiktoken encoder
enc = tiktoken.get_encoding('cl100k_base')

def count_tokens(text: str) -> int:
    """Count tokens in text using cl100k_base encoding."""
    return len(enc.encode(text))

def analyze_output(name: str, output: str) -> Dict:
    """Analyze token breakdown of output."""
    total = count_tokens(output)

    # Categorize tokens
    lines = output.split('\n')

    # Structural: headers, boxes, separators
    structural_lines = [l for l in lines if any(c in l for c in ['─', '│', '┌', '┐', '└', '┘', '═', '║'])]
    structural = sum(count_tokens(l) for l in structural_lines)

    # Metadata: pagination, project info, location
    metadata_keywords = ['Page', 'Total', 'Location:', 'Pagination:', 'Filter', 'Scope:']
    metadata_lines = [l for l in lines if any(kw in l for kw in metadata_keywords)]
    metadata = sum(count_tokens(l) for l in metadata_lines)

    # Entry content (rough estimate: everything not structural/metadata)
    content = total - structural - metadata

    return {
        "name": name,
        "total_tokens": total,
        "structural_tokens": structural,
        "metadata_tokens": metadata,
        "content_tokens": content,
        "structural_pct": round(structural / total * 100, 1) if total > 0 else 0,
        "metadata_pct": round(metadata / total * 100, 1) if total > 0 else 0,
        "content_pct": round(content / total * 100, 1) if total > 0 else 0,
    }

# Sample 1: Readable format with 5 entries
sample_1_readable = """Search Results for Project: scribe_systematic_audit_1

Filters Applied:
  • Scope: project
  • Page: 1 / 1

╔══════════════════════════════════════════════════════════╗
║ Entry 1                                                  ║
╠══════════════════════════════════════════════════════════╣
  [✅] [2026-01-05 02:40:34 UTC] [ResearchAgent-C-QueryEntries]
  Created comprehensive wiki documentation for query_entries.py (40+ page analysis).

  Meta: phase=wiki_creation, document_created=wiki/tools/query_entries.md,
  sections=8, sub_systems_documented=9
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ Entry 2                                                  ║
╠══════════════════════════════════════════════════════════╣
  [✅] [2026-01-05 02:35:43 UTC] [ResearchAgent-C-QueryEntries]
  Complete sub-system mapping of query_entries.py finished. Identified 9 distinct
  architectural layers.

  Meta: phase=sub_system_mapping, total_functions=24, total_lines=2030
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ Entry 3                                                  ║
╠══════════════════════════════════════════════════════════╣
  [⚠️] [2026-01-05 02:35:17 UTC] [ResearchAgent-C-QueryEntries]
  Filter application analysis reveals non-composable sequential filter chain.

  Meta: phase=filter_analysis, filter_count=10, bug_found=true
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ Entry 4                                                  ║
╠══════════════════════════════════════════════════════════╣
  [ℹ️] [2026-01-05 02:34:45 UTC] [ResearchAgent-C-QueryEntries]
  Identified search scope routing architecture. Found 6 scopes with distinct behaviors.

  Meta: phase=architecture_mapping, scope_count=6
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ Entry 5                                                  ║
╠══════════════════════════════════════════════════════════╣
  [ℹ️] [2026-01-05 02:33:48 UTC] [ResearchAgent-C-QueryEntries]
  Initial structural scan reveals massive parameter validation sub-system.

  Meta: complexity_indicators=["25_parameters", "dual_config_support"]
╚══════════════════════════════════════════════════════════╝

────────────────────────────────────────────────────────────

Pagination:
  Page 1 of 1 | Total Entries: 5 | Page Size: 10

📁 Location: .scribe/docs/dev_plans/scribe_systematic_audit_1/PROGRESS_LOG.md
"""

# Sample 2: Structured format (JSON)
sample_2_structured = {
    "ok": True,
    "entries": [
        {
            "id": "entry-1",
            "ts": "2026-01-05T02:40:34Z",
            "message": "Created comprehensive wiki documentation for query_entries.py (40+ page analysis).",
            "emoji": "✅",
            "agent": "ResearchAgent-C-QueryEntries",
            "meta": {
                "phase": "wiki_creation",
                "document_created": "wiki/tools/query_entries.md",
                "sections": 8,
                "sub_systems_documented": 9
            }
        },
        {
            "id": "entry-2",
            "ts": "2026-01-05T02:35:43Z",
            "message": "Complete sub-system mapping of query_entries.py finished.",
            "emoji": "✅",
            "agent": "ResearchAgent-C-QueryEntries",
            "meta": {
                "phase": "sub_system_mapping",
                "total_functions": 24,
                "total_lines": 2030
            }
        },
        {
            "id": "entry-3",
            "ts": "2026-01-05T02:35:17Z",
            "message": "Filter application analysis reveals non-composable sequential filter chain.",
            "emoji": "⚠️",
            "agent": "ResearchAgent-C-QueryEntries",
            "meta": {
                "phase": "filter_analysis",
                "filter_count": 10,
                "bug_found": True
            }
        }
    ],
    "pagination": {
        "page": 1,
        "page_size": 10,
        "total_entries": 3,
        "total_pages": 1,
        "has_next": False,
        "has_prev": False
    },
    "search_params": {
        "scope": "project",
        "project": "scribe_systematic_audit_1"
    }
}

# Sample 3: Compact format
sample_3_compact = """5 entries | page 1/1

[✅] 2026-01-05 02:40:34 | ResearchAgent-C-QueryEntries
Created comprehensive wiki documentation for query_entries.py (40+ page analysis).

[✅] 2026-01-05 02:35:43 | ResearchAgent-C-QueryEntries
Complete sub-system mapping of query_entries.py finished.

[⚠️] 2026-01-05 02:35:17 | ResearchAgent-C-QueryEntries
Filter application analysis reveals non-composable sequential filter chain.

[ℹ️] 2026-01-05 02:34:45 | ResearchAgent-C-QueryEntries
Identified search scope routing architecture. Found 6 scopes.

[ℹ️] 2026-01-05 02:33:48 | ResearchAgent-C-QueryEntries
Initial structural scan reveals massive parameter validation sub-system.
"""

# Sample 4: Cross-project search (multiple projects)
sample_4_cross_project = """Search Results Across All Projects

Projects Searched: 3
  • scribe_systematic_audit_1
  • scribe_tool_output_refinement
  • enhanced_log_rotation_with_auditability

Filters Applied:
  • Scope: all_projects
  • Message: "parameter"
  • Page: 1 / 2

╔══════════════════════════════════════════════════════════╗
║ Entry 1 [scribe_systematic_audit_1]                     ║
╠══════════════════════════════════════════════════════════╣
  [ℹ️] [2026-01-05 02:33:48 UTC] [ResearchAgent-C-QueryEntries]
  Initial structural scan reveals massive parameter validation sub-system.

  Meta: complexity_indicators=["25_parameters", "dual_config_support"]
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ Entry 2 [scribe_tool_output_refinement]                 ║
╠══════════════════════════════════════════════════════════╣
  [ℹ️] [2026-01-04 15:22:10 UTC] [CoderAgent]
  Implemented parameter validation with BulletproofParameterCorrector.

  Meta: phase=implementation, files_modified=["utils/parameter_validator.py"]
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ Entry 3 [enhanced_log_rotation_with_auditability]       ║
╠══════════════════════════════════════════════════════════╣
  [✅] [2026-01-03 10:15:30 UTC] [ArchitectAgent]
  Designed parameter healing system for rotate_log tool.

  Meta: phase=architecture, parameter_count=12
╚══════════════════════════════════════════════════════════╝

────────────────────────────────────────────────────────────

Pagination:
  Page 1 of 2 | Total Entries: 15 | Page Size: 10 | Showing 3 entries

📁 Projects: .scribe/docs/dev_plans/
"""

# Sample 5: Large result set (10 entries, full page)
sample_5_large = """Search Results for Project: scribe_systematic_audit_1

Filters Applied:
  • Scope: project
  • Agent: ResearchAgent-C-QueryEntries
  • Page: 1 / 2

""" + "\n".join([f"""╔══════════════════════════════════════════════════════════╗
║ Entry {i}                                                  ║
╠══════════════════════════════════════════════════════════╣
  [{'✅' if i % 2 == 0 else 'ℹ️'}] [2026-01-05 02:{40-i:02d}:34 UTC] [ResearchAgent-C-QueryEntries]
  Log entry number {i} with some analysis results and findings documented here.

  Meta: phase=analysis, step={i}, confidence=0.{85+i}
╚══════════════════════════════════════════════════════════╝
""" for i in range(1, 11)]) + """
────────────────────────────────────────────────────────────

Pagination:
  Page 1 of 2 | Total Entries: 15 | Page Size: 10

📁 Location: .scribe/docs/dev_plans/scribe_systematic_audit_1/PROGRESS_LOG.md
"""

# Sample 6: Empty result set
sample_6_empty = """Search Results for Project: scribe_systematic_audit_1

Filters Applied:
  • Scope: project
  • Message: "nonexistent_term"
  • Status: ["critical"]
  • Page: 1 / 1

No entries found matching your search criteria.

Try adjusting your filters or search scope.

────────────────────────────────────────────────────────────

Pagination:
  Page 1 of 1 | Total Entries: 0 | Page Size: 10

📁 Location: .scribe/docs/dev_plans/scribe_systematic_audit_1/PROGRESS_LOG.md
"""

# Sample 7: With warnings
sample_7_warnings = """Search Results for Project: scribe_systematic_audit_1

⚠️ Warnings:
  • Relevance scoring is experimental and may not reflect semantic similarity
  • 2 entries skipped due to invalid timestamp format
  • Parameter 'page' was corrected from -1 to 1

Filters Applied:
  • Scope: project
  • Relevance Threshold: 0.7
  • Page: 1 / 1

╔══════════════════════════════════════════════════════════╗
║ Entry 1                                                  ║
╠══════════════════════════════════════════════════════════╣
  [✅] [2026-01-05 02:40:34 UTC] [ResearchAgent-C-QueryEntries]
  Created comprehensive wiki documentation for query_entries.py with detailed
  analysis of all sub-systems, extractable modules, and architectural patterns.

  Meta: phase=wiki_creation, relevance_score=0.89
╚══════════════════════════════════════════════════════════╝

────────────────────────────────────────────────────────────

Pagination:
  Page 1 of 1 | Total Entries: 1 | Page Size: 10

📁 Location: .scribe/docs/dev_plans/scribe_systematic_audit_1/PROGRESS_LOG.md
"""

# Measure all samples
samples = [
    ("readable_5_entries", sample_1_readable),
    ("structured_3_entries", json.dumps(sample_2_structured, indent=2)),
    ("compact_5_entries", sample_3_compact),
    ("cross_project_3_entries", sample_4_cross_project),
    ("large_10_entries", sample_5_large),
    ("empty_results", sample_6_empty),
    ("with_warnings", sample_7_warnings)
]

results = []
for name, output in samples:
    result = analyze_output(name, output)
    results.append(result)
    print(f"\n{'='*60}")
    print(f"Sample: {name}")
    print(f"{'='*60}")
    print(f"Total Tokens:      {result['total_tokens']:4d}")
    print(f"Structural:        {result['structural_tokens']:4d} ({result['structural_pct']:4.1f}%)")
    print(f"Metadata:          {result['metadata_tokens']:4d} ({result['metadata_pct']:4.1f}%)")
    print(f"Content:           {result['content_tokens']:4d} ({result['content_pct']:4.1f}%)")

# Calculate statistics
print(f"\n{'='*60}")
print(f"SUMMARY STATISTICS")
print(f"{'='*60}")

totals = [r['total_tokens'] for r in results]
print(f"\nTotal Tokens:")
print(f"  Min:  {min(totals)}")
print(f"  Max:  {max(totals)}")
print(f"  Avg:  {sum(totals) / len(totals):.0f}")
print(f"  P95:  {sorted(totals)[int(len(totals) * 0.95)]}")

structural_pcts = [r['structural_pct'] for r in results]
print(f"\nStructural % (boxes, separators):")
print(f"  Min:  {min(structural_pcts):.1f}%")
print(f"  Max:  {max(structural_pcts):.1f}%")
print(f"  Avg:  {sum(structural_pcts) / len(structural_pcts):.1f}%")

metadata_pcts = [r['metadata_pct'] for r in results]
print(f"\nMetadata % (pagination, filters, location):")
print(f"  Min:  {min(metadata_pcts):.1f}%")
print(f"  Max:  {max(metadata_pcts):.1f}%")
print(f"  Avg:  {sum(metadata_pcts) / len(metadata_pcts):.1f}%")

# Per-entry analysis
print(f"\n{'='*60}")
print(f"PER-ENTRY TOKEN COST")
print(f"{'='*60}")

# Extract entry counts from sample names
entry_counts = {
    "readable_5_entries": 5,
    "structured_3_entries": 3,
    "compact_5_entries": 5,
    "cross_project_3_entries": 3,
    "large_10_entries": 10,
    "empty_results": 0,
    "with_warnings": 1
}

for result in results:
    name = result['name']
    total = result['total_tokens']
    entries = entry_counts.get(name, 1)
    if entries > 0:
        per_entry = (total - result['metadata_tokens']) / entries
        print(f"{name:30s}: {per_entry:6.1f} tokens/entry")

# Save results to JSON
output_file = '/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/scribe_systematic_audit_1/token_measurements_query_entries.json'
with open(output_file, 'w') as f:
    json.dump({
        "measurements": results,
        "statistics": {
            "total_tokens": {
                "min": min(totals),
                "max": max(totals),
                "avg": sum(totals) / len(totals),
                "p95": sorted(totals)[int(len(totals) * 0.95)]
            },
            "structural_pct": {
                "min": min(structural_pcts),
                "max": max(structural_pcts),
                "avg": sum(structural_pcts) / len(structural_pcts)
            },
            "metadata_pct": {
                "min": min(metadata_pcts),
                "max": max(metadata_pcts),
                "avg": sum(metadata_pcts) / len(metadata_pcts)
            }
        }
    }, f, indent=2)

print(f"\n✅ Results saved to: {output_file}")
