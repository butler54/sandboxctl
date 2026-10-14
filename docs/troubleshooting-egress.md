# Troubleshooting Sandbox Egress Failures

When a tool inside a sandbox cannot reach a network endpoint, the failure
almost always comes from one of three layers: the network **policy** (which
hosts/ports are allowed), the **executable identity** (which binaries may use a
rule), or **provider composition** (which `_provider_*` rules were merged into
the sandbox's effective policy). This guide walks through diagnosing each layer
with sandboxctl commands.

## Run the full diagnostic

```bash
sandboxctl doctor <sandbox>
```

Doctor reports, in order: host credentials, sandbox health, policy drift, and
an **Egress Diagnostics** section.

### Reading the egress findings

Findings come in two clearly-distinguished flavors:

- **Static findings** (`!` warning / `i` info) — computed by correlating the
  sandbox's real executables (resolved with `command -v` + `readlink -f`)
  against the active policy's binary allowlists:
  - `binary-not-covered` — an executable (e.g.
    `/usr/lib/node_modules/@opencode/cli/bin/opencode.exe` on the v2 sandbox
    image) matches **no** allowlist entry, so every connection it makes hits
    the default deny-all posture. This usually means the policy allowlisted a
    per-layout path from a different image generation. Newer sandboxctl
    versions emit package-root globs instead (`/usr/lib/node_modules/@opencode/**`,
    `/usr/lib/node_modules/opencode-ai/**`); recreate the sandbox or run
    `sandboxctl policy sync` after updating its profile's policy.
  - `allowlist-unmatched` *(info)* — a literal allowlist path matches nothing
    installed in the sandbox; a stale literal from an older image layout. It
    is harmless when a covering glob is also present, but worth pruning from
    the profile's policy YAML.
  - `upstream-limited` *(info)* — sandboxctl could not resolve the sandbox's
    executables or policy (gateway unreachable, exec failed). The check is
    **unknown**, not clean.
- **Observed denies** — a verbatim tail of upstream logs, labeled *observed*.
  Today's OpenShell supervisor log carries no destination or executable on
  denies, so sandboxctl states that limitation explicitly rather than guessing.

## Policy drift after profile edits

Sandboxes keep their create-time policy. If you edited a profile's
`policy.yaml`:

```bash
sandboxctl list                    # Policy column shows current / network-drift / filesystem-drift / unknown
sandboxctl policy show <sandbox>   # status + added/removed/changed rule summary
sandboxctl policy sync <sandbox> --dry-run   # preview, no mutation
sandboxctl policy sync <sandbox>   # hot-reload (verified against the live policy)
```

Filesystem-policy changes cannot be reloaded at runtime — `sync` refuses and
tells you to recreate with `sandboxctl restart <sandbox>`.

## Provider egress (custom OpenAI-compatible endpoints)

Every `[opencode.custom_providers.<id>]` entry is registered with OpenShell
(profile written to `~/.config/sandboxctl/providers/<id>.yaml`, imported, then
attached at create) so a `_provider_<id>` egress rule is composed
automatically. If the credential is missing, `sandboxctl create` **fails
closed** with the exact keychain service name to store; a selected provider is
never silently unprovisioned.

To recover a provider on an existing sandbox:

```bash
sandboxctl setup          # re-assert provider profile + registration
sandboxctl doctor <sandbox> --fix   # re-inject env vars and sync policy drift
```

## The legacy repair script

For profiles still carrying legacy OpenCode paths, dry-run the migration
helper and check its output before writing:

```bash
python scripts/apply_opencode_policy.py --profiles-dir ~/.config/sandboxctl/profiles
python scripts/apply_opencode_policy.py --profiles-dir ~/.config/sandboxctl/profiles --write
```

It backfills the compiled-binary globs on any rule that authorizes an OpenCode
launcher, leaves a `.bak` copy of every file it modifies, and skips policies
using `!include` so hand-maintained structure is never flattened.
