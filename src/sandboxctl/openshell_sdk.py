"""Optional openshell SDK adapter: gateway operations over gRPC.

This module is the ONLY place that imports the upstream openshell Python
SDK (the ``sdk`` extra: ``pip install sandboxctl[sdk]``). Without it, every
public helper raises :class:`SdkUnavailable` and the facade
(:mod:`sandboxctl.openshell`) falls back to the CLI path.

Design constraints (specs/004-openshell-sdk-adoption):
- FR-008: ``resolve_workspace()`` is the single workspace resolution point.
- FR-012: auth is fail-closed — the client never refreshes or rewrites the
  token cache shared with the CLI (``auto_refresh=False``).
- R-3: fallback happens only at client acquisition; after an operation
  dispatches, failures raise ``SandboxError`` and are never retried on the
  CLI backend (double-execution hazard).
- FR-011: SDK exception types never cross this module's boundary.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

# 004 FR-007/FR-008: the default workspace, resolved in exactly one place.
# Future selectable workspaces change only this seam (spec US3 scenario 3).
DEFAULT_WORKSPACE = "default"

_BACKEND_ENV = "SANDBOXCTL_OPENSHELL_BACKEND"
_BACKEND_AUTO = "auto"
_BACKEND_CLI = "cli"

# Process-wide state (see data-model.md "Backend selection"):
_backend_decision: str | None = None
_client: Any = None


class SdkUnavailable(Exception):
    """The SDK path cannot be used (not installed, disabled, or init failed).

    Raised only at client acquisition; the facade treats it as the signal
    to use the CLI implementation for the current operation.
    """


def resolve_workspace() -> str:
    """Return the workspace every SDK operation targets (single seam)."""
    return DEFAULT_WORKSPACE


def _backend_mode() -> str:
    """Resolve and cache the backend mode for this process (FR-006)."""
    global _backend_decision
    if _backend_decision is None:
        mode = os.environ.get(_BACKEND_ENV, _BACKEND_AUTO).strip().lower()
        _backend_decision = mode if mode in (_BACKEND_AUTO, _BACKEND_CLI) else _BACKEND_AUTO
    return _backend_decision


def sdk_enabled() -> bool:
    """True when the backend mode allows the SDK path."""
    return _backend_mode() != _BACKEND_CLI


def _build_client() -> Any:
    """Import and construct the SDK client (patched in tests)."""
    from openshell import SandboxClient

    # auto_refresh=False: fail-closed consumer of the CLI's token cache
    # (FR-012) — no background refresh, no writes to shared state.
    return SandboxClient.from_active_cluster(auto_refresh=False)


def get_client() -> Any:
    """Return the process-wide SDK client or raise ``SdkUnavailable``."""
    global _client
    if _client is not None:
        return _client
    if not sdk_enabled():
        raise SdkUnavailable(f"{_BACKEND_ENV}={_BACKEND_CLI} forces the CLI backend")
    try:
        _client = _build_client()
    except SdkUnavailable:
        raise
    except Exception as exc:  # construction failure -> CLI fallback (R-3)
        raise SdkUnavailable(f"openshell SDK client could not initialize: {exc}") from exc
    return _client


def _map_error(action: str, exc: Exception) -> Exception:
    """Convert an SDK exception into the facade's SandboxError (FR-011)."""
    from sandboxctl.openshell import SandboxError

    detail = str(exc).strip() or exc.__class__.__name__
    # FR-010: a workspace mismatch must be loud and name the mismatch —
    # never a silent empty/successful result.
    if "workspace" in detail.lower():
        detail = f"{detail} (workspace mismatch? sandboxctl targets '{resolve_workspace()}')"
    return SandboxError(f"{action} failed: {detail}")


def _run_sdk(action: str, operation: Callable[[], Any]) -> Any:
    """Run an SDK operation with error mapping; never falls back mid-flight."""
    get_client()  # raises SdkUnavailable at acquisition time only
    try:
        return operation()
    except SdkUnavailable:
        raise
    except Exception as exc:
        raise _map_error(action, exc) from exc


def exec_command(name: str, command: list[str], stdin: bytes | None = None) -> Any:
    """Execute a command in a sandbox; returns the SDK ExecResult."""
    workspace = resolve_workspace()

    def operation() -> Any:
        client = get_client()
        return client.exec(name, command, workspace=workspace, stdin=stdin)

    return _run_sdk(f"exec in sandbox '{name}'", operation)


def delete_sandbox(name: str) -> Any:
    """Delete a sandbox; returns the SDK DeletionResult.

    ``allow_missing=True`` preserves the CLI's fire-and-forget semantics for
    absent sandboxes (parity, SC-003). Real gateway errors — including a
    workspace mismatch — raise ``SandboxError`` loudly (FR-010).
    """
    workspace = resolve_workspace()

    def operation() -> Any:
        client = get_client()
        return client.delete(name, workspace=workspace, allow_missing=True)

    return _run_sdk(f"delete sandbox '{name}'", operation)


def wait_deleted(name: str, timeout_seconds: float = 60.0) -> None:
    """Block until a sandbox is gone (used by restart before re-creating)."""
    workspace = resolve_workspace()

    def operation() -> None:
        client = get_client()
        client.wait_deleted(name, workspace=workspace, timeout_seconds=timeout_seconds)

    _run_sdk(f"wait for deletion of sandbox '{name}'", operation)


def _reset_for_tests() -> None:
    """Reset process-wide state between tests."""
    global _backend_decision, _client
    _backend_decision = None
    _client = None
