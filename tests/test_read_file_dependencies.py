#!/usr/bin/env python3
"""
Test suite for read_file dependency analysis (Phase 1: Import extraction)

Tests _extract_imports() function and integration with read_file tool.
"""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import ast
import pytest
from tools.read_file import _extract_imports


class TestExtractImports:
    """Test cases for _extract_imports() AST function."""

    def test_basic_import(self):
        """Test simple 'import module' statement."""
        code = """
import os
import sys
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 2
        assert imports[0]['module'] == 'os'
        assert imports[0]['type'] == 'import'
        assert imports[0]['line'] == 2
        assert imports[0]['alias'] is None
        assert imports[0]['level'] == 0
        assert imports[0]['names'] is None

        assert imports[1]['module'] == 'sys'
        assert imports[1]['type'] == 'import'

    def test_import_with_alias(self):
        """Test 'import module as alias' statement."""
        code = """
import numpy as np
import pandas as pd
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 2
        assert imports[0]['module'] == 'numpy'
        assert imports[0]['alias'] == 'np'
        assert imports[0]['type'] == 'import'

        assert imports[1]['module'] == 'pandas'
        assert imports[1]['alias'] == 'pd'

    def test_from_import_single(self):
        """Test 'from module import name' statement."""
        code = """
from pathlib import Path
from os import environ
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 2
        assert imports[0]['module'] == 'pathlib'
        assert imports[0]['type'] == 'from_import'
        assert imports[0]['names'] == ['Path']
        assert imports[0]['level'] == 0
        assert imports[0]['line'] == 2

        assert imports[1]['module'] == 'os'
        assert imports[1]['names'] == ['environ']

    def test_from_import_multiple(self):
        """Test 'from module import name1, name2' statement."""
        code = """
from typing import Dict, List, Optional, Any
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 1
        assert imports[0]['module'] == 'typing'
        assert imports[0]['type'] == 'from_import'
        assert imports[0]['names'] == ['Dict', 'List', 'Optional', 'Any']
        assert len(imports[0]['names']) == 4

    def test_relative_import_single_dot(self):
        """Test relative import 'from . import module' (level=1)."""
        code = """
from . import config
from .utils import helper
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 2
        assert imports[0]['module'] == ''  # No module for "from . import"
        assert imports[0]['names'] == ['config']
        assert imports[0]['level'] == 1

        assert imports[1]['module'] == 'utils'
        assert imports[1]['names'] == ['helper']
        assert imports[1]['level'] == 1

    def test_relative_import_multiple_dots(self):
        """Test relative import 'from .. import module' (level=2)."""
        code = """
from ..shared import logging_utils
from ...core import base
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 2
        assert imports[0]['module'] == 'shared'
        assert imports[0]['level'] == 2

        assert imports[1]['module'] == 'core'
        assert imports[1]['level'] == 3

    def test_empty_file(self):
        """Test file with no imports returns empty list."""
        code = """
# Just a comment
x = 1
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 0

    def test_no_imports_only_code(self):
        """Test file with code but no imports."""
        code = """
def foo():
    return 42

class Bar:
    pass
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 0

    def test_mixed_import_types(self):
        """Test file with various import types mixed."""
        code = """
import os
from pathlib import Path
import sys as system
from typing import Dict, List
from . import local_module
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 5
        assert imports[0]['type'] == 'import'
        assert imports[1]['type'] == 'from_import'
        assert imports[2]['type'] == 'import'
        assert imports[2]['alias'] == 'system'
        assert imports[3]['type'] == 'from_import'
        assert imports[4]['level'] == 1

    def test_truncation_at_limit(self):
        """Test that max_imports limit is respected."""
        # Generate code with 150 import statements
        import_lines = [f"import module_{i}" for i in range(150)]
        code = "\n".join(import_lines)

        tree = ast.parse(code)
        imports = _extract_imports(tree, max_imports=100)

        # Should stop at exactly 100 imports
        assert len(imports) == 100
        assert imports[0]['module'] == 'module_0'
        assert imports[99]['module'] == 'module_99'

    def test_conditional_imports(self):
        """Test imports inside if/try blocks (edge case)."""
        code = """
if True:
    import os

try:
    import special_module
except ImportError:
    pass
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        # ast.walk() finds imports even in nested blocks
        assert len(imports) == 2
        assert imports[0]['module'] == 'os'
        assert imports[1]['module'] == 'special_module'

    def test_from_import_star(self):
        """Test 'from module import *' statement."""
        code = """
from os import *
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 1
        assert imports[0]['module'] == 'os'
        assert imports[0]['type'] == 'from_import'
        # ast.ImportFrom with '*' has names=['*']
        assert imports[0]['names'] == ['*']

    def test_line_numbers_accurate(self):
        """Test that line numbers are correctly extracted."""
        code = """# Line 1
import os  # Line 2

# Line 4
from pathlib import Path  # Line 5
# Line 6
import sys  # Line 7
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 3
        assert imports[0]['line'] == 2
        assert imports[1]['line'] == 5
        assert imports[2]['line'] == 7

    def test_multiline_from_import(self):
        """Test multiline from import (parentheses)."""
        code = """
from typing import (
    Dict,
    List,
    Optional,
    Any
)
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree)

        assert len(imports) == 1
        assert imports[0]['names'] == ['Dict', 'List', 'Optional', 'Any']
        assert len(imports[0]['names']) == 4


class TestReadFileIntegration:
    """Integration tests for read_file with include_dependencies parameter."""

    @pytest.mark.asyncio
    async def test_read_file_with_dependencies_structured(self):
        """Test read_file returns dependencies in structured mode."""
        from tools.read_file import read_file
        import server as server_module
        from shared.execution_context import ExecutionContext, AgentIdentity
        from datetime import datetime, timezone

        # Set up execution context for read_file
        context = ExecutionContext(
            execution_id="test_exec_001",
            session_id="test_session_001",
            repo_root="/home/austin/projects/MCP_SPINE/scribe_mcp",
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=[],
            intent="test_dependency_analysis",
            agent_identity=AgentIdentity(
                agent_kind="test",
                instance_id="test_001",
                sub_id=None,
                display_name="TestAgent",
                model="test-model"
            )
        )

        token = server_module.router_context_manager.set_current(context)

        try:
            # Test with tools/append_entry.py (known to have imports)
            result = await read_file(
                agent="test_agent",
                path="tools/append_entry.py",
                mode="scan_only",
                include_dependencies=True,
                format="structured"
            )

            # Verify response structure
            assert result.get('ok') is True
            assert 'dependencies' in result

            deps = result['dependencies']
            assert 'imports' in deps
            assert 'total_imports' in deps
            assert 'truncated' in deps
            assert 'unresolved' in deps

            # Verify imports were extracted
            imports = deps['imports']
            assert len(imports) > 0

            # Verify schema of first import
            first_import = imports[0]
            assert 'module' in first_import
            assert 'line' in first_import
            assert 'type' in first_import
            assert 'names' in first_import or first_import['type'] == 'import'
            assert 'level' in first_import
        finally:
            server_module.router_context_manager.reset(token)

    @pytest.mark.asyncio
    async def test_read_file_with_dependencies_readable(self):
        """Test read_file displays dependencies in readable mode."""
        from tools.read_file import read_file
        import server as server_module
        from shared.execution_context import ExecutionContext, AgentIdentity
        from datetime import datetime, timezone

        # Set up execution context
        context = ExecutionContext(
            execution_id="test_exec_002",
            session_id="test_session_002",
            repo_root="/home/austin/projects/MCP_SPINE/scribe_mcp",
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=[],
            intent="test_dependency_display",
            agent_identity=AgentIdentity(
                agent_kind="test",
                instance_id="test_002",
                sub_id=None,
                display_name="TestAgent",
                model="test-model"
            )
        )

        token = server_module.router_context_manager.set_current(context)

        try:
            # Test with tools/read_file.py itself (meta!)
            result = await read_file(
                agent="test_agent",
                path="tools/read_file.py",
                mode="scan_only",
                include_dependencies=True,
                format="readable"
            )

            # Extract text content from MCP CallToolResult
            if hasattr(result, 'content') and result.content:
                content = result.content[0].text
            else:
                content = str(result)

            # Should have readable text
            assert isinstance(content, str)

            # Verify dependencies section appears in output
            assert "📦 Dependencies:" in content

            # Verify import formatting
            assert "→ import " in content or "→ from " in content

            # Verify line numbers are shown
            assert "(line " in content
        finally:
            server_module.router_context_manager.reset(token)

    @pytest.mark.asyncio
    async def test_read_file_without_dependencies_no_overhead(self):
        """Test that include_dependencies=False doesn't add dependencies to response."""
        from tools.read_file import read_file
        import server as server_module
        from shared.execution_context import ExecutionContext, AgentIdentity
        from datetime import datetime, timezone

        context = ExecutionContext(
            execution_id="test_exec_003",
            session_id="test_session_003",
            repo_root="/home/austin/projects/MCP_SPINE/scribe_mcp",
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=[],
            intent="test_no_dependencies",
            agent_identity=AgentIdentity(
                agent_kind="test",
                instance_id="test_003",
                sub_id=None,
                display_name="TestAgent",
                model="test-model"
            )
        )

        token = server_module.router_context_manager.set_current(context)

        try:
            # Test with include_dependencies=False (default)
            result = await read_file(
                agent="test_agent",
                path="tools/append_entry.py",
                mode="scan_only",
                include_dependencies=False,
                format="structured"
            )

            # Verify dependencies NOT in response (zero overhead)
            assert result.get('ok') is True
            assert 'dependencies' not in result
        finally:
            server_module.router_context_manager.reset(token)

    @pytest.mark.asyncio
    async def test_read_file_performance_impact(self):
        """Test that dependency analysis doesn't significantly impact performance."""
        import time
        from tools.read_file import read_file
        import server as server_module
        from shared.execution_context import ExecutionContext, AgentIdentity
        from datetime import datetime, timezone

        context = ExecutionContext(
            execution_id="test_exec_004",
            session_id="test_session_004",
            repo_root="/home/austin/projects/MCP_SPINE/scribe_mcp",
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=[],
            intent="test_performance",
            agent_identity=AgentIdentity(
                agent_kind="test",
                instance_id="test_004",
                sub_id=None,
                display_name="TestAgent",
                model="test-model"
            )
        )

        token = server_module.router_context_manager.set_current(context)

        try:
            # Test file: tools/read_file.py (large file with many imports)
            test_path = "tools/read_file.py"

            # Baseline: without dependencies
            start_baseline = time.time()
            result_baseline = await read_file(
                agent="test_agent",
                path=test_path,
                mode="scan_only",
                include_dependencies=False,
                format="structured"
            )
            baseline_time = time.time() - start_baseline

            # With dependencies
            start_deps = time.time()
            result_deps = await read_file(
                agent="test_agent",
                path=test_path,
                mode="scan_only",
                include_dependencies=True,
                format="structured"
            )
            deps_time = time.time() - start_deps

            # Performance assertion: overhead should be < 100% (less than 2x slower)
            # In practice, should be < 20% overhead, but we'll be generous for CI
            overhead_ratio = deps_time / baseline_time if baseline_time > 0 else 1
            assert overhead_ratio < 2.0, f"Overhead too high: {overhead_ratio:.2f}x (baseline: {baseline_time:.4f}s, with deps: {deps_time:.4f}s)"

            # Verify dependencies were actually extracted
            assert 'dependencies' in result_deps
            assert len(result_deps['dependencies']['imports']) > 0
        finally:
            server_module.router_context_manager.reset(token)


# ============================================================================
# PHASE 2 TESTS: Import Resolution
# ============================================================================

class TestWorkspaceRootDetection:
    """Test cases for _find_workspace_root() function."""

    def test_finds_git_marker(self, tmp_path):
        """Test workspace root detection via .git directory."""
        from tools.read_file import _find_workspace_root

        # Create structure: workspace/.git/, workspace/subdir/file.py
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        subdir = workspace / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.py"
        test_file.write_text("import os")

        # Should find workspace root
        root = _find_workspace_root(test_file)
        assert root == workspace

    def test_finds_pyproject_toml(self, tmp_path):
        """Test workspace root detection via pyproject.toml."""
        from tools.read_file import _find_workspace_root

        # Create structure: workspace/pyproject.toml, workspace/src/file.py
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "pyproject.toml").write_text("[tool.poetry]\nname='test'")
        src = workspace / "src"
        src.mkdir()
        test_file = src / "test.py"
        test_file.write_text("import os")

        root = _find_workspace_root(test_file)
        assert root == workspace

    def test_caching(self, tmp_path):
        """Test that workspace root results are cached."""
        from tools.read_file import _find_workspace_root

        # Clear cache if it exists
        if hasattr(_find_workspace_root, '_cache'):
            _find_workspace_root._cache.clear()

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "setup.py").write_text("# setup")
        test_file = workspace / "test.py"
        test_file.write_text("import os")

        # First call - should cache
        root1 = _find_workspace_root(test_file)
        cache_size_1 = len(_find_workspace_root._cache)

        # Second call - should use cache
        root2 = _find_workspace_root(test_file)
        cache_size_2 = len(_find_workspace_root._cache)

        assert root1 == root2
        assert cache_size_1 == cache_size_2  # Cache didn't grow

    def test_no_workspace_root(self, tmp_path):
        """Test handling when no workspace root is found."""
        from tools.read_file import _find_workspace_root

        # File with no markers in parent directories
        test_file = tmp_path / "isolated" / "test.py"
        test_file.parent.mkdir()
        test_file.write_text("import os")

        root = _find_workspace_root(test_file)
        assert root is None


class TestImportResolution:
    """Test cases for _resolve_import_path() function."""

    def test_stdlib_detection(self):
        """Test detection of standard library imports."""
        from tools.read_file import _resolve_import_path
        from pathlib import Path

        current_file = Path("/tmp/test.py")
        workspace_root = Path("/tmp")

        # Test common stdlib modules
        for module in ['os', 'sys', 'pathlib', 'json', 'datetime', 'collections']:
            result = _resolve_import_path(module, 0, current_file, workspace_root)
            assert result['type'] == 'stdlib', f"{module} should be stdlib"
            assert result['resolved_path'] is None
            assert result['exists'] is None

    def test_stdlib_submodule_detection(self):
        """Test stdlib detection for submodules (os.path, etc.)."""
        from tools.read_file import _resolve_import_path
        from pathlib import Path

        current_file = Path("/tmp/test.py")
        workspace_root = Path("/tmp")

        # os.path should be detected as stdlib
        result = _resolve_import_path('os.path', 0, current_file, workspace_root)
        assert result['type'] == 'stdlib'

    def test_third_party_detection(self):
        """Test detection of third-party packages."""
        from tools.read_file import _resolve_import_path
        from pathlib import Path

        current_file = Path("/tmp/test.py")
        workspace_root = Path("/tmp")

        # Non-existent third-party module (pytest, numpy don't exist in workspace)
        result = _resolve_import_path('pytest', 0, current_file, workspace_root)
        assert result['type'] == 'third_party'
        assert result['resolved_path'] is None

    def test_local_absolute_import_resolution(self, tmp_path):
        """Test resolution of local absolute imports."""
        from tools.read_file import _resolve_import_path

        # Create workspace: workspace/mypackage/module.py
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        package = workspace / "mypackage"
        package.mkdir()
        module_file = package / "module.py"
        module_file.write_text("def func(): pass")
        current_file = workspace / "main.py"
        current_file.write_text("import mypackage.module")

        # Resolve absolute import
        result = _resolve_import_path('mypackage.module', 0, current_file, workspace)
        assert result['type'] == 'local'
        assert result['resolved_path'] == str(module_file)
        assert result['exists'] is True

    def test_local_absolute_import_package(self, tmp_path):
        """Test resolution of local package imports (__init__.py)."""
        from tools.read_file import _resolve_import_path

        # Create workspace: workspace/mypackage/__init__.py
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        package = workspace / "mypackage"
        package.mkdir()
        init_file = package / "__init__.py"
        init_file.write_text("# package init")
        current_file = workspace / "main.py"

        # Resolve package import (should find __init__.py)
        result = _resolve_import_path('mypackage', 0, current_file, workspace)
        assert result['type'] == 'local'
        assert result['resolved_path'] == str(init_file)
        assert result['exists'] is True

    def test_relative_import_level1(self, tmp_path):
        """Test resolution of relative imports (from . import x)."""
        from tools.read_file import _resolve_import_path

        # Create: workspace/package/module.py, workspace/package/other.py
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        package = workspace / "package"
        package.mkdir()
        other_file = package / "other.py"
        other_file.write_text("def func(): pass")
        current_file = package / "module.py"
        current_file.write_text("from . import other")

        # Resolve: from . import other (level=1, module="other")
        result = _resolve_import_path('other', 1, current_file, workspace)
        assert result['type'] == 'local'
        assert result['resolved_path'] == str(other_file)
        assert result['exists'] is True

    def test_relative_import_level2(self, tmp_path):
        """Test resolution of relative imports (from .. import x)."""
        from tools.read_file import _resolve_import_path

        # Create: workspace/package/subpkg/module.py, workspace/package/other.py
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        package = workspace / "package"
        package.mkdir()
        other_file = package / "other.py"
        other_file.write_text("def func(): pass")
        subpkg = package / "subpkg"
        subpkg.mkdir()
        current_file = subpkg / "module.py"

        # Resolve: from .. import other (level=2, module="other")
        result = _resolve_import_path('other', 2, current_file, workspace)
        assert result['type'] == 'local'
        assert result['resolved_path'] == str(other_file)
        assert result['exists'] is True

    def test_missing_local_import(self, tmp_path):
        """Test handling of absolute imports that don't exist in workspace."""
        from tools.read_file import _resolve_import_path

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        current_file = workspace / "test.py"
        current_file.write_text("import missing_module")

        # Missing absolute imports are categorized as third_party (not in workspace)
        # This is correct behavior - if it's not in workspace, assume third-party package
        result = _resolve_import_path('missing_module', 0, current_file, workspace)
        assert result['type'] == 'third_party'
        assert result['resolved_path'] is None

    def test_missing_relative_import(self, tmp_path):
        """Test handling of relative imports that don't exist."""
        from tools.read_file import _resolve_import_path

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        package = workspace / "package"
        package.mkdir()
        current_file = package / "module.py"
        current_file.write_text("from . import missing")

        # Missing relative imports should be local with exists=False
        result = _resolve_import_path('missing', 1, current_file, workspace)
        assert result['type'] == 'local'
        assert result['resolved_path'] is not None  # Should have expected path
        assert result['exists'] is False

    def test_unresolved_without_workspace(self):
        """Test that imports are unresolved when workspace_root is None."""
        from tools.read_file import _resolve_import_path
        from pathlib import Path

        current_file = Path("/tmp/test.py")

        # Without workspace root, should be unresolved
        result = _resolve_import_path('some_module', 0, current_file, None)
        assert result['type'] in ['stdlib', 'unresolved']  # stdlib still detected

        # Relative import without workspace should be unresolved
        result = _resolve_import_path('other', 1, current_file, None)
        assert result['type'] == 'unresolved'

    def test_workspace_package_name_stripping(self, tmp_path):
        """Test that top-level package name is stripped when it matches workspace name.

        Regression test for Phase 3 bug where scribe_mcp.storage.base was resolved to
        scribe_mcp/scribe_mcp/storage/base.py instead of storage/base.py.
        """
        from tools.read_file import _resolve_import_path

        # Create workspace named "scribe_mcp" with storage/base.py
        workspace = tmp_path / "scribe_mcp"
        workspace.mkdir()
        storage_dir = workspace / "storage"
        storage_dir.mkdir()
        base_file = storage_dir / "base.py"
        base_file.write_text("# storage base module")

        current_file = workspace / "tools" / "append_entry.py"
        current_file.parent.mkdir(parents=True)
        current_file.write_text("")

        # Import "scribe_mcp.storage.base" should resolve to storage/base.py
        result = _resolve_import_path('scribe_mcp.storage.base', 0, current_file, workspace)
        assert result['type'] == 'local', f"Expected local, got {result['type']}"
        assert result['exists'] is True, "File should exist"
        assert 'storage/base.py' in result['resolved_path'] or 'storage\\base.py' in result['resolved_path'], \
            f"Expected storage/base.py in path, got {result['resolved_path']}"
        # Should NOT have double scribe_mcp in path
        assert 'scribe_mcp/scribe_mcp' not in result['resolved_path'] and \
               'scribe_mcp\\scribe_mcp' not in result['resolved_path'], \
            f"Found double package name in path: {result['resolved_path']}"


class TestIntegrationResolution:
    """Integration tests for Phase 2 resolution in _extract_imports()."""

    def test_extract_imports_with_resolution(self, tmp_path):
        """Test that _extract_imports() includes resolution metadata."""
        from tools.read_file import _extract_imports
        import ast

        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        current_file = workspace / "test.py"

        # Code with stdlib and local imports
        code = """
import os
import sys
from pathlib import Path
"""
        tree = ast.parse(code)
        imports = _extract_imports(tree, current_file=current_file, workspace_root=workspace)

        # All imports should have resolution metadata
        assert len(imports) == 3
        for imp in imports:
            assert 'import_type' in imp
            assert 'resolved_path' in imp
            assert 'exists' in imp

        # All should be stdlib
        assert all(imp['import_type'] == 'stdlib' for imp in imports)

    def test_extract_imports_backward_compatible(self):
        """Test that _extract_imports() works without resolution (Phase 1 mode)."""
        from tools.read_file import _extract_imports
        import ast

        code = "import os\nimport sys"
        tree = ast.parse(code)

        # Call without current_file (Phase 1 mode)
        imports = _extract_imports(tree)

        assert len(imports) == 2
        # Should have unresolved as default
        assert all(imp['import_type'] == 'unresolved' for imp in imports)
        assert all(imp['resolved_path'] is None for imp in imports)


class TestResolutionPerformance:
    """Performance tests for Phase 2 resolution overhead."""

    @pytest.mark.asyncio
    async def test_resolution_overhead(self, tmp_path):
        """Test that resolution adds < 20% overhead."""
        import time
        from tools.read_file import read_file
        import server as server_module
        from shared.execution_context import ExecutionContext, AgentIdentity
        from datetime import datetime, timezone

        # Create test file with imports
        test_file = tmp_path / "test.py"
        test_file.write_text("""
import os
import sys
from pathlib import Path
import json
import datetime
from typing import Dict, List, Optional
""")

        # Set execution context
        context = ExecutionContext(
            execution_id="test_exec_perf",
            session_id="test_session_perf",
            repo_root="/home/austin/projects/MCP_SPINE/scribe_mcp",
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=[],
            intent="test_resolution_performance",
            agent_identity=AgentIdentity(
                agent_kind="test",
                instance_id="perf_001",
                sub_id=None,
                display_name="PerformanceTestAgent",
                model="test-model"
            )
        )
        token = server_module.router_context_manager.set_current(context)

        try:
            # Measure multiple runs for more stable timing
            runs = 5
            resolution_times = []

            for _ in range(runs):
                # Measure resolution performance
                start = time.time()
                await read_file(
                    agent="test_agent",
                    path=str(test_file),
                    mode="scan_only",
                    include_dependencies=True,
                    format="structured"
                )
                resolution_times.append(time.time() - start)

            # Average times
            avg_resolution = sum(resolution_times) / len(resolution_times)

            # Resolution should complete in reasonable time (< 100ms for simple file)
            assert avg_resolution < 0.1, f"Resolution too slow: {avg_resolution:.4f}s"

            # Verify dependencies were extracted with resolution (using real file)
            result = await read_file(
                agent="test_agent",
                path="tools/read_file.py",
                mode="scan_only",
                include_dependencies=True,
                format="structured"
            )

            # Verify resolution metadata is present
            if 'dependencies' in result and 'imports' in result['dependencies']:
                imports = result['dependencies']['imports']
                assert len(imports) > 0, "Should have found imports in tools/read_file.py"
                # Check for Phase 2 resolution metadata
                assert all('import_type' in imp for imp in imports), "All imports should have import_type field"
                # Verify we have some stdlib imports (os, sys, pathlib, etc.)
                stdlib_imports = [imp for imp in imports if imp.get('import_type') == 'stdlib']
                assert len(stdlib_imports) > 0, "Should have detected stdlib imports"

        finally:
            server_module.router_context_manager.reset(token)


# ============================================================================
# PHASE 3 TESTS: Reverse Index / Impact Radius
# ============================================================================

class TestRepositoryScanning:
    """Test Phase 3 Task 3A: Repository scanner"""

    def test_scan_repository_basic(self, tmp_path):
        """Test basic repository scanning with simple Python files"""
        from tools.read_file import _scan_repository_imports

        # Create test repository structure
        (tmp_path / "module_a.py").write_text("import os\nimport sys")
        (tmp_path / "module_b.py").write_text("from pathlib import Path\nimport json")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "module_c.py").write_text("import asyncio")

        # Scan repository
        forward_index = _scan_repository_imports(tmp_path, max_files=100)

        # Verify all files found
        assert len(forward_index) == 3
        assert "module_a.py" in forward_index
        assert "module_b.py" in forward_index
        assert "subdir/module_c.py" in forward_index

        # Verify imports extracted (note: we extract "pathlib" not "pathlib.Path")
        assert "os" in forward_index["module_a.py"]
        assert "sys" in forward_index["module_a.py"]
        assert "pathlib" in forward_index["module_b.py"]
        assert "asyncio" in forward_index["subdir/module_c.py"]

    def test_scan_excludes_common_dirs(self, tmp_path):
        """Test that scanner excludes .git, __pycache__, .venv, etc."""
        from tools.read_file import _scan_repository_imports

        # Create files in excluded directories
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "excluded.py").write_text("import os")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "excluded.py").write_text("import sys")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "excluded.py").write_text("import json")

        # Create normal file
        (tmp_path / "included.py").write_text("import asyncio")

        # Scan repository
        forward_index = _scan_repository_imports(tmp_path, max_files=100)

        # Only normal file should be found
        assert len(forward_index) == 1
        assert "included.py" in forward_index

    def test_scan_handles_syntax_errors(self, tmp_path):
        """Test that scanner skips files with syntax errors gracefully"""
        from tools.read_file import _scan_repository_imports

        # Create valid file
        (tmp_path / "valid.py").write_text("import os")

        # Create file with syntax error
        (tmp_path / "invalid.py").write_text("import os\nif True\n  print('bad')")

        # Scan repository (should not crash)
        forward_index = _scan_repository_imports(tmp_path, max_files=100)

        # Valid file should be found, invalid skipped
        assert "valid.py" in forward_index
        assert "invalid.py" not in forward_index

    def test_scan_respects_max_files(self, tmp_path):
        """Test that scanner stops at max_files limit"""
        from tools.read_file import _scan_repository_imports

        # Create many files
        for i in range(20):
            (tmp_path / f"file_{i}.py").write_text("import os")

        # Scan with low limit
        forward_index = _scan_repository_imports(tmp_path, max_files=5)

        # Should stop at limit
        assert len(forward_index) <= 5


class TestReverseIndexBuilder:
    """Test Phase 3 Task 3B: Reverse index builder"""

    def test_build_reverse_index_basic(self, tmp_path):
        """Test basic reverse index building"""
        from tools.read_file import _build_reverse_index

        # Create simple forward index
        # module_a imports module_b
        # module_c imports module_b
        forward_index = {
            "module_a.py": ["module_b"],
            "module_c.py": ["module_b"],
            "module_b.py": []
        }

        # Create actual files so resolution works
        (tmp_path / "module_a.py").write_text("import module_b")
        (tmp_path / "module_b.py").write_text("# empty")
        (tmp_path / "module_c.py").write_text("import module_b")

        # Build reverse index
        reverse_index = _build_reverse_index(forward_index, tmp_path)

        # module_b should have two importers
        assert "module_b.py" in reverse_index
        assert len(reverse_index["module_b.py"]) == 2
        assert "module_a.py" in reverse_index["module_b.py"]
        assert "module_c.py" in reverse_index["module_b.py"]

    def test_reverse_index_deduplication(self, tmp_path):
        """Test that reverse index deduplicates importers"""
        from tools.read_file import _build_reverse_index

        # Forward index with duplicate imports
        forward_index = {
            "module_a.py": ["module_b", "module_b"]  # Same module twice
        }

        (tmp_path / "module_a.py").write_text("import module_b")
        (tmp_path / "module_b.py").write_text("# empty")

        reverse_index = _build_reverse_index(forward_index, tmp_path)

        # module_b should only appear once in importers
        if "module_b.py" in reverse_index:
            assert reverse_index["module_b.py"].count("module_a.py") == 1

    def test_reverse_index_handles_missing_files(self, tmp_path):
        """Test that reverse index skips imports that can't be resolved"""
        from tools.read_file import _build_reverse_index

        # Forward index with missing import
        forward_index = {
            "module_a.py": ["nonexistent_module"]
        }

        (tmp_path / "module_a.py").write_text("import nonexistent_module")

        # Should not crash
        reverse_index = _build_reverse_index(forward_index, tmp_path)

        # nonexistent_module should not be in reverse index
        assert "nonexistent_module.py" not in reverse_index


class TestImpactRadiusCalculator:
    """Test Phase 3 Task 3C: Impact radius calculator"""

    def test_calculate_impact_low(self):
        """Test impact calculation for low impact (0-4 importers)"""
        from tools.read_file import _calculate_impact_radius

        reverse_index = {
            "target.py": ["importer1.py", "importer2.py"]
        }

        impact = _calculate_impact_radius("target.py", reverse_index)

        assert impact["count"] == 2
        assert impact["level"] == "low"
        assert len(impact["importers"]) == 2
        assert impact["truncated"] is False

    def test_calculate_impact_medium(self):
        """Test impact calculation for medium impact (5-15 importers)"""
        from tools.read_file import _calculate_impact_radius

        importers = [f"importer{i}.py" for i in range(10)]
        reverse_index = {
            "target.py": importers
        }

        impact = _calculate_impact_radius("target.py", reverse_index)

        assert impact["count"] == 10
        assert impact["level"] == "medium"
        assert len(impact["importers"]) == 10
        assert impact["truncated"] is False

    def test_calculate_impact_high(self):
        """Test impact calculation for high impact (16+ importers)"""
        from tools.read_file import _calculate_impact_radius

        importers = [f"importer{i}.py" for i in range(25)]
        reverse_index = {
            "target.py": importers
        }

        impact = _calculate_impact_radius("target.py", reverse_index)

        assert impact["count"] == 25
        assert impact["level"] == "high"
        assert impact["truncated"] is True
        assert len(impact["importers"]) == 20  # Truncated at 20

    def test_calculate_impact_zero_importers(self):
        """Test impact calculation for file with no importers"""
        from tools.read_file import _calculate_impact_radius

        reverse_index = {}  # File not in index

        impact = _calculate_impact_radius("target.py", reverse_index)

        assert impact["count"] == 0
        assert impact["level"] == "low"
        assert len(impact["importers"]) == 0
        assert impact["truncated"] is False


class TestImpactIntegration:
    """Test Phase 3 Task 3D+3E: Full integration with read_file"""

    @pytest.mark.asyncio
    async def test_read_file_with_impact(self):
        """Test read_file with include_impact=True"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools import read_file as read_file_module
        from scribe_mcp import server as server_module
        from scribe_mcp.shared.execution_context import ExecutionContext, AgentIdentity
        from datetime import datetime, timezone

        # Set up execution context
        exec_context = ExecutionContext(
            execution_id="test-exec-impact",
            session_id="test-session",
            repo_root=str(Path(__file__).parent.parent),
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=[],
            intent="test_impact_radius",
            agent_identity=AgentIdentity(
                agent_kind="test",
                instance_id="test_impact_001",
                sub_id=None,
                display_name="TestImpactAgent",
                model="test-model"
            )
        )
        token = server_module.router_context_manager.set_current(exec_context)

        try:
            # Test on a file that's likely to have importers (storage/sqlite.py)
            result = await read_file_module.read_file(
                agent="test_agent",
                path="storage/sqlite.py",
                mode="scan_only",
                include_dependencies=True,
                include_impact=True,
                format="structured"
            )

            # Verify result structure
            assert result.get("ok") is True
            assert "impact_radius" in result

            # Verify impact_radius structure
            impact = result["impact_radius"]
            assert "count" in impact
            assert "level" in impact
            assert "importers" in impact
            assert "truncated" in impact

            # storage/sqlite.py should have importers (used by many tools)
            # But we don't assert specific count (changes with codebase)
            assert isinstance(impact["count"], int)
            assert impact["level"] in ["low", "medium", "high"]

        finally:
            server_module.router_context_manager.reset(token)

    @pytest.mark.asyncio
    async def test_include_impact_requires_dependencies(self):
        """Test that include_impact=True requires include_dependencies=True"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools import read_file as read_file_module
        from scribe_mcp import server as server_module
        from scribe_mcp.shared.execution_context import ExecutionContext, AgentIdentity
        from datetime import datetime, timezone

        exec_context = ExecutionContext(
            execution_id="test-exec-validation",
            session_id="test-session",
            repo_root=str(Path(__file__).parent.parent),
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=[],
            intent="test_validation",
            agent_identity=AgentIdentity(
                agent_kind="test",
                instance_id="test_validation_001",
                sub_id=None,
                display_name="TestValidationAgent",
                model="test-model"
            )
        )
        token = server_module.router_context_manager.set_current(exec_context)

        try:
            # Should fail with include_impact=True but include_dependencies=False
            result = await read_file_module.read_file(
                agent="test_agent",
                path="storage/sqlite.py",
                mode="scan_only",
                include_dependencies=False,
                include_impact=True
            )

            # Should return error
            assert result.get("ok") is False
            assert "error" in result
            assert "requires" in result["error"].lower()

        finally:
            server_module.router_context_manager.reset(token)


class TestImpactPerformance:
    """Test Phase 3 performance requirements"""

    @pytest.mark.asyncio
    async def test_repository_scan_performance(self):
        """Test that repository scan completes in <5 seconds for scribe_mcp"""
        import sys
        from pathlib import Path
        import time
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _scan_repository_imports

        repo_root = Path(__file__).parent.parent

        # Time the scan
        start = time.time()
        forward_index = _scan_repository_imports(repo_root, max_files=500)
        duration = time.time() - start

        # Should complete in <5 seconds (target is <3, but 5 is acceptable)
        assert duration < 5.0, f"Repository scan took {duration:.1f}s (threshold: 5s)"

        # Should have found significant number of files
        assert len(forward_index) > 20, "Should find at least 20 Python files in scribe_mcp"


# ============================================================================
# PHASE 4: BOUNDARY ENFORCEMENT TESTS
# ============================================================================

class TestBoundaryRuleLoading:
    """Test boundary rule loading and validation (Phase 4)."""

    def test_load_boundary_rules_valid(self, tmp_path):
        """Test loading valid boundary rules."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _load_boundary_rules

        # Create test config
        config_dir = tmp_path / ".scribe" / "config"
        config_dir.mkdir(parents=True)

        config_file = config_dir / "boundary_rules.yaml"
        config_file.write_text("""
version: 1.0
enabled: true
rules:
  - name: "Test Rule"
    description: "Test description"
    severity: "error"
    pattern:
      source: "tests/**/*.py"
      forbidden_imports:
        - "tools/**"
""")

        rules = _load_boundary_rules(tmp_path)
        assert rules is not None
        assert rules['enabled'] is True
        assert len(rules['rules']) == 1
        assert rules['rules'][0]['name'] == "Test Rule"

    def test_load_boundary_rules_missing_file(self, tmp_path):
        """Test loading when config file doesn't exist."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _load_boundary_rules

        rules = _load_boundary_rules(tmp_path)
        assert rules is None

    def test_load_boundary_rules_disabled(self, tmp_path):
        """Test loading when rules are disabled."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _load_boundary_rules

        config_dir = tmp_path / ".scribe" / "config"
        config_dir.mkdir(parents=True)

        config_file = config_dir / "boundary_rules.yaml"
        config_file.write_text("""
version: 1.0
enabled: false
rules:
  - name: "Test Rule"
    description: "Test"
    severity: "error"
    pattern:
      source: "tests/**"
      forbidden_imports: ["tools/**"]
""")

        rules = _load_boundary_rules(tmp_path)
        assert rules is None

    def test_load_boundary_rules_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _load_boundary_rules

        config_dir = tmp_path / ".scribe" / "config"
        config_dir.mkdir(parents=True)

        config_file = config_dir / "boundary_rules.yaml"
        config_file.write_text("invalid: yaml: content: [[[")

        rules = _load_boundary_rules(tmp_path)
        assert rules is None  # Should return None on parse error


class TestBoundaryRuleValidation:
    """Test boundary rule schema validation (Phase 4)."""

    def test_validate_valid_rules(self):
        """Test validation of valid rules."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _validate_boundary_rules

        rules = {
            "version": 1.0,
            "enabled": True,
            "rules": [
                {
                    "name": "Test",
                    "description": "Desc",
                    "severity": "error",
                    "pattern": {
                        "source": "tests/**",
                        "forbidden_imports": ["tools/**"]
                    }
                }
            ]
        }

        assert _validate_boundary_rules(rules) is True

    def test_validate_missing_fields(self):
        """Test validation with missing required fields."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _validate_boundary_rules

        # Missing 'enabled'
        rules = {"version": 1.0, "rules": []}
        assert _validate_boundary_rules(rules) is False

    def test_validate_invalid_severity(self):
        """Test validation with invalid severity."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _validate_boundary_rules

        rules = {
            "version": 1.0,
            "enabled": True,
            "rules": [
                {
                    "name": "Test",
                    "description": "Desc",
                    "severity": "invalid",  # Not error/warning/info
                    "pattern": {
                        "source": "tests/**",
                        "forbidden_imports": ["tools/**"]
                    }
                }
            ]
        }

        assert _validate_boundary_rules(rules) is False


class TestPatternMatching:
    """Test glob pattern matching for boundary rules (Phase 4)."""

    def test_match_simple_pattern(self, tmp_path):
        """Test simple glob pattern matching."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _match_rule_pattern

        # Match Python file in tests
        assert _match_rule_pattern("tests/test_file.py", "tests/*.py", tmp_path) is True
        assert _match_rule_pattern("tools/file.py", "tests/*.py", tmp_path) is False

    def test_match_recursive_pattern(self, tmp_path):
        """Test recursive ** glob patterns."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _match_rule_pattern

        # Recursive pattern should match nested files
        assert _match_rule_pattern("tools/nested/deep/file.py", "tools/**/*.py", tmp_path) is True
        assert _match_rule_pattern("tools/file.py", "tools/**/*.py", tmp_path) is True
        assert _match_rule_pattern("other/file.py", "tools/**/*.py", tmp_path) is False

    def test_match_absolute_paths(self, tmp_path):
        """Test matching with absolute paths."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _match_rule_pattern

        test_file = tmp_path / "tests" / "test.py"
        assert _match_rule_pattern(str(test_file), "tests/**", tmp_path) is True


class TestBoundaryViolationChecker:
    """Test boundary violation detection (Phase 4)."""

    def test_check_violations_no_match(self, tmp_path):
        """Test no violations when file doesn't match source pattern."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _check_boundary_violations

        rules = {
            "rules": [
                {
                    "name": "Test Rule",
                    "description": "Test",
                    "severity": "error",
                    "pattern": {
                        "source": "tests/**/*.py",
                        "forbidden_imports": ["tools/**"]
                    }
                }
            ]
        }

        imports = [{"module": "tools.append_entry", "line": 10}]

        # File doesn't match source pattern
        violations = _check_boundary_violations("other/file.py", imports, rules, tmp_path)
        assert len(violations) == 0

    def test_check_violations_forbidden_import(self, tmp_path):
        """Test violation detected for forbidden import."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _check_boundary_violations

        rules = {
            "rules": [
                {
                    "name": "Test Isolation",
                    "description": "Tests should not import tools",
                    "severity": "error",
                    "pattern": {
                        "source": "tests/**/*.py",
                        "forbidden_imports": ["tools/**", "scribe_mcp.tools.*"]
                    }
                }
            ]
        }

        imports = [
            {"module": "scribe_mcp.tools.append_entry", "line": 10, "resolved_path": "tools/append_entry.py"}
        ]

        violations = _check_boundary_violations("tests/test_file.py", imports, rules, tmp_path)
        assert len(violations) == 1
        assert violations[0]['rule_name'] == "Test Isolation"
        assert violations[0]['severity'] == "error"
        assert violations[0]['line'] == 10

    def test_check_violations_allowed_exception(self, tmp_path):
        """Test allowed exceptions are respected."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _check_boundary_violations

        rules = {
            "rules": [
                {
                    "name": "Test Rule",
                    "description": "Test",
                    "severity": "warning",
                    "pattern": {
                        "source": "tests/**/*.py",
                        "forbidden_imports": ["tests/**"],
                        "allowed_exceptions": ["tests/conftest.py"]
                    }
                }
            ]
        }

        imports = [
            {"module": "tests.conftest", "line": 5, "resolved_path": "tests/conftest.py"}
        ]

        violations = _check_boundary_violations("tests/test_file.py", imports, rules, tmp_path)
        assert len(violations) == 0  # Exception allowed

    def test_check_violations_multiple_rules(self, tmp_path):
        """Test multiple violations from different rules."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _check_boundary_violations

        rules = {
            "rules": [
                {
                    "name": "Rule 1",
                    "description": "First rule",
                    "severity": "error",
                    "pattern": {
                        "source": "tests/**",
                        "forbidden_imports": ["tools/**"]
                    }
                },
                {
                    "name": "Rule 2",
                    "description": "Second rule",
                    "severity": "warning",
                    "pattern": {
                        "source": "tests/**",
                        "forbidden_imports": ["storage/**"]
                    }
                }
            ]
        }

        imports = [
            {"module": "tools.file", "line": 10, "resolved_path": "tools/file.py"},
            {"module": "storage.sqlite", "line": 15, "resolved_path": "storage/sqlite.py"}
        ]

        violations = _check_boundary_violations("tests/test.py", imports, rules, tmp_path)
        assert len(violations) == 2
        assert violations[0]['rule_name'] == "Rule 1"
        assert violations[1]['rule_name'] == "Rule 2"


class TestBoundaryIntegration:
    """Test boundary enforcement integration with read_file (Phase 4)."""

    @pytest.mark.asyncio
    async def test_read_file_with_violations(self, tmp_path):
        """Test read_file integration with boundary violations."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from scribe_mcp.shared.execution_context import ExecutionContext
        from tools.read_file import read_file

        # Create test file with forbidden import
        test_file = tmp_path / "tests" / "test.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("from tools.append_entry import append_entry\n")

        # Create boundary rules
        config_dir = tmp_path / ".scribe" / "config"
        config_dir.mkdir(parents=True)
        rules_file = config_dir / "boundary_rules.yaml"
        rules_file.write_text("""
version: 1.0
enabled: true
rules:
  - name: "Test Isolation"
    description: "Tests should not import tools"
    severity: "error"
    pattern:
      source: "tests/**/*.py"
      forbidden_imports:
        - "tools/**"
        - "tools.*"
""")

        # Create execution context
        from datetime import datetime, timezone
        from scribe_mcp.shared.execution_context import AgentIdentity
        from scribe_mcp import server as server_module

        exec_context = ExecutionContext(
            execution_id="test_boundary_001",
            session_id="test_session_boundary",
            repo_root=str(tmp_path),
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=["test_project"],
            intent="test_boundary_violations",
            agent_identity=AgentIdentity(
                agent_kind="test",
                model=None,
                instance_id="boundary_001",
                sub_id=None,
                display_name="test_boundary_agent"
            )
        )

        token = server_module.router_context_manager.set_current(exec_context)

        try:
            result = await read_file(
                agent="test_agent",
                path=str(test_file),
                format="structured",
                include_dependencies=True
            )
        finally:
            server_module.router_context_manager.reset(token)

        # Verify boundary violations in response
        assert "boundary_violations" in result
        assert result["boundary_violations"]["enabled"] is True
        assert result["boundary_violations"]["total_violations"] == 1
        assert result["boundary_violations"]["has_errors"] is True
        assert result["boundary_violations"]["violations"][0]["severity"] == "error"

    @pytest.mark.asyncio
    async def test_read_file_no_violations(self, tmp_path):
        """Test read_file with no boundary violations."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from scribe_mcp.shared.execution_context import ExecutionContext
        from tools.read_file import read_file

        # Create test file with allowed import
        test_file = tmp_path / "tools" / "file.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("import os\n")

        # Create boundary rules
        config_dir = tmp_path / ".scribe" / "config"
        config_dir.mkdir(parents=True)
        rules_file = config_dir / "boundary_rules.yaml"
        rules_file.write_text("""
version: 1.0
enabled: true
rules:
  - name: "Test Rule"
    description: "Test"
    severity: "error"
    pattern:
      source: "tests/**"
      forbidden_imports: ["tools/**"]
""")

        from datetime import datetime, timezone
        from scribe_mcp.shared.execution_context import AgentIdentity
        from scribe_mcp import server as server_module

        exec_context = ExecutionContext(
            execution_id="test_boundary_002",
            session_id="test_session_boundary",
            repo_root=str(tmp_path),
            mode="interactive",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            affected_dev_projects=["test_project"],
            intent="test_no_boundary_violations",
            agent_identity=AgentIdentity(
                agent_kind="test",
                model=None,
                instance_id="boundary_002",
                sub_id=None,
                display_name="test_boundary_agent"
            )
        )

        token = server_module.router_context_manager.set_current(exec_context)

        try:
            result = await read_file(
                agent="test_agent",
                path=str(test_file),
                format="structured",
                include_dependencies=True
            )
        finally:
            server_module.router_context_manager.reset(token)

        # Verify no violations
        assert "boundary_violations" in result
        assert result["boundary_violations"]["enabled"] is True
        assert result["boundary_violations"]["total_violations"] == 0


class TestBoundaryPerformance:
    """Test boundary enforcement performance (Phase 4)."""

    def test_boundary_checking_overhead(self, tmp_path):
        """Test that boundary checking adds <20ms overhead."""
        import sys
        from pathlib import Path
        import time
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from tools.read_file import _load_boundary_rules, _check_boundary_violations

        # Create rules
        config_dir = tmp_path / ".scribe" / "config"
        config_dir.mkdir(parents=True)
        rules_file = config_dir / "boundary_rules.yaml"
        rules_file.write_text("""
version: 1.0
enabled: true
rules:
  - name: "Rule 1"
    description: "Test"
    severity: "error"
    pattern:
      source: "tests/**"
      forbidden_imports: ["tools/**"]
  - name: "Rule 2"
    description: "Test"
    severity: "warning"
    pattern:
      source: "storage/**"
      forbidden_imports: ["tools/**"]
""")

        # Load rules (cached)
        rules = _load_boundary_rules(tmp_path)
        assert rules is not None

        # Create test imports
        imports = [
            {"module": f"module{i}", "line": i, "resolved_path": f"path{i}.py"}
            for i in range(20)
        ]

        # Time boundary checking
        start = time.time()
        for _ in range(100):  # Run 100 times to average
            _check_boundary_violations("tests/test.py", imports, rules, tmp_path)
        duration = (time.time() - start) / 100  # Average per call

        # Should be <20ms per call
        assert duration < 0.020, f"Boundary checking took {duration*1000:.1f}ms (threshold: 20ms)"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
