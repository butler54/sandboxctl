"""Tests for credential abstraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sandboxctl.credentials import (
    EnvVarBackend,
    LinuxSecretToolBackend,
    MacOSKeychainBackend,
    _detect_backend,
    delete_credential,
    get_credential,
    store_credential,
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

    def test_get_success(self) -> None:
        backend = MacOSKeychainBackend()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="my-secret\n")
            assert backend.get("service", "account") == "my-secret"

    def test_store_deletes_first(self) -> None:
        backend = MacOSKeychainBackend()
        with patch("subprocess.run"):
            backend.store("service", "account", "secret")


class TestLinuxSecretToolBackend:
    """Tests for Linux secret-tool backend (mocked subprocess)."""

    def test_get_success(self) -> None:
        backend = LinuxSecretToolBackend()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="my-secret\n")
            assert backend.get("service", "account") == "my-secret"

    def test_get_empty(self) -> None:
        backend = LinuxSecretToolBackend()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="")
            assert backend.get("service", "account") is None

    def test_get_not_found(self) -> None:
        backend = LinuxSecretToolBackend()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert backend.get("service", "account") is None

    def test_store(self) -> None:
        backend = LinuxSecretToolBackend()
        with patch("subprocess.run") as mock_run:
            backend.store("service", "account", "secret")
            mock_run.assert_called_once()
            assert mock_run.call_args[1]["input"] == "secret"

    def test_delete_success(self) -> None:
        backend = LinuxSecretToolBackend()
        with patch("subprocess.run"):
            assert backend.delete("service", "account") is True

    def test_delete_not_found(self) -> None:
        backend = LinuxSecretToolBackend()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert backend.delete("service", "account") is False

    def test_name(self) -> None:
        assert LinuxSecretToolBackend().name == "secret-tool (libsecret)"


class TestModuleLevelFunctions:
    """Tests for the convenience module-level functions."""

    def test_get_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SANDBOXCTL_GITHUB_TOKEN", "ghp_test")
        import sandboxctl.credentials

        sandboxctl.credentials._backend = None
        with (
            patch("sandboxctl.credentials.sys") as mock_sys,
            patch("sandboxctl.credentials.shutil") as mock_shutil,
        ):
            mock_sys.platform = "linux"
            mock_shutil.which.return_value = None
            result = get_credential("sandboxctl-github-token", "default")
            assert result == "ghp_test"
        sandboxctl.credentials._backend = None

    def test_store_credential_env_raises(self) -> None:
        import sandboxctl.credentials

        sandboxctl.credentials._backend = None
        with (
            patch("sandboxctl.credentials.sys") as mock_sys,
            patch("sandboxctl.credentials.shutil") as mock_shutil,
        ):
            mock_sys.platform = "linux"
            mock_shutil.which.return_value = None
            with pytest.raises(RuntimeError):
                store_credential("service", "account", "secret")
        sandboxctl.credentials._backend = None

    def test_delete_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_SVC", "val")
        import sandboxctl.credentials

        sandboxctl.credentials._backend = None
        with (
            patch("sandboxctl.credentials.sys") as mock_sys,
            patch("sandboxctl.credentials.shutil") as mock_shutil,
        ):
            mock_sys.platform = "linux"
            mock_shutil.which.return_value = None
            assert delete_credential("test-svc", "default") is True
        sandboxctl.credentials._backend = None
