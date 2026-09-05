"""Tests for configuration module."""

from __future__ import annotations

from pathlib import Path

import pytest

from sandboxctl.config import load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    """Config loads with sensible defaults when no file exists."""
    cfg = load_config(config_dir=tmp_path)
    assert cfg.config_dir == tmp_path
    assert cfg.profiles_dir == tmp_path / "profiles"
    assert cfg.default_theme == "dark"
    assert cfg.default_zoom == -1
    assert cfg.git_user_name == ""
    assert cfg.git_user_email == ""


def test_load_config_from_file(tmp_path: Path) -> None:
    """Config reads values from config.toml."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[identity]\nuser_name = "Test User"\nuser_email = "test@example.com"\n'
        '[defaults]\nmodel = "claude-opus-4-6"\ntheme = "light"\nzoom = 0\n'
    )
    cfg = load_config(config_dir=tmp_path)
    assert cfg.git_user_name == "Test User"
    assert cfg.git_user_email == "test@example.com"
    assert cfg.default_model == "claude-opus-4-6"
    assert cfg.default_theme == "light"
    assert cfg.default_zoom == 0


def test_load_config_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables override file values."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[identity]\nuser_name = "File User"\n')
    monkeypatch.setenv("SANDBOXCTL_IDENTITY__USER_NAME", "Env User")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.git_user_name == "Env User"


def test_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Respects XDG_CONFIG_HOME environment variable."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = load_config()
    assert cfg.config_dir == tmp_path / "sandboxctl"


def test_ensure_config_dir(tmp_path: Path) -> None:
    """Creates config and profiles directories."""
    from sandboxctl.config import ensure_config_dir

    cfg = load_config(config_dir=tmp_path / "new")
    ensure_config_dir(cfg)
    assert cfg.config_dir.is_dir()
    assert cfg.profiles_dir.is_dir()


def test_config_properties(tmp_path: Path) -> None:
    """Convenience properties provide flat access to nested config."""
    cfg = load_config(config_dir=tmp_path)
    assert cfg.default_model == "claude-sonnet-4-20250514"
    assert cfg.default_theme == "dark"
    assert cfg.default_zoom == -1
    assert cfg.vertex_project_id == ""
    assert cfg.keychain_github == "sandboxctl-github-token"
    assert cfg.keychain_gitlab == "sandboxctl-gitlab-token"
    assert isinstance(cfg.ssh_key, Path)
    assert cfg.ca_bundle is None


def test_vertex_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vertex project ID settable via nested env var."""
    monkeypatch.setenv("SANDBOXCTL_PROVIDERS__VERTEX_PROJECT_ID", "my-project")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.vertex_project_id == "my-project"


def test_nested_model_from_toml(tmp_path: Path) -> None:
    """Nested models populated from TOML sections."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[providers]\nvertex_project_id = "gcp-proj"\nvertex_region = "us-east1"\n'
        '[keychain]\ngithub_service = "custom-gh"\n'
    )
    cfg = load_config(config_dir=tmp_path)
    assert cfg.providers.vertex_project_id == "gcp-proj"
    assert cfg.providers.vertex_region == "us-east1"
    assert cfg.keychain.github_service == "custom-gh"
    assert cfg.keychain.gitlab_service == "sandboxctl-gitlab-token"


def test_opencode_config_from_toml(tmp_path: Path) -> None:
    """OpenCode provider and agent defaults load from their own config section."""
    (tmp_path / "config.toml").write_text(
        '[opencode]\nenabled_providers = ["vertex", "openai-work"]\n'
        'disabled_providers = ["github-copilot"]\n'
        'model = "vertex/claude-sonnet"\n'
        'build_model = "openai-work/gpt-5.6"\n'
        'plan_model = "vertex/claude-opus"\n'
    )
    cfg = load_config(config_dir=tmp_path)
    assert cfg.opencode.enabled_providers == ["vertex", "openai-work"]
    assert cfg.opencode.disabled_providers == ["github-copilot"]
    assert cfg.opencode.model == "vertex/claude-sonnet"
    assert cfg.opencode.build_model == "openai-work/gpt-5.6"
    assert cfg.opencode.plan_model == "vertex/claude-opus"


def test_extra_fields_ignored(tmp_path: Path) -> None:
    """Unknown TOML fields don't cause errors."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[identity]\nuser_name = "Test"\nunknown_field = "ignored"\n')
    cfg = load_config(config_dir=tmp_path)
    assert cfg.git_user_name == "Test"


def test_path_expansion_in_config(tmp_path: Path) -> None:
    """Tilde paths in config are expanded."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[paths]\nssh_key = "~/.ssh/my_key"\n')
    cfg = load_config(config_dir=tmp_path)
    assert "~" not in str(cfg.ssh_key)
    assert str(cfg.ssh_key).endswith(".ssh/my_key")


def test_profile_mlflow_opt_out() -> None:
    """Profile.mlflow defaults to True; mlflow=false opts out."""
    import tempfile

    from sandboxctl.profile import load_profile

    # Profile with mlflow = false → Profile.mlflow is False
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        profiles_dir = config_dir / "profiles"
        profiles_dir.mkdir()
        profile_toml = profiles_dir / "opt-out.toml"
        profile_toml.write_text('mlflow = false\n\n[sandbox]\ncontainerfile = "Containerfile"\n')
        config = load_config(config_dir=config_dir)
        profile = load_profile("opt-out", config)
        assert profile.mlflow is False

    # Profile with no mlflow key → defaults to True (default-on)
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        profiles_dir = config_dir / "profiles"
        profiles_dir.mkdir()
        profile_toml = profiles_dir / "default-on.toml"
        profile_toml.write_text('[sandbox]\ncontainerfile = "Containerfile"\n')
        config = load_config(config_dir=config_dir)
        profile = load_profile("default-on", config)
        assert profile.mlflow is True


def test_mlflow_config() -> None:
    """MlflowConfig section loads, validates, and rejects bad values."""
    import tempfile

    # Happy path: valid config
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        config_file = config_dir / "config.toml"
        config_file.write_text('[mlflow]\ntracking_uri = "http://localhost:5050"\nmanaged = true\nport = 5050\n')
        cfg = load_config(config_dir=config_dir)
        assert cfg.mlflow.tracking_uri == "http://localhost:5050"
        assert cfg.mlflow.managed is True
        assert cfg.mlflow.port == 5050
        assert cfg.mlflow_tracking_uri == "http://localhost:5050"

    # No [mlflow] section → defaults
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        cfg = load_config(config_dir=config_dir)
        assert cfg.mlflow.managed is True
        assert cfg.mlflow.port == 5050
        assert "mlflow-data" in str(cfg.mlflow.data_dir)

    # Bad port → ValueError
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        config_file = config_dir / "config.toml"
        config_file.write_text("[mlflow]\nport = 70000\n")
        with pytest.raises(ValueError, match="port must be between 1 and 65535"):
            load_config(config_dir=config_dir)

    # Parent traversal in data_dir → ValueError
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        config_file = config_dir / "config.toml"
        config_file.write_text('[mlflow]\ndata_dir = "/home/user/../etc/passwd"\n')
        with pytest.raises(ValueError, match="data_dir cannot contain parent directory traversal"):
            load_config(config_dir=config_dir)

    # Non-http scheme → ValueError
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        config_file = config_dir / "config.toml"
        config_file.write_text('[mlflow]\ntracking_uri = "file:///etc/passwd"\n')
        with pytest.raises(ValueError, match="tracking_uri scheme must be http or https"):
            load_config(config_dir=config_dir)


class TestFindTerminalApp:
    """Tests for terminal app detection (iTerm2-first, then Terminal.app, then None)."""

    def test_finds_iterm_when_present(self) -> None:
        """Returns 'iTerm' when iTerm.app exists."""
        from unittest.mock import patch

        from sandboxctl.config import find_terminal_app

        with patch("pathlib.Path.exists") as mock_exists:
            # /Applications/iTerm.app exists
            mock_exists.return_value = True
            result = find_terminal_app()
            assert result == "iTerm"

    def test_finds_terminal_when_iterm_absent(self) -> None:
        """Returns 'Terminal' when iTerm.app absent but Terminal.app exists."""
        from unittest.mock import patch

        from sandboxctl.config import find_terminal_app

        def exists_side_effect(path_self: Path) -> bool:
            # iTerm.app missing, Terminal.app present
            return str(path_self).endswith("Terminal.app")

        with patch("pathlib.Path.exists", new=exists_side_effect):
            result = find_terminal_app()
            assert result == "Terminal"

    def test_returns_none_when_no_terminal(self) -> None:
        """Returns None when neither iTerm.app nor Terminal.app exists."""
        from unittest.mock import patch

        from sandboxctl.config import find_terminal_app

        with patch("pathlib.Path.exists", return_value=False):
            result = find_terminal_app()
            assert result is None
