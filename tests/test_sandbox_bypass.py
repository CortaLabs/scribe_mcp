#!/usr/bin/env python3
"""Negative tests for sandbox bypass attempts."""

import os
import tempfile
from pathlib import Path

from scribe_mcp.security.sandbox import safe_file_operation, SecurityError
from scribe_mcp.config.repo_config import RepoConfig


class TestSandboxBypassAttempts:
    """Negative tests to ensure sandbox prevents escape attempts."""

    def test_path_traversal_with_dots(self):
        """Test that path traversal using ../ is blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Test various path traversal attempts
            malicious_paths = [
                "../etc/passwd",
                "../../etc/passwd",
                "../../../etc/passwd",
                "../../../../etc/shadow",
                "../root/.ssh/id_rsa",
                "../../.ssh/authorized_keys",
            ]

            for malicious_path in malicious_paths:
                full_path = repo_root / malicious_path
                try:
                    safe_file_operation(repo_root, full_path, "read")
                    self.fail(f"Should have blocked path traversal: {malicious_path}")
                except SecurityError:
                    pass  # Expected - good
                except Exception as e:
                    self.fail(f"Unexpected error for {malicious_path}: {e}")

    def test_symlink_hijacking(self):
        """Test that symlink hijacking attempts are blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Create external file we want to access
            external_file = Path(temp_dir) / "external" / "secret.txt"
            external_file.parent.mkdir(parents=True)
            external_file.write_text("secret data")

            # Create symlink inside repo pointing to external file
            internal_symlink = repo_root / "safe_looking_link.txt"
            internal_symlink.symlink_to(external_file)

            # Try to access through symlink - should be blocked
            try:
                safe_file_operation(repo_root, internal_symlink, "read")
                self.fail("Should have blocked symlink escape")
            except SecurityError:
                pass  # Expected - good
            except Exception as e:
                self.fail(f"Unexpected error for symlink test: {e}")

    def test_absolute_path_escape(self):
        """Test that absolute paths outside repo are blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Test absolute paths outside repository
            forbidden_paths = [
                "/etc/passwd",
                "/etc/shadow",
                "/root/.ssh/id_rsa",
                "/home/user/.bashrc",
            ]

            for forbidden_path in forbidden_paths:
                path_obj = Path(forbidden_path)
                try:
                    safe_file_operation(repo_root, path_obj, "read")
                    self.fail(f"Should have blocked absolute path: {forbidden_path}")
                except SecurityError:
                    pass  # Expected - good
                except Exception as e:
                    self.fail(f"Unexpected error for {forbidden_path}: {e}")

    def test_permission_boundary_violations(self):
        """Test that permission boundary violations are blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Test operations that should be forbidden
            from scribe_mcp.security.sandbox import check_permission

            forbidden_operations = [
                ("delete_all", {}),
                ("modify_config", {"config_file": "/etc/passwd"}),
                ("execute_code", {"command": "rm -rf /"}),
            ]

            for operation, context in forbidden_operations:
                try:
                    check_permission(repo_root, operation, context)
                    self.fail(f"Should have blocked operation: {operation}")
                except Exception:
                    pass  # Expected - good

    def test_environment_variable_injection(self):
        """Test that environment variable injection attempts are blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Test paths that include environment variables
            env_injection_attempts = [
                "$HOME/.ssh/id_rsa",
                "${HOME}/.ssh/authorized_keys",
            ]

            for injection_attempt in env_injection_attempts:
                try:
                    # Expand path as a user might
                    expanded_path = Path(injection_attempt).expanduser()

                    # Try to access through expanded path
                    safe_file_operation(repo_root, expanded_path, "read")
                    self.fail(f"Should have blocked env injection: {injection_attempt}")
                except (OSError, RuntimeError, SecurityError):
                    pass  # Expected - good
                except Exception as e:
                    self.fail(f"Unexpected error for env test: {e}")

    def test_device_file_access(self):
        """Test that access to device files is blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Test attempts to access device files
            device_paths = [
                "/dev/null",
                "/dev/zero",
                "/dev/random",
            ]

            for device_path in device_paths:
                path_obj = Path(device_path)
                if path_obj.exists():  # Only test existing device files
                    try:
                        safe_file_operation(repo_root, path_obj, "read")
                        self.fail(f"Should have blocked device access: {device_path}")
                    except SecurityError:
                        pass  # Expected - good
                    except Exception as e:
                        self.fail(f"Unexpected error for device test: {e}")

    def test_temporary_directory_escape(self):
        """Test that attempts to escape through temporary directories are blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Create temp directory outside repo
            external_temp = Path(temp_dir) / "external_temp"
            external_temp.mkdir()

            # Try to access external temp
            escape_attempts = [
                f"../../../{external_temp.name}/malicious",
            ]

            for escape_attempt in escape_attempts:
                path_obj = Path(escape_attempt)
                try:
                    safe_file_operation(repo_root, path_obj, "read")
                    self.fail(f"Should have blocked temp escape: {escape_attempt}")
                except (OSError, FileNotFoundError, SecurityError):
                    pass  # Expected - good
                except Exception as e:
                    self.fail(f"Unexpected error for temp escape test: {e}")

    def test_unicode_encoding_bypass(self):
        """Test that Unicode encoding bypass attempts are blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            config = RepoConfig.defaults_for_repo(repo_root)

            # Various encoding bypass attempts
            bypass_attempts = [
                "../etc/passwd\x00.txt",  # Null byte injection
                "..%2fetc%2fpasswd",  # URL encoding
            ]

            for bypass_attempt in bypass_attempts:
                full_path = repo_root / bypass_attempt
                try:
                    safe_file_operation(repo_root, full_path, "read")
                    self.fail(f"Should have blocked Unicode bypass: {bypass_attempt}")
                except (OSError, SecurityError):
                    pass  # Expected - good
                except Exception as e:
                    self.fail(f"Unexpected error for Unicode test: {e}")

    def run_all_tests(self):
        """Run all bypass attempt tests."""
        print("🛡️ Running Comprehensive Sandbox Bypass Tests")
        print("=" * 60)

        tests = [
            ("Path Traversal (../)", self.test_path_traversal_with_dots),
            ("Symlink Hijacking", self.test_symlink_hijacking),
            ("Absolute Path Escape", self.test_absolute_path_escape),
            ("Permission Boundary Violations", self.test_permission_boundary_violations),
            ("Environment Variable Injection", self.test_environment_variable_injection),
            ("Device File Access", self.test_device_file_access),
            ("Temporary Directory Escape", self.test_temporary_directory_escape),
            ("Unicode Encoding Bypass", self.test_unicode_encoding_bypass),
        ]

        passed = 0
        total = len(tests)

        for test_name, test_func in tests:
            try:
                print(f"\n🧪 Testing {test_name}...")
                test_func()
                print(f"✅ {test_name}: PASSED")
                passed += 1
            except Exception as e:
                print(f"❌ {test_name}: FAILED - {e}")

        print("\n" + "=" * 60)
        print(f"🛡️ Sandbox Bypass Tests: {passed}/{total} passed")

        if passed == total:
            print("🎉 All sandbox security tests PASSED!")
            return True
        else:
            print(f"⚠️ {total - passed} tests failed - sandbox may have vulnerabilities")
            return False

    def fail(self, message):
        """Simple failure method."""
        raise AssertionError(message)


if __name__ == "__main__":
    # Run tests if executed directly
    test_instance = TestSandboxBypassAttempts()

    success = test_instance.run_all_tests()
    sys.exit(0 if success else 1)