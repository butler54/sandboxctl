"""TOML profile loading, listing, and skeleton creation."""

from __future__ import annotations

import tomllib
from pathlib import Path

from sandboxctl.config import SandboxctlConfig
from sandboxctl.models import Profile, SandboxConfig, SshHostConfig, WorkspaceConfig


def load_profile(name: str, config: SandboxctlConfig) -> Profile:
    path = config.profiles_dir / f"{name}.toml"
    if not path.exists():
        msg = f"Profile not found: {path}"
        raise FileNotFoundError(msg)

    with path.open("rb") as f:
        data = tomllib.load(f)

    sandbox = SandboxConfig(**data.get("sandbox", {}))
    workspace = WorkspaceConfig(**data.get("workspace", {}))
    repos: dict[str, list[str]] = data.get("repos", {})
    ssh: dict[str, SshHostConfig] = {host: SshHostConfig(**cfg) for host, cfg in data.get("ssh", {}).items()}

    if not sandbox.model:
        sandbox = sandbox.model_copy(update={"model": config.default_model})

    return Profile(
        name=name,
        sandbox=sandbox,
        workspace=workspace,
        repos=repos,
        ssh=ssh,
    )


def list_profiles(config: SandboxctlConfig) -> list[str]:
    if not config.profiles_dir.exists():
        return []
    return sorted(p.stem for p in config.profiles_dir.glob("*.toml"))


_SKELETON = """\
# Sandbox profile: {name}
# Usage: sandboxctl create --profile {name}

[sandbox]
# Build from a local Containerfile (default)
# containerfile = "Containerfile"

# OR use a pre-built container image (mutually exclusive with containerfile)
# image = "ghcr.io/org/sandbox:latest"

# policy = "policy.yaml"
# default_repo = ""
# model = ""

[workspace]
# theme = "Cobalt2"
# zoom = -1

[repos]
github = [
    # "owner/repo-name",
]

# "gitlab.com" = [
#     "group/repo-name",
# ]

# [ssh]
# "hostname.example.com" = {{ user = "root" }}
"""


def init_profile(name: str, config: SandboxctlConfig) -> Path:
    config.profiles_dir.mkdir(parents=True, exist_ok=True)
    path = config.profiles_dir / f"{name}.toml"
    if path.exists():
        msg = f"Profile already exists: {path}"
        raise FileExistsError(msg)
    path.write_text(_SKELETON.format(name=name))
    return path
