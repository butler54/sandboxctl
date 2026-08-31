"""MLflow tracking server container lifecycle management."""

from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from sandboxctl.config import SandboxctlConfig

# Module-level constants (single pin point per D-01)
MLFLOW_IMAGE = "ghcr.io/mlflow/mlflow:v3.15.1"
MLFLOW_CONTAINER_NAME = "mlflow-tracking"

# Typer sub-app
mlflow_app = typer.Typer(help="Manage MLflow tracking server.")


def _run(
    args: list[str],
    check: bool = True,
    capture: bool = True,
    stdin_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run subprocess with list args (reused from openshell.py pattern)."""
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        text=True,
        input=stdin_data,
    )


def start_mlflow_container(data_dir: Path, port: int = 5050) -> None:
    """Start MLflow tracking server container with bind-mounted storage.

    If the container already exists in a stopped/exited state, restarts it
    via `podman start` rather than attempting to create a duplicate.
    """
    if _mlflow_container_exists():
        result = _run(["podman", "start", MLFLOW_CONTAINER_NAME], check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start MLflow container: {result.stderr}")
        return

    # Container does not exist — create and start it
    data_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "podman",
        "run",
        "-d",  # detached
        "--name",
        MLFLOW_CONTAINER_NAME,
        "--restart",
        "unless-stopped",
        "-p",
        f"{port}:{port}",
        "-v",
        f"{data_dir}:/mlflow-data",
        MLFLOW_IMAGE,
        "mlflow",
        "server",
        "--backend-store-uri",
        "sqlite:////mlflow-data/mlflow.db",
        "--artifacts-destination",
        "/mlflow-data/artifacts",
        "--host",
        "0.0.0.0",  # noqa: S104
        "--port",
        str(port),
        # MLflow's Host-header allowlist replaces the default (localhost-only) list rather
        # than extending it, and matches the full header including port. Without this,
        # requests via the host-gateway hostname (host.openshell.internal, used to reach
        # this container from inside sandboxes — see #138) are rejected as a DNS-rebinding
        # attempt, and *plain* localhost access (used by `sandboxctl mlflow status`/`doctor`)
        # would break too if the default list were dropped without re-adding it explicitly.
        "--allowed-hosts",
        f"localhost,localhost:{port},127.0.0.1,127.0.0.1:{port},host.openshell.internal,host.openshell.internal:{port}",
    ]

    result = _run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to start MLflow container: {result.stderr}")


def stop_mlflow_container() -> None:
    """Stop MLflow tracking server container."""
    _run(["podman", "stop", MLFLOW_CONTAINER_NAME], check=False)


def is_mlflow_running() -> bool:
    """Check if MLflow container is running."""
    result = _run(
        ["podman", "ps", "--filter", f"name={MLFLOW_CONTAINER_NAME}", "--format", "{{.Names}}"],
        check=False,
    )
    return MLFLOW_CONTAINER_NAME in result.stdout


def _mlflow_container_exists() -> bool:
    """Check if MLflow container exists in any state (running, stopped, exited)."""
    result = _run(
        ["podman", "ps", "-a", "--filter", f"name={MLFLOW_CONTAINER_NAME}", "--format", "{{.Names}}"],
        check=False,
    )
    return MLFLOW_CONTAINER_NAME in result.stdout


def check_mlflow_health(tracking_uri: str, timeout: int = 5) -> bool:
    """Check if MLflow server is healthy (returns True if /health responds 200)."""
    health_url = f"{tracking_uri.rstrip('/')}/health"
    try:
        req = urllib.request.Request(health_url, method="GET")  # noqa: S310
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        # OSError covers http.client.RemoteDisconnected / ConnectionError raised when the
        # container's port is accepting connections but the server isn't serving yet (#122).
        return False


def wait_for_mlflow_health(tracking_uri: str, attempts: int = 6, delay: float = 2.0) -> bool:
    """Poll check_mlflow_health with backoff; return True as soon as it is healthy (#122).

    The MLflow container takes a few seconds to bind and serve its port after start, so a
    single immediate check races the server. Retries up to `attempts` times, sleeping
    `delay` seconds between tries (~10s total by default).
    """
    for attempt in range(attempts):
        if check_mlflow_health(tracking_uri):
            return True
        if attempt < attempts - 1:
            time.sleep(delay)
    return False


def get_directory_size(path: Path) -> int:
    """Calculate total size of directory in bytes (cross-platform)."""
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    # Skip files we can't read (permissions, symlinks)
                    continue
    except (OSError, FileNotFoundError):
        return 0
    return total


def format_size(bytes_size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def mlflow_status(config: SandboxctlConfig) -> str:
    """Generate MLflow status output (managed or external mode)."""
    lines = []

    if config.mlflow.managed:
        # Managed mode: container state, tracking URI, data-dir size
        if is_mlflow_running():
            state = "running"
        elif _mlflow_container_exists():
            state = "stopped (container exists — run `sandboxctl mlflow start` to resume)"
        else:
            state = "stopped (no container)"
        lines.append(f"MLflow Status: {state}")
        lines.append(f"Tracking URI: {config.mlflow.tracking_uri}")

        size_bytes = get_directory_size(config.mlflow.data_dir)
        lines.append(f"Data Directory: {config.mlflow.data_dir} ({format_size(size_bytes)})")
    else:
        # External mode: external (unmanaged), tracking URI, reachability probe
        lines.append("MLflow Status: external (unmanaged)")
        lines.append(f"Tracking URI: {config.mlflow.tracking_uri}")

        # Live reachability probe
        is_up = check_mlflow_health(config.mlflow.tracking_uri, timeout=5)
        reachability = "up" if is_up else "down"
        lines.append(f"Reachability: {reachability}")

        # Container state and data-dir size are N/A in external mode
        lines.append("Container State: N/A")
        lines.append("Data Directory: N/A")

    return "\n".join(lines)


@mlflow_app.command("start")
def start_command() -> None:
    """Start MLflow tracking server container."""
    from sandboxctl.config import load_config

    config = load_config()

    if not config.mlflow.managed:
        typer.echo("MLflow is in external (unmanaged) mode — nothing to start")
        return

    try:
        start_mlflow_container(config.mlflow.data_dir, config.mlflow.port)
        typer.echo(f"MLflow started: {config.mlflow.tracking_uri}")
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@mlflow_app.command("stop")
def stop_command() -> None:
    """Stop MLflow tracking server container."""
    from sandboxctl.config import load_config

    config = load_config()

    if not config.mlflow.managed:
        typer.echo("MLflow is in external (unmanaged) mode — nothing to stop")
        return

    stop_mlflow_container()
    typer.echo("MLflow stopped")


@mlflow_app.command("status")
def status_command() -> None:
    """Show MLflow tracking server status."""
    from sandboxctl.config import load_config

    config = load_config()
    output = mlflow_status(config)
    typer.echo(output)
