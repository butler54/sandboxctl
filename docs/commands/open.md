# sandboxctl open

Open an existing sandbox. By default this launches OpenCode in interactive
mode, resuming the most recent session in the sandbox's default workspace.

## Usage

```
sandboxctl open NAME [--new] [--shell | --code-only | --claude-only | --code | --opencode-server]
```

## Arguments

| Name | Description | Required |
|------|-------------|----------|
| `NAME` | Sandbox name | Yes |

## Options

| Flag | Description |
|------|-------------|
| `--new` | Start a fresh agent session instead of resuming the most recent one |
| `--shell` | Open an interactive shell |
| `--code-only` | Open VS Code only |
| `--claude-only` | Open Claude Code (legacy) |
| `--code` | Open both VS Code and OpenCode |
| `--opencode-server` | Start the OpenCode server and set up an SSH port-forward |

## Session behavior

- **Default** (`sandboxctl open NAME`): OpenCode resumes the most recent
  session in the sandbox's default workspace (`opencode -c`). If there is no
  prior session (for example on a freshly created sandbox), a new session
  starts automatically. Claude Code mode behaves the same way
  (`claude --continue`, falling back to a fresh session).
- **`--new`** (`sandboxctl open NAME --new`): a fresh session starts and the
  most recent session is left untouched for later resumption. With
  `--claude-only` this skips the resume attempt; with the other modes
  (`--shell`, `--code-only`, `--code`, `--opencode-server`) the flag has no
  effect.
- **Failure fallback**: if OpenCode (or Claude Code) cannot start, the
  command falls back to an interactive shell and prints the command to run
  manually inside the sandbox.

## Examples

```bash
# Resume where you left off (default)
sandboxctl open my-project

# Start a fresh session, leaving existing sessions untouched
sandboxctl open my-project --new

# Open an interactive shell instead
sandboxctl open my-project --shell
```

## See also

- `sandboxctl create` — creating a sandbox auto-opens it with the default
  behavior above
- [Egress troubleshooting](doctor.md) — `open` prints a warning when the
  sandbox's policy has drifted from its profile; run
  `sandboxctl policy sync NAME` to reconcile
