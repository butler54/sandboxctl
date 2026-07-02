"""Tests for sandbox creation module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sandboxctl.create import (
    clone_repos,
    create_sandbox,
    generate_workspace,
    post_launch_setup,
    resolve_build_context,
    setup_providers,
    stage_claude_settings,
    stage_claude_state,
    stage_credentials,
    stage_skills,
)
from sandboxctl.models import Profile, SandboxConfig, WorkspaceConfig


class TestStageSkills:
    def test_copies_skills(self, tmp_path: Path) -> None:
        skills_src = tmp_path / "home" / ".claude" / "skills"
        skills_src.mkdir(parents=True)
        (skills_src / "my-skill").mkdir()
        (skills_src / "my-skill" / "SKILL.md").write_text("skill content")

        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
            count = stage_skills(stage_dir)

        assert count == 1
        assert (stage_dir / ".claude" / "skills" / "my-skill" / "SKILL.md").exists()

    def test_no_skills_dir(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
            count = stage_skills(stage_dir)

        assert count == 0


class TestStageClaudeSettings:
    def test_generates_settings_from_profile(self, tmp_path: Path) -> None:
        profile = Profile(
            name="test",
            sandbox=SandboxConfig(model="claude-opus-4-20250514"),
            workspace=WorkspaceConfig(theme="Cobalt2"),
        )
        config = MagicMock(default_model="claude-sonnet-4-20250514", default_theme="dark")

        stage_claude_settings(tmp_path, profile, config)

        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text())
        assert data["model"] == "claude-opus-4-20250514"
        assert data["theme"] == "Cobalt2"

    def test_falls_back_to_config_defaults(self, tmp_path: Path) -> None:
        profile = Profile(name="test")
        config = MagicMock(default_model="claude-sonnet-4-20250514", default_theme="dark")

        stage_claude_settings(tmp_path, profile, config)

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert data["model"] == "claude-sonnet-4-20250514"
        assert data["theme"] == "dark"


class TestStageClaudeState:
    def test_generates_state_file(self, tmp_path: Path) -> None:
        stage_claude_state(tmp_path)

        state_path = tmp_path / ".claude.json"
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert data["hasCompletedOnboarding"] is True
        assert data["autoUpdates"] is False


class TestStageCredentials:
    def test_stages_ssh_key(self, tmp_path: Path) -> None:
        ssh_key = tmp_path / "key"
        ssh_key.write_text("private")
        ssh_key_pub = tmp_path / "key.pub"
        ssh_key_pub.write_text("public")

        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        config = MagicMock(ssh_key=ssh_key)
        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"):
            staged = stage_credentials(stage_dir, config)

        assert "SSH key" in staged
        assert (stage_dir / ".ssh" / "id_ed25519").exists()
        assert (stage_dir / ".ssh" / "id_ed25519.pub").exists()

    def test_stages_ssh_config(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "config").write_text("Host *\n")

        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        config = MagicMock(ssh_key=MagicMock(exists=MagicMock(return_value=False)))
        with patch("sandboxctl.create.Path.home", return_value=home):
            staged = stage_credentials(stage_dir, config)

        assert "SSH config" in staged
        assert (stage_dir / ".ssh" / "config").exists()

    def test_nothing_to_stage(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        config = MagicMock(ssh_key=MagicMock(exists=MagicMock(return_value=False)))
        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"):
            staged = stage_credentials(stage_dir, config)

        assert staged == []


class TestResolveBuildContext:
    def test_image_returns_string(self) -> None:
        profile = Profile(name="test", sandbox=SandboxConfig(image="ghcr.io/org/sandbox:latest"))
        config = MagicMock()
        result, cleanup = resolve_build_context(profile, config)
        assert result == "ghcr.io/org/sandbox:latest"
        assert cleanup is None

    def test_containerfile_image_ref_detected(self) -> None:
        profile = Profile(name="test", sandbox=SandboxConfig(containerfile="ghcr.io/org/sandbox:latest"))
        config = MagicMock()
        result, cleanup = resolve_build_context(profile, config)
        assert result == "ghcr.io/org/sandbox:latest"
        assert cleanup is None

    def test_default_containerfile(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        (profiles_dir / "test").mkdir(parents=True)
        (profiles_dir / "test" / "Containerfile").write_text("FROM ubuntu")

        profile = Profile(name="test")
        config = MagicMock(profiles_dir=profiles_dir, config_dir=tmp_path)

        result, cleanup = resolve_build_context(profile, config)
        assert result == profiles_dir / "test"
        assert cleanup is None

    def test_missing_containerfile(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir(parents=True)

        profile = Profile(name="test")
        config = MagicMock(profiles_dir=profiles_dir, config_dir=tmp_path)

        with pytest.raises(FileNotFoundError, match="Containerfile not found"):
            resolve_build_context(profile, config)

    def test_custom_containerfile(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        (profiles_dir / "test").mkdir(parents=True)
        (profiles_dir / "test" / "Custom.containerfile").write_text("FROM fedora")
        (profiles_dir / "test" / "extra.sh").write_text("#!/bin/bash")

        profile = Profile(name="test", sandbox=SandboxConfig(containerfile="Custom.containerfile"))
        config = MagicMock(profiles_dir=profiles_dir, config_dir=tmp_path)

        result, cleanup = resolve_build_context(profile, config)
        assert isinstance(result, Path)
        assert cleanup is not None
        assert (result / "Dockerfile").is_symlink()


class TestGenerateProviderYaml:
    def test_vertex_provider(self, tmp_path: Path) -> None:
        config = MagicMock(
            vertex_project_id="my-project",
            config_dir=tmp_path,
        )
        with (
            patch("sandboxctl.create.osh.settings_set"),
            patch("sandboxctl.create.osh.provider_create") as mock_create,
        ):
            providers = setup_providers(config)
        assert "vertex-claude" in providers
        mock_create.assert_called_once_with("vertex-claude", "vertex-claude", "ANTHROPIC_VERTEX_PROJECT_ID=my-project")

    def test_anthropic_direct_provider(self, tmp_path: Path) -> None:
        config = MagicMock(vertex_project_id="", keychain_github="sandboxctl-github-token", config_dir=tmp_path)
        with (
            patch("sandboxctl.create.get_credential", return_value="sk-test"),
            patch("sandboxctl.create.osh.provider_create") as mock_create,
        ):
            providers = setup_providers(config)
        assert "anthropic-direct" in providers
        mock_create.assert_called_once_with("anthropic-direct", "anthropic", "ANTHROPIC_API_KEY=sk-test")


class TestPostLaunchSetup:
    def _make_config(self, tmp_path: Path, vertex: bool = False, gitlab: bool = False) -> MagicMock:
        config = MagicMock(
            vertex_project_id="my-project" if vertex else "",
            vertex_region="us-central1" if vertex else "global",
            providers=MagicMock(vertex_region="us-central1" if vertex else "global"),
            ca_bundle=None,
            ca_paths=[],
            keychain_gitlab="sandboxctl-gitlab-token",
        )
        return config

    def test_vertex_env_vars_injected(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, vertex=True)
        profile = Profile(name="test")

        with (
            patch("sandboxctl.create.osh.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
        ):
            post_launch_setup("mybox", profile, config)

        vertex_calls = [c for c in mock_pipe.call_args_list if "CLAUDE_CODE_USE_VERTEX" in str(c)]
        assert len(vertex_calls) == 1
        script = vertex_calls[0][0][1]
        assert "CLAUDE_CODE_USE_VERTEX=1" in script
        assert "CLOUD_ML_REGION=us-central1" in script

    def test_no_vertex_env_vars_when_not_configured(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, vertex=False)
        profile = Profile(name="test")

        with (
            patch("sandboxctl.create.osh.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
        ):
            post_launch_setup("mybox", profile, config)

        vertex_calls = [c for c in mock_pipe.call_args_list if "CLAUDE_CODE_USE_VERTEX" in str(c)]
        assert len(vertex_calls) == 0

    def test_gitlab_token_injected(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test")

        with (
            patch("sandboxctl.create.osh.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value="glpat-test-token"),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
        ):
            post_launch_setup("mybox", profile, config)

        token_calls = [c for c in mock_pipe.call_args_list if "GITLAB_TOKEN" in str(c)]
        assert len(token_calls) >= 2  # token injection + credential helper
        inject_call = [c for c in token_calls if "base64" in str(c)]
        assert len(inject_call) == 1


class TestCloneRepos:
    def test_no_repos(self) -> None:
        profile = Profile(name="test")
        result = clone_repos("mybox", profile)
        assert result == []

    def test_github_repos(self) -> None:
        profile = Profile(name="test", repos={"github": ["owner/repo1"]})
        with (
            patch("sandboxctl.create.osh.sandbox_exec_pipe"),
            patch("sandboxctl.create.osh.sandbox_exec") as mock_exec,
        ):
            result = clone_repos("mybox", profile)

        assert result == ["repo1"]
        mock_exec.assert_called_once_with(
            "mybox",
            ["gh", "repo", "clone", "owner/repo1", "/sandbox/workspace/repo1"],
        )

    def test_non_github_repos(self) -> None:
        profile = Profile(name="test", repos={"gitlab.com": ["group/project"]})
        with patch("sandboxctl.create.osh.sandbox_exec_pipe") as mock_pipe:
            result = clone_repos("mybox", profile)

        assert result == ["project"]
        calls = [c for c in mock_pipe.call_args_list if "git clone" in str(c)]
        assert len(calls) == 1


class TestGenerateWorkspace:
    def test_generates_workspace(self) -> None:
        profile = Profile(
            name="test",
            workspace=WorkspaceConfig(theme="Cobalt2", zoom=2),
        )
        with patch("sandboxctl.create.osh.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, ["repo1", "repo2"])

        call_script = mock_pipe.call_args[0][1]
        assert "code-workspace" in call_script

    def test_empty_repos_noop(self) -> None:
        profile = Profile(name="test")
        with patch("sandboxctl.create.osh.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, [])

        mock_pipe.assert_not_called()


class TestCreateSandbox:
    def test_happy_path(self, tmp_path: Path) -> None:
        profile = Profile(name="test", sandbox=SandboxConfig(image="ghcr.io/org/img:v1"))
        policy_dir = tmp_path / "profiles" / "test"
        policy_dir.mkdir(parents=True)
        (policy_dir / "policy.yaml").write_text("network: {}")

        config = MagicMock(
            default_model="claude-sonnet-4-20250514",
            default_theme="dark",
            ssh_key=MagicMock(exists=MagicMock(return_value=False)),
            vertex_project_id="proj",
            providers=MagicMock(vertex_region="us-central1"),
            profiles_dir=tmp_path / "profiles",
            config_dir=tmp_path,
        )

        with (
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.create.setup_providers", return_value=["github", "vertex-claude"]),
            patch("sandboxctl.create.osh.sandbox_create"),
            patch("sandboxctl.create.osh.policy_set") as mock_policy_set,
            patch("sandboxctl.create.post_launch_setup"),
            patch("sandboxctl.create.clone_repos", return_value=[]),
            patch("sandboxctl.create.generate_workspace"),
        ):
            name = create_sandbox(profile, config, open_editor=False)

        assert name == "test"
        mock_policy_set.assert_called_once_with("test", policy_dir / "policy.yaml")

    def test_ephemeral_passes_no_keep(self, tmp_path: Path) -> None:
        profile = Profile(name="test", sandbox=SandboxConfig(image="img:v1"))
        config = MagicMock(
            default_model="m",
            default_theme="d",
            ssh_key=MagicMock(exists=MagicMock(return_value=False)),
            vertex_project_id="",
            keychain_github="svc",
            profiles_dir=tmp_path / "profiles",
            config_dir=tmp_path,
        )

        with (
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.create.setup_providers", return_value=["github", "anthropic-direct"]),
            patch("sandboxctl.create.osh.sandbox_create") as mock_create,
            patch("sandboxctl.create.osh.policy_set"),
            patch("sandboxctl.create.post_launch_setup"),
            patch("sandboxctl.create.clone_repos", return_value=[]),
            patch("sandboxctl.create.generate_workspace"),
        ):
            create_sandbox(profile, config, ephemeral=True, open_editor=False)

        assert mock_create.call_args[1]["no_keep"] is True
