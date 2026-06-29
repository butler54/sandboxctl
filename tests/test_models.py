"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sandboxctl.models import ClaudeSettings, ClaudeState, Profile, SandboxConfig, SshHostConfig


def test_profile_defaults() -> None:
    """Profile with only name uses sensible defaults."""
    p = Profile(name="test")
    assert p.sandbox.containerfile == "Containerfile"
    assert p.workspace.zoom == -1
    assert p.repos == {}
    assert p.ssh == {}


def test_profile_with_repos() -> None:
    """Profile with repos parses correctly."""
    p = Profile(
        name="dev",
        repos={"github": ["owner/repo1", "owner/repo2"], "gitlab.com": ["group/project"]},
    )
    assert len(p.repos["github"]) == 2
    assert "gitlab.com" in p.repos


def test_profile_extra_fields_ignored() -> None:
    """Unknown fields in profile sections are silently ignored."""
    sc = SandboxConfig(containerfile="Custom", unknown_field="value")  # type: ignore[call-arg]
    assert sc.containerfile == "Custom"


def test_claude_settings_defaults() -> None:
    """Claude settings have empty defaults (filled from config at runtime)."""
    cs = ClaudeSettings()
    assert cs.theme == ""
    assert cs.model == ""
    assert cs.permissions.defaultMode == "bypassPermissions"


def test_claude_state_defaults() -> None:
    """Claude state skips onboarding by default."""
    state = ClaudeState()
    assert state.hasCompletedOnboarding is True
    assert state.autoUpdates is False


def test_ssh_host_config() -> None:
    """SSH host config with proxy."""
    ssh = SshHostConfig(user="admin", proxy_host="gateway:3128")
    assert ssh.user == "admin"
    assert ssh.proxy_host == "gateway:3128"


class TestSandboxConfigImage:
    def test_image_field_default_empty(self) -> None:
        sc = SandboxConfig()
        assert sc.image == ""

    def test_image_and_default_containerfile_ok(self) -> None:
        sc = SandboxConfig(image="ghcr.io/org/sandbox:latest")
        assert sc.image == "ghcr.io/org/sandbox:latest"
        assert sc.containerfile == "Containerfile"

    def test_image_and_custom_containerfile_fails(self) -> None:
        with pytest.raises(ValidationError, match="mutually exclusive"):
            SandboxConfig(image="ghcr.io/org/sandbox:latest", containerfile="Custom.containerfile")
