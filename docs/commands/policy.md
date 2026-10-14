# sandboxctl policy

Show and reconcile sandbox policies.

A sandbox keeps the policy it was created with until it is reloaded or
recreated. When a profile's `policy.yaml` is edited after the sandbox was
created, the sandbox's active policy **drifts** from the profile. The `policy`
command group makes that drift visible and reconciles network-only drift
without recreating the sandbox.

## Usage

```
sandboxctl policy show NAME [OPTIONS]
sandboxctl policy sync NAME [OPTIONS]
```

## sandboxctl policy show

Print the drift status of a sandbox: `current`, `network-drift`,
`filesystem-drift`, or `unknown`, with details. For network drift, a compact
added / removed / changed summary of the differing network rules is included.
`show` is read-only and always exits 0.

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--profile, -p` | Profile to compare against (overrides the recorded association). | Recorded association, else the profile matching the sandbox name |

## sandboxctl policy sync

Reload a sandbox's drifted **network** policy from its profile (hot reload, no
recreation). Sync is opt-in: it asks for confirmation before mutating unless
`--yes` is given. Use `--dry-run` to print the pending rule changes without
applying anything.

Filesystem, `filesystem_policy`, and `landlock` drift cannot be hot-reloaded;
sync refuses and tells you to recreate the sandbox with
`sandboxctl restart NAME`.

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--profile, -p` | Profile to reconcile from. Recorded as the sandbox's association so future `open`/`sync` calls don't need the flag. | Recorded association, else the profile matching the sandbox name |
| `--dry-run` | Show the pending network rule changes without mutating. | `False` |
| `--yes, -y` | Skip the confirmation prompt. | `False` |

## Sandbox → profile associations

`sandboxctl create` records which profile each sandbox was created from in
`<config-dir>/sandboxes.json`, so sandboxes created with a custom
`--name` are still compared against the right profile. `sandboxctl delete`
removes the record. `policy show`, `policy sync`, `open`, `list`, and `doctor`
all resolve the profile through this store, falling back to the profile whose
name matches the sandbox.

## Drift visibility elsewhere

- `sandboxctl open NAME` prints a WARNING when the sandbox has drifted.
- `sandboxctl list` shows a Policy column per running sandbox.
- `sandboxctl doctor NAME` reports drift and `doctor --fix` hot-reloads
  network-only drift (see [doctor](doctor.md)).

## Status

Implemented.
