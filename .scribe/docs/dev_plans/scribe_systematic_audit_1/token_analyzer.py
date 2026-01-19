#!/usr/bin/env python3
"""
Token Analysis Script for Phase 5 Team C
Measures token counts using tiktoken (cl100k_base encoding)
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import tiktoken
except ImportError:
    print("ERROR: tiktoken not installed. Run: pip install tiktoken")
    exit(1)

# Initialize tiktoken encoder (cl100k_base is used by GPT-4)
encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken cl100k_base encoding"""
    return len(encoder.encode(text))

def analyze_file(filepath: Path) -> Dict:
    """Analyze a single file and return token metrics"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        char_count = len(content)
        token_count = count_tokens(content)
        line_count = content.count('\n') + 1

        return {
            "file": str(filepath),
            "chars": char_count,
            "tokens": token_count,
            "lines": line_count,
            "tokens_per_char": round(token_count / char_count, 3) if char_count > 0 else 0,
            "chars_per_token": round(char_count / token_count, 2) if token_count > 0 else 0
        }
    except Exception as e:
        return {
            "file": str(filepath),
            "error": str(e)
        }

def analyze_tool_outputs(base_dir: str) -> Dict:
    """Analyze all tool outputs and categorize by tool and mode"""
    base_path = Path(base_dir)
    results = {}

    # Walk through tool_outputs directory
    for tool_dir in sorted(base_path.iterdir()):
        if not tool_dir.is_dir():
            continue

        tool_name = tool_dir.name
        results[tool_name] = {
            "modes": {},
            "total_tokens": 0,
            "file_count": 0
        }

        # Analyze all .txt files in this tool directory
        for file_path in sorted(tool_dir.glob("*.txt")):
            mode = file_path.stem  # readable, structured, compact, default, error, notes
            analysis = analyze_file(file_path)

            results[tool_name]["modes"][mode] = analysis
            if "tokens" in analysis:
                results[tool_name]["total_tokens"] += analysis["tokens"]
                results[tool_name]["file_count"] += 1

    return results

def categorize_bloat(content: str) -> Dict[str, List[str]]:
    """
    Categorize bloat sources in content:
    - Structural: Tables, headers, boxes, ASCII art
    - Metadata: IDs, timestamps, reminders, status indicators
    - Duplication: Repeated blocks, redundant information
    - Safety: "Just in case" messages, excessive context
    """
    bloat_categories = {
        "structural": [],
        "metadata": [],
        "duplication": [],
        "safety": []
    }

    lines = content.split('\n')

    for i, line in enumerate(lines):
        # Structural bloat
        if any(char in line for char in ['═', '║', '╔', '╗', '╚', '╝', '─', '│', '┌', '┐', '└', '┘']):
            bloat_categories["structural"].append(f"Line {i+1}: Box drawing characters")
        elif line.strip().startswith('|') and '|' in line[1:]:
            bloat_categories["structural"].append(f"Line {i+1}: Table row")
        elif line.strip().startswith('#'):
            bloat_categories["structural"].append(f"Line {i+1}: Markdown header")

        # Metadata bloat
        if 'UTC]' in line or 'timestamp' in line.lower():
            bloat_categories["metadata"].append(f"Line {i+1}: Timestamp")
        if '[Agent:' in line or 'agent=' in line.lower():
            bloat_categories["metadata"].append(f"Line {i+1}: Agent ID")
        if any(x in line for x in ['[Project:', 'project=', 'Priority:', 'Status:']):
            bloat_categories["metadata"].append(f"Line {i+1}: Project/Status metadata")

        # Safety bloat (warnings, reminders, suggestions)
        if any(x in line.lower() for x in ['reminder:', 'suggestion:', 'tip:', 'note:', 'warning:']):
            bloat_categories["safety"].append(f"Line {i+1}: Informational message")
        if 'next' in line.lower() or 'consider' in line.lower():
            bloat_categories["safety"].append(f"Line {i+1}: Suggestion/guidance")

    return bloat_categories

def generate_report(results: Dict, output_path: str):
    """Generate comprehensive token analysis report"""
    report_lines = []

    report_lines.append("# Token Measurement Report")
    report_lines.append("")
    report_lines.append("**Generated**: 2026-01-05")
    report_lines.append("**Analyzer**: ResearchAgent-Phase5-TokenAnalyzer (Team C)")
    report_lines.append("**Encoding**: tiktoken cl100k_base (GPT-4)")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Executive Summary")
    report_lines.append("")

    # Calculate totals
    total_tools = len(results)
    total_files = sum(r["file_count"] for r in results.values())
    total_tokens = sum(r["total_tokens"] for r in results.values())

    report_lines.append(f"- **Tools Analyzed**: {total_tools}")
    report_lines.append(f"- **Total Files**: {total_files}")
    report_lines.append(f"- **Total Tokens**: {total_tokens:,}")
    report_lines.append(f"- **Average Tokens/Tool**: {total_tokens // total_tools if total_tools > 0 else 0:,}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Tool-by-Tool Analysis")
    report_lines.append("")

    # Sort tools by total tokens (descending)
    sorted_tools = sorted(results.items(), key=lambda x: x[1]["total_tokens"], reverse=True)

    for tool_name, tool_data in sorted_tools:
        if tool_data["file_count"] == 0:
            continue

        report_lines.append(f"### {tool_name}")
        report_lines.append("")
        report_lines.append(f"**Total Tokens**: {tool_data['total_tokens']:,}")
        report_lines.append("")

        # Mode breakdown
        if tool_data["modes"]:
            report_lines.append("| Mode | Chars | Tokens | Lines | Tokens/Char | Chars/Token |")
            report_lines.append("|------|-------|--------|-------|-------------|-------------|")

            for mode, analysis in sorted(tool_data["modes"].items()):
                if "error" in analysis:
                    report_lines.append(f"| {mode} | ERROR | {analysis['error']} | - | - | - |")
                else:
                    report_lines.append(
                        f"| {mode} | {analysis['chars']:,} | {analysis['tokens']:,} | "
                        f"{analysis['lines']} | {analysis['tokens_per_char']} | {analysis['chars_per_token']} |"
                    )

            report_lines.append("")

        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## High-Frequency Tools Priority")
    report_lines.append("")
    report_lines.append("Tools called most frequently in typical development workflows:")
    report_lines.append("")

    high_freq_tools = ["list_projects", "set_project", "get_project", "read_recent", "append_entry", "query_entries"]

    for tool in high_freq_tools:
        if tool in results and results[tool]["total_tokens"] > 0:
            report_lines.append(f"- **{tool}**: {results[tool]['total_tokens']:,} tokens")

    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Bloat Categorization")
    report_lines.append("")
    report_lines.append("*Detailed bloat analysis requires examining actual content - see bloat_analysis.md*")
    report_lines.append("")

    # Write report
    with open(output_path, 'w') as f:
        f.write('\n'.join(report_lines))

    print(f"\n✅ Report written to: {output_path}")
    print(f"   Total tools: {total_tools}")
    print(f"   Total tokens: {total_tokens:,}")

def main():
    """Main analysis routine"""
    base_dir = "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/tool_outputs"
    output_dir = "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis"

    print("🔍 Starting token analysis...")
    print(f"   Base directory: {base_dir}")
    print(f"   Encoding: tiktoken cl100k_base (GPT-4)")

    # Analyze all tool outputs
    results = analyze_tool_outputs(base_dir)

    # Generate report
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "token_measurement_report.md")
    generate_report(results, report_path)

    # Save raw JSON data
    json_path = os.path.join(output_dir, "token_measurements.json")
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"✅ JSON data written to: {json_path}")

if __name__ == "__main__":
    main()
