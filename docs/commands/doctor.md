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

## Status

Implemented.
