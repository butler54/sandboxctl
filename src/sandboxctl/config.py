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


class BackupConfig(_SubConfig):
    extra_paths: list[str] = Field(default_factory=list)


class MlflowConfig(_SubConfig):
    tracking_uri: str = "http://localhost:5050"
    managed: bool = True
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".config" / "sandboxctl" / "mlflow-data")
    port: int = 5050

    @model_validator(mode="after")
    def _validate_and_expand(self) -> MlflowConfig:
        from urllib.parse import urlparse

        # Expand tilde in data_dir
        if "~" in str(self.data_dir):
            object.__setattr__(self, "data_dir", self.data_dir.expanduser())

        # Reject parent traversal in data_dir
        for part in self.data_dir.parts:
            if part == "..":
                msg = f"data_dir cannot contain parent directory traversal: {self.data_dir}"
                raise ValueError(msg)

        # Validate port range
        if not (1 <= self.port <= 65535):
            msg = f"port must be between 1 and 65535, got {self.port}"
            raise ValueError(msg)

        # Validate tracking_uri scheme
        parsed = urlparse(self.tracking_uri)
        if parsed.scheme not in ("http", "https"):
            msg = f"tracking_uri scheme must be http or https, got {parsed.scheme}"
            raise ValueError(msg)

        return self


class OpencodeConfig(_SubConfig):
    # Named OpenAI accounts. Each name maps to a host keychain entry
    # "sandboxctl-openai-<name>"; the key is injected into the sandbox as
    # OPENAI_API_KEY_<NAME> (uppercased), and the first account also sets
    # OPENAI_API_KEY (opencode's built-in openai provider default). #129
    openai_accounts: list[str] = Field(default_factory=list)


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
    backup: BackupConfig = Field(default_factory=BackupConfig)
    mlflow: MlflowConfig = Field(default_factory=MlflowConfig)
    opencode: OpencodeConfig = Field(default_factory=OpencodeConfig)

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
    def vertex_region(self) -> str:
        return self.providers.vertex_region

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

    @property
    def backup_extra_paths(self) -> list[str]:
        return self.backup.extra_paths

    @property
    def mlflow_tracking_uri(self) -> str:
        return self.mlflow.tracking_uri


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

[backup]
# extra_paths = [".some-plugin"]

# [mlflow]
# MLflow tracking server configuration
# tracking_uri = "http://localhost:5050"
# managed = true  # If false, sandboxctl will not manage the container (external MLflow)
# data_dir = "~/.config/sandboxctl/mlflow-data"
# port = 5050
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


def find_terminal_app() -> str | None:
    """Detect the terminal app to use for spawning a Claude Code session.

    Returns the app name suitable for osascript ("iTerm" or "Terminal"), NOT a full path.
    User can override via config [workspace] terminal_app field.

    Priority: infer from the CURRENT terminal environment first so the new window
    opens in the same app the user is already in. Only fall back to installed-app
    detection if the environment gives no signal.
    """
    import subprocess

    # 1. Current-terminal inference via environment variables.
    #    These are set by the terminal app itself and survive tmux sessions.
    iterm_session = os.environ.get("ITERM_SESSION_ID")
    term_program = os.environ.get("TERM_PROGRAM", "")

    if iterm_session or "iterm" in term_program.lower():
        return "iTerm"

    if term_program == "Apple_Terminal":
        return "Terminal"

    # 2. Installed-app fallback (no useful env signal — e.g. launched from a
    #    script or CI context). Check common locations and mdfind.
    for iterm_path in (
        Path("/Applications/iTerm.app"),
        Path.home() / "Applications" / "iTerm.app",
    ):
        if iterm_path.exists():
            return "iTerm"

    try:
        result = subprocess.run(
            ["mdfind", "kMDItemCFBundleIdentifier == 'com.googlecode.iterm2'"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return "iTerm"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if Path("/System/Applications/Utilities/Terminal.app").exists():
        return "Terminal"

    return None  # No terminal found — caller prints manual command
