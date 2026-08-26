#!/usr/bin/env python3
"""Simple integration test for global Scribe deployment."""

import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.mark.regression
def test_repo_discovery():
    """Test repository discovery functionality."""
    print("🧪 Testing repository discovery...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a test repository
        repo_path = temp_path / "test-repo"
        repo_path.mkdir()

        # Add .git directory to make it a repository
        (repo_path / ".git").mkdir()

        # Import and test discovery
        try:
            from scribe_mcp.config.repo_config import RepoDiscovery

            discovered = RepoDiscovery.find_repo_root(repo_path)
            assert discovered == repo_path, f"Expected {repo_path}, got {discovered}"

            council_repo = temp_path / "council-repo"
            council_marker = council_repo / ".council" / "council.yaml"
            nested_path = council_repo / "nested" / "child"
            council_marker.parent.mkdir(parents=True)
            council_marker.write_text("council: test\n", encoding="utf-8")
            nested_path.mkdir(parents=True)

            assert RepoDiscovery.find_repo_root(council_repo) == council_repo
            assert RepoDiscovery.find_repo_root(nested_path) == council_repo

            refusal_cases = {
                "bare-council-dir": lambda root: (root / ".council").mkdir(parents=True),
                "misplaced-council-yaml": lambda root: (root / "council.yaml").write_text(
                    "council: misplaced\n",
                    encoding="utf-8",
                ),
                "similar-council-marker": lambda root: (
                    (root / ".council").mkdir(parents=True),
                    (root / ".council" / "council.yml").write_text(
                        "council: similar\n",
                        encoding="utf-8",
                    ),
                ),
            }
            for name, create_marker in refusal_cases.items():
                candidate = temp_path / name
                candidate.mkdir()
                create_marker(candidate)
                tree_before = {
                    path.relative_to(candidate)
                    for path in candidate.rglob("*")
                }

                assert RepoDiscovery.find_repo_root(candidate) is None
                assert {
                    path.relative_to(candidate)
                    for path in candidate.rglob("*")
                } == tree_before

            print("   ✅ Repository discovery works")

        except Exception as e:
            print(f"   ❌ Repository discovery failed: {e}")
            raise

    # Test passed if we get here


def test_config_loading():
    """Test configuration loading."""
    print("🧪 Testing configuration loading...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test repository
        repo_path = temp_path / "test-repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        # Create .scribe config
        scribe_dir = repo_path / ".scribe"
        scribe_dir.mkdir()

        config_content = """
repo_slug: test-config-repo
dev_plans_dir: documentation
progress_log_name: CHANGELOG.md
permissions:
  allow_rotate: false
  allow_generate_docs: true
default_emoji: "🧪"
"""

        config_file = scribe_dir / "scribe.yaml"
        config_file.write_text(config_content)

        try:
            from scribe_mcp.config.repo_config import RepoDiscovery

            config = RepoDiscovery.load_config(repo_path)
            assert config.repo_slug == "test-config-repo"
            assert config.dev_plans_dir.name == "documentation"
            assert config.progress_log_name == "CHANGELOG.md"
            assert config.permissions["allow_rotate"] is False
            assert config.default_emoji == "🧪"

            print("   ✅ Configuration loading works")

        except Exception as e:
            print(f"   ❌ Configuration loading failed: {e}")
            raise

    # Test passed if we get here


def test_sandbox_isolation():
    """Test path sandboxing and isolation."""
    print("🧪 Testing sandbox isolation...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create two test repositories
        repo1 = temp_path / "repo1"
        repo1.mkdir()
        (repo1 / ".git").mkdir()

        repo2 = temp_path / "repo2"
        repo2.mkdir()
        (repo2 / ".git").mkdir()

        try:
            from scribe_mcp.security.sandbox import get_safety_instance, SecurityError

            # Get safety instance and sandboxes
            safety = get_safety_instance()
            sandbox1 = safety.get_sandbox(repo1)
            _sandbox2 = safety.get_sandbox(repo2)

            # Test isolation
            file1 = repo1 / "docs" / "test.md"
            file2 = repo2 / "docs" / "test.md"

            # Repo 1 should allow its own files
            assert sandbox1.is_allowed(file1), "Repo 1 should allow its own files"

            # Repo 1 should NOT allow repo 2 files
            assert not sandbox1.is_allowed(file2), "Repo 1 should not allow repo 2 files"

            # Test sandboxing enforcement
            sandbox1.sandbox_path(file1)  # Should not raise

            try:
                sandbox1.sandbox_path(file2)
                assert False, "Should have raised SecurityError"
            except SecurityError:
                pass  # Expected

            print("   ✅ Sandbox isolation works")

        except Exception as e:
            print(f"   ❌ Sandbox isolation failed: {e}")
            raise

    # Test passed if we get here


def test_cli_doctor():
    """Test the CLI doctor functionality."""
    print("🧪 Testing CLI doctor functionality...")

    try:
        # Change to a temporary directory for testing
        original_cwd = os.getcwd()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a test repository
            repo_path = temp_path / "test-repo"
            repo_path.mkdir()
            (repo_path / ".git").mkdir()
            (repo_path / ".scribe" / "docs" / "dev_plans").mkdir(parents=True)

            # Create .scribe config
            scribe_dir = repo_path / ".scribe"
            scribe_dir.mkdir(exist_ok=True)
            config_file = scribe_dir / "scribe.yaml"
            config_file.write_text("repo_slug: test-repo\\n")

            os.chdir(repo_path)

            # Test the doctor function
            from scripts.scribe_cli import doctor

            # Capture print output by redirecting stdout
            import io
            from contextlib import redirect_stdout

            f = io.StringIO()
            with redirect_stdout(f):
                doctor()

            output = f.getvalue()
            assert "Repository Discovery:" in output
            assert "Configuration:" in output
            assert "test-repo" in output

            print("   ✅ CLI doctor functionality works")

    except Exception as e:
        print(f"   ❌ CLI doctor functionality failed: {e}")
        raise
    finally:
        os.chdir(original_cwd)

    # Test passed if we get here


def main():
    """Run all integration tests."""
    print("🚀 Running Global Scribe Integration Tests...\\n")

    tests = [
        test_repo_discovery,
        test_config_loading,
        test_sandbox_isolation,
        test_cli_doctor,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"   Test failed: {test.__name__}")
        except Exception as e:
            print(f"   Test error in {test.__name__}: {e}")
        print()

    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All integration tests passed!")
        print("✅ Global Scribe deployment is working correctly!")
        # Test passed if we get here
    else:
        print("❌ Some tests failed")
        raise


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
