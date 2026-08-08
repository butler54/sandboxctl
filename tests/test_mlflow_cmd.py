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


def test_stop_mlflow_container() -> None:
    """Stop command calls podman stop with container name."""
    from sandboxctl.mlflow_cmd import stop_mlflow_container

    with patch("sandboxctl.mlflow_cmd._run") as mock_run:
        mock_run.return_value = mock_completed_process(returncode=0)

        stop_mlflow_container()

        # Verify podman stop was called with correct args
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["podman", "stop", "mlflow-tracking"]
        # Verify check=False (missing container is not an error)
        assert mock_run.call_args[1]["check"] is False


def test_stop_mlflow_container_missing() -> None:
    """Stop command handles missing container gracefully (no error)."""
    from sandboxctl.mlflow_cmd import stop_mlflow_container

    with patch("sandboxctl.mlflow_cmd._run") as mock_run:
        # Non-zero returncode (container not found)
        mock_run.return_value = mock_completed_process(returncode=1, stderr="Error: no such container")

        # Should not raise
        stop_mlflow_container()

        mock_run.assert_called_once()


def test_is_mlflow_running_true() -> None:
    """is_mlflow_running returns True when container is running."""
    from sandboxctl.mlflow_cmd import is_mlflow_running

    with patch("sandboxctl.mlflow_cmd._run") as mock_run:
        mock_run.return_value = mock_completed_process(returncode=0, stdout="mlflow-tracking\n")

        result = is_mlflow_running()

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "podman" in call_args
        assert "ps" in call_args
        assert "--filter" in call_args
        assert "name=mlflow-tracking" in call_args


def test_is_mlflow_running_false() -> None:
    """is_mlflow_running returns False when container is not running."""
    from sandboxctl.mlflow_cmd import is_mlflow_running

    with patch("sandboxctl.mlflow_cmd._run") as mock_run:
        mock_run.return_value = mock_completed_process(returncode=0, stdout="")

        result = is_mlflow_running()

        assert result is False


def test_check_mlflow_health_success() -> None:
    """check_mlflow_health returns True on 200 status."""
    from sandboxctl.mlflow_cmd import check_mlflow_health

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockHTTPResponse(status=200)

        result = check_mlflow_health("http://localhost:5050", timeout=5)

        assert result is True
        # Verify /health endpoint was used
        call_args = mock_urlopen.call_args[0][0]
        assert "/health" in call_args.full_url


def test_check_mlflow_health_timeout() -> None:
    """check_mlflow_health returns False on timeout."""
    from sandboxctl.mlflow_cmd import check_mlflow_health
    from urllib.error import URLError

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = URLError("timeout")

        result = check_mlflow_health("http://localhost:5050", timeout=5)

        assert result is False


def test_check_mlflow_health_http_error() -> None:
    """check_mlflow_health returns False on HTTP error."""
    from sandboxctl.mlflow_cmd import check_mlflow_health
    from urllib.error import HTTPError

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError("http://localhost:5050/health", 500, "Internal Server Error", {}, None)

        result = check_mlflow_health("http://localhost:5050", timeout=5)

        assert result is False


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
