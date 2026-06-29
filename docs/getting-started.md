# Getting Started

This guide walks you through installing sandboxctl, configuring it for first
use, and creating your first sandbox profile.

## Prerequisites

- **Python 3.12** or later
- **[NVIDIA OpenShell](https://github.com/NVIDIA/openshell)** installed and configured
- **macOS or Linux** (Windows is not supported)
- **Git**

## Installation

### From PyPI

```bash
pip install sandboxctl
```

### From source

```bash
git clone https://github.com/butler54/sandboxctl.git
cd sandboxctl
pip install -e "."
```

## Initial Configuration

Run `sandboxctl config init` to create the default configuration file at
`~/.config/sandboxctl/config.toml`:

```toml
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
# provider = "anthropic"                  # "anthropic" (default) or "vertex"
# anthropic_api_key = ""                  # API key for direct Anthropic access
# vertex_project_id = ""                  # Google Cloud project (vertex only)
# vertex_region = "global"               # Vertex AI region (vertex only)

[paths]
# ssh_key = "~/.ssh/sandboxctl_ed25519"
# ca_bundle = ""

[keychain]
# github_service = "sandboxctl-github-token"
# gitlab_service = "sandboxctl-gitlab-token"
```

### Configuration sections

- **`[identity]`** -- Git user name and email used for commits inside
  sandboxes. These values are injected into the container's Git config.

- **`[defaults]`** -- Default Claude model, VS Code theme, and zoom level
  applied to new sandboxes unless overridden by a profile.

- **`[providers]`** -- Claude API provider selection. Use `anthropic` (default) for
  direct API access with an API key, or `vertex` for Google Cloud Vertex AI.

- **`[paths]`** -- Path to an SSH key for repository cloning and an optional
  CA certificate bundle for corporate environments.

- **`[keychain]`** -- Service names used by the credential storage backend
  (macOS Keychain, libsecret, etc.) for GitHub and GitLab tokens.

### Environment variable overrides

All configuration values can be set via environment variables using the
`SANDBOXCTL_` prefix with `__` as the section separator. For example:

```bash
export SANDBOXCTL_IDENTITY__USER_NAME="Your Name"
export SANDBOXCTL_IDENTITY__USER_EMAIL="you@example.com"
export SANDBOXCTL_PROVIDERS__VERTEX_PROJECT_ID="my-gcp-project"
```

## Creating Your First Profile

Run `sandboxctl init my-project` to create a profile skeleton at
`~/.config/sandboxctl/profiles/my-project.toml`:

```toml
# Sandbox profile: my-project
# Usage: sandboxctl create --profile my-project

[sandbox]
# containerfile = "Containerfile"       # Custom Containerfile (optional)
# policy = "policy.yaml"               # Custom policy (optional)
# default_repo = ""                    # Repo to cd into for Claude Code
# model = ""                           # Claude model override

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

# "gitlab.corp.com" = [
#     "team/internal-repo",
# ]

# [ssh]
# "hostname.example.com" = { user = "root" }
```

### Profile sections

- **`[sandbox]`** -- Optional Containerfile path, network policy, default
  repository to open in Claude Code, and a model override.

- **`[workspace]`** -- VS Code theme and zoom level for the sandbox editor
  window. Overrides the values in `config.toml`.

- **`[repos]`** -- Git repositories to clone into the sandbox. List GitHub
  repos under the `github` key. For GitLab or other hosts, use the hostname
  as the key (e.g., `"gitlab.com"` or `"gitlab.corp.com"` for privately
  hosted instances).

- **`[ssh]`** -- SSH proxy host configuration for accessing remote machines
  from within the sandbox.

## Creating a Sandbox

!!! note

    The `create` and `open` commands are planned but not yet implemented.
    See [create](commands/create.md) and [open](commands/open.md) for the
    intended design.

Once implemented, the workflow will be:

```bash
sandboxctl create --profile my-project my-sandbox
```

This will build the container image, clone the configured repositories, inject
credentials, and launch the sandbox.

## Working with Sandboxes

The following commands are available for managing existing sandboxes:

```bash
# List all sandboxes and their current state
sandboxctl list

# Show detailed status for a specific sandbox
sandboxctl status my-sandbox

# Validate a sandbox profile and configuration
sandboxctl validate my-sandbox

# Run health checks and attempt automatic recovery
sandboxctl doctor my-sandbox

# Run health checks without automatic recovery
sandboxctl doctor my-sandbox --no-recover
```

## Cleaning Up

To remove a sandbox and its associated resources:

```bash
sandboxctl delete my-sandbox
```

!!! warning

    Deleting a sandbox removes the container and any uncommitted work inside
    it. Make sure all changes are pushed to a remote before deleting.

## Next Steps

- See [Commands](commands/index.md) for the full command reference.
- See [Configuration](configuration/index.md) for advanced setup options.
- See [Profiles](configuration/profiles.md) for profile customization.
