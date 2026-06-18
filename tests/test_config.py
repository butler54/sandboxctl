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
