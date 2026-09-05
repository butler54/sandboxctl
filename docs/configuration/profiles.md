# Profiles

Profiles define per-sandbox settings -- which repos to clone, what VS Code theme
to apply, SSH hosts to configure, and which Claude model to use.

## Overview

Each profile is a TOML file stored in the profiles directory:

```
~/.config/sandboxctl/profiles/
  ai-dev.toml
  dev.toml
  minimal.toml
```

The profiles directory lives at `{config_dir}/profiles/` by default. This
resolves to `~/.config/sandboxctl/profiles/` unless `XDG_CONFIG_HOME` is set.

Use a profile when creating a sandbox:

```bash
sandboxctl create --profile ai-dev
```

## Profile Structure

A profile has four sections: `[sandbox]`, `[workspace]`, `[repos]`, and `[ssh]`.
All sections and keys are optional.

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

### Section Reference

#### `[sandbox]`

| Key | Default | Description |
|---|---|---|
| `containerfile` | `"Containerfile"` | Path to a custom Containerfile for the sandbox image |
| `policy` | `"policy.yaml"` | Path to a custom sandbox policy file |
| `default_repo` | `""` | Repository directory to `cd` into when Claude Code starts |
| `model` | `""` | Claude model override; inherits from `[defaults].model` in `config.toml` if empty |

#### `[workspace]`

| Key | Default | Description |
|---|---|---|
| `theme` | `""` | VS Code color theme name |
| `zoom` | `-1` | VS Code editor zoom level |

#### `[repos]`

The `[repos]` section maps Git hosting providers to lists of repositories to
clone into the sandbox.

```toml
[repos]
github = [
    "owner/repo-one",
    "owner/repo-two",
]

"gitlab.com" = [
    "group/project",
]

"gitlab.internal.example.com" = [
    "team/private-project",
]
```

- Use `github` (or `github.com`) for GitHub repositories.
- Use the GitLab server hostname as the key for GitLab repositories.
- Private GitLab instances are supported by using their hostname directly.

#### `[ssh]`

Configure SSH host access for the sandbox. Each key is a hostname, with
connection parameters as values.

```toml
[ssh]
"bastion.example.com" = { user = "admin" }
"node01.example.com" = { user = "root", proxy_host = "bastion.example.com" }
```

| Key | Default | Description |
|---|---|---|
| `user` | `"root"` | SSH username |
| `proxy_host` | `""` | Jump host for ProxyJump connections |

#### `skills` and `agents`

By default every skill under `~/.claude/skills` and every agent under
`~/.claude/agents` is staged into the sandbox. Set these top-level allowlists to
stage only the named entries — useful for narrowly-scoped profiles that don't
need your whole skill/agent library. An empty list (the default) stages
everything.

```toml
# Stage only these skills/agents (by directory or file name); empty = stage all
skills = ["general-purpose", "container-hardening"]
agents = ["code-reviewer.md"]
```

OpenCode custom agents are staged separately: every entry in
`~/.config/opencode/agents/` (or the legacy singular `agent/` directory) is
copied to the same location in the sandbox. Configure their model, permissions,
and instructions in the OpenCode agent file; sandboxctl preserves those files
without transformation.

### Shared Policy Fragments

Policies may reuse YAML maps with a `!include` tag. Include paths are relative
to the file declaring them and must remain under the profiles directory.

```yaml
network_policies:
  opencode: !include ../_shared/opencode.yaml
```

When an included or local policy allowlists `/usr/local/bin/opencode` or
`/usr/bin/opencode`, sandboxctl also adds OpenCode's kernel-resolved compiled
binary path. This works around OpenShell deployments that cannot resolve the
launcher symlink from the sandbox filesystem.

#### `mlflow`

Whether to wire this sandbox up to MLflow tracking. Defaults to `true`. When
enabled, `sandboxctl create` validates (and, in managed mode, starts) the MLflow
server and injects `MLFLOW_TRACKING_URI` plus Claude Code tracing env vars into
the sandbox. Set to `false` to opt a profile out entirely. See the
[`mlflow` command](../commands/mlflow.md) and the `[mlflow]` section of
`config.toml`.

```toml
mlflow = true
```

#### `[gsd]`

Opt into the GSD runtime for this profile (off by default). When `enabled`, the
GSD runtime is installed in the sandbox if missing, and `model_profile` (when
set) is written to `/sandbox/.gsd/defaults.json`, overriding the image default.

```toml
[gsd]
enabled = true
model_profile = "balanced"   # quality | balanced | budget | adaptive | inherit
```

| Key | Default | Description |
|---|---|---|
| `enabled` | `false` | Install the GSD runtime into the sandbox |
| `model_profile` | `""` | GSD model profile written to `defaults.json` |

## Creating a Profile

Generate a new profile skeleton:

```bash
sandboxctl init my-project
```

This creates `~/.config/sandboxctl/profiles/my-project.toml` with all sections
and commented-out options. Edit the file to fill in your project details.

!!! note
    `sandboxctl init` will refuse to overwrite an existing profile. Delete or
    rename the existing file first if you need to regenerate it.

## Example Profiles

sandboxctl ships with three example profiles in the `examples/profiles/`
directory.

### ai-dev.toml

AI-assisted development sandbox with Vertex AI provider support.

```toml
# AI-assisted development sandbox profile
# Includes Claude Code with Vertex AI provider
# Usage: sandboxctl create --profile ai-dev

[sandbox]
# default_repo = "my-ai-project"
# model = "claude-sonnet-4-20250514"

[workspace]
theme = "Default Dark Modern"
zoom = -1

[repos]
github = [
    # "owner/ai-project",
]
```

### dev.toml

General-purpose development sandbox.

```toml
# General development sandbox profile
# Usage: sandboxctl create --profile dev

[sandbox]
# default_repo = "my-project"

[workspace]
theme = "Default Dark Modern"
zoom = -1

[repos]
github = [
    # "owner/repo-name",
]
```

### minimal.toml

Bare-minimum profile with empty sections -- no repos, no extras.

```toml
# Minimal sandbox profile — no repos, no extras
# Usage: sandboxctl create --profile minimal

[sandbox]

[workspace]

[repos]
```

!!! tip
    Copy an example profile to your profiles directory and customize it:

    ```bash
    cp examples/profiles/dev.toml ~/.config/sandboxctl/profiles/my-project.toml
    ```
