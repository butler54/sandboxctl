"""Tests for credential abstraction."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sandboxctl.credentials import (
    EnvVarBackend,
    MacOSKeychainBackend,
    _detect_backend,
)


class TestEnvVarBackend:
    """Tests for the environment variable fallback backend."""

    def test_get_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SANDBOXCTL_GITHUB_TOKEN", "ghp_test123")
        backend = EnvVarBackend()
        assert backend.get("sandboxctl-github-token", "user") == "ghp_test123"

    def test_get_missing(self) -> None:
        backend = EnvVarBackend()
        assert backend.get("nonexistent-service", "user") is None

    def test_store_raises(self) -> None:
        backend = EnvVarBackend()
        with pytest.raises(RuntimeError, match="Cannot persist"):
            backend.store("service", "user", "secret")

    def test_delete_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_SERVICE", "value")
        backend = EnvVarBackend()
        assert backend.delete("test-service", "user") is True

    def test_delete_missing(self) -> None:
        backend = EnvVarBackend()
        assert backend.delete("nonexistent-service", "user") is False

    def test_name(self) -> None:
        assert EnvVarBackend().name == "environment variables"

    def test_env_key_conversion(self) -> None:
        backend = EnvVarBackend()
        assert backend._env_key("sandboxctl-github-token", "user") == "SANDBOXCTL_GITHUB_TOKEN"


class TestBackendDetection:
    """Tests for auto-detection of credential backend."""

    def test_linux_with_secret_tool(self) -> None:
        with (
            patch("sandboxctl.credentials.sys") as mock_sys,
            patch("sandboxctl.credentials.shutil") as mock_shutil,
        ):
            mock_sys.platform = "linux"
            mock_shutil.which.return_value = "/usr/bin/secret-tool"
            backend = _detect_backend()
            assert backend.name == "secret-tool (libsecret)"

    def test_darwin_with_security(self) -> None:
        with (
            patch("sandboxctl.credentials.sys") as mock_sys,
            patch("sandboxctl.credentials.shutil") as mock_shutil,
        ):
            mock_sys.platform = "darwin"
            mock_shutil.which.return_value = "/usr/bin/security"
            backend = _detect_backend()
            assert backend.name == "macOS Keychain"

    def test_fallback_to_env(self) -> None:
        with (
            patch("sandboxctl.credentials.sys") as mock_sys,
            patch("sandboxctl.credentials.shutil") as mock_shutil,
        ):
            mock_sys.platform = "linux"
            mock_shutil.which.return_value = None
            backend = _detect_backend()
            assert backend.name == "environment variables"


class TestMacOSKeychainBackend:
    """Tests for macOS keychain backend (mocked subprocess)."""

    def test_get_not_found(self) -> None:
        backend = MacOSKeychainBackend()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert backend.get("service", "account") is None

    def test_delete_not_found(self) -> None:
        backend = MacOSKeychainBackend()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert backend.delete("service", "account") is False
