#!/usr/bin/env python3
"""
Circular Dependency Analyzer for scribe_mcp
Systematically finds all circular import relationships
"""
import ast
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, List, Tuple

def get_python_files(root_dir: str) -> List[Path]:
    """Get all Python files in the directory."""
    root = Path(root_dir)
    return [f for f in root.rglob("*.py") if "__pycache__" not in str(f) and ".venv" not in str(f)]

def extract_imports(file_path: Path) -> Tuple[List[str], List[str]]:
    """Extract all imports from a Python file.
    Returns (absolute_imports, relative_imports)
    """
    absolute_imports = []
    relative_imports = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    absolute_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    if node.level > 0:
                        relative_imports.append((node.module, node.level))
                    else:
                        absolute_imports.append(node.module)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")

    return absolute_imports, relative_imports

def module_path_to_import(file_path: Path, root_dir: Path) -> str:
    """Convert file path to module import path."""
    rel_path = file_path.relative_to(root_dir)
    if rel_path.name == "__init__.py":
        module_parts = rel_path.parent.parts
    else:
        module_parts = rel_path.with_suffix('').parts
    return ".".join(module_parts)

def build_dependency_graph(root_dir: str) -> Dict[str, Set[str]]:
    """Build a dependency graph showing which modules import which."""
    root = Path(root_dir)
    files = get_python_files(root_dir)

    graph = defaultdict(set)

    for file_path in files:
        module_name = module_path_to_import(file_path, root)
        abs_imports, rel_imports = extract_imports(file_path)

        # Add scribe_mcp imports
        for imp in abs_imports:
            if imp.startswith("scribe_mcp"):
                graph[module_name].add(imp)

        # Handle relative imports (convert to absolute)
        for rel_module, level in rel_imports:
            # Calculate the absolute module path
            current_parts = module_name.split('.')
            if level > len(current_parts):
                continue

            base_parts = current_parts[:-level] if level > 0 else current_parts
            if rel_module:
                absolute_module = '.'.join(base_parts + rel_module.split('.'))
            else:
                absolute_module = '.'.join(base_parts)

            if absolute_module.startswith("scribe_mcp"):
                graph[module_name].add(absolute_module)

    return graph

def find_circular_dependencies(graph: Dict[str, Set[str]]) -> List[List[str]]:
    """Find all circular dependencies using DFS."""
    visited = set()
    rec_stack = set()
    cycles = []

    def dfs(node: str, path: List[str]):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path.copy())
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]

                # Normalize cycle (start with lexicographically smallest)
                min_idx = cycle.index(min(cycle[:-1]))
                normalized = cycle[min_idx:-1] + cycle[:min_idx] + [cycle[min_idx]]

                # Check if we already have this cycle
                if normalized not in cycles:
                    cycles.append(normalized)

        rec_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return cycles

def main():
    root_dir = "/home/austin/projects/MCP_SPINE/scribe_mcp"

    print("Building dependency graph...")
    graph = build_dependency_graph(root_dir)

    print(f"Analyzed {len(graph)} modules")
    print(f"Total dependencies: {sum(len(deps) for deps in graph.values())}")

    print("\nFinding circular dependencies...")
    cycles = find_circular_dependencies(graph)

    print(f"\nFound {len(cycles)} circular dependency cycles:\n")

    for i, cycle in enumerate(cycles, 1):
        print(f"Cycle {i}: ({len(cycle)-1} modules)")
        for j in range(len(cycle)-1):
            print(f"  {cycle[j]}")
            print(f"    ↓ imports")
        print(f"  {cycle[-1]} (back to start)")
        print()

    # Export results for detailed analysis
    with open("/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/circular_deps_raw.txt", "w") as f:
        f.write(f"Circular Dependencies Found: {len(cycles)}\n")
        f.write("=" * 80 + "\n\n")

        for i, cycle in enumerate(cycles, 1):
            f.write(f"CYCLE {i}:\n")
            f.write("-" * 80 + "\n")
            for j in range(len(cycle)-1):
                f.write(f"{cycle[j]} → {cycle[j+1]}\n")
            f.write("\n")

    print(f"Detailed results written to .scribe/circular_deps_raw.txt")

if __name__ == "__main__":
    main()
