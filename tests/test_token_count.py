#!/usr/bin/env python3
"""
Test actual token counts for SPEC-TOKEN-002 optimization.
Uses tiktoken cl100k_base encoding to measure before/after.
"""

import sys

try:
    import tiktoken
except ImportError:
    print("tiktoken not installed. Install with: pip install tiktoken")
    sys.exit(1)

from scribe_mcp.utils.response import ResponseFormatter

def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding (GPT-4)."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))

def test_token_counts():
    """Compare before/after token counts for append_entry optimization."""

    formatter = ResponseFormatter()

    # Test entry with custom metadata
    data = {
        'ok': True,
        'written_line': '[ℹ️] [2026-01-05 14:34:25 UTC] [Agent: PhaseTestAgent] [Project: scribe_systematic_audit_1_phase5_tool_output] Test message for append_entry readable mode - Phase 5 tool output recording | phase=5; test_mode=readable; unicode_test=日本語🎯; priority=low; log_type=progress; content_type=log',
        'path': '/tmp/.scribe/docs/dev_plans/scribe_systematic_audit_1_phase5_tool_output/PROGRESS_LOG.md',
        'meta': {'phase': 5, 'test_mode': 'readable', 'unicode_test': '日本語🎯'}
    }

    # NEW FORMAT (after optimization)
    new_output = formatter.format_readable_append_entry(data)

    # OLD FORMAT (simulated)
    old_output = """✅ Entry written to progress log (scribe_systematic_audit_1_phase5_tool_output)
   [ℹ️] [2026-01-05 14:34:25 UTC] [Agent: PhaseTestAgent] [Project: scribe_systematic_audit_1_phase5_tool_output] Test message for append_entry readable mode - Phase 5 tool output recording | phase=5; test_mode=readable; unicode_test=日本語🎯; priority=low; log_type=progress; content_type=log

📁 .scribe/docs/dev_plans/scribe_systematic_audit_1_phase5_tool_output/PROGRESS_LOG.md"""

    # Count tokens
    old_tokens = count_tokens(old_output)
    new_tokens = count_tokens(new_output)
    reduction = old_tokens - new_tokens
    reduction_pct = (reduction / old_tokens) * 100

    print("=" * 80)
    print("SPEC-TOKEN-002 TOKEN COUNT VERIFICATION")
    print("=" * 80)
    print()

    print("OLD FORMAT (current):")
    print("-" * 80)
    print(old_output)
    print()
    print(f"Token count: {old_tokens} tokens")
    print()

    print("NEW FORMAT (optimized):")
    print("-" * 80)
    print(new_output)
    print()
    print(f"Token count: {new_tokens} tokens")
    print()

    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Before:     {old_tokens} tokens")
    print(f"After:      {new_tokens} tokens")
    print(f"Reduction:  {reduction} tokens ({reduction_pct:.1f}%)")
    print()
    print(f"SPEC Target: 85 tokens (37% reduction)")
    print(f"Achieved:    {new_tokens} tokens ({reduction_pct:.1f}% reduction)")
    print()

    if new_tokens <= 90:  # Allow 5 token margin
        print("✅ SUCCESS: Met SPEC-TOKEN-002 target (< 90 tokens)")
    else:
        print(f"⚠️  WARNING: Exceeded target by {new_tokens - 85} tokens")
    print()

    # Test simple entry (no custom metadata)
    data_simple = {
        'ok': True,
        'written_line': '[ℹ️] [2026-01-07 23:10:45 UTC] [Agent: CoderAgent] [Project: test_project] Simple test message | priority=low; log_type=progress; content_type=log',
        'path': '/tmp/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md',
        'meta': {}
    }

    simple_output = formatter.format_readable_append_entry(data_simple)
    simple_tokens = count_tokens(simple_output)

    print("SIMPLE ENTRY (default metadata only):")
    print("-" * 80)
    print(simple_output)
    print()
    print(f"Token count: {simple_tokens} tokens")
    print()

if __name__ == '__main__':
    test_token_counts()
