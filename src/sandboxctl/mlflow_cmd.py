"""MLflow tracking server container lifecycle management."""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import typer

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
    """Start MLflow tracking server container with bind-mounted storage."""
    # Ensure data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)

    # Build podman argv as list (no shell=True)
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
        "0.0.0.0",
        "--port",
        str(port),
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


def check_mlflow_health(tracking_uri: str, timeout: int = 5) -> bool:
    """Check if MLflow server is healthy (returns True if /health responds 200)."""
    health_url = f"{tracking_uri.rstrip('/')}/health"
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


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
        raise typer.Exit(code=1)


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
