"""Bundled example profiles installed by sandboxctl setup."""

from __future__ import annotations

PROFILES: dict[str, str] = {
    "generic-dev": """\
# sandboxctl profile: generic-dev

[sandbox]

[workspace]

[repos]
github = []
""",
    "ai-assisted": """\
# sandboxctl profile: ai-assisted

[sandbox]
model = "claude-sonnet-4-20250514"

[workspace]

[repos]
github = []
""",
    "minimal": """\
# sandboxctl profile: minimal

[sandbox]

[workspace]

[repos]
github = []
""",
}
