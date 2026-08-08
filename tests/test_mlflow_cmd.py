"""Tests for mlflow_cmd module (container lifecycle, health check, status)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest


# Helper to build a mocked CompletedProcess
def mock_completed_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a mocked subprocess.CompletedProcess with configurable returncode/stdout."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# Helper to mock urllib.request.urlopen with configurable status
class MockHTTPResponse:
    """Mock HTTP response with configurable status code."""

    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> MockHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_start_mlflow_container(tmp_path) -> None:
    """Start command creates data_dir and runs podman with correct args."""
    from sandboxctl.mlflow_cmd import start_mlflow_container

    data_dir = tmp_path / "mlflow-data"
    port = 5050

    with patch("sandboxctl.mlflow_cmd._run") as mock_run:
        mock_run.return_value = mock_completed_process(returncode=0, stdout="container-id\n")

        start_mlflow_container(data_dir, port)

        # Verify data_dir was created
        assert data_dir.exists()

        # Verify _run was called with podman args as list
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]  # First positional arg (args list)

        # Assert every critical arg is present
        assert call_args[0] == "podman"
        assert call_args[1] == "run"
        assert "-d" in call_args
        assert "--name" in call_args
        assert "mlflow-tracking" in call_args
        assert "--restart" in call_args
        assert "unless-stopped" in call_args
        assert "-p" in call_args
        assert f"{port}:{port}" in call_args
        assert "-v" in call_args
        # Bind mount path should contain data_dir
        bind_mount_arg = next((arg for arg in call_args if str(data_dir) in arg), None)
        assert bind_mount_arg is not None
        assert ":/mlflow-data" in bind_mount_arg
        # Image
        assert "ghcr.io/mlflow/mlflow:v3.15.1" in call_args
        # MLflow server command
        assert "mlflow" in call_args
        assert "server" in call_args
        # Backend store
        assert "--backend-store-uri" in call_args
        assert "sqlite:////mlflow-data/mlflow.db" in call_args
        # Artifacts destination
        assert "--artifacts-destination" in call_args
        assert "/mlflow-data/artifacts" in call_args
        # Host and port
        assert "--host" in call_args
        assert "0.0.0.0" in call_args
        assert "--port" in call_args
        assert str(port) in call_args

        # Verify check=False was passed
        assert mock_run.call_args[1]["check"] is False


def test_start_mlflow_container_failure(tmp_path) -> None:
    """Start command raises RuntimeError when podman fails."""
    from sandboxctl.mlflow_cmd import start_mlflow_container

    data_dir = tmp_path / "mlflow-data"

    with patch("sandboxctl.mlflow_cmd._run") as mock_run:
        mock_run.return_value = mock_completed_process(returncode=125, stderr="Error: image not found")

        with pytest.raises(RuntimeError, match="Failed to start MLflow container"):
            start_mlflow_container(data_dir, 5050)


@pytest.mark.skip(reason="implemented in 21-02")
def test_stop_mlflow_container() -> None:
    """Stop command calls podman stop with container name."""
    # Wave 0 stub — implementation in Plan 21-02
    pass


@pytest.mark.skip(reason="implemented in 21-02")
def test_mlflow_status() -> None:
    """Status shows container state, URI, data_dir size for managed mode."""
    # Wave 0 stub — implementation in Plan 21-02
    pass


@pytest.mark.skip(reason="implemented in 21-02")
def test_external_mlflow_mode() -> None:
    """External mode (managed=false) skips container mgmt, shows reachability probe."""
    # Wave 0 stub — implementation in Plan 21-02
    pass
