# Skill Authoring Guide

## Overview

Sandboxctl skills are Claude Code skill packages that provide domain-specific instructions, reference data, and lifecycle hooks. Skills are distributed as git repositories with a structured directory layout and YAML frontmatter manifest.

All skills installed in `~/.claude/skills/` are automatically staged into every sandbox at creation time. Skills provide Claude with additional context and automation capabilities for specialized domains (debugging, linting, security analysis, etc.).

## Quick Start

A minimal skill has just one file:

```
my-skill/
└── SKILL.md
```

Install it:

```bash
sandboxctl skill install https://github.com/user/my-skill.git
```

Claude will read `SKILL.md` in every sandbox you create. That's it.

## SKILL.md Specification

`SKILL.md` is a markdown file with YAML frontmatter between `---` delimiters. The frontmatter is the skill's manifest.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Skill identifier (alphanumeric, dots, hyphens, underscores). Must be unique. |
| `description` | string | One-line summary of what the skill does. |

### Optional Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `version` | string | Semantic version (semver format). | `"1.2.3"` |
| `author` | string | Skill author name or organization. | `"Red Hat Engineering"` |
| `license` | string | License identifier. | `"MIT"`, `"Apache-2.0"` |
| `tags` | list of strings | Categorization tags for discovery. | `["networking", "debug"]` |
| `requires` | string | Semver range constraint on sandboxctl version. | `">=1.8.0"` |
| `dependencies` | list of strings | Other skill names that should be installed. | `["skill-a", "skill-b"]` |
| `hooks` | object | Lifecycle hooks (see Hooks section). | `{on_create: "install.sh"}` |

### Example Frontmatter

```yaml
---
name: sandbox-network-debug
description: Diagnose and fix OpenShell sandbox networking failures — proxy 403, TLS certs, SSRF denials, DNS, gateway issues
version: 1.0.0
author: Red Hat Engineering
license: Apache-2.0
tags:
  - networking
  - debug
  - diagnostics
requires: ">=1.8.0"
dependencies:
  - sandbox-policy-lint
hooks:
  on_create: "bash hooks/setup.sh"
  on_delete: "bash hooks/cleanup.sh"
---
```

### Markdown Body

Everything after the second `---` delimiter is the skill's instructions for Claude Code. This is what Claude reads and follows when working in a sandbox. Write it as documentation for Claude, not for humans:

- Explain **when** to use the skill (trigger patterns, error messages, user requests)
- Provide **step-by-step instructions** with exact commands to run
- Include **decision trees** for diagnosis (if X, do Y; else do Z)
- Reference supporting data files in `references/` using `@references/file.yaml` notation
- Document **important context** Claude needs to avoid common mistakes

## Directory Layout

```
skill-name/
├── SKILL.md                  # Required: frontmatter + instructions
├── references/               # Optional: supporting data files
│   ├── data.yaml
│   ├── config.json
│   └── examples/
│       └── sample.sh
└── hooks/                    # Optional: hook scripts
    ├── setup.sh
    └── cleanup.sh
```

- **Required:** `SKILL.md` is the only required file.
- **Optional:** `references/` contains YAML, JSON, shell scripts, or any data files referenced from `SKILL.md`. Claude can read these for structured data (e.g., lookup tables, configuration examples, diagnostic commands).
- **Optional:** `hooks/` contains shell scripts for lifecycle hooks. If hooks are simple one-liners, specify them directly in frontmatter. Use `hooks/` for complex multi-step scripts.

No other files are required. Most skills are just `SKILL.md` + `references/`.

## Hooks

Hooks are shell commands run at specific lifecycle points. Both are optional.

### on_create

**When:** After skill files are staged into a new sandbox (runs inside the sandbox).

**Use for:**
- Installing tools (`apt-get install`, `pip install`)
- Setting up environment variables
- Creating configuration files

**Example:**
```yaml
hooks:
  on_create: "pip install --user mydiagtool"
```

### on_delete

**When:** Before skill removal from `~/.claude/skills/` (runs in the skill directory on the host).

**Use for:**
- Cleanup tasks
- Removing global configuration

**Example:**
```yaml
hooks:
  on_delete: "rm -f ~/.config/mytool/config.json"
```

### Important Notes

- Hooks run with user permissions (not root).
- `on_create` runs inside the sandbox after skill files are copied. It cannot modify the host.
- `on_delete` runs on the host before the skill directory is deleted.
- If a hook fails, skill installation/removal continues anyway (hooks are best-effort).
- Most skills are **passive** (just instructions + reference data) — no hooks needed.

## CLI Commands

### Install

```bash
sandboxctl skill install <git-url> [--force]
```

Clone a skill repository and install it to `~/.claude/skills/<name>`. The skill name comes from the frontmatter `name` field.

- Use `--force` to overwrite an existing skill.
- If `dependencies` are listed, you'll see warnings for any that aren't installed (install them manually).

### Remove

```bash
sandboxctl skill remove <name>
```

Delete a skill from `~/.claude/skills/`. You'll be prompted for confirmation. If the skill has an `on_delete` hook, it runs before removal.

### List

```bash
sandboxctl skill list
```

Show all installed skills in a table with name, version, and description.

### Update

```bash
sandboxctl skill update <name>
```

Run `git pull` in the skill's directory to fetch updates from the remote repository.

**Requirement:** The skill must have been installed via `sandboxctl skill install` (not copied manually). Only git-cloned skills can be updated.

### Validate

```bash
sandboxctl skill validate <path>
```

Check a skill directory against the packaging spec before installing:

- `SKILL.md` exists
- Frontmatter is valid YAML with required fields (`name`, `description`)
- `version` is semver format (if provided)
- `references/` exists if referenced in `SKILL.md`

Use this to lint skills during development.

## Example: Minimal Skill

The simplest skill is just instructions with no hooks or references.

**File: `simple-greeter/SKILL.md`**

```markdown
---
name: simple-greeter
description: Greet the user when they open a sandbox
---

# simple-greeter

When the user opens a sandbox, greet them with a welcome message.

## Instructions

If this is the first command in a new sandbox session, print:

```
Welcome to your sandbox! Type 'help' for common commands.
```

Then continue with the user's request.
```

Install it:

```bash
sandboxctl skill install https://github.com/user/simple-greeter.git
```

Claude now greets users in every sandbox.

## Example: Full-Featured Skill

This skill shows all features: frontmatter with all fields, references directory, and hooks.

**File: `network-debugger/SKILL.md`**

```yaml
---
name: network-debugger
description: Diagnose network failures with a decision tree and command reference
version: 1.0.0
author: Example Corp
license: MIT
tags:
  - networking
  - diagnostics
requires: ">=1.8.0"
dependencies:
  - policy-linter
hooks:
  on_create: "bash hooks/install-tools.sh"
---

# network-debugger

Diagnose sandbox networking failures using a structured decision tree.

## When to use

- Connection timeouts
- TLS certificate errors
- Proxy 403 denials

## Instructions

### Step 1: Identify error type

Read the error message. Match it against @references/error-patterns.yaml to determine the failure category.

### Step 2: Run diagnostic commands

For each category, run commands from @references/diagnostic-commands.yaml in order until one succeeds.

### Step 3: Apply fix

Use the fix script from @references/fixes/ corresponding to the diagnostic result.

## Important context

- Always run diagnostics before applying fixes (read-only first).
- TLS errors require CA bundle rebuild — no hot-reload.
```

**File: `network-debugger/references/error-patterns.yaml`**

```yaml
tls_errors:
  - "server certificate verification failed"
  - "certificate verify failed"
proxy_denials:
  - "403 Forbidden"
  - "Connection to proxy refused"
timeouts:
  - "Connection timed out"
  - "Operation timed out"
```

**File: `network-debugger/references/diagnostic-commands.yaml`**

```yaml
tls_check:
  command: "openssl s_client -connect {host}:443 -CAfile /sandbox/.ca-bundle.pem"
  success_pattern: "Verify return code: 0"
proxy_check:
  command: "curl -I -x http://10.200.0.1:3128 {url}"
  success_pattern: "HTTP/1.1 200"
```

**File: `network-debugger/hooks/install-tools.sh`**

```bash
#!/bin/bash
apt-get update -qq
apt-get install -y openssl curl netcat-openbsd
```

Install it:

```bash
sandboxctl skill install https://github.com/user/network-debugger.git
```

The hook runs automatically in new sandboxes. Claude references the YAML data files for structured diagnostics.

## Dependencies

Dependencies are **informational only**. If a skill lists dependencies in frontmatter:

```yaml
dependencies:
  - skill-a
  - skill-b
```

`sandboxctl skill install` will warn if those dependencies aren't installed, but it won't auto-install them. You must install dependencies manually:

```bash
sandboxctl skill install https://github.com/user/skill-a.git
sandboxctl skill install https://github.com/user/skill-b.git
sandboxctl skill install https://github.com/user/my-skill.git
```

**Why not auto-install?** Dependency resolution (version conflicts, circular deps, transitive deps) is complex. Sandboxctl keeps it simple: warn and let the user decide.

## Skill Scope

All skills in `~/.claude/skills/` are **global** — they are staged into every sandbox you create. There is no per-profile skill configuration.

If you want different skills for different projects:

1. Install all skills globally.
2. Use skill `tags` and Claude's judgment to apply the right skill to the right context.
3. Or, manually toggle skills by moving them in/out of `~/.claude/skills/` before creating a sandbox.

Future versions of sandboxctl may add per-profile skill include/exclude lists, but for now, it's all-or-nothing.

## Best Practices

### Writing Instructions for Claude

- **Be explicit:** "Run `command --flag value`", not "use the command".
- **Provide decision trees:** "If X, do Y. Else if Z, do A. Otherwise, do B."
- **Include error recovery:** "If the command fails with error E, try fallback F."
- **Reference examples:** Store multi-line scripts or config files in `references/` and tell Claude to read them.

### Organizing References

- Use YAML for structured data (lookup tables, patterns, mappings).
- Use JSON for API responses or configuration examples.
- Use shell scripts for multi-step procedures.
- Name files descriptively: `error-patterns.yaml`, `fix-commands.sh`, not `data.yaml`.

### Testing Skills

Before publishing:

1. **Validate:** `sandboxctl skill validate /path/to/skill`
2. **Install locally:** `sandboxctl skill install file:///path/to/skill`
3. **Create a sandbox:** Verify the skill files appear in `~/.claude/skills/` inside the sandbox.
4. **Test instructions:** Ask Claude to use the skill. Check if it reads references correctly.
5. **Test hooks:** Verify `on_create` runs and installs tools/sets up environment.

### Version Bumping

When updating a published skill:

1. Increment `version` in frontmatter following semver.
2. Commit and tag the git repo with `vX.Y.Z`.
3. Users run `sandboxctl skill update <name>` to pull the new version.

## Troubleshooting

### Skill not appearing in sandbox

Check:
1. Is it in `~/.claude/skills/` on the host? `ls ~/.claude/skills/`
2. Did you create the sandbox **after** installing the skill? (Skills are staged at creation time, not into running sandboxes.)
3. Does `SKILL.md` have valid frontmatter? `sandboxctl skill validate ~/.claude/skills/my-skill`

### Hook failed

Hooks are best-effort. If `on_create` fails, check:
1. Does the sandbox have network access for `apt-get`/`pip install`?
2. Is the hook command valid? Test it manually inside a sandbox.
3. Use absolute paths in hooks — relative paths may not resolve correctly.

### Dependency warnings

Dependency warnings are informational. If you're sure the dependency isn't needed (e.g., it's optional), ignore the warning. If it is needed, install it:

```bash
sandboxctl skill install <dependency-git-url>
```

Then reinstall the dependent skill (or just continue — the dependency is now present for future sandboxes).
