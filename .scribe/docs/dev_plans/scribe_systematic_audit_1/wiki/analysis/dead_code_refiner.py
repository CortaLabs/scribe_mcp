#!/usr/bin/env python3
"""
Dead Code Refiner - Filter false positives and categorize true dead code
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set

class DeadCodeRefiner:
    """Refine AST analysis results to separate true dead code from false positives"""

    # Known false positive patterns
    FALSE_POSITIVE_IMPORTS = {
        'annotations',  # PEP 563 - used by type checker
    }

    LIKELY_INTENTIONAL_UNUSED = {
        'Dict', 'List', 'Any', 'Optional', 'Union', 'Tuple', 'Set',  # Type hints
        'timezone', 'datetime',  # May be used in type annotations
        'AsyncMock', 'MagicMock', 'Mock', 'patch',  # Test utilities
    }

    def __init__(self, results_file: str):
        with open(results_file, 'r') as f:
            self.data = json.load(f)

        self.true_unused_imports = {}
        self.false_positive_imports = {}
        self.production_unreferenced = []
        self.test_unreferenced = []

    def categorize_unused_imports(self):
        """Separate true unused imports from false positives"""
        for filepath, imports in self.data['unused_imports'].items():
            true_unused = []
            false_positives = []

            for name, line in imports:
                if name in self.FALSE_POSITIVE_IMPORTS:
                    false_positives.append((name, line, 'PEP 563 annotations'))
                elif name in self.LIKELY_INTENTIONAL_UNUSED:
                    false_positives.append((name, line, 'Type hint or test utility'))
                else:
                    true_unused.append((name, line))

            if true_unused:
                self.true_unused_imports[filepath] = true_unused
            if false_positives:
                self.false_positive_imports[filepath] = false_positives

    def categorize_unreferenced_defs(self):
        """Separate production code from test code unreferenced definitions"""
        for defn in self.data['unreferenced_definitions']:
            if defn['file'].startswith('tests/'):
                self.test_unreferenced.append(defn)
            else:
                self.production_unreferenced.append(defn)

    def analyze_production_dead_code(self) -> Dict:
        """Deep dive into production code unreferenced definitions"""
        # Group by file
        by_file = defaultdict(list)
        for defn in self.production_unreferenced:
            by_file[defn['file']].append(defn)

        # Categorize by likely safety
        safe_to_remove = []
        needs_investigation = []
        likely_false_positive = []

        for defn in self.production_unreferenced:
            name = defn['name']
            file = defn['file']

            # Private helpers are likely actually used (called internally)
            if name.startswith('_') and not name.startswith('__'):
                likely_false_positive.append({**defn, 'reason': 'Private helper - may be called internally'})

            # __init__ exports
            elif file.endswith('__init__.py'):
                likely_false_positive.append({**defn, 'reason': 'Module __init__ export'})

            # Test utilities/fixtures in non-test files
            elif 'test' in name.lower() or 'fixture' in name.lower() or 'mock' in name.lower():
                needs_investigation.append({**defn, 'reason': 'Test-related name in production code'})

            # Classes and functions without special markers
            else:
                needs_investigation.append({**defn, 'reason': 'Potentially unused'})

        return {
            'by_file': dict(by_file),
            'safe_to_remove': safe_to_remove,
            'needs_investigation': needs_investigation,
            'likely_false_positive': likely_false_positive
        }

    def generate_refined_report(self, output_file: str):
        """Generate refined markdown report"""
        self.categorize_unused_imports()
        self.categorize_unreferenced_defs()
        prod_analysis = self.analyze_production_dead_code()

        with open(output_file, 'w') as f:
            f.write("# Dead Code Analysis - Refined Report\n\n")
            f.write("**Date**: 2026-01-05\n")
            f.write("**Agent**: ResearchAgent-Phase4-DeadCode\n")
            f.write("**Status**: Filtered for false positives\n\n")

            f.write("## Executive Summary\n\n")
            f.write(f"- **Total Files Analyzed**: {self.data['total_files']}\n")
            f.write(f"- **True Unused Imports**: {sum(len(v) for v in self.true_unused_imports.values())}\n")
            f.write(f"- **False Positive Imports**: {sum(len(v) for v in self.false_positive_imports.values())} (annotations, type hints)\n")
            f.write(f"- **Production Unreferenced**: {len(self.production_unreferenced)}\n")
            f.write(f"- **Test Unreferenced**: {len(self.test_unreferenced)} (expected - pytest fixtures/helpers)\n\n")

            # True unused imports
            f.write("## True Unused Imports (Action Required)\n\n")
            f.write("These imports should be removed as they serve no purpose:\n\n")
            if self.true_unused_imports:
                for filepath, imports in sorted(self.true_unused_imports.items()):
                    f.write(f"### {filepath}\n\n")
                    for name, line in imports:
                        f.write(f"- Line {line}: `{name}` - **SAFE TO REMOVE**\n")
                    f.write("\n")
            else:
                f.write("No true unused imports found (all are false positives).\n\n")

            # False positive imports explanation
            f.write("## False Positive Imports (Intentional)\n\n")
            f.write("These imports appear unused but serve legitimate purposes:\n\n")
            annotation_count = sum(1 for fp_list in self.false_positive_imports.values() for name, _, _ in fp_list if name == 'annotations')
            f.write(f"- **`annotations` imports**: {annotation_count} files (PEP 563 - required for postponed type hint evaluation)\n")
            type_hint_count = sum(len([x for x in fp_list if x[0] != 'annotations']) for fp_list in self.false_positive_imports.values())
            f.write(f"- **Type hint imports**: ~{type_hint_count} (Dict, List, Any, etc. - used in type annotations)\n\n")

            # Production code unreferenced
            f.write("## Production Code - Unreferenced Definitions\n\n")

            f.write("### Likely False Positives (Do Not Remove)\n\n")
            for item in prod_analysis['likely_false_positive']:
                f.write(f"- **{item['name']}** ({item['type']}) in `{item['file']}:{item['line']}` - *{item['reason']}*\n")
            if not prod_analysis['likely_false_positive']:
                f.write("None identified.\n")
            f.write("\n")

            f.write("### Needs Investigation (Verify Before Removal)\n\n")
            for item in prod_analysis['needs_investigation']:
                f.write(f"- **{item['name']}** ({item['type']}) in `{item['file']}:{item['line']}` - *{item['reason']}*\n")
            if not prod_analysis['needs_investigation']:
                f.write("None identified.\n")
            f.write("\n")

            # Test code section
            f.write("## Test Code - Unreferenced Definitions\n\n")
            f.write(f"**Total**: {len(self.test_unreferenced)} test functions/classes\n\n")
            f.write("**Analysis**: Test files contain many helper functions and fixtures that pytest discovers dynamically.\n")
            f.write("These are NOT dead code - they're invoked by pytest's test discovery mechanism.\n\n")

            # Top test files
            test_by_file = defaultdict(int)
            for defn in self.test_unreferenced:
                test_by_file[defn['file']] += 1

            f.write("Top test files with 'unreferenced' functions:\n\n")
            for filepath, count in sorted(test_by_file.items(), key=lambda x: -x[1])[:10]:
                f.write(f"- `{filepath}`: {count} functions (pytest test functions/fixtures)\n")
            f.write("\n")

            # Recommendations
            f.write("## Recommendations\n\n")
            f.write("### Immediate Actions\n\n")
            true_unused_count = sum(len(v) for v in self.true_unused_imports.values())
            f.write(f"1. Remove {true_unused_count} true unused imports (safe, automated cleanup)\n")
            f.write(f"2. Review {len(prod_analysis['needs_investigation'])} production unreferenced definitions\n")
            f.write("3. Validate private helper functions are actually called (grep verification)\n\n")

            f.write("### No Action Required\n\n")
            f.write(f"1. {annotation_count} `annotations` imports (PEP 563 requirement)\n")
            f.write(f"2. {len(self.test_unreferenced)} test function 'unreferenced' findings (pytest discovery)\n")
            f.write(f"3. {len(prod_analysis['likely_false_positive'])} __init__ exports and private helpers\n\n")

if __name__ == "__main__":
    results_file = Path(__file__).parent / "dead_code_results.json"
    output_file = Path(__file__).parent / "dead_code_refined.md"

    refiner = DeadCodeRefiner(str(results_file))
    refiner.generate_refined_report(str(output_file))

    print(f"Refined report generated: {output_file}")
    print(f"\nKey Findings:")
    refiner.categorize_unused_imports()
    refiner.categorize_unreferenced_defs()
    print(f"  True unused imports: {sum(len(v) for v in refiner.true_unused_imports.values())}")
    print(f"  False positive imports: {sum(len(v) for v in refiner.false_positive_imports.values())}")
    print(f"  Production unreferenced: {len(refiner.production_unreferenced)}")
    print(f"  Test unreferenced: {len(refiner.test_unreferenced)} (expected)")
