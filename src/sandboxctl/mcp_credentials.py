"""Extract and stage MCP OAuth credentials from host keychain into sandboxes."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from sandboxctl import openshell as osh

_KEYCHAIN_SERVICE = "Claude Code-credentials"


def _read_keychain_entry() -> dict | None:
    """Read the Claude Code credentials entry from macOS keychain."""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return None


def extract_mcp_credentials(server_names: list[str] | None = None) -> dict[str, dict]:
    """Extract MCP OAuth credentials from the host keychain.

    Returns a dict mapping server name to its credential blob.
    If server_names is provided, only those servers are returned.
    """
    entry = _read_keychain_entry()
    if not entry:
        return {}

    mcp_oauth = entry.get("mcpOAuth", {})
    if not mcp_oauth:
        return {}

    if server_names:
        return {k: v for k, v in mcp_oauth.items() if k in server_names}
    return dict(mcp_oauth)


def stage_mcp_credentials(
    sandbox_name: str,
    server_names: list[str] | None = None,
) -> list[str]:
    """Stage MCP OAuth credentials into a running sandbox.

    Writes the credential blob to the sandbox's file-based credential store
    so Claude Code can use the refresh token to maintain MCP sessions.

    Returns list of server names that were staged.
    """
    creds = extract_mcp_credentials(server_names)
    if not creds:
        return []

    keychain_entry = _read_keychain_entry() or {}
    keychain_entry["mcpOAuth"] = creds

    staged: list[str] = []
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(keychain_entry, f)
        tmp_path = Path(f.name)

    try:
        osh.sandbox_exec_pipe(sandbox_name, "mkdir -p /sandbox/.claude")
        osh.sandbox_upload(sandbox_name, tmp_path, "/sandbox/.claude/.credentials.json")
        staged = list(creds.keys())
    finally:
        tmp_path.unlink(missing_ok=True)

    return staged
