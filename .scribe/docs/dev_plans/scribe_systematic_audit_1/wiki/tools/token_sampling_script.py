#!/usr/bin/env python3
"""
Token sampling script for set_project SITREP analysis.

Generates 10+ SITREP samples and measures token consumption with tiktoken.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add scribe_mcp to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.rotate_log import rotate_log
import tiktoken


async def count_tokens(text: str) -> dict:
    """Count tokens using tiktoken (GPT-4 encoding)."""
    enc = tiktoken.encoding_for_model("gpt-4")
    tokens = enc.encode(text)
    return {
        "total_tokens": len(tokens),
        "char_count": len(text),
        "tokens_per_char": len(tokens) / len(text) if text else 0
    }


async def extract_readable_content(response: dict) -> str:
    """Extract readable_content from set_project response."""
    if "readable_content" in response:
        return response["readable_content"]
    # Fallback: use full response as string
    return str(response)


async def sample_1_new_project_minimal():
    """Sample 1: New project with no reminders (baseline)."""
    project_name = "token_sample_1_new_minimal"

    # Clean slate
    import shutil
    dev_plan = Path(f".scribe/docs/dev_plans/{project_name}")
    if dev_plan.exists():
        shutil.rmtree(dev_plan)

    response = await set_project(name=project_name, format="readable")
    content = await extract_readable_content(response)
    metrics = await count_tokens(content)

    return {
        "sample_id": "1_new_minimal",
        "scenario": "New project, no reminders",
        "is_new": response.get("is_new", True),
        **metrics,
        "raw_content": content
    }


async def sample_2_existing_minimal():
    """Sample 2: Existing project with minimal inventory (baseline existing)."""
    project_name = "token_sample_2_existing_minimal"

    # Create project first
    await set_project(name=project_name)

    # Add one entry to make it "used"
    await append_entry(message="Test entry", project=project_name)

    # Now call again
    response = await set_project(name=project_name, format="readable")
    content = await extract_readable_content(response)
    metrics = await count_tokens(content)

    return {
        "sample_id": "2_existing_minimal",
        "scenario": "Existing project, minimal inventory",
        "is_new": response.get("is_new", False),
        **metrics,
        "raw_content": content
    }


async def sample_3_bug_001_reproduction():
    """Sample 3: BUG-001 reproduction (empty log after rotation)."""
    project_name = "token_sample_3_bug_001"

    # Create project
    await set_project(name=project_name)

    # Add entry
    await append_entry(message="Test entry", project=project_name)

    # Rotate log (creates empty file)
    await rotate_log(project=project_name, confirm=True)

    # Call set_project again - should show existing but shows new (BUG)
    response = await set_project(name=project_name, format="readable")
    content = await extract_readable_content(response)
    metrics = await count_tokens(content)

    return {
        "sample_id": "3_bug_001",
        "scenario": "BUG-001: Empty log after rotation",
        "is_new": response.get("is_new"),  # Should be False, likely True (bug)
        "bug_detected": response.get("is_new") == True,  # This IS the bug
        **metrics,
        "raw_content": content
    }


async def sample_4_existing_with_research():
    """Sample 4: Existing project with research files (custom content)."""
    project_name = "token_sample_4_with_research"

    # Create project
    await set_project(name=project_name)

    # Add entries
    for i in range(5):
        await append_entry(message=f"Entry {i}", project=project_name)

    # Create fake research files
    dev_plan = Path(f".scribe/docs/dev_plans/{project_name}")
    research_dir = dev_plan / "research"
    research_dir.mkdir(exist_ok=True)

    for i in range(3):
        (research_dir / f"RESEARCH_TOPIC_{i}.md").write_text("# Research\nContent here\n")

    # Call set_project
    response = await set_project(name=project_name, format="readable")
    content = await extract_readable_content(response)
    metrics = await count_tokens(content)

    return {
        "sample_id": "4_with_research",
        "scenario": "Existing project with 3 research files",
        "is_new": response.get("is_new", False),
        **metrics,
        "raw_content": content
    }


async def sample_5_structured_format():
    """Sample 5: Structured format for comparison."""
    project_name = "token_sample_5_structured"

    await set_project(name=project_name)
    await append_entry(message="Test", project=project_name)

    response = await set_project(name=project_name, format="structured")
    content = json.dumps(response, indent=2)
    metrics = await count_tokens(content)

    return {
        "sample_id": "5_structured",
        "scenario": "Structured format (JSON)",
        "format": "structured",
        **metrics,
        "raw_content": content
    }


async def main():
    """Run all samples and generate report."""
    print("🔬 Token Sampling Script for set_project SITREP Analysis\n")

    samples = []

    try:
        print("Running sample 1: New project minimal...")
        samples.append(await sample_1_new_project_minimal())

        print("Running sample 2: Existing project minimal...")
        samples.append(await sample_2_existing_minimal())

        print("Running sample 3: BUG-001 reproduction...")
        samples.append(await sample_3_bug_001_reproduction())

        print("Running sample 4: Existing with research...")
        samples.append(await sample_4_existing_with_research())

        print("Running sample 5: Structured format...")
        samples.append(await sample_5_structured_format())

    except Exception as e:
        print(f"❌ Error during sampling: {e}")
        import traceback
        traceback.print_exc()
        return

    # Generate report
    print("\n" + "="*80)
    print("TOKEN ANALYSIS REPORT")
    print("="*80 + "\n")

    for sample in samples:
        print(f"Sample {sample['sample_id']}:")
        print(f"  Scenario: {sample['scenario']}")
        print(f"  Tokens: {sample['total_tokens']}")
        print(f"  Chars: {sample['char_count']}")
        print(f"  Tokens/Char: {sample['tokens_per_char']:.3f}")
        if "is_new" in sample:
            print(f"  Is New: {sample['is_new']}")
        if sample.get("bug_detected"):
            print(f"  ⚠️  BUG DETECTED: Shows as new when should be existing")
        print()

    # Statistics
    token_counts = [s["total_tokens"] for s in samples if s.get("format") != "structured"]
    if token_counts:
        avg = sum(token_counts) / len(token_counts)
        print(f"Average tokens (readable format): {avg:.1f}")
        print(f"Min: {min(token_counts)}, Max: {max(token_counts)}")
        print(f"Range: {max(token_counts) - min(token_counts)}")

    # Save results
    output_file = Path(__file__).parent / "token_analysis_results.json"
    with open(output_file, "w") as f:
        json.dump(samples, f, indent=2)

    print(f"\n✅ Results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
