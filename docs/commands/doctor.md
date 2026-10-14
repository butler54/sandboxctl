# sandboxctl doctor

Diagnose and recover sandbox issues.

## Usage

```
sandboxctl doctor NAME [OPTIONS]
```

## Arguments

| Name | Description | Required |
|------|-------------|----------|
| `NAME` | Sandbox name to diagnose. | Yes |

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--fix` | Re-inject credentials and hot-reload drifted network policy. Filesystem-policy drift requires `sandboxctl restart`. | `False` |
| `--no-recover` | Skip auto-recovery, diagnose only. | `False` |
| `--all` | Check or fix every running sandbox. | `False` |

## Policy Drift

For a sandbox whose name matches a profile, doctor compares the running base
policy with the rendered profile policy. `doctor --fix` reloads network-only
drift. Filesystem or Landlock policy drift cannot be hot-reloaded and is
reported with the required restart command instead.

## Egress diagnostics

For every running sandbox, doctor also runs a static egress correlation: it
resolves the sandbox's real (kernel-resolved, symlink-followed) executables
inside the sandbox and compares them against the binary allowlists in the
active base policy. Findings come in two forms:

- `! executable <path> (<name>) matches no allowlist in any network rule` —
  a **warning**: under the default-deny egress posture, every connection from
  that executable is denied. This is the check that surfaces a mismatch
  between the image's binary layout and the policy's allowlist paths.
- `i allowlist entry <path> in rule '<rule>' matches no executable found in
  this sandbox` — an **info** hint that the allowlist literal is stale
  (e.g. a layout from an older image generation). Glob entries ending in
  `/**` are never flagged, since they may legitimately cover paths doctor
  cannot enumerate.

If upstream exposes gateway logs (`openshell logs`), the tail is printed
verbatim under an `observed` label. Today upstream only logs
`DENIED staged connection` without destination or executable, and the log
subcommand may not exist at all — in that case doctor reports an
`upstream-limited` info note instead of fabricating deny entries, so the
observed-deny surface never invents data. The **static** findings above are
inference from policy correlation, not from observed traffic.

## Status

Implemented.
