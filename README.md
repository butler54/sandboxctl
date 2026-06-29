# sandboxctl

OpenShell sandbox management CLI -- create, manage, and validate isolated development sandboxes.

> **Experimental.** sandboxctl is under active development. Commands, configuration, and
> behavior may change between releases.

## Features

- **Isolated sandboxes** -- each sandbox runs in its own OpenShell container with a dedicated filesystem and toolchain.
- **Profile system** -- define reusable sandbox configurations (repos, extensions, settings) as declarative profiles.
- **Cross-platform credentials** -- OS keychain integration for GitHub and GitLab tokens on macOS and Linux.
- **Scoped Git tokens** -- per-sandbox token injection so credentials never leak across projects.
- **Health checks and auto-recovery** -- `doctor` and `validate` commands detect drift and repair common issues automatically.
- **CLI lifecycle management** -- create, list, inspect, delete, and upgrade sandboxes from a single tool.

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
# 1. Create the default configuration file
sandboxctl config init

# 2. Edit the config with your identity and preferences
#    (see Configuration section below)
$EDITOR "$(sandboxctl config path)"

# 3. Create a new profile skeleton
sandboxctl init my-project

# 4. Edit the profile to add repos, extensions, and settings
$EDITOR ~/.config/sandboxctl/profiles/my-project.toml

# 5. Create a sandbox from the profile (planned)
sandboxctl create my-project

# 6. Open the sandbox in VS Code (planned)
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
# vertex_project_id = ""
# vertex_region = "global"

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

| Command | Description |
|---|---|
| `sandboxctl --version` | Show version and exit |
| `sandboxctl list` | List profiles and running sandboxes |
| `sandboxctl status` | Show gateway and sandbox status |
| `sandboxctl init <name>` | Create a new profile skeleton |
| `sandboxctl delete <name>` | Delete a sandbox |
| `sandboxctl validate <name>` | Run validation tests inside a sandbox |
| `sandboxctl doctor <name>` | Diagnose and recover sandbox issues (`--no-recover` to skip recovery) |
| `sandboxctl upgrade` | Upgrade OpenShell to latest version |
| `sandboxctl config init` | Create default configuration file |
| `sandboxctl config show` | Show current configuration |
| `sandboxctl config path` | Print config file path |
| `sandboxctl create <name>` | Create a sandbox from a profile (planned) |
| `sandboxctl open <name>` | Open a sandbox in VS Code (planned) |
| `sandboxctl setup` | Initial setup and credential configuration (planned) |
| `sandboxctl restart <name>` | Restart a sandbox (planned) |

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
