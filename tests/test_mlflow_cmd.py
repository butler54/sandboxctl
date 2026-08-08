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


@pytest.mark.skip(reason="implemented in 21-02")
def test_start_mlflow_container() -> None:
    """Start command creates data_dir and runs podman with correct args."""
    # Wave 0 stub — implementation in Plan 21-02
    pass


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
