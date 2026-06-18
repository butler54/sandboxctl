"""Cross-platform credential storage abstraction."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod


class CredentialBackend(ABC):
    """Abstract credential storage backend."""

    @abstractmethod
    def get(self, service: str, account: str) -> str | None:
        """Retrieve a credential. Returns None if not found."""

    @abstractmethod
    def store(self, service: str, account: str, secret: str) -> None:
        """Store a credential."""

    @abstractmethod
    def delete(self, service: str, account: str) -> bool:
        """Delete a credential. Returns True if deleted, False if not found."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name."""


class MacOSKeychainBackend(CredentialBackend):
    """macOS Keychain via the security CLI."""

    @property
    def name(self) -> str:
        return "macOS Keychain"

    def get(self, service: str, account: str) -> str | None:
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def store(self, service: str, account: str, secret: str) -> None:
        self.delete(service, account)
        subprocess.run(
            ["security", "add-generic-password", "-s", service, "-a", account, "-w", secret],
            check=True,
            capture_output=True,
        )

    def delete(self, service: str, account: str) -> bool:
        try:
            subprocess.run(
                ["security", "delete-generic-password", "-s", service, "-a", account],
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


class LinuxSecretToolBackend(CredentialBackend):
    """Linux secret-tool (libsecret) backend."""

    @property
    def name(self) -> str:
        return "secret-tool (libsecret)"

    def get(self, service: str, account: str) -> str | None:
        try:
            result = subprocess.run(
                ["secret-tool", "lookup", "service", service, "account", account],
                capture_output=True,
                text=True,
                check=True,
            )
            val = result.stdout.strip()
            return val if val else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def store(self, service: str, account: str, secret: str) -> None:
        subprocess.run(
            [
                "secret-tool",
                "store",
                "--label",
                f"{service}/{account}",
                "service",
                service,
                "account",
                account,
            ],
            input=secret,
            text=True,
            check=True,
            capture_output=True,
        )

    def delete(self, service: str, account: str) -> bool:
        try:
            subprocess.run(
                ["secret-tool", "clear", "service", service, "account", account],
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


class EnvVarBackend(CredentialBackend):
    """Environment variable fallback backend."""

    @property
    def name(self) -> str:
        return "environment variables"

    def _env_key(self, service: str, _account: str) -> str:
        return service.upper().replace("-", "_")

    def get(self, service: str, account: str) -> str | None:
        return os.environ.get(self._env_key(service, account))

    def store(self, service: str, account: str, secret: str) -> None:
        msg = f"Cannot persist credentials via env vars. Set {self._env_key(service, account)} in your shell profile."
        raise RuntimeError(msg)

    def delete(self, service: str, account: str) -> bool:
        key = self._env_key(service, account)
        if key in os.environ:
            del os.environ[key]
            return True
        return False


def _detect_backend() -> CredentialBackend:
    """Auto-detect the best available credential backend."""
    if sys.platform == "darwin" and shutil.which("security"):
        return MacOSKeychainBackend()
    if sys.platform == "linux" and shutil.which("secret-tool"):
        return LinuxSecretToolBackend()
    return EnvVarBackend()


_backend: CredentialBackend | None = None


def get_backend() -> CredentialBackend:
    """Get the credential backend (cached)."""
    global _backend  # noqa: PLW0603
    if _backend is None:
        _backend = _detect_backend()
    return _backend


def get_credential(service: str, account: str) -> str | None:
    """Retrieve a credential using the detected backend."""
    return get_backend().get(service, account)


def store_credential(service: str, account: str, secret: str) -> None:
    """Store a credential using the detected backend."""
    get_backend().store(service, account, secret)


def delete_credential(service: str, account: str) -> bool:
    """Delete a credential using the detected backend."""
    return get_backend().delete(service, account)
