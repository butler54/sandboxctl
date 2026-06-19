"""Tests for profile loading and management."""

from __future__ import annotations

from pathlib import Path

import pytest

from sandboxctl.config import load_config
from sandboxctl.profile import init_profile, list_profiles, load_profile


def test_load_profile(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "dev.toml").write_text('[sandbox]\ndefault_repo = "my-repo"\n\n[repos]\ngithub = ["owner/repo"]\n')
    cfg = load_config(config_dir=tmp_path)
    profile = load_profile("dev", cfg)
    assert profile.name == "dev"
    assert profile.sandbox.default_repo == "my-repo"
    assert "github" in profile.repos


def test_load_profile_not_found(tmp_path: Path) -> None:
    cfg = load_config(config_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        load_profile("nonexistent", cfg)


def test_load_profile_fills_default_model(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "test.toml").write_text("[sandbox]\n")
    cfg = load_config(config_dir=tmp_path)
    profile = load_profile("test", cfg)
    assert profile.sandbox.model == cfg.default_model


def test_list_profiles(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "alpha.toml").touch()
    (profiles_dir / "beta.toml").touch()
    cfg = load_config(config_dir=tmp_path)
    assert list_profiles(cfg) == ["alpha", "beta"]


def test_list_profiles_empty(tmp_path: Path) -> None:
    cfg = load_config(config_dir=tmp_path)
    assert list_profiles(cfg) == []


def test_init_profile(tmp_path: Path) -> None:
    cfg = load_config(config_dir=tmp_path)
    path = init_profile("newprofile", cfg)
    assert path.exists()
    assert "sandboxctl" in path.read_text()


def test_init_profile_already_exists(tmp_path: Path) -> None:
    cfg = load_config(config_dir=tmp_path)
    init_profile("existing", cfg)
    with pytest.raises(FileExistsError):
        init_profile("existing", cfg)
