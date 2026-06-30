"""XDG-compliant configuration using pydantic-settings."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


def _default_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "sandboxctl"
    return Path.home() / ".config" / "sandboxctl"


class _SubConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")


class IdentityConfig(_SubConfig):
    user_name: str = ""
    user_email: str = ""


class DefaultsConfig(_SubConfig):
    model: str = "claude-sonnet-4-20250514"
    theme: str = "dark"
    zoom: int = -1


class ProvidersConfig(_SubConfig):
    vertex_project_id: str = ""
    vertex_region: str = "global"


class PathsConfig(_SubConfig):
    ssh_key: Path = Field(default_factory=lambda: Path.home() / ".ssh" / "sandboxctl_ed25519")
    ca_bundle: Path | None = None

    @model_validator(mode="after")
    def _expand_paths(self) -> PathsConfig:
        if "~" in str(self.ssh_key):
            object.__setattr__(self, "ssh_key", self.ssh_key.expanduser())
        if self.ca_bundle and "~" in str(self.ca_bundle):
            object.__setattr__(self, "ca_bundle", self.ca_bundle.expanduser())
        return self


class KeychainConfig(_SubConfig):
    github_service: str = "sandboxctl-github-token"
    gitlab_service: str = "sandboxctl-gitlab-token"


class TlsConfig(_SubConfig):
    ca_paths: list[Path] = Field(default_factory=list)

    @model_validator(mode="after")
    def _expand_paths(self) -> TlsConfig:
        expanded = [p.expanduser() if "~" in str(p) else p for p in self.ca_paths]
        object.__setattr__(self, "ca_paths", expanded)
        return self


class SandboxctlConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SANDBOXCTL_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    config_dir: Path = Field(default_factory=_default_config_dir)
    profiles_dir: Path | None = None

    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    keychain: KeychainConfig = Field(default_factory=KeychainConfig)
    tls: TlsConfig = Field(default_factory=TlsConfig)

    _config_dir_override: ClassVar[Path | None] = None

    @model_validator(mode="after")
    def _resolve_profiles_dir(self) -> SandboxctlConfig:
        if self.profiles_dir is None:
            object.__setattr__(self, "profiles_dir", self.config_dir / "profiles")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        toml_path = cls._resolve_toml_path()
        sources = [init_settings, env_settings]
        if toml_path and toml_path.is_file():
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=toml_path))
        return tuple(sources)

    @classmethod
    def _resolve_toml_path(cls) -> Path | None:
        if cls._config_dir_override:
            return cls._config_dir_override / "config.toml"
        return _default_config_dir() / "config.toml"

    # Convenience accessors for flat access patterns used by callers
    @property
    def git_user_name(self) -> str:
        return self.identity.user_name

    @property
    def git_user_email(self) -> str:
        return self.identity.user_email

    @property
    def default_model(self) -> str:
        return self.defaults.model

    @property
    def default_theme(self) -> str:
        return self.defaults.theme

    @property
    def default_zoom(self) -> int:
        return self.defaults.zoom

    @property
    def vertex_project_id(self) -> str:
        return self.providers.vertex_project_id

    @property
    def ssh_key(self) -> Path:
        return self.paths.ssh_key

    @property
    def ca_bundle(self) -> Path | None:
        return self.paths.ca_bundle

    @property
    def keychain_github(self) -> str:
        return self.keychain.github_service

    @property
    def keychain_gitlab(self) -> str:
        return self.keychain.gitlab_service

    @property
    def ca_paths(self) -> list[Path]:
        return self.tls.ca_paths


def load_config(config_dir: Path | None = None) -> SandboxctlConfig:
    """Load config with optional config_dir override (mainly for testing)."""
    SandboxctlConfig._config_dir_override = config_dir
    try:
        kwargs: dict[str, Any] = {}
        if config_dir:
            kwargs["config_dir"] = config_dir
            kwargs["profiles_dir"] = config_dir / "profiles"
        return SandboxctlConfig(**kwargs)
    finally:
        SandboxctlConfig._config_dir_override = None


def ensure_config_dir(config: SandboxctlConfig) -> None:
    """Create config and profiles directories if they don't exist."""
    config.config_dir.mkdir(parents=True, exist_ok=True)
    if config.profiles_dir:
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

[tls]
# ca_paths = ["~/.config/certs/custom-ca.pem"]
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
