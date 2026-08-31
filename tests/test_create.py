"""Tests for sandbox creation module."""

from __future__ import annotations

import base64
import json
import subprocess
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
    stage_agents,
    stage_claude_settings,
    stage_claude_state,
    stage_credentials,
    stage_opencode_agents,
    stage_opencode_config,
    stage_opencode_plugins,
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

    def test_allowlist_stages_only_selected(self, tmp_path: Path) -> None:
        """A non-empty allowlist stages only the named skills (#118)."""
        skills_src = tmp_path / "home" / ".claude" / "skills"
        skills_src.mkdir(parents=True)
        for skill in ("wanted", "unwanted", "also-unwanted"):
            (skills_src / skill).mkdir()
            (skills_src / skill / "SKILL.md").write_text("x")

        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
            count = stage_skills(stage_dir, ["wanted"])

        assert count == 1
        assert (stage_dir / ".claude" / "skills" / "wanted" / "SKILL.md").exists()
        assert not (stage_dir / ".claude" / "skills" / "unwanted").exists()

    def test_empty_allowlist_stages_all(self, tmp_path: Path) -> None:
        """An empty allowlist preserves the stage-all default (#118)."""
        skills_src = tmp_path / "home" / ".claude" / "skills"
        skills_src.mkdir(parents=True)
        for skill in ("a", "b"):
            (skills_src / skill).mkdir()
            (skills_src / skill / "SKILL.md").write_text("x")

        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
            count = stage_skills(stage_dir, [])

        assert count == 2


class TestStageAgents:
    def test_copies_agents(self, tmp_path: Path) -> None:
        agents_src = tmp_path / "home" / ".claude" / "agents"
        agents_src.mkdir(parents=True)
        (agents_src / "my-agent.md").write_text("agent definition")

        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
            count = stage_agents(stage_dir)

        assert count == 1
        assert (stage_dir / ".claude" / "agents" / "my-agent.md").exists()

    def test_no_agents_dir(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
            count = stage_agents(stage_dir)

        assert count == 0

    def test_allowlist_stages_only_selected(self, tmp_path: Path) -> None:
        """A non-empty allowlist stages only the named agents (#119)."""
        agents_src = tmp_path / "home" / ".claude" / "agents"
        agents_src.mkdir(parents=True)
        for agent in ("keep.md", "drop.md"):
            (agents_src / agent).write_text("agent")

        stage_dir = tmp_path / "stage"
        stage_dir.mkdir()

        with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
            count = stage_agents(stage_dir, ["keep.md"])

        assert count == 1
        assert (stage_dir / ".claude" / "agents" / "keep.md").exists()
        assert not (stage_dir / ".claude" / "agents" / "drop.md").exists()


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
            patch("sandboxctl.create.osh.provider_profile_import") as mock_import,
        ):
            providers = setup_providers(config)
        assert "vertex-claude" in providers
        mock_create.assert_called_once_with("vertex-claude", "google-vertex-ai", from_gcloud_adc=True)

        # Verify provider profile YAML is generated and imported with tls:skip
        mock_import.assert_called_once()
        yaml_path = mock_import.call_args[0][0]
        assert yaml_path.exists()
        yaml_content = yaml_path.read_text()
        assert "tls: skip" in yaml_content
        assert "oauth2.googleapis" in yaml_content and ".com" in yaml_content
        assert "accounts.google" in yaml_content and ".com" in yaml_content
        # #120: provider profile import requires both id and display_name
        assert "id: vertex-claude" in yaml_content
        assert "display_name:" in yaml_content

    def test_vertex_provider_yaml_regenerated_when_missing_display_name(self, tmp_path: Path) -> None:
        """A stale YAML with id but no display_name is regenerated (#120)."""
        from sandboxctl.create import _ensure_vertex_provider_yaml

        providers_dir = tmp_path / "providers"
        providers_dir.mkdir(parents=True)
        stale = providers_dir / "vertex-claude.yaml"
        stale.write_text("id: vertex-claude\nendpoints: []\n")  # old format, no display_name

        _ensure_vertex_provider_yaml(tmp_path)

        assert "display_name:" in stale.read_text()

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
            opencode=MagicMock(openai_accounts=[]),
        )
        return config

    def test_vertex_env_vars_injected(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, vertex=True)
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        vertex_calls = [c for c in mock_pipe.call_args_list if "CLAUDE_CODE_USE_VERTEX" in str(c)]
        assert len(vertex_calls) == 1
        script = vertex_calls[0][0][1]
        assert "CLAUDE_CODE_USE_VERTEX=1" in script
        assert "CLOUD_ML_REGION=us-central1" in script
        assert "ANTHROPIC_VERTEX_PROJECT_ID=my-project" in script

    def test_no_vertex_env_vars_when_not_configured(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, vertex=False)
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        vertex_calls = [c for c in mock_pipe.call_args_list if "CLAUDE_CODE_USE_VERTEX" in str(c)]
        assert len(vertex_calls) == 0

    def test_opencode_yolo_permission_injected(self, tmp_path: Path) -> None:
        """OPENCODE_PERMISSION is always injected for autonomous opencode (#128)."""
        config = self._make_config(tmp_path)
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        perm_calls = [c for c in mock_pipe.call_args_list if "OPENCODE_PERMISSION" in str(c)]
        assert len(perm_calls) == 1
        script = perm_calls[0][0][1]
        assert '\\"*\\":\\"allow\\"' in script

    def test_openai_keys_injected_from_keychain(self, tmp_path: Path) -> None:
        """Named OpenAI accounts are injected as OPENAI_API_KEY_<NAME>; first sets OPENAI_API_KEY (#129)."""
        config = self._make_config(tmp_path)
        config.opencode = MagicMock(openai_accounts=["work", "personal"])
        profile = Profile(name="test", mlflow=False)

        def fake_get_credential(service: str, account: str) -> str | None:
            if service == "sandboxctl-openai-work":
                return "sk-work"
            if service == "sandboxctl-openai-personal":
                return "sk-personal"
            return None

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", side_effect=fake_get_credential),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        scripts = [c[0][1] for c in mock_pipe.call_args_list]
        assert any("OPENAI_API_KEY_WORK=" in s for s in scripts)
        assert any("OPENAI_API_KEY_PERSONAL=" in s for s in scripts)
        # First account (work) also sets the default OPENAI_API_KEY
        assert any("OPENAI_API_KEY=" in s and "base64" in s for s in scripts)
        # Keys never appear in plaintext in the scripts (base64-encoded)
        assert not any("sk-work" in s or "sk-personal" in s for s in scripts)

    def test_openai_accounts_generate_selectable_providers(self, tmp_path: Path) -> None:
        """Named accounts become opencode providers via OPENCODE_CONFIG_CONTENT (#129)."""
        import base64 as _b64
        import json as _json

        config = self._make_config(tmp_path)
        config.opencode = MagicMock(openai_accounts=["work", "personal"])
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value="sk-x"),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        cfg_calls = [c for c in mock_pipe.call_args_list if "OPENCODE_CONFIG_CONTENT" in str(c)]
        assert len(cfg_calls) == 1
        # Decode the base64 JSON payload embedded in the injection script.
        script = cfg_calls[0][0][1]
        b64 = next(tok for tok in script.split() if tok.startswith("eyJ"))  # base64 of {"...
        patch_obj = _json.loads(_b64.b64decode(b64).decode())
        providers = patch_obj["provider"]
        assert "openai-work" in providers and "openai-personal" in providers
        assert providers["openai-work"]["options"]["apiKey"] == "{env:OPENAI_API_KEY_WORK}"
        assert providers["openai-work"]["npm"] == "@ai-sdk/openai"
        assert "gpt-5.6-sol" in providers["openai-work"]["models"]
        assert "gpt-5.6-luna" in providers["openai-work"]["models"]

    def test_openai_account_without_keychain_entry_skipped(self, tmp_path: Path) -> None:
        """An account with no keychain entry is skipped, not injected (#129)."""
        config = self._make_config(tmp_path)
        config.opencode = MagicMock(openai_accounts=["ghost"])
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        scripts = [c[0][1] for c in mock_pipe.call_args_list]
        assert not any("OPENAI_API_KEY_GHOST" in s for s in scripts)

    def test_gitlab_token_injected_without_shell_expansion(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test", repos={"gitlab.com": ["group/project"]}, mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value="glpat-test-token"),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        token_calls = [c for c in mock_pipe.call_args_list if "GITLAB_TOKEN" in str(c)]
        assert len(token_calls) >= 2  # token injection + credential helper
        inject_call = [c for c in token_calls if "base64" in str(c)]
        assert len(inject_call) == 1
        script = inject_call[0][0][1]
        assert "$(" not in script  # no command substitution

    def test_gitlab_credential_helper_per_server(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test", repos={"gitlab.example.com": ["team/project"]}, mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value="glpat-test"),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        helper_calls = [c for c in mock_pipe.call_args_list if "credential.https://" in str(c)]
        assert len(helper_calls) == 1
        script = helper_calls[0][0][1]
        assert "credential.https://gitlab.example.com.helper" in script
        global_calls = [
            c for c in mock_pipe.call_args_list if "credential.helper " in str(c) and "https://" not in str(c)
        ]
        assert len(global_calls) == 0

    def test_gitlab_servers_from_credentials_config(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        from sandboxctl.models import CredentialConfig

        profile = Profile(
            name="test",
            credentials=CredentialConfig(gitlab_servers=["gitlab.com", "gitlab.internal.co"]),
            mlflow=False,
        )

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value="glpat-test"),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        helper_calls = [c for c in mock_pipe.call_args_list if "credential.https://" in str(c)]
        assert len(helper_calls) == 2
        scripts = [c[0][1] for c in helper_calls]
        assert any("credential.https://gitlab.com.helper" in s for s in scripts)
        assert any("credential.https://gitlab.internal.co.helper" in s for s in scripts)

    def test_gitlab_credential_uses_user_account(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe"),
            patch("sandboxctl.create.get_credential") as mock_get_cred,
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch.dict("os.environ", {"USER": "testuser"}),
        ):
            mock_get_cred.return_value = None
            post_launch_setup("mybox", profile, config)

        gitlab_calls = [c for c in mock_get_cred.call_args_list if c[0][0] == "sandboxctl-gitlab-token"]
        assert len(gitlab_calls) == 1
        assert gitlab_calls[0][0][1] == "testuser"

    def test_ca_env_vars_include_gh_ssl_cainfo(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        ca_calls = [c for c in mock_pipe.call_args_list if "GIT_SSL_CAINFO" in str(c)]
        assert len(ca_calls) == 1
        script = ca_calls[0][0][1]
        assert "GH_SSL_CAINFO=/sandbox/.ca-bundle.pem" in script

    def test_gws_credentials_exported_when_gws_installed(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test", mlflow=False)
        gws_dir = tmp_path / "nohome" / ".config" / "gws"
        gws_dir.mkdir(parents=True)
        (gws_dir / "client_secret.json").write_text('{"installed":{}}')

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe"),
            patch("sandboxctl.openshell.sandbox_upload") as mock_upload,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.create.shutil.which", return_value="/usr/bin/gws"),
            patch("sandboxctl.create.subprocess.run") as mock_run,
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            mock_run.return_value = MagicMock(stdout='{"refresh_token": "tok"}', returncode=0)
            post_launch_setup("mybox", profile, config)

        upload_calls = [c for c in mock_upload.call_args_list if "gws" in str(c)]
        assert len(upload_calls) == 2  # client_secret + credentials

    def test_gws_skipped_when_not_installed(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test", mlflow=False)
        gws_dir = tmp_path / "nohome" / ".config" / "gws"
        gws_dir.mkdir(parents=True)
        (gws_dir / "client_secret.json").write_text('{"installed":{}}')

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe"),
            patch("sandboxctl.openshell.sandbox_upload") as mock_upload,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        upload_calls = [c for c in mock_upload.call_args_list if "gws" in str(c)]
        assert len(upload_calls) == 0

    def test_gws_graceful_on_export_failure(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        profile = Profile(name="test", mlflow=False)
        gws_dir = tmp_path / "nohome" / ".config" / "gws"
        gws_dir.mkdir(parents=True)
        (gws_dir / "client_secret.json").write_text('{"installed":{}}')

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe"),
            patch("sandboxctl.openshell.sandbox_upload") as mock_upload,
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.create.shutil.which", return_value="/usr/bin/gws"),
            patch(
                "sandboxctl.create.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "gws"),
            ),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        upload_calls = [c for c in mock_upload.call_args_list if "gws" in str(c)]
        assert len(upload_calls) == 1  # client_secret only


class TestCloneRepos:
    def test_no_repos(self) -> None:
        profile = Profile(name="test")
        result = clone_repos("mybox", profile)
        assert result == []

    def test_github_repos(self) -> None:
        profile = Profile(name="test", repos={"github": ["owner/repo1"]})
        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe"),
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
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
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
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, ["repo1", "repo2"])

        call_script = mock_pipe.call_args[0][1]
        assert "code-workspace" in call_script

    def test_empty_repos_noop(self) -> None:
        profile = Profile(name="test")
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, [])

        mock_pipe.assert_not_called()

    def test_workspace_includes_remote_ssh_settings(self) -> None:
        profile = Profile(name="test")
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, ["repo1", "repo2"])

        # Extract the base64 payload from the script
        call_script = mock_pipe.call_args[0][1]
        # Script format: echo <base64> | base64 -d > <path>
        base64_token = call_script.split("|")[0].strip().replace("echo ", "")
        decoded = base64.b64decode(base64_token).decode()
        workspace_json = json.loads(decoded)

        # Assert Remote-SSH settings exist
        assert "settings" in workspace_json
        settings = workspace_json["settings"]
        assert settings["remote.SSH.connectTimeout"] == 120
        assert settings["remote.SSH.useLocalServer"] is False

    def test_workspace_includes_extension_recommendations(self) -> None:
        profile = Profile(name="test")
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, ["repo1", "repo2"])

        # Extract and decode the base64 payload
        call_script = mock_pipe.call_args[0][1]
        base64_token = call_script.split("|")[0].strip().replace("echo ", "")
        decoded = base64.b64decode(base64_token).decode()
        workspace_json = json.loads(decoded)

        # Assert extensions object exists with empty recommendations
        assert "extensions" in workspace_json
        assert workspace_json["extensions"] == {"recommendations": []}

    def test_workspace_recommendations_populated_from_profile(self) -> None:
        """Workspace recommendations include full declared list from profile.extensions.list (Task 2 - Phase 20)."""
        from sandboxctl.models import Extensions

        profile = Profile(
            name="test",
            extensions=Extensions(extensions_list=["ms-python.python", "dracula-theme.theme-dracula"]),
        )
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, ["repo1"])

        # Extract and decode the base64 payload
        call_script = mock_pipe.call_args[0][1]
        base64_token = call_script.split("|")[0].strip().replace("echo ", "")
        decoded = base64.b64decode(base64_token).decode()
        workspace_json = json.loads(decoded)

        # Assert recommendations == full declared list (remote + local per D-06)
        assert workspace_json["extensions"]["recommendations"] == ["ms-python.python", "dracula-theme.theme-dracula"]

    def test_workspace_recommendations_empty_when_no_extensions(self) -> None:
        """Workspace recommendations are empty list when profile.extensions.list is empty."""
        from sandboxctl.models import Extensions

        profile = Profile(name="test", extensions=Extensions(extensions_list=[]))
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, ["repo1"])

        # Extract and decode the base64 payload
        call_script = mock_pipe.call_args[0][1]
        base64_token = call_script.split("|")[0].strip().replace("echo ", "")
        decoded = base64.b64decode(base64_token).decode()
        workspace_json = json.loads(decoded)

        # Assert empty recommendations
        assert workspace_json["extensions"]["recommendations"] == []

    def test_workspace_recommendations_include_local_only(self) -> None:
        """Workspace recommendations include local_only extensions (no denylist filtering per D-06)."""
        from sandboxctl.models import Extensions

        profile = Profile(
            name="test",
            extensions=Extensions(
                extensions_list=["ms-python.python", "dracula-theme.theme-dracula"],
                local_only=["dracula-theme.theme-dracula"],
            ),
        )
        with patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe:
            generate_workspace("mybox", "mybox", profile, ["repo1"])

        # Extract and decode
        call_script = mock_pipe.call_args[0][1]
        base64_token = call_script.split("|")[0].strip().replace("echo ", "")
        decoded = base64.b64decode(base64_token).decode()
        workspace_json = json.loads(decoded)

        # Assert BOTH extensions in recommendations (local_only NOT excluded)
        assert workspace_json["extensions"]["recommendations"] == ["ms-python.python", "dracula-theme.theme-dracula"]


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
            vertex_region="us-central1",
            profiles_dir=tmp_path / "profiles",
            config_dir=tmp_path,
        )

        with (
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.create.setup_providers", return_value=["github", "vertex-claude"]),
            patch("sandboxctl.create.osh.sandbox_create"),
            patch("sandboxctl.create.osh.update_local_ssh_config") as mock_ssh,
            patch("sandboxctl.create.osh.policy_set") as mock_policy_set,
            patch("sandboxctl.create.post_launch_setup"),
            patch("sandboxctl.create.clone_repos", return_value=[]),
            patch("sandboxctl.create.generate_workspace"),
        ):
            name = create_sandbox(profile, config, open_editor=False)

        assert name == "test"
        mock_ssh.assert_called_once_with("test")
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
            patch("sandboxctl.create.osh.update_local_ssh_config"),
            patch("sandboxctl.create.osh.policy_set"),
            patch("sandboxctl.create.post_launch_setup"),
            patch("sandboxctl.create.clone_repos", return_value=[]),
            patch("sandboxctl.create.generate_workspace"),
        ):
            create_sandbox(profile, config, ephemeral=True, open_editor=False)

        assert mock_create.call_args[1]["no_keep"] is True


def test_create_injects_mlflow_uri() -> None:
    """Create validates MLflow is up and injects MLFLOW_TRACKING_URI into sandbox."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import MlflowConfig, SandboxctlConfig
    from sandboxctl.create import post_launch_setup
    from sandboxctl.models import Profile

    # Scenario 1: managed mode, healthy server → injection proceeds
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        mlflow_cfg = MlflowConfig(managed=True, port=5050, tracking_uri="http://localhost:5050")
        config = SandboxctlConfig(config_dir=config_dir, mlflow=mlflow_cfg)
        profile = Profile(name="test", mlflow=True)

        def _exec_plugin_ok_s1(name: str, script: str) -> str:
            return "MLflow tracing: plugin installed" if "claude plugin marketplace add" in script else ""

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=True) as mock_health,
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.openshell.sandbox_exec_pipe", side_effect=_exec_plugin_ok_s1) as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            # Mock Path.home to return a non-existent path
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            post_launch_setup("test-sandbox", profile, config)

            # Health check was called
            mock_health.assert_called_once_with("http://localhost:5050")

            # Injection script contains grep-q check and the gateway IP
            injection_calls = [c for c in mock_exec.call_args_list if "MLFLOW_TRACKING_URI" in str(c)]
            assert len(injection_calls) == 1
            script = injection_calls[0][0][1]
            assert "grep -q MLFLOW_TRACKING_URI /sandbox/.bashrc" in script
            assert "export MLFLOW_TRACKING_URI=http://10.200.0.1:5050" in script

    # Scenario 2: managed mode, down-then-recovered → start called, injection proceeds
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        mlflow_cfg = MlflowConfig(managed=True, port=5050, tracking_uri="http://localhost:5050", data_dir=Path(tmpdir))
        config = SandboxctlConfig(config_dir=config_dir, mlflow=mlflow_cfg)
        profile = Profile(name="test", mlflow=True)

        def _exec_plugin_ok_s2(name: str, script: str) -> str:
            return "MLflow tracing: plugin installed" if "claude plugin marketplace add" in script else ""

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=False) as mock_health,
            patch("sandboxctl.create.mlflow_cmd.wait_for_mlflow_health", return_value=True) as mock_wait,
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.openshell.sandbox_exec_pipe", side_effect=_exec_plugin_ok_s2) as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            post_launch_setup("test-sandbox", profile, config)

            # Initial check down → start → retry loop reports healthy
            assert mock_health.call_count == 1
            mock_wait.assert_called_once()
            mock_start.assert_called_once_with(Path(tmpdir), 5050)

            # Injection still happened
            injection_calls = [c for c in mock_exec.call_args_list if "MLFLOW_TRACKING_URI" in str(c)]
            assert len(injection_calls) == 1

    # Scenario 3: managed mode, stays down → create fails (fail-closed)
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        mlflow_cfg = MlflowConfig(managed=True, port=5050, tracking_uri="http://localhost:5050", data_dir=Path(tmpdir))
        config = SandboxctlConfig(config_dir=config_dir, mlflow=mlflow_cfg)
        profile = Profile(name="test", mlflow=True)

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=False),
            patch("sandboxctl.create.mlflow_cmd.wait_for_mlflow_health", return_value=False),
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container"),
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            with pytest.raises(RuntimeError, match="MLflow tracking server is not responding"):
                post_launch_setup("test-sandbox", profile, config)

            # No injection happened
            injection_calls = [c for c in mock_exec.call_args_list if "MLFLOW_TRACKING_URI" in str(c)]
            assert len(injection_calls) == 0

    # Scenario 4: opt-out (profile.mlflow=False) → no health check, no injection
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        mlflow_cfg = MlflowConfig(managed=True, port=5050)
        config = SandboxctlConfig(config_dir=config_dir, mlflow=mlflow_cfg)
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health") as mock_health,
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            post_launch_setup("test-sandbox", profile, config)

            # No health check or start
            mock_health.assert_not_called()
            mock_start.assert_not_called()

            # No injection
            injection_calls = [c for c in mock_exec.call_args_list if "MLFLOW_TRACKING_URI" in str(c)]
            assert len(injection_calls) == 0

    # Scenario 5: external mode (managed=False) → health check only, no start, user URI injected
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        external_uri = "https://mlflow.example.com"
        mlflow_cfg = MlflowConfig(managed=False, tracking_uri=external_uri)
        config = SandboxctlConfig(config_dir=config_dir, mlflow=mlflow_cfg)
        profile = Profile(name="test", mlflow=True)

        def _exec_plugin_ok_s5(name: str, script: str) -> str:
            return "MLflow tracing: plugin installed" if "claude plugin marketplace add" in script else ""

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=True) as mock_health,
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.openshell.sandbox_exec_pipe", side_effect=_exec_plugin_ok_s5) as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            post_launch_setup("test-sandbox", profile, config)

            # Health check on user URI
            mock_health.assert_called_once_with(external_uri)
            # No start call
            mock_start.assert_not_called()

            # Injection with user URI
            injection_calls = [c for c in mock_exec.call_args_list if "MLFLOW_TRACKING_URI" in str(c)]
            assert len(injection_calls) == 1
            script = injection_calls[0][0][1]
            assert f"export MLFLOW_TRACKING_URI={external_uri}" in script

    # Scenario 6: external mode, down → create fails
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        external_uri = "https://mlflow.example.com"
        mlflow_cfg = MlflowConfig(managed=False, tracking_uri=external_uri)
        config = SandboxctlConfig(config_dir=config_dir, mlflow=mlflow_cfg)
        profile = Profile(name="test", mlflow=True)

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=False),
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            with pytest.raises(RuntimeError, match="External MLflow server .* is not reachable"):
                post_launch_setup("test-sandbox", profile, config)

            # No start
            mock_start.assert_not_called()
            # No injection
            injection_calls = [c for c in mock_exec.call_args_list if "MLFLOW_TRACKING_URI" in str(c)]
            assert len(injection_calls) == 0


def test_git_identity_injected_from_config() -> None:
    """Git identity is set inside the sandbox when [identity] is configured (#80)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import IdentityConfig, SandboxctlConfig
    from sandboxctl.models import Profile

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SandboxctlConfig(
            config_dir=Path(tmpdir),
            identity=IdentityConfig(user_name="Alice Dev", user_email="alice@example.com"),
        )
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=Path(tmpdir) / "nohome"),
        ):
            from sandboxctl.create import post_launch_setup

            post_launch_setup("mybox", profile, config)

        identity_calls = [c for c in mock_exec.call_args_list if "user.name" in str(c)]
        assert len(identity_calls) == 1
        script = identity_calls[0][0][1]
        assert "Alice Dev" in script
        assert "alice@example.com" in script
        assert "gpg.format ssh" in script
        assert "commit.gpgsign true" in script


def test_git_identity_skipped_when_not_configured() -> None:
    """Git identity block is skipped when [identity] is empty (#80)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import SandboxctlConfig
    from sandboxctl.models import Profile

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SandboxctlConfig(config_dir=Path(tmpdir))  # no identity
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=Path(tmpdir) / "nohome"),
        ):
            from sandboxctl.create import post_launch_setup

            post_launch_setup("mybox", profile, config)

        identity_calls = [c for c in mock_exec.call_args_list if "user.name" in str(c)]
        assert len(identity_calls) == 0


def test_gsd_model_profile_written_when_set() -> None:
    """GSD defaults.json is written with model_profile when [gsd] sets one (#81)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import SandboxctlConfig
    from sandboxctl.models import GsdConfig, Profile

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SandboxctlConfig(config_dir=Path(tmpdir))
        profile = Profile(name="test", mlflow=False, gsd=GsdConfig(enabled=True, model_profile="quality"))

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=Path(tmpdir) / "nohome"),
        ):
            from sandboxctl.create import post_launch_setup

            post_launch_setup("mybox", profile, config)

        gsd_calls = [c for c in mock_exec.call_args_list if "defaults.json" in str(c)]
        assert len(gsd_calls) == 1
        script = gsd_calls[0][0][1]
        assert "quality" in script
        assert "model_profile" in script
        assert "/sandbox/.gsd/defaults.json" in script


def test_gsd_model_profile_skipped_when_not_set() -> None:
    """No defaults.json write when gsd.model_profile is empty (#81)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import SandboxctlConfig
    from sandboxctl.models import Profile

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SandboxctlConfig(config_dir=Path(tmpdir))
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=Path(tmpdir) / "nohome"),
        ):
            from sandboxctl.create import post_launch_setup

            post_launch_setup("mybox", profile, config)

        gsd_calls = [c for c in mock_exec.call_args_list if "defaults.json" in str(c)]
        assert len(gsd_calls) == 0


def test_create_installs_mlflow_tracing_plugin() -> None:
    """Plugin install and env var injection for Claude Code tracing (TRACE-01/02/03)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import MlflowConfig, SandboxctlConfig
    from sandboxctl.create import post_launch_setup
    from sandboxctl.models import Profile

    # Scenario 1: Happy path — mlflow=True, plugin install succeeds
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=True, port=5050, tracking_uri="http://localhost:5050")
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)
        profile = Profile(name="test-sandbox", mlflow=True)

        def exec_side_effect_happy(name: str, script: str) -> str:
            if "claude plugin marketplace add" in script:
                return "MLflow tracing: plugin installed"
            return ""

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=True),
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container"),
            patch("sandboxctl.openshell.sandbox_exec_pipe", side_effect=exec_side_effect_happy) as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            # Should not raise
            post_launch_setup("test-sandbox", profile, config)

            all_scripts = [c[0][1] for c in mock_exec.call_args_list]
            assert any("MLFLOW_EXPERIMENT_NAME=sandbox/test-sandbox" in s for s in all_scripts)
            assert any("MLFLOW_CLAUDE_TRACING_ENABLED=true" in s for s in all_scripts)
            assert any("claude plugin marketplace add" in s for s in all_scripts)

    # Scenario 2: Fail-closed — plugin install returns empty string → RuntimeError raised
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=True, port=5050, tracking_uri="http://localhost:5050")
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)
        profile = Profile(name="test-sandbox", mlflow=True)

        def exec_side_effect_fail(name: str, script: str) -> str:
            return ""

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=True),
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container"),
            patch("sandboxctl.openshell.sandbox_exec_pipe", side_effect=exec_side_effect_fail),
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            with pytest.raises(RuntimeError, match="plugin install failed"):
                post_launch_setup("test-sandbox", profile, config)

    # Scenario 3: Opt-out — profile.mlflow=False → no tracing env vars or plugin calls
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=True, port=5050)
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)
        profile = Profile(name="test-sandbox", mlflow=False)

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health"),
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container"),
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            post_launch_setup("test-sandbox", profile, config)

            all_scripts = [c[0][1] for c in mock_exec.call_args_list]
            assert not any("MLFLOW_EXPERIMENT_NAME" in s for s in all_scripts)
            assert not any("claude plugin" in s for s in all_scripts)

    # Scenario 4: Experiment name format — sandbox name "my-sandbox" → correct experiment path
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=True, port=5050, tracking_uri="http://localhost:5050")
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)
        profile = Profile(name="my-sandbox", mlflow=True)

        def exec_side_effect_mysandbox(name: str, script: str) -> str:
            if "claude plugin marketplace add" in script:
                return "MLflow tracing: plugin installed"
            return ""

        with (
            patch("sandboxctl.create.mlflow_cmd.check_mlflow_health", return_value=True),
            patch("sandboxctl.create.mlflow_cmd.start_mlflow_container"),
            patch("sandboxctl.openshell.sandbox_exec_pipe", side_effect=exec_side_effect_mysandbox) as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home") as mock_home,
        ):
            mock_home.return_value = Path(tmpdir) / "nonexistent"
            post_launch_setup("my-sandbox", profile, config)

            all_scripts = [c[0][1] for c in mock_exec.call_args_list]
            assert any("MLFLOW_EXPERIMENT_NAME=sandbox/my-sandbox" in s for s in all_scripts)


def test_gsd_auto_installs_when_missing() -> None:
    """GSD is installed via npx when enabled and not present in the sandbox (#82)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import SandboxctlConfig
    from sandboxctl.models import GsdConfig, Profile

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SandboxctlConfig(config_dir=Path(tmpdir))
        profile = Profile(name="test", mlflow=False, gsd=GsdConfig(enabled=True))

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=Path(tmpdir) / "nohome"),
        ):
            # Simulate GSD not present: 'missing' returned for gsd-core check
            def exec_side_effect(name: str, script: str) -> str:
                if "gsd-core" in script and "echo 'present'" in script:
                    return "missing"
                return ""

            mock_exec.side_effect = exec_side_effect

            from sandboxctl.create import post_launch_setup

            post_launch_setup("mybox", profile, config)

        npx_calls = [c for c in mock_exec.call_args_list if "npx" in str(c)]
        assert len(npx_calls) == 1
        assert "@opengsd/gsd-core@latest" in str(npx_calls[0])


def test_gsd_skipped_when_disabled() -> None:
    """GSD install and model_profile write are skipped when gsd.enabled=False (default, #111)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from sandboxctl.config import SandboxctlConfig
    from sandboxctl.models import Profile

    with tempfile.TemporaryDirectory() as tmpdir:
        config = SandboxctlConfig(config_dir=Path(tmpdir))
        profile = Profile(name="test", mlflow=False)  # gsd.enabled defaults to False

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_exec,
            patch("sandboxctl.openshell.sandbox_upload"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.shutil.which", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=Path(tmpdir) / "nohome"),
        ):
            from sandboxctl.create import post_launch_setup

            post_launch_setup("mybox", profile, config)

        all_scripts = [str(c) for c in mock_exec.call_args_list]
        assert not any("gsd-core" in s for s in all_scripts), "GSD check ran despite gsd.enabled=False"
        assert not any("@opengsd/gsd-core" in s for s in all_scripts), "GSD install ran despite gsd.enabled=False"
        assert not any("defaults.json" in s for s in all_scripts), "GSD defaults.json written despite gsd.enabled=False"


# ── OpenCode staging tests (#112) ────────────────────────────────────────────


def test_stage_opencode_config_copies_host_file(tmp_path: Path) -> None:
    """stage_opencode_config copies host config.json when it exists."""
    from sandboxctl.config import SandboxctlConfig

    host_config_dir = tmp_path / "home" / ".config" / "opencode"
    host_config_dir.mkdir(parents=True)
    host_config_dir.joinpath("config.json").write_text('{"providers":[]}')

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    config = SandboxctlConfig(config_dir=tmp_path / "sandboxctl")

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
        result = stage_opencode_config(stage_dir, config)

    assert result is True
    staged = stage_dir / ".config" / "opencode" / "config.json"
    assert staged.exists()
    assert staged.read_text() == '{"providers":[]}'


def test_stage_opencode_config_copies_jsonc_file(tmp_path: Path) -> None:
    """stage_opencode_config picks up opencode.jsonc (real-world convention, #115)."""
    from sandboxctl.config import SandboxctlConfig

    host_config_dir = tmp_path / "home" / ".config" / "opencode"
    host_config_dir.mkdir(parents=True)
    host_config_dir.joinpath("opencode.jsonc").write_text('{"provider":{}}')

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    config = SandboxctlConfig(config_dir=tmp_path / "sandboxctl")

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
        result = stage_opencode_config(stage_dir, config)

    assert result is True
    assert (stage_dir / ".config" / "opencode" / "opencode.jsonc").exists()


def test_stage_opencode_config_returns_false_when_no_host_file(tmp_path: Path) -> None:
    """stage_opencode_config returns False when no host config exists (no generated baseline)."""
    from sandboxctl.config import SandboxctlConfig

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    config = SandboxctlConfig(config_dir=tmp_path / "sandboxctl")

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"):
        result = stage_opencode_config(stage_dir, config)

    assert result is False
    # No config file should be generated — Vertex auth is via env vars, not a config file
    assert not (stage_dir / ".config" / "opencode").exists()


def test_stage_opencode_plugins_stages_from_host(tmp_path: Path) -> None:
    """stage_opencode_plugins copies plugins from host when present."""

    plugins_src = tmp_path / "home" / ".config" / "opencode" / "plugins"
    plugins_src.mkdir(parents=True)
    (plugins_src / "myplugin").mkdir()
    (plugins_src / "myplugin" / "index.js").write_text("// plugin")

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
        count = stage_opencode_plugins(stage_dir)

    assert count == 1
    assert (stage_dir / ".config" / "opencode" / "plugins" / "myplugin" / "index.js").exists()


def test_stage_opencode_plugins_returns_zero_when_absent(tmp_path: Path) -> None:
    """stage_opencode_plugins returns 0 when no host plugins directory."""

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"):
        count = stage_opencode_plugins(stage_dir)

    assert count == 0


def test_stage_opencode_agents_from_agent_dir(tmp_path: Path) -> None:
    """stage_opencode_agents copies host ~/.config/opencode/agent/*.md (#124)."""
    agents_src = tmp_path / "home" / ".config" / "opencode" / "agent"
    agents_src.mkdir(parents=True)
    (agents_src / "reviewer.md").write_text("---\n---\nreviewer")
    (agents_src / "planner.md").write_text("---\n---\nplanner")

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
        count = stage_opencode_agents(stage_dir)

    assert count == 2
    assert (stage_dir / ".config" / "opencode" / "agent" / "reviewer.md").exists()


def test_stage_opencode_agents_from_agents_dir(tmp_path: Path) -> None:
    """stage_opencode_agents also accepts the plural 'agents' directory name (#124)."""
    agents_src = tmp_path / "home" / ".config" / "opencode" / "agents"
    agents_src.mkdir(parents=True)
    (agents_src / "solo.md").write_text("agent")

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "home"):
        count = stage_opencode_agents(stage_dir)

    assert count == 1
    assert (stage_dir / ".config" / "opencode" / "agents" / "solo.md").exists()


def test_stage_opencode_agents_returns_zero_when_absent(tmp_path: Path) -> None:
    """stage_opencode_agents returns 0 when no host agent directory (#124)."""
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()

    with patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"):
        count = stage_opencode_agents(stage_dir)

    assert count == 0
