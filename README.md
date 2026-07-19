# sandboxctl

Safe, isolated sandboxes for using LLMs with minimal guardrails to maximize developer productivity.

> **Experimental.** sandboxctl is under active development. Commands, configuration, and
> behavior may change between releases.

## Features

- **Isolated sandboxes** -- each sandbox runs in its own OpenShell container with a dedicated filesystem and toolchain.
- **Profile system** -- define reusable sandbox configurations (repos, extensions, settings) as declarative profiles.
- **Cross-platform credentials** -- OS keychain integration for GitHub and GitLab tokens on macOS and Linux.
- **Scoped Git tokens** -- per-sandbox token injection so credentials never leak across projects.
- **Health checks and auto-recovery** -- `doctor` and `recover` commands detect drift and repair common issues automatically.
- **Claude context management** -- backup and restore Claude Code memory, settings, and projects across sandbox lifecycle.
- **Bundled skills** -- ships sandbox-specific Claude Code skills (network debugging, policy linting) installed automatically during setup.
- **CLI lifecycle management** -- create, open, list, backup, restore, delete, and upgrade sandboxes from a single tool.

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.12+ |
| [NVIDIA OpenShell](https://github.com/NVIDIA/openshell) | latest |
| OS | macOS or Linux |

## Installation

Install from PyPI:

```bash
pip install sandboxctl
```

Or install with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install sandboxctl
```

For development:

```bash
git clone https://github.com/butler54/sandboxctl.git
cd sandboxctl
make dev
```

## Quickstart

```bash
# 1. Run first-time setup (prerequisites, SSH key, credentials, providers, shell completion)
sandboxctl setup

# 2. Review and customize your config
$EDITOR "$(sandboxctl config path)"

# 3. Create a new profile skeleton
sandboxctl init my-project

# 4. Edit the profile to add repos, extensions, and settings
$EDITOR ~/.config/sandboxctl/profiles/my-project.toml

# 5. Create a sandbox from the profile
sandboxctl create --profile my-project

# 6. Open the sandbox in VS Code + Claude Code
sandboxctl open my-project
```

## Configuration

sandboxctl uses an XDG-compliant TOML configuration file, typically located at
`~/.config/sandboxctl/config.toml`. Run `sandboxctl config init` to generate the
default template:

```toml
[identity]
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

All values can also be set via environment variables with the `SANDBOXCTL_` prefix
(e.g., `SANDBOXCTL_IDENTITY__USER_NAME`).

## Profiles

Profiles are TOML files under `~/.config/sandboxctl/profiles/` that describe a
sandbox environment. Run `sandboxctl init <name>` to scaffold a new profile, then
customize the generated file with your repositories, container settings, and SSH
configuration.

## Commands

### Lifecycle

| Command | Description |
|---|---|
| `sandboxctl create --profile <name>` | Create a sandbox from a profile |
| `sandboxctl open <name>` | Open a sandbox in VS Code, Claude Code, or shell |
| `sandboxctl restart <name>` | Delete and recreate a sandbox (with data loss warning) |
| `sandboxctl delete <name>` | Delete a sandbox |

### Inspection

| Command | Description |
|---|---|
| `sandboxctl list` | List profiles and running sandboxes |
| `sandboxctl status` | Show gateway and sandbox status |
| `sandboxctl validate <name>` | Run validation tests inside a sandbox |

### Health & Recovery

| Command | Description |
|---|---|
| `sandboxctl doctor [name]` | Diagnose sandbox health, credentials, and profile readiness |
| `sandboxctl doctor --fix [name]` | Re-inject credentials and CA bundles into running sandboxes |
| `sandboxctl recover [name]` | Recover stopped sandboxes after host reboot or podman restart |

### Context Management

| Command | Description |
|---|---|
| `sandboxctl backup [name]` | Back up Claude context (memory, settings) from a sandbox |
| `sandboxctl restore <name>` | Restore Claude context into a sandbox |

### Setup & Maintenance

| Command | Description |
|---|---|
| `sandboxctl setup` | First-time setup: prerequisites, SSH key, credentials, providers, shell completion, bundled skills |
| `sandboxctl upgrade` | Upgrade OpenShell (detects Homebrew/pip, advises gateway restart) |
| `sandboxctl init <name>` | Create a new profile skeleton |
| `sandboxctl config init` | Create default configuration file |
| `sandboxctl config show` | Show current configuration |
| `sandboxctl config path` | Print config file path |
| `sandboxctl --version` | Show version and exit |

### Shell Completion

Shell completion is installed automatically during `sandboxctl setup`. To install or update manually:

```bash
sandboxctl --install-completion
```

Supports bash, zsh, fish, and PowerShell.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management and
[ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
make dev       # Install in dev mode with all dependencies
make lint      # Check code style (ruff check + format check)
make format    # Auto-format code
make test      # Run tests with coverage
make clean     # Remove build artifacts
```

Tests run with pytest and require no external services. Integration tests that need
a running OpenShell instance are marked with `@pytest.mark.integration` and skipped
by default in CI.

## License

[Apache-2.0](LICENSE)
