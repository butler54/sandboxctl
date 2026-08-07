"""Bundled example profiles installed by sandboxctl setup."""

from __future__ import annotations

PROFILES: dict[str, str] = {
    "generic-dev": """\
# sandboxctl profile: generic-dev

[sandbox]

[workspace]

[repos]
github = []

[extensions]
# VS Code extensions to install in the sandbox (remote) and recommend on host (local).
# Extensions are classified automatically: UI-only extensions (themes, icons) are skipped
# for remote install; workspace extensions are auto-installed.
list = [
    "ms-python.python",           # Python language support
    "ms-python.vscode-pylance",   # Python IntelliSense
]
# local_only = []  # Uncomment to exclude specific extensions from remote install
""",
    "ai-assisted": """\
# sandboxctl profile: ai-assisted

[sandbox]
model = "claude-sonnet-4-20250514"

[workspace]

[repos]
github = []

[extensions]
# VS Code extensions to install in the sandbox (remote) and recommend on host (local).
# Extensions are classified automatically: UI-only extensions (themes, icons) are skipped
# for remote install; workspace extensions are auto-installed.
list = [
    "ms-python.python",           # Python language support
    "ms-python.vscode-pylance",   # Python IntelliSense
    "github.copilot",             # GitHub Copilot
]
# local_only = []  # Uncomment to exclude specific extensions from remote install
""",
    "minimal": """\
# sandboxctl profile: minimal

[sandbox]

[workspace]

[repos]
github = []
""",
}
