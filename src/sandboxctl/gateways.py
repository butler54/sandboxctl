"""Named openshell gateway configuration and sandbox→gateway routing (005).

The gateway resolution seam: every sandbox operation resolves which
openshell gateway it targets through this module (spec FR-010), composing
with the 004 workspace seam. Gateways are *referenced* by name — openshell
owns the registry (endpoint, TLS, OIDC) under
``~/.config/openshell/gateways/<name>/`` — so this module stores only
names, a Kubernetes type hint, and sandbox associations.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from sandboxctl.config import GatewayEntry, SandboxctlConfig

# ---------------------------------------------------------------------------
# Active gateway name (mirrors the openshell resolver's precedence) — R-1
# ---------------------------------------------------------------------------


def active_gateway_name() -> str | None:
    """The openshell CLI's active gateway: ``$OPENSHELL_GATEWAY`` first,
    then ``~/.config/openshell/active_gateway`` (SDK ``_resolve_active_cluster``
    precedence)."""
    env = os.environ.get("OPENSHELL_GATEWAY")
    if env:
        return env
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    try:
        return (base / "openshell" / "active_gateway").read_text().strip() or None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Key → openshell-name resolution (loud on unknown keys, FR-008) — R-1/R-8
# ---------------------------------------------------------------------------


def resolve_openshell_name(config: SandboxctlConfig, gateway_key: str) -> str:
    """Map a ``[gateways]`` key to its openshell-registered gateway name."""
    from sandboxctl.openshell import SandboxError

    entry = config.gateways.get(gateway_key)
    if entry is None:
        known = ", ".join(sorted(config.gateways)) or "none configured"
        raise SandboxError(f"gateway '{gateway_key}' is not configured (known gateways: {known})")
    return entry.openshell_name or gateway_key


def configured_gateways(config: SandboxctlConfig) -> list[str]:
    """All configured gateway keys plus the active gateway name, deduplicated.

    Used by list/status/doctor to iterate every gateway the user works with
    (spec FR-007).
    """
    keys = list(config.gateways)
    active = active_gateway_name()
    if active and active not in keys:
        keys.append(active)
    return keys


def gateway_targets(config: SandboxctlConfig) -> list[str | None]:
    """Gateway names for cross-gateway commands (list/status/doctor).

    One entry per configured gateway (resolved to its openshell name), plus
    the active gateway — always included so the command never shows less
    than today's single-gateway view. ``None`` denotes "the active gateway"
    (no env injection, today's behavior exactly).
    """
    targets: list[str | None] = [resolve_openshell_name(config, key) for key in config.gateways]
    active = active_gateway_name()
    if active not in targets:
        # None when no active gateway is recorded: query the CLI default,
        # exactly as today (and skip when configured gateways already cover
        # everything and nothing is active).
        if active is not None or not targets:
            targets.append(active)
    return targets


# ---------------------------------------------------------------------------
# Sandbox → gateway association store (mirrors the 002 policy-association
# pattern; shares sandboxes.json so one store records both associations) — R-2
# ---------------------------------------------------------------------------


def _associations_path(config: SandboxctlConfig) -> Path:
    return config.config_dir / "sandboxes.json"


def _load_associations(config: SandboxctlConfig) -> dict[str, dict[str, str]]:
    try:
        data = json.loads(_associations_path(config).read_text())
    except (OSError, ValueError, TypeError):
        return {}
    sandboxes = data.get("sandboxes") if isinstance(data, dict) else None
    return sandboxes if isinstance(sandboxes, dict) else {}


def _store_associations(config: SandboxctlConfig, sandboxes: dict[str, dict[str, str]]) -> None:
    path = _associations_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".sandboxes-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump({"sandboxes": sandboxes}, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def record_gateway_association(config: SandboxctlConfig, sandbox_name: str, gateway_key: str) -> None:
    """Persist which gateway a sandbox was created on (key form)."""
    sandboxes = _load_associations(config)
    entry = sandboxes.get(sandbox_name, {})
    entry["gateway"] = gateway_key
    sandboxes[sandbox_name] = entry
    _store_associations(config, sandboxes)


def lookup_gateway_association(config: SandboxctlConfig, sandbox_name: str) -> str | None:
    """Return the gateway key recorded for a sandbox, or None."""
    entry = _load_associations(config).get(sandbox_name)
    if not isinstance(entry, dict):
        return None
    key = entry.get("gateway")
    return key if isinstance(key, str) and key else None


def remove_gateway_association(config: SandboxctlConfig, sandbox_name: str) -> None:
    """Drop a sandbox's gateway association (e.g. after deletion)."""
    sandboxes = _load_associations(config)
    entry = sandboxes.get(sandbox_name)
    if isinstance(entry, dict) and "gateway" in entry:
        del entry["gateway"]
        if entry:
            sandboxes[sandbox_name] = entry
        else:
            del sandboxes[sandbox_name]
        _store_associations(config, sandboxes)


def resolve_gateway_for_sandbox(sandbox_name: str, config: SandboxctlConfig) -> str | None:
    """THE gateway resolution seam for sandbox operations (spec FR-010).

    Returns the openshell gateway name for a sandbox, or None (= the
    CLI-active gateway, today's behavior, FR-001). A recorded association
    whose key is no longer configured fails loudly (FR-008) — never a
    silent redirect to the active gateway.
    """
    key = lookup_gateway_association(config, sandbox_name)
    if not key:
        return None
    return resolve_openshell_name(config, key)


def gateway_is_kubernetes(config: SandboxctlConfig, gateway_key: str) -> bool:
    """Whether a configured gateway carries the Kubernetes type hint."""
    entry: GatewayEntry | None = config.gateways.get(gateway_key)
    return bool(entry and entry.kubernetes)
