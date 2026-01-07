#!/usr/bin/env python3
"""
Manual token analysis of SITREP examples from set_project.

Since we can't easily run the MCP server in test mode, we'll analyze
representative SITREP examples based on the code structure.
"""

import tiktoken
import json


# Example 1: NEW PROJECT SITREP (from lines 472-489)
NEW_PROJECT_SITREP = """╔══════════════════════════════════════════════════════════╗
║ ✨ NEW PROJECT CREATED: token_sample_1                    ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/token_sample_1/

📄 Documents Created:
  ✓ ARCHITECTURE_GUIDE.md (template, 768 lines)
  ✓ PHASE_PLAN.md (template, 922 lines)
  ✓ CHECKLIST.md (template, 322 lines)
  ✓ PROGRESS_LOG.md (empty, ready for entries)

🎯 Status: planning (new project)
💡 Next: Start with research or architecture phase"""


# Example 2: EXISTING PROJECT SITREP - Minimal (from lines 512-531)
EXISTING_PROJECT_MINIMAL = """╔══════════════════════════════════════════════════════════╗
║ 📂 PROJECT ACTIVATED: token_sample_2                      ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/token_sample_2/

📊 Documentation Inventory:
  ✓ ARCHITECTURE_GUIDE.md (768 lines)
  ✓ PHASE_PLAN.md (922 lines)
  ✓ CHECKLIST.md (322 lines)
  ✓ PROGRESS_LOG.md (5 entries)

📈 Activity Summary:
  Status: in_progress
  Total Entries: 5
  Last Entry: 2026-01-05 02:30:15 UTC (5 minutes ago)

🎯 Status: in_progress
💡 Next: Continue with current phase"""


# Example 3: EXISTING PROJECT SITREP - With Research (fuller inventory)
EXISTING_PROJECT_WITH_RESEARCH = """╔══════════════════════════════════════════════════════════╗
║ 📂 PROJECT ACTIVATED: token_sample_4                      ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/token_sample_4/

📊 Documentation Inventory:
  ✓ ARCHITECTURE_GUIDE.md (1,274 lines, custom content detected)
  ✓ PHASE_PLAN.md (1,102 lines, custom content detected)
  ✓ CHECKLIST.md (445 lines, custom content detected)
  ✓ PROGRESS_LOG.md (127 entries)

📚 Research & Custom Content:
  • 3 research documents in research/
  • TOOL_LOG.jsonl detected (custom logging)

📈 Activity Summary:
  Status: in_progress
  Total Entries: 127
  Last Entry: 2026-01-04 18:45:23 UTC (8 hours ago)
  Per-Log Counts:
    • progress: 100 entries
    • doc_updates: 15 entries
    • bugs: 12 entries

🎯 Status: in_progress
⚠️  Warning: No activity in 8 hours (consider logging update)
💡 Next: Continue with current phase"""


# Example 4: EXISTING PROJECT with REMINDERS (worst case)
EXISTING_PROJECT_WITH_REMINDERS = """╔══════════════════════════════════════════════════════════╗
║ 📂 PROJECT ACTIVATED: token_sample_5                      ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/token_sample_5/

📊 Documentation Inventory:
  ✓ ARCHITECTURE_GUIDE.md (1,274 lines, custom content detected)
  ✓ PHASE_PLAN.md (1,102 lines, custom content detected)
  ✓ CHECKLIST.md (445 lines, custom content detected)
  ✓ PROGRESS_LOG.md (127 entries)

📚 Research & Custom Content:
  • 3 research documents in research/
  • TOOL_LOG.jsonl detected (custom logging)

📈 Activity Summary:
  Status: in_progress
  Total Entries: 127
  Last Entry: 2026-01-04 18:45:23 UTC (8 hours ago)
  Per-Log Counts:
    • progress: 100 entries
    • doc_updates: 15 entries
    • bugs: 12 entries

🎯 Status: in_progress
⚠️  Warning: No activity in 8 hours (consider logging update)
💡 Next: Continue with current phase

──────────────────────────────────────────────────────────
⏰ REMINDERS:
  1. 📝 Consider logging progress (last entry 8h ago)
  2. 📊 ARCHITECTURE_GUIDE.md may need review (custom modifications detected)
  3. 🔍 Multiple custom logs detected - consider documentation update"""


# Example 5: COMPACT response (for comparison)
COMPACT_RESPONSE = """✅ Project: token_sample_1 | Status: planning | Entries: 0"""


def analyze_sample(name: str, content: str) -> dict:
    """Analyze token count and categorize verbosity."""
    enc = tiktoken.encoding_for_model("gpt-4")
    tokens = enc.encode(content)

    # Categorize by line type
    lines = content.split('\n')
    categories = {
        "structural": 0,  # Boxes, headers, separators
        "metadata": 0,    # Paths, timestamps, counts
        "duplication": 0, # Repeated blocks
        "content": 0      # Actual data
    }

    for line in lines:
        line_tokens = len(enc.encode(line))
        if '═' in line or '─' in line or '║' in line or '╔' in line or '╚' in line:
            categories["structural"] += line_tokens
        elif 'Root:' in line or 'Dev Plan:' in line or 'Location:' in line:
            categories["duplication"] += line_tokens  # Repeated in every response
        elif 'Status:' in line or 'Entries:' in line or 'Last Entry:' in line:
            categories["metadata"] += line_tokens
        else:
            categories["content"] += line_tokens

    return {
        "name": name,
        "total_tokens": len(tokens),
        "char_count": len(content),
        "tokens_per_char": len(tokens) / len(content) if content else 0,
        "line_count": len(lines),
        "categories": categories,
        "category_percentages": {
            k: f"{(v / len(tokens) * 100):.1f}%"
            for k, v in categories.items()
        }
    }


def main():
    samples = [
        ("NEW_PROJECT_SITREP", NEW_PROJECT_SITREP),
        ("EXISTING_MINIMAL", EXISTING_PROJECT_MINIMAL),
        ("EXISTING_WITH_RESEARCH", EXISTING_PROJECT_WITH_RESEARCH),
        ("EXISTING_WITH_REMINDERS", EXISTING_PROJECT_WITH_REMINDERS),
        ("COMPACT", COMPACT_RESPONSE),
    ]

    results = []
    print("="*80)
    print("TOKEN ANALYSIS: set_project SITREP Output")
    print("="*80 + "\n")

    for name, content in samples:
        result = analyze_sample(name, content)
        results.append(result)

        print(f"{result['name']}:")
        print(f"  Total Tokens: {result['total_tokens']}")
        print(f"  Characters: {result['char_count']}")
        print(f"  Lines: {result['line_count']}")
        print(f"  Tokens/Char: {result['tokens_per_char']:.3f}")
        print(f"  Token Distribution:")
        for cat, pct in result['category_percentages'].items():
            print(f"    {cat}: {pct} ({result['categories'][cat]} tokens)")
        print()

    # Summary statistics
    readable_samples = [r for r in results if r['name'] != 'COMPACT']
    token_counts = [r['total_tokens'] for r in readable_samples]

    print("="*80)
    print("SUMMARY STATISTICS (readable format only)")
    print("="*80)
    print(f"Average: {sum(token_counts) / len(token_counts):.1f} tokens")
    print(f"Min: {min(token_counts)} tokens ({[r['name'] for r in readable_samples if r['total_tokens'] == min(token_counts)][0]})")
    print(f"Max: {max(token_counts)} tokens ({[r['name'] for r in readable_samples if r['total_tokens'] == max(token_counts)][0]})")
    print(f"Range: {max(token_counts) - min(token_counts)} tokens")
    print(f"\nCompact format: {results[-1]['total_tokens']} tokens")
    print(f"Reduction from avg: {((sum(token_counts)/len(token_counts) - results[-1]['total_tokens']) / (sum(token_counts)/len(token_counts)) * 100):.1f}%")

    # Identify optimization opportunities
    print("\n" + "="*80)
    print("OPTIMIZATION OPPORTUNITIES")
    print("="*80)

    avg_structural = sum(r['categories']['structural'] for r in readable_samples) / len(readable_samples)
    avg_duplication = sum(r['categories']['duplication'] for r in readable_samples) / len(readable_samples)

    print(f"1. Structural (boxes/headers): Avg {avg_structural:.0f} tokens (~{avg_structural/sum(token_counts)*len(token_counts)*100:.1f}%)")
    print(f"   → Could be optional in compact mode")
    print(f"\n2. Duplication (Location block): Avg {avg_duplication:.0f} tokens (~{avg_duplication/sum(token_counts)*len(token_counts)*100:.1f}%)")
    print(f"   → Appears in every response, could be templated")
    print(f"\n3. Reminders: Up to {results[3]['total_tokens'] - results[2]['total_tokens']} additional tokens")
    print(f"   → Could be factored to separate concern")

    # Save results
    import pathlib
    output = pathlib.Path(__file__).parent / "token_analysis_results.json"
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to: {output}")


if __name__ == "__main__":
    main()
