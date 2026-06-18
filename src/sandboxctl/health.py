"""Container liveness checks and auto-recovery."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum


class ContainerState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    MISSING = "missing"
    UNKNOWN = "unknown"


class GatewayState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass
class HealthReport:
    """Diagnostic report for a sandbox."""

    sandbox_name: str
    container_state: ContainerState
    gateway_state: GatewayState
    ssh_reachable: bool
    recovery_action: str
    details: list[str]

    @property
    def healthy(self) -> bool:
        return self.container_state == ContainerState.RUNNING and self.ssh_reachable


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    """Run a command with timeout, capturing output."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def check_gateway_state() -> GatewayState:
    """Check if the podman machine / OpenShell gateway is running."""
    try:
        result = _run(["podman", "machine", "info"])
        if result.returncode == 0:
            return GatewayState.RUNNING
        return GatewayState.STOPPED
    except FileNotFoundError:
        return GatewayState.MISSING
    except subprocess.TimeoutExpired:
        return GatewayState.UNKNOWN


def check_container_state(sandbox_name: str) -> ContainerState:
    """Check the state of a sandbox container."""
    try:
        result = _run(["podman", "ps", "-a", "--filter", f"name={sandbox_name}", "--format", "{{.Status}}"])
        if result.returncode != 0:
            return ContainerState.UNKNOWN

        status = result.stdout.strip().lower()
        if not status:
            return ContainerState.MISSING
        if "up" in status or "running" in status:
            return ContainerState.RUNNING
        if "paused" in status:
            return ContainerState.PAUSED
        return ContainerState.STOPPED
    except FileNotFoundError:
        return ContainerState.MISSING
    except subprocess.TimeoutExpired:
        return ContainerState.UNKNOWN


def check_ssh_connectivity(sandbox_name: str, timeout: int = 5) -> bool:
    """Check if SSH into the sandbox works."""
    try:
        cmd = ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no", sandbox_name, "echo", "ok"]
        result = _run(cmd, timeout=timeout)
        return result.returncode == 0 and "ok" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def recover_gateway() -> bool:
    """Attempt to start the podman machine."""
    try:
        result = _run(["podman", "machine", "start"], timeout=60)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def recover_container(sandbox_name: str) -> bool:
    """Attempt to start a stopped container (safe — no data loss)."""
    try:
        result = _run(["podman", "start", sandbox_name], timeout=30)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def diagnose(sandbox_name: str, auto_recover: bool = True) -> HealthReport:
    """Run full health check with optional auto-recovery.

    Auto-recovery only performs safe operations (starting stopped containers).
    Never recreates or flushes a container — that requires explicit user action.
    """
    details: list[str] = []
    recovery_action = "none"

    gw_state = check_gateway_state()
    details.append(f"Gateway: {gw_state.value}")

    if gw_state == GatewayState.STOPPED and auto_recover:
        details.append("Attempting gateway recovery...")
        if recover_gateway():
            gw_state = GatewayState.RUNNING
            details.append("Gateway recovered successfully")
            recovery_action = "gateway_restarted"
        else:
            details.append("Gateway recovery failed")
            return HealthReport(
                sandbox_name=sandbox_name,
                container_state=ContainerState.UNKNOWN,
                gateway_state=gw_state,
                ssh_reachable=False,
                recovery_action="gateway_recovery_failed",
                details=details,
            )

    if gw_state != GatewayState.RUNNING:
        return HealthReport(
            sandbox_name=sandbox_name,
            container_state=ContainerState.UNKNOWN,
            gateway_state=gw_state,
            ssh_reachable=False,
            recovery_action="gateway_not_running",
            details=details,
        )

    container_state = check_container_state(sandbox_name)
    details.append(f"Container: {container_state.value}")

    if container_state == ContainerState.STOPPED and auto_recover:
        details.append("Attempting container recovery (safe — no data loss)...")
        if recover_container(sandbox_name):
            container_state = ContainerState.RUNNING
            details.append("Container recovered successfully")
            recovery_action = "container_restarted"
        else:
            details.append("Container recovery failed")
            recovery_action = "container_recovery_failed"

    if container_state == ContainerState.MISSING:
        recovery_action = "container_missing_needs_recreate"
        details.append("Container not found — needs `sandboxctl create` to recreate")

    ssh_ok = False
    if container_state == ContainerState.RUNNING:
        ssh_ok = check_ssh_connectivity(sandbox_name)
        details.append(f"SSH: {'reachable' if ssh_ok else 'unreachable'}")
        if not ssh_ok:
            details.append("Container is running but SSH failed — may still be starting up")

    return HealthReport(
        sandbox_name=sandbox_name,
        container_state=container_state,
        gateway_state=gw_state,
        ssh_reachable=ssh_ok,
        recovery_action=recovery_action,
        details=details,
    )
