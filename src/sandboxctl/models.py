"""Pydantic models for profiles, Claude settings, and sandbox state."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SandboxConfig(BaseModel):
    """Per-sandbox settings within a profile."""

    containerfile: str = "Containerfile"
    image: str = ""
    policy: str = "policy.yaml"
    default_repo: str = ""
    model: str = ""

    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def _check_image_or_containerfile(self) -> SandboxConfig:
        if self.image and self.containerfile != "Containerfile":
            msg = "Cannot set both 'image' and a custom 'containerfile' — they are mutually exclusive"
            raise ValueError(msg)
        return self


class WorkspaceConfig(BaseModel):
    """VS Code workspace preferences."""

    theme: str = ""
    zoom: int = -1
    terminal_app: str = ""  # "iTerm", "Terminal", or "" (auto-detect)

    model_config = {"extra": "ignore"}


class SshHostConfig(BaseModel):
    """SSH host proxy configuration."""

    user: str = "root"
    proxy_host: str = ""

    model_config = {"extra": "ignore"}


class McpServerConfig(BaseModel):
    """MCP server OAuth credential staging configuration."""

    servers: list[str] = Field(default_factory=list)
    model_config = {"extra": "ignore"}


class CredentialConfig(BaseModel):
    github: bool = True
    gitlab: bool = False
    gitlab_servers: list[str] = Field(default_factory=list)
    gcloud_adc: bool = False
    gws: bool = False
    ssh_key: bool = True
    mcp: McpServerConfig = Field(default_factory=McpServerConfig)
    model_config = {"extra": "ignore"}


class Extensions(BaseModel):
    """VS Code extension declarations."""

    extensions_list: list[str] = Field(default_factory=list, alias="list")
    local_only: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore", "populate_by_name": True}


class GsdConfig(BaseModel):
    """GSD runtime settings staged at sandbox creation."""

    model_profile: str = ""

    model_config = {"extra": "ignore"}


class Profile(BaseModel):
    """Sandbox profile loaded from TOML."""

    name: str
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    repos: dict[str, list[str]] = Field(default_factory=dict)
    ssh: dict[str, SshHostConfig] = Field(default_factory=dict)
    credentials: CredentialConfig = Field(default_factory=CredentialConfig)
    extensions: Extensions = Field(default_factory=Extensions)
    mlflow: bool = True
    gsd: GsdConfig = Field(default_factory=GsdConfig)


class ClaudePermissions(BaseModel):
    """Claude Code permission settings."""

    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)
    defaultMode: str = "bypassPermissions"


class ClaudeSettings(BaseModel):
    """Claude Code settings staged into sandboxes."""

    permissions: ClaudePermissions = Field(default_factory=ClaudePermissions)
    theme: str = ""
    model: str = ""
    skipWorkflowUsageWarning: bool = True


class ClaudeState(BaseModel):
    """Claude Code state flags for skip-onboarding behavior."""

    numStartups: int = 1
    hasCompletedOnboarding: bool = True
    hasSeenTasksHint: bool = True
    autoUpdates: bool = False
    tipsHistory: dict[str, int] = Field(default_factory=lambda: {"new-user-warmup": 1, "theme-command": 1})
