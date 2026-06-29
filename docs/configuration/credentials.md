# Credentials

sandboxctl stores Git provider tokens (GitHub, GitLab) using a platform-native
credential backend. The backend is auto-detected at runtime based on your
operating system and available tooling.

## Backend Detection

sandboxctl selects a credential backend using the following logic:

1. **macOS** -- If `sys.platform == "darwin"` and the `security` CLI is available,
   use the macOS Keychain.
2. **Linux** -- If `sys.platform == "linux"` and the `secret-tool` CLI is
   available, use libsecret via `secret-tool`.
3. **Fallback** -- If neither platform-native backend is available, fall back to
   environment variables.

| Platform | Backend | Requirement | Persistence |
|---|---|---|---|
| macOS | macOS Keychain | `security` CLI (ships with macOS) | Yes |
| Linux | secret-tool (libsecret) | `secret-tool` package installed | Yes |
| Any | environment variables | None | No (read-only) |

!!! warning
    The environment variable backend **cannot persist** credentials. Calling
    `store()` on it raises a `RuntimeError`. You must set the environment
    variables in your shell profile manually.

## Storing Credentials

### GitHub Token

Store a GitHub personal access token:

**macOS (Keychain):**

```bash
security add-generic-password \
  -s sandboxctl-github-token \
  -a default \
  -w "ghp_your_token_here"
```

**Linux (secret-tool):**

```bash
echo -n "ghp_your_token_here" | secret-tool store \
  --label "sandboxctl-github-token/default" \
  service sandboxctl-github-token \
  account default
```

**Environment variable fallback:**

```bash
export SANDBOXCTL_GITHUB_TOKEN="ghp_your_token_here"
```

### GitLab Token

Store a GitLab personal access token:

**macOS (Keychain):**

```bash
security add-generic-password \
  -s sandboxctl-gitlab-token \
  -a default \
  -w "glpat-your_token_here"
```

**Linux (secret-tool):**

```bash
echo -n "glpat-your_token_here" | secret-tool store \
  --label "sandboxctl-gitlab-token/default" \
  service sandboxctl-gitlab-token \
  account default
```

**Environment variable fallback:**

```bash
export SANDBOXCTL_GITLAB_TOKEN="glpat-your_token_here"
```

### Private GitLab Instances

For private GitLab servers, store a server-specific credential using the service
name pattern `sandboxctl-gitlab-{server}`, where dots in the hostname are
replaced with hyphens:

```bash
# For gitlab.internal.example.com
export SANDBOXCTL_GITLAB_GITLAB_INTERNAL_EXAMPLE_COM="glpat-your_token_here"
```

If no server-specific credential is found, sandboxctl falls back to the generic
`sandboxctl-gitlab-token` credential.

## Scoped Git Tokens

When a profile lists repositories, sandboxctl resolves credentials per provider
using the `resolve_token_strategy()` function.

### GitHub

For repositories listed under `github` or `github.com` in a profile's `[repos]`
section, sandboxctl looks up the credential stored under the
`sandboxctl-github-token` service.

The `GitHubTokenManager` supports fine-grained personal access tokens (PATs)
via the `gh` CLI API. Fine-grained PATs can provide repo-level read/write access
for listed repositories and read-only access elsewhere.

### GitLab

For GitLab repositories, sandboxctl first tries a server-specific credential:

```
sandboxctl-gitlab-{server}
```

where `{server}` is the GitLab hostname with dots replaced by hyphens (e.g.,
`sandboxctl-gitlab-gitlab-com` for `gitlab.com`).

If no server-specific credential is found, it falls back to the generic
`sandboxctl-gitlab-token` credential.

The `GitLabTokenManager` supports both `gitlab.com` and private GitLab instances
with a configurable `server` parameter. It uses project-level or group-level
access tokens via the GitLab REST API.

### Token Resolution Summary

| Profile `[repos]` key | Credential service lookup | Fallback |
|---|---|---|
| `github` or `github.com` | `sandboxctl-github-token` | None |
| `gitlab.com` | `sandboxctl-gitlab-gitlab-com` | `sandboxctl-gitlab-token` |
| `gitlab.example.com` | `sandboxctl-gitlab-gitlab-example-com` | `sandboxctl-gitlab-token` |

Resolved credentials are returned as `ScopedToken` objects containing the
provider name, token value, list of repositories, and a scope description.

## Environment Variable Fallback

When the platform-native keychain is unavailable, the `EnvVarBackend` reads
credentials from environment variables. It converts the service name to an
environment variable key using this rule:

1. Convert to uppercase
2. Replace hyphens (`-`) with underscores (`_`)

| Service Name | Environment Variable |
|---|---|
| `sandboxctl-github-token` | `SANDBOXCTL_GITHUB_TOKEN` |
| `sandboxctl-gitlab-token` | `SANDBOXCTL_GITLAB_TOKEN` |
| `sandboxctl-gitlab-gitlab-com` | `SANDBOXCTL_GITLAB_GITLAB_COM` |

!!! note
    The environment variable backend is read-only at runtime. To "store" a
    credential, add the `export` statement to your shell profile
    (`~/.bashrc`, `~/.zshrc`, etc.) and restart your shell.

### Keychain Service Names

The default service names used for credential lookup are configured in the
`[keychain]` section of `config.toml`:

```toml
[keychain]
github_service = "sandboxctl-github-token"
gitlab_service = "sandboxctl-gitlab-token"
```

These defaults can be overridden if your organization uses different naming
conventions.
