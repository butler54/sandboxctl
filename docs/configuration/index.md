# Configuration

sandboxctl uses an [XDG-compliant](https://specifications.freedesktop.org/basedir-spec/latest/)
configuration directory with TOML files for both global settings and per-profile
overrides.

## Config Location

The configuration directory defaults to `~/.config/sandboxctl/`. Override it by
setting `XDG_CONFIG_HOME`:

```
~/.config/sandboxctl/          # default
$XDG_CONFIG_HOME/sandboxctl/   # when XDG_CONFIG_HOME is set
```

The directory contains:

```
~/.config/sandboxctl/
  config.toml          # global settings
  profiles/            # per-sandbox profile TOML files
    ai-dev.toml
    dev.toml
```

## Config File

The global config file lives at `{config_dir}/config.toml`. Generate it with:

```bash
sandboxctl config init
```

Full template with all available options:

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

### Section Reference

| Section | Key | Default | Description |
|---|---|---|---|
| `[identity]` | `user_name` | `""` | Git author name used inside sandboxes |
| | `user_email` | `""` | Git author email used inside sandboxes |
| `[defaults]` | `model` | `"claude-sonnet-4-20250514"` | Claude model for new sandboxes |
| | `theme` | `"dark"` | VS Code color theme |
| | `zoom` | `-1` | VS Code zoom level |
| `[providers]` | `provider` | `"anthropic"` | Claude API provider (`anthropic` or `vertex`) |
| | `anthropic_api_key` | `""` | API key for direct Anthropic access |
| | `vertex_project_id` | `""` | Google Cloud project (vertex only) |
| | `vertex_region` | `"global"` | Vertex AI region (vertex only) |
| `[paths]` | `ssh_key` | `"~/.ssh/sandboxctl_ed25519"` | Path to SSH private key |
| | `ca_bundle` | `None` | Path to custom CA certificate bundle |
| `[keychain]` | `github_service` | `"sandboxctl-github-token"` | Keychain service name for GitHub token |
| | `gitlab_service` | `"sandboxctl-gitlab-token"` | Keychain service name for GitLab token |

!!! note "Tilde expansion"
    Paths containing `~` are automatically expanded to your home directory at
    load time. Both `ssh_key` and `ca_bundle` support this.

## Environment Variables

Every config value can be set via environment variables using the `SANDBOXCTL_`
prefix. Nested sections use `__` (double underscore) as a delimiter.

### Naming Convention

The pattern is `SANDBOXCTL_<SECTION>__<KEY>`:

```bash
# [identity] section
export SANDBOXCTL_IDENTITY__USER_NAME="Your Name"
export SANDBOXCTL_IDENTITY__USER_EMAIL="you@example.com"

# [defaults] section
export SANDBOXCTL_DEFAULTS__MODEL="claude-sonnet-4-20250514"
export SANDBOXCTL_DEFAULTS__THEME="dark"

# [providers] section
export SANDBOXCTL_PROVIDERS__VERTEX_PROJECT_ID="my-gcp-project"

# [paths] section
export SANDBOXCTL_PATHS__SSH_KEY="~/.ssh/id_ed25519"
```

### Runtime Overrides

Some `SANDBOXCTL_` environment variables are runtime switches rather than
config-file values — they are not mapped into `config.toml` sections.

| Variable | Values | Effect |
|----------|--------|--------|
| `SANDBOXCTL_OPENSHELL_BACKEND` | `auto` (default), `cli` | Selects the backend for non-interactive gateway operations (script execution, delete). `auto` uses the [openshell Python SDK](https://pypi.org/project/openshell/) when installed (enable with `pip install sandboxctl[sdk]`), falling back to the `openshell` CLI; `cli` always uses the CLI — useful for diagnostics and rollback. The choice is made once per invocation. |

See the [installation section](../../README.md#optional-openshell-sdk-backend) for
the `sdk` extra.

## Gateways

Multiple openshell gateways are supported (for example, a local gateway and
an openshell instance on a Kubernetes cluster). Gateways are **referenced by
name**: each entry points at a gateway registered with the openshell CLI
(`openshell` owns endpoints, TLS, and authentication under
`~/.config/openshell/gateways/<name>/`), so sandboxctl never stores
credential material.

```toml
[gateways.k8s-prod]        # key = the name you use in profiles
# openshell_name = "k8s-prod"   # optional: the registered name, if different
kubernetes = true          # optional type hint: enables cluster-access checks in doctor
```

- **Default**: with no `[gateways]` section and no per-profile `gateway`
  key, every operation targets the CLI's currently active gateway — exactly
  the previous behavior.
- **Routing**: a profile's `gateway = "<key>"` records a sandbox→gateway
  association at creation; every later operation (open, delete, restart,
  status, doctor, connect) targets that gateway regardless of the CLI's
  active gateway. A missing or unreachable gateway is a loud error —
  operations never silently fall back to another gateway.
- **Visibility**: `sandboxctl list`, `status`, and `doctor` cover all
  configured gateways plus the active one; each sandbox row identifies its
  gateway, and unreachable gateways are reported rather than omitted.
- **Secrets**: gateway entries hold only names and a type hint. Provider
  credentials continue to flow through the secure credential store.

### Precedence

Configuration sources are loaded in this order, with earlier sources taking
priority:

1. **Init settings** -- code defaults (lowest priority)
2. **Environment variables** -- `SANDBOXCTL_*` vars override defaults
3. **TOML config file** -- `config.toml` values override both

!!! warning "Precedence order"
    The TOML file has the **highest** priority. If a value is set in both an
    environment variable and `config.toml`, the TOML file wins. To use
    environment variables as overrides, leave the corresponding key commented
    out in `config.toml`.

## Custom OpenAI-compatible providers

The `[opencode]` section can register generic OpenAI-compatible inference
endpoints as first-class providers. Each entry is registered with OpenShell
(profile imported, provider created, endpoint enforced) and becomes a
selectable provider in OpenCode's model picker.

```toml
[opencode]
# `matilda = true` is a shorthand for the built-in matilda declaration below.
matilda = true

[opencode.custom_providers.my-llm]
base_url = "https://host.example.com/api/v1"   # required, HTTPS only
display_name = "My LLM"                        # optional, defaults to the id
models = ["model-id"]                          # optional model allowlist
api_key_env = "MY_LLM_API_KEY"                 # optional, defaults to MY_LLM_API_KEY style
keychain_service = "sandboxctl-my-llm-api-key" # optional, default shown
```

| Key | Default | Description |
|---|---|---|
| `base_url` | *(required)* | Endpoint base URL. HTTPS only — configuration is rejected otherwise |
| `display_name` | provider id | Friendly name shown in OpenCode's model picker |
| `models` | `[]` | Optional allowlist of model IDs selectable as `<provider-id>/<model-id>` |
| `api_key_env` | `<ID>_API_KEY` (uppercased id, symbols → `_`) | Env var exported into the sandbox holding the API key |
| `keychain_service` | `sandboxctl-<id>-api-key` | Credential-store service name |

**Credential storage.** The API key is read from the host credential store
(macOS Keychain; `secret-tool` on Linux) before sandbox creation. Store it
with the corresponding CLI, for example on Linux:

```bash
secret-tool store --label='sandboxctl my-llm' \
  service sandboxctl-my-llm-api-key account "$USER"
```

**Fail closed.** Creating a sandbox fails with an error when a configured
custom provider's credential is missing from the credential store — a
selected provider is never silently skipped. Run `sandboxctl setup` (which
registers any providers whose credentials exist) and `sandboxctl doctor`
reports missing entries under *Custom providers*.

## Config Commands

| Command | Description |
|---|---|
| `sandboxctl config init` | Create a default `config.toml` in the config directory |
| `sandboxctl config show` | Display current resolved configuration values |
| `sandboxctl config path` | Print the path to `config.toml` |
