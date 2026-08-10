"""VS Code extension management: classification, validation, and installation."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sandboxctl.models import Extensions

# Built-in denylist of UI-only extension publishers and patterns
# These are skipped for remote installation (themes, icon packs, color schemes)
DENYLIST: tuple[str, ...] = (
    "theme",
    "color-theme",
    "icon-theme",
    "material-icon-theme",
    "vscode-icons",
    "icons",
    "iconpack",
)

# Marketplace extension ID format: publisher.name
# Must match alphanumerics, hyphens, and dots in publisher.name pattern
_EXTENSION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$", re.IGNORECASE)

# Shell metacharacters that indicate potential command injection
# Described in prose: semicolons, pipes, ampersands, dollar signs, backticks,
# quotes (single and double), angle brackets, and parentheses
_SHELL_METACHARACTERS = {";", "|", "&", "$", "`", '"', "'", "<", ">", "(", ")"}


def is_denylisted(ext_id: str) -> bool:
    """Check if an extension ID matches the built-in denylist.

    Performs case-insensitive substring matching against UI-only extension patterns.
    """
    ext_lower = ext_id.lower()
    return any(pattern in ext_lower for pattern in DENYLIST)


def validate_extension_id(ext_id: str) -> bool:
    """Validate extension ID against marketplace format and security rules.

    Rejects IDs that:
    - Start with '-' (option injection into code CLI)
    - Contain shell metacharacters (command injection risk)
    - Don't match marketplace publisher.name format

    This is the primary command-injection mitigation (T-20-01).
    """
    if not ext_id:
        return False

    # Reject leading dash (option injection)
    if ext_id.startswith("-"):
        return False

    # Reject shell metacharacters
    if any(char in ext_id for char in _SHELL_METACHARACTERS):
        return False

    # Validate marketplace format
    return bool(_EXTENSION_ID_PATTERN.match(ext_id))


def classify_remote_extensions(ext: Extensions) -> list[str]:
    """Classify which extensions should be installed remotely in the sandbox.

    Returns the remote install set computed as:
    declared list - denylist matches - local_only - invalid IDs

    De-duplicates while preserving order.
    """
    seen = set()
    remote = []
    local_only_set = set(ext.local_only)

    for ext_id in ext.extensions_list:
        # Skip duplicates
        if ext_id in seen:
            continue
        seen.add(ext_id)

        # Skip invalid IDs (security: never reach subprocess)
        if not validate_extension_id(ext_id):
            continue

        # Skip denylisted (UI-only extensions)
        if is_denylisted(ext_id):
            continue

        # Skip local_only
        if ext_id in local_only_set:
            continue

        remote.append(ext_id)

    return remote


@dataclass
class InstallReport:
    """Result of install_extensions operation."""

    installed: list[str] = field(default_factory=list)
    skipped_invalid: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def install_extensions(ssh_host: str, ext_ids: list[str], vscode_bin: Path) -> InstallReport:
    """Install VS Code extensions into a sandbox via host code CLI.

    Runs one subprocess per extension ID:
    code --remote ssh-remote+<ssh_host> --install-extension <id>

    IDs are validated; invalid IDs skip subprocess and are recorded in skipped_invalid.
    Non-zero returncode is recorded in failed; the loop continues (warn-and-continue).
    The command is idempotent (code CLI no-ops if already installed).

    Args:
        ssh_host: The resolved SSH alias for the sandbox (see health.resolve_ssh_host —
            OpenShell has used both bare `openshell-<name>` and workspace-scoped
            `openshell-<name>.<workspace>` aliases across versions, so callers must
            resolve the live one rather than assuming a fixed format here)
        ext_ids: List of extension IDs to install
        vscode_bin: Path to the code CLI binary

    Returns:
        InstallReport with installed, skipped_invalid, and failed lists
    """
    report = InstallReport()

    for ext_id in ext_ids:
        # Validate ID (security: never reach subprocess if invalid)
        if not validate_extension_id(ext_id):
            report.skipped_invalid.append(ext_id)
            continue

        print(f"Installing {ext_id}...")

        # Invoke code CLI with list args (never shell=True)
        result = subprocess.run(
            [
                str(vscode_bin),
                "--remote",
                f"ssh-remote+{ssh_host}",
                "--install-extension",
                ext_id,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            report.installed.append(ext_id)
        else:
            # Capture failure but continue (warn-and-continue)
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            report.failed.append((ext_id, error_msg))

    return report
