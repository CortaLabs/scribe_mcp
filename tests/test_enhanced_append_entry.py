#!/usr/bin/env python3
"""Comprehensive test suite for enhanced append_entry functionality.

This test validates all the new features:
- Newline handling and sanitization
- Auto-split multiline detection
- Enhanced bulk mode with direct list support
- Individual timestamps for bulk entries
- Robust error handling with fallbacks
- Performance optimizations for large content
"""

import asyncio
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scribe_mcp.tools.append_entry import (
    _sanitize_message,
    _should_use_bulk_mode,
    _split_multiline_message,
    _prepare_bulk_items_with_timestamps,
    _apply_inherited_metadata,
    append_entry,
)
from scribe_mcp.config.settings import Settings
from scribe_mcp.state import StateManager


class MockStorage:
    """Mock storage backend for testing."""

    def __init__(self):
        self.projects = {}
        self.entries = []

    async def setup(self):
        pass

    async def close(self):
        pass

    async def fetch_project(self, name: str):
        return self.projects.get(name)

    async def upsert_project(self, name: str, repo_root: str, progress_log_path: str):
        project = {"name": name, "root": repo_root, "progress_log": progress_log_path}
        self.projects[name] = project
        return project

    async def insert_entry(self, **kwargs):
        self.entries.append(kwargs)


class EnhancedAppendEntryTest:
    """Test suite for enhanced append_entry functionality."""

    def __init__(self):
        self.temp_dir = None
        self.mock_storage = None

    def setup(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_storage = MockStorage()

        # Create test project directory structure
        self.project_dir = self.temp_dir / "test-project"
        self.project_dir.mkdir()
        (self.project_dir / ".scribe" / "docs" / "dev_plans").mkdir(parents=True)

        self.log_path = self.project_dir / ".scribe" / "docs" / "dev_plans" / "PROGRESS_LOG.md"

    def cleanup(self):
        """Clean up test environment."""
        import shutil
        if self.temp_dir:
            shutil.rmtree(self.temp_dir)

    def test_message_sanitization(self):
        """Test message sanitization for MCP protocol."""
        print("🧪 Testing message sanitization...")

        # Test basic newline replacement
        message = "Line 1\nLine 2\r\nLine 3"
        sanitized = _sanitize_message(message)
        expected = "Line 1\\nLine 2\\nLine 3"
        assert sanitized == expected, f"Expected {expected}, got {sanitized}"
        print("   ✅ Basic newline sanitization")

        # Test empty message
        assert _sanitize_message("") == ""
        assert _sanitize_message(None) == None
        print("   ✅ Empty message handling")

        # Test complex multiline with special characters
        complex_msg = "Error: Something went wrong\nTraceback: line 42\n  -> function call"
        sanitized = _sanitize_message(complex_msg)
        assert "\\n" in sanitized and "\n" not in sanitized
        print("   ✅ Complex multiline sanitization")

    def test_bulk_mode_detection(self):
        """Test bulk mode detection logic."""
        print("🧪 Testing bulk mode detection...")

        # Test newline detection
        single_line = "This is a single line"
        multiline = "Line 1\nLine 2\nLine 3"

        assert not _should_use_bulk_mode(single_line)
        assert _should_use_bulk_mode(multiline)
        print("   ✅ Newline detection")

        # Test pipe character detection
        pipe_message = "Status: OK | Component: auth | Time: 1.2s"
        assert _should_use_bulk_mode(pipe_message)
        print("   ✅ Pipe character detection")

        # Test long message detection
        long_message = "x" * 600  # Over 500 character threshold
        assert _should_use_bulk_mode(long_message)
        print("   ✅ Long message detection")

        # Test explicit bulk parameters
        assert _should_use_bulk_mode("", items="[]")
        assert _should_use_bulk_mode("", items_list=[{"message": "test"}])
        print("   ✅ Explicit bulk parameter detection")

    def test_multiline_splitting(self):
        """Test multiline message splitting with smart detection."""
        print("🧪 Testing multiline splitting...")

        # Test basic splitting
        message = "Task 1: Setup\nTask 2: Implement\nTask 3: Test\n\nTask 4: Deploy"
        entries = _split_multiline_message(message)

        assert len(entries) == 4  # Should skip empty line
        assert entries[0]["message"] == "Task 1: Setup"
        assert entries[3]["message"] == "Task 4: Deploy"
        print("   ✅ Basic splitting with empty line filtering")

        # Test status auto-detection
        error_message = "Error: Connection failed\n  timeout after 30s\nSUCCESS: Retry worked"
        entries = _split_multiline_message(error_message)

        assert entries[0].get("status") == "error"
        assert entries[2].get("status") == "success"
        print("   ✅ Status auto-detection")

        # Test emoji detection
        emoji_message = "🚀 Deploying application\n✅ Deployment complete\n🎉 All systems operational"
        entries = _split_multiline_message(emoji_message)

        assert entries[0].get("emoji") == "🚀"
        assert entries[1].get("emoji") == "✅"
        assert entries[2].get("emoji") == "🎉"
        print("   ✅ Emoji auto-detection")

    def test_timestamp_preparation(self):
        """Test timestamp preparation for bulk entries."""
        print("🧪 Testing timestamp preparation...")

        items = [
            {"message": "First task"},
            {"message": "Second task"},
            {"message": "Third task"},
        ]

        # Test with base timestamp
        base_time = "2025-10-25 12:00:00 UTC"
        prepared = _prepare_bulk_items_with_timestamps(items, base_time, stagger_seconds=5)

        assert len(prepared) == 3
        assert prepared[0]["timestamp_utc"] == "2025-10-25 12:00:00 UTC"
        assert prepared[1]["timestamp_utc"] == "2025-10-25 12:00:05 UTC"
        assert prepared[2]["timestamp_utc"] == "2025-10-25 12:00:10 UTC"
        print("   ✅ Timestamp staggering with base time")

        # Test without base timestamp (should use current time)
        items_no_timestamp = [{"message": "Test"}]
        prepared_now = _prepare_bulk_items_with_timestamps(items_no_timestamp)

        assert "timestamp_utc" in prepared_now[0]
        # Should be close to current time
        ts = datetime.strptime(prepared_now[0]["timestamp_utc"], "%Y-%m-%d %H:%M:%S UTC")
        now = datetime.now(timezone.utc)
        assert abs((now - ts).total_seconds()) < 5  # Within 5 seconds
        print("   ✅ Auto-timestamp generation")

    def test_metadata_inheritance(self):
        """Test metadata inheritance for bulk entries."""
        print("🧪 Testing metadata inheritance...")

        items = [
            {"message": "Task 1"},
            {"message": "Task 2", "status": "success"},
            {"message": "Task 3", "meta": {"component": "auth"}},
            {"message": "Task 4", "status": "error", "meta": {"component": "db", "retry": 3}},
            {"message": "Task 5", "meta": "scope=child"},
        ]

        inherited_meta = {"project": "my-app", "version": "2.0"}
        inherited_status = "info"
        inherited_emoji = "🔧"
        inherited_agent = "BuildBot"

        result = _apply_inherited_metadata(
            items, inherited_meta, inherited_status, inherited_emoji, inherited_agent
        )

        # Check inherited values applied to items without explicit values
        assert result[0]["status"] == "info"  # Inherited
        assert result[0]["emoji"] == "🔧"     # Inherited
        assert result[0]["agent"] == "BuildBot"  # Inherited
        assert result[0]["meta"]["project"] == "my-app"  # Inherited
        assert result[0]["meta"]["version"] == "2.0"   # Inherited

        # Check explicit values are preserved
        assert result[1]["status"] == "success"  # Explicit, not inherited
        assert result[1]["emoji"] == "🔧"        # Inherited
        assert result[2]["meta"]["component"] == "auth"  # Explicit
        assert result[2]["meta"]["project"] == "my-app"   # Merged with inherited

        # Check proper merging for complex case
        assert result[3]["status"] == "error"  # Explicit preserved
        assert result[3]["meta"]["component"] == "db"  # Explicit preserved
        assert result[3]["meta"]["retry"] == 3          # Explicit preserved
        assert result[3]["meta"]["project"] == "my-app" # Inherited merged

        # String metadata should be normalized and merged
        assert result[4]["meta"]["scope"] == "child"
        assert result[4]["meta"]["project"] == "my-app"

        print("   ✅ Metadata inheritance and merging")

    async def test_enhanced_append_entry_functionality(self):
        """Test the enhanced append_entry function with various scenarios."""
        print("🧪 Testing enhanced append_entry functionality...")

        # Mock the global dependencies
        import scribe_mcp.tools.append_entry as append_module
        import scribe_mcp.server as server_module

        # Set up mock server state
        original_storage = server_module.storage_backend
        original_state_manager = server_module.state_manager

        try:
            server_module.storage_backend = self.mock_storage
            server_module.state_manager = StateManager()

            # Create mock project data
            project_data = {
                "name": "test-project",
                "root": str(self.project_dir),
                "progress_log": str(self.log_path),
                "defaults": {
                    "emoji": "📋",
                    "agent": "TestAgent"
                }
            }

            # Mock agent project data
            async def mock_get_agent_project_data(agent_id):
                return project_data, ["test-project"]

            original_get_agent_project_data = append_module.get_agent_project_data
            append_module.get_agent_project_data = mock_get_agent_project_data

            # Mock agent identity
            class MockAgentIdentity:
                async def get_or_create_agent_id(self):
                    return "test-agent"
                async def update_agent_activity(self, *args, **kwargs):
                    pass

            server_module.agent_identity = MockAgentIdentity()

            # Test 1: Single line message (should work normally)
            result = await append_entry(
                message="Single line test message",
                status="info",
                meta={"test": "single_line"}
            )

            assert result["ok"], f"Single line failed: {result.get('error')}"
            assert result["written_count"] == 1
            print("   ✅ Single line message")

            # Test 2: Multiline message with auto_split (should auto-convert to bulk)
            multiline_message = "🚀 Starting deployment\n✅ Build completed\n🔧 Installing dependencies\n✅ Deployment successful"
            result = await append_entry(
                message=multiline_message,
                status="info",
                meta={"phase": "deployment"},
                auto_split=True,
                stagger_seconds=2
            )

            assert result["ok"], f"Multiline auto-split failed: {result.get('error')}"
            assert result["written_count"] == 4
            print("   ✅ Multiline auto-split functionality")

            # Test 3: Direct list bulk mode
            bulk_items = [
                {"message": "Database migration", "status": "info"},
                {"message": "Cache clearing", "status": "success"},
                {"message": "Service restart", "status": "info"},
            ]
            result = await append_entry(
                items_list=bulk_items,
                meta={"operation": "maintenance"},
                stagger_seconds=1
            )

            assert result["ok"], f"Direct list bulk failed: {result.get('error')}"
            assert result["written_count"] == 3
            print("   ✅ Direct list bulk mode")

            # Test 4: JSON string bulk mode (backwards compatibility)
            json_items = json.dumps([
                {"message": "API endpoint created", "status": "success"},
                {"message": "Documentation updated", "status": "info"},
            ])
            result = await append_entry(
                items=json_items,
                meta={"component": "api"}
            )

            assert result["ok"], f"JSON bulk failed: {result.get('error')}"
            assert result["written_count"] == 2
            print("   ✅ JSON string bulk mode (backwards compatibility)")

            # Test 5: Error handling for invalid input
            result = await append_entry(
                message="Invalid | pipe | characters",
                auto_split=False  # Disable auto-split to test validation
            )

            assert not result["ok"]
            assert "pipe" in result["error"]
            assert "suggestion" in result
            print("   ✅ Error handling with helpful suggestions")

            # Test 6: Large bulk content (performance test)
            large_bulk = []
            for i in range(25):  # Test with 25 items
                large_bulk.append({
                    "message": f"Processing item {i+1}",
                    "status": "info" if i % 2 == 0 else "success",
                    "meta": {"batch_id": "test_batch", "item": i+1}
                })

            start_time = time.time()
            result = await append_entry(
                items_list=large_bulk,
                meta={"test": "performance"}
            )
            duration = time.time() - start_time

            assert result["ok"], f"Large bulk failed: {result.get('error')}"
            assert result["written_count"] == 25
            assert duration < 5.0  # Should complete within 5 seconds
            print(f"   ✅ Large bulk performance ({duration:.2f}s for 25 items)")

            # Verify log file was created and has content
            assert self.log_path.exists()
            log_content = self.log_path.read_text()
            assert len(log_content.splitlines()) >= 1 + 4 + 3 + 2 + 25  # All previous entries
            print("   ✅ Log file integrity")

            # Restore original functions
            append_module.get_agent_project_data = original_get_agent_project_data

        finally:
            # Restore original dependencies
            server_module.storage_backend = original_storage
            server_module.state_manager = original_state_manager

    def run_all_tests(self):
        """Run all test cases."""
        print("🚀 Enhanced append_entry Test Suite")
        print("=" * 50)

        try:
            self.setup()

            # Run synchronous tests
            self.test_message_sanitization()
            self.test_bulk_mode_detection()
            self.test_multiline_splitting()
            self.test_timestamp_preparation()
            self.test_metadata_inheritance()

            # Run async tests
            asyncio.run(self.test_enhanced_append_entry_functionality())

            print("\n🎉 All tests passed!")
            print("✅ Enhanced append_entry is working perfectly!")

        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            self.cleanup()

        return True


def main():
    """Run the enhanced append_entry test suite."""
    test_suite = EnhancedAppendEntryTest()
    success = test_suite.run_all_tests()

    if success:
        print("\n🎯 ENHANCED FEATURES VALIDATED:")
        print("   ✅ Newline rejection fixed with message sanitization")
        print("   ✅ Smart multiline detection and auto-split")
        print("   ✅ Enhanced bulk mode with direct list support")
        print("   ✅ Individual timestamps with staggering")
        print("   ✅ Metadata inheritance and merging")
        print("   ✅ Robust error handling with helpful suggestions")
        print("   ✅ Performance optimizations for large content")
        print("   ✅ Backwards compatibility maintained")

        print("\n💡 USAGE EXAMPLES:")
        print("   # Multiline content (auto-splits):")
        print("   await append_entry(message='Task 1\\nTask 2\\nTask 3')")
        print("")
        print("   # Direct list bulk mode:")
        print("   await append_entry(items_list=[")
        print("       {'message': 'Item 1', 'status': 'info'},")
        print("       {'message': 'Item 2', 'status': 'success'}")
        print("   ])")
        print("")
        print("   # With metadata inheritance:")
        print("   await append_entry(")
        print("       message='Line 1\\nLine 2\\nLine 3',")
        print("       meta={'project': 'my-app', 'version': '2.0'},")
        print("       status='info',")
        print("       stagger_seconds=5")
        print("   )")

        return True
    else:
        print("\n❌ Some tests failed - check the implementation")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
