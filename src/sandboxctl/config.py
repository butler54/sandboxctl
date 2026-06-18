"""XDG-compliant configuration loading."""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _default_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "sandboxctl"
    return Path.home() / ".config" / "sandboxctl"


@dataclass(frozen=True)
class SandboxctlConfig:
    config_dir: Path = field(default_factory=_default_config_dir)
    profiles_dir: Path = field(default=None)  # type: ignore[assignment]
    ssh_key: Path = field(default_factory=lambda: Path.home() / ".ssh" / "sandboxctl_ed25519")
    git_user_name: str = ""
    git_user_email: str = ""
    default_model: str = "claude-sonnet-4-20250514"
    default_theme: str = "dark"
    default_zoom: int = -1
    vertex_project_id: str = ""
    vertex_region: str = "global"
    ca_bundle: Path | None = None
    keychain_github: str = "sandboxctl-github-token"
    keychain_gitlab: str = "sandboxctl-gitlab-token"

    def __post_init__(self) -> None:
        if self.profiles_dir is None:
            object.__setattr__(self, "profiles_dir", self.config_dir / "profiles")


def _merge_toml(defaults: dict[str, Any], toml_data: dict[str, Any]) -> dict[str, Any]:
    """Merge TOML sections into a flat dict matching config fields."""
    mapping = {
        "identity": {"user_name": "git_user_name", "user_email": "git_user_email"},
        "defaults": {"model": "default_model", "theme": "default_theme", "zoom": "default_zoom"},
        "providers": {"vertex_project_id": "vertex_project_id", "vertex_region": "vertex_region"},
        "paths": {"ssh_key": "ssh_key", "ca_bundle": "ca_bundle"},
        "keychain": {"github_service": "keychain_github", "gitlab_service": "keychain_gitlab"},
    }
    result = dict(defaults)
    for section, fields in mapping.items():
        section_data = toml_data.get(section, {})
        for toml_key, config_key in fields.items():
            if toml_key in section_data:
                val = section_data[toml_key]
                if config_key in ("ssh_key", "ca_bundle") and val:
                    val = Path(os.path.expanduser(str(val)))
                result[config_key] = val
    return result


_ENV_OVERRIDES = {
    "SANDBOXCTL_GIT_USER_NAME": "git_user_name",
    "SANDBOXCTL_GIT_USER_EMAIL": "git_user_email",
    "ANTHROPIC_VERTEX_PROJECT_ID": "vertex_project_id",
    "SANDBOXCTL_DEFAULT_MODEL": "default_model",
}


def load_config(config_dir: Path | None = None) -> SandboxctlConfig:
    """Load config from TOML file with env var overrides."""
    base_dir = config_dir or _default_config_dir()
    config_file = base_dir / "config.toml"

    defaults: dict[str, Any] = {
        "config_dir": base_dir,
        "profiles_dir": base_dir / "profiles",
    }

    if config_file.is_file():
        with config_file.open("rb") as f:
            toml_data = tomllib.load(f)
        defaults = _merge_toml(defaults, toml_data)

    for env_var, config_key in _ENV_OVERRIDES.items():
        val = os.environ.get(env_var)
        if val:
            defaults[config_key] = val

    return SandboxctlConfig(**defaults)


def ensure_config_dir(config: SandboxctlConfig) -> None:
    """Create config and profiles directories if they don't exist."""
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.profiles_dir.mkdir(parents=True, exist_ok=True)


CONFIG_TEMPLATE = """\
# sandboxctl configuration
# See: https://github.com/butler54/sandboxctl

[identity]
# Required: your git identity for commits inside sandboxes
# user_name = "Your Name"
# user_email = "you@example.com"

[defaults]
# model = "claude-sonnet-4-20250514"
# theme = "dark"
# zoom = -1

[providers]
# vertex_project_id = ""
# vertex_region = "global"

[paths]
# ssh_key = "~/.ssh/sandboxctl_ed25519"
# ca_bundle = ""

[keychain]
# github_service = "sandboxctl-github-token"
# gitlab_service = "sandboxctl-gitlab-token"
"""


def find_vscode_bin() -> Path | None:
    """Find the VS Code binary, checking PATH then platform-specific locations."""
    path = shutil.which("code")
    if path:
        return Path(path)
    mac_path = Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")
    if mac_path.exists():
        return mac_path
    return None
