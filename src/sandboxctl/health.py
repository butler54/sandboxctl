"""Container liveness checks and auto-recovery."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

# Legacy naming (pre-workspace scoping): openshell-sandbox-{name}
_CONTAINER_PREFIX = "openshell-sandbox-"
# Workspace-scoped naming (OpenShell 0.0.9x+): openshell-{workspace}--{name}-{uuid}
_WORKSPACE_SCOPED_RE = r"^openshell-[^-]+--{name}-[0-9a-f-]+$"


class ContainerState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    MISSING = "missing"
    UNKNOWN = "unknown"


class GatewayState(Enum):
    """State of the OpenShell gateway service."""

    RUNNING = "running"
    STOPPED = "stopped"
    MISSING = "missing"
    UNKNOWN = "unknown"


class ComputeState(Enum):
    """State of the Podman compute backend."""

    RUNNING = "running"
    STOPPED = "stopped"
    MISSING = "missing"
    UNKNOWN = "unknown"


class GatewayApiState(Enum):
    """Reachability of the OpenShell gateway API."""

    RUNNING = "running"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


@dataclass
class HealthReport:
    """Diagnostic report for a sandbox."""

    sandbox_name: str
    container_state: ContainerState
    compute_state: ComputeState
    gateway_state: GatewayState
    gateway_api_state: GatewayApiState
    ssh_reachable: bool
    recovery_action: str
    details: list[str]

    @property
    def healthy(self) -> bool:
        return (
            self.compute_state == ComputeState.RUNNING
            and self.gateway_state == GatewayState.RUNNING
            and self.gateway_api_state == GatewayApiState.RUNNING
            and self.container_state == ContainerState.RUNNING
            and self.ssh_reachable
        )


def _podman_env() -> dict[str, str] | None:
    """Build environment for podman commands. macOS needs CONTAINERS_MACHINE_PROVIDER."""
    if sys.platform != "darwin":
        return None
    env = os.environ.copy()
    env.setdefault("CONTAINERS_MACHINE_PROVIDER", "applehv")
    return env


def _run(
    cmd: list[str],
    timeout: int = 10,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with timeout, capturing output."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def check_compute_state() -> ComputeState:
    """Check the Podman machine on macOS or native Podman elsewhere."""
    command = ["podman", "machine", "info"] if sys.platform == "darwin" else ["podman", "info"]
    try:
        result = _run(command, env=_podman_env())
        if result.returncode == 0:
            return ComputeState.RUNNING
        return ComputeState.STOPPED
    except FileNotFoundError:
        return ComputeState.MISSING
    except subprocess.TimeoutExpired:
        return ComputeState.UNKNOWN


def check_gateway_state() -> GatewayState:
    """Check the platform service that hosts the OpenShell gateway."""
    if sys.platform == "darwin":
        try:
            installed = _run(["brew", "list", "openshell"])
            if installed.returncode != 0:
                return GatewayState.MISSING
            result = _run(["brew", "services", "list"])
        except FileNotFoundError:
            return GatewayState.MISSING
        except subprocess.TimeoutExpired:
            return GatewayState.UNKNOWN

        if result.returncode != 0:
            return GatewayState.UNKNOWN
        for line in result.stdout.splitlines():
            fields = line.split()
            if fields and fields[0] == "openshell":
                return GatewayState.RUNNING if "started" in fields else GatewayState.STOPPED
        return GatewayState.STOPPED

    try:
        result = _run(
            ["systemctl", "--user", "show", "openshell-gateway", "--property=LoadState", "--property=ActiveState"]
        )
    except FileNotFoundError:
        return GatewayState.UNKNOWN
    except subprocess.TimeoutExpired:
        return GatewayState.UNKNOWN
    if result.returncode != 0:
        return GatewayState.UNKNOWN
    state = result.stdout
    if "LoadState=not-found" in state:
        return GatewayState.MISSING
    if "ActiveState=active" in state:
        return GatewayState.RUNNING
    return GatewayState.STOPPED


def check_gateway_api_state() -> GatewayApiState:
    """Check the gateway through the OpenShell CLI rather than process state."""
    from sandboxctl import openshell as osh

    try:
        status = osh.gateway_status()
    except osh.SandboxError:
        return GatewayApiState.UNREACHABLE
    if status.get("status") == "Connected":
        return GatewayApiState.RUNNING
    if status:
        return GatewayApiState.UNREACHABLE
    return GatewayApiState.UNKNOWN


def resolve_container_name(sandbox_name: str) -> str | None:
    """Resolve the actual podman container name for a sandbox.

    OpenShell has used more than one container naming scheme across versions
    (e.g. legacy `openshell-sandbox-{name}` vs. workspace-scoped
    `openshell-{workspace}--{name}-{uuid}`), so we match against all known
    patterns instead of assuming a fixed prefix.
    """
    try:
        result = _run(["podman", "ps", "-a", "--format", "{{.Names}}"], env=_podman_env())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    legacy_name = f"{_CONTAINER_PREFIX}{sandbox_name}"
    scoped_re = re.compile(_WORKSPACE_SCOPED_RE.format(name=re.escape(sandbox_name)))
    for line in result.stdout.splitlines():
        name = line.strip()
        if name == legacy_name or scoped_re.match(name):
            return name
    return None


def check_container_state(sandbox_name: str) -> ContainerState:
    """Check the state of a sandbox container."""
    container_name = resolve_container_name(sandbox_name)
    if container_name is None:
        return ContainerState.MISSING
    try:
        result = _run(
            ["podman", "ps", "-a", "--filter", f"name=^{container_name}$", "--format", "{{.Status}}"],
            env=_podman_env(),
        )
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


def resolve_ssh_host(sandbox_name: str, timeout: int = 5) -> str | None:
    """Resolve the SSH alias that actually connects for this sandbox.

    OpenShell has used both a bare host alias (openshell-{name}) and a
    workspace-scoped one (openshell-{name}.{workspace}) across versions, so we
    probe both and return whichever one is live.
    """
    for ssh_host in (f"openshell-{sandbox_name}.default", f"openshell-{sandbox_name}"):
        try:
            # Accepted risk: StrictHostKeyChecking=no — health probe only, not data channel
            cmd = ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no", ssh_host, "echo", "ok"]
            result = _run(cmd, timeout=timeout)
            if result.returncode == 0 and "ok" in result.stdout:
                return ssh_host
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def check_ssh_connectivity(sandbox_name: str, timeout: int = 5) -> bool:
    """Check if SSH into the sandbox works."""
    return resolve_ssh_host(sandbox_name, timeout=timeout) is not None


def recover_compute() -> bool:
    """Attempt to start a stopped Podman machine on macOS."""
    if sys.platform != "darwin":
        return False
    try:
        result = _run(["podman", "machine", "start"], timeout=60, env=_podman_env())
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def recover_gateway() -> bool:
    """Restart the platform-managed OpenShell gateway service."""
    command = (
        ["brew", "services", "restart", "openshell"]
        if sys.platform == "darwin"
        else ["systemctl", "--user", "restart", "openshell-gateway"]
    )
    try:
        return _run(command, timeout=60).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def recover_container(sandbox_name: str) -> bool:
    """Attempt to start a stopped container (safe — no data loss)."""
    container_name = resolve_container_name(sandbox_name)
    if container_name is None:
        return False
    try:
        result = _run(["podman", "start", container_name], timeout=30, env=_podman_env())
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

    compute_state = check_compute_state()
    details.append(f"Compute: {compute_state.value}")

    if compute_state == ComputeState.STOPPED and auto_recover:
        details.append("Attempting compute recovery...")
        if recover_compute():
            compute_state = check_compute_state()
            details.append("Compute recovery completed")
            recovery_action = "compute_restarted"
        else:
            details.append("Compute recovery failed")
            return HealthReport(
                sandbox_name=sandbox_name,
                container_state=ContainerState.UNKNOWN,
                compute_state=compute_state,
                gateway_state=GatewayState.UNKNOWN,
                gateway_api_state=GatewayApiState.UNKNOWN,
                ssh_reachable=False,
                recovery_action="compute_recovery_failed",
                details=details,
            )

    if compute_state != ComputeState.RUNNING:
        return HealthReport(
            sandbox_name=sandbox_name,
            container_state=ContainerState.UNKNOWN,
            compute_state=compute_state,
            gateway_state=GatewayState.UNKNOWN,
            gateway_api_state=GatewayApiState.UNKNOWN,
            ssh_reachable=False,
            recovery_action="compute_not_running",
            details=details,
        )

    gw_state = check_gateway_state()
    details.append(f"Gateway service: {gw_state.value}")
    if gw_state == GatewayState.STOPPED and auto_recover:
        details.append("Attempting gateway service recovery...")
        if recover_gateway():
            gw_state = check_gateway_state()
            details.append("Gateway service recovery completed")
            recovery_action = "gateway_restarted"
        else:
            details.append("Gateway service recovery failed")
            return HealthReport(
                sandbox_name=sandbox_name,
                container_state=ContainerState.UNKNOWN,
                compute_state=compute_state,
                gateway_state=gw_state,
                gateway_api_state=GatewayApiState.UNKNOWN,
                ssh_reachable=False,
                recovery_action="gateway_recovery_failed",
                details=details,
            )
    if gw_state != GatewayState.RUNNING:
        return HealthReport(
            sandbox_name,
            ContainerState.UNKNOWN,
            compute_state,
            gw_state,
            GatewayApiState.UNKNOWN,
            False,
            "gateway_not_running",
            details,
        )

    api_state = check_gateway_api_state()
    details.append(f"Gateway API: {api_state.value}")
    if api_state != GatewayApiState.RUNNING:
        return HealthReport(
            sandbox_name,
            ContainerState.UNKNOWN,
            compute_state,
            gw_state,
            api_state,
            False,
            "gateway_api_unreachable",
            details,
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
        compute_state=compute_state,
        gateway_state=gw_state,
        gateway_api_state=api_state,
        ssh_reachable=ssh_ok,
        recovery_action=recovery_action,
        details=details,
    )
