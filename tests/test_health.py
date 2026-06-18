"""Tests for container health checks and recovery."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from sandboxctl.health import (
    ContainerState,
    GatewayState,
    HealthReport,
    check_container_state,
    check_gateway_state,
    diagnose,
)


class TestGatewayState:
    def test_running(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0)
            assert check_gateway_state() == GatewayState.RUNNING

    def test_stopped(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=1)
            assert check_gateway_state() == GatewayState.STOPPED

    def test_missing(self) -> None:
        with patch("sandboxctl.health._run", side_effect=FileNotFoundError):
            assert check_gateway_state() == GatewayState.MISSING

    def test_timeout(self) -> None:
        with patch("sandboxctl.health._run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
            assert check_gateway_state() == GatewayState.UNKNOWN


class TestContainerState:
    def test_running(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="Up 2 hours")
            assert check_container_state("test") == ContainerState.RUNNING

    def test_stopped(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="Exited (0) 5 minutes ago")
            assert check_container_state("test") == ContainerState.STOPPED

    def test_missing(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="")
            assert check_container_state("test") == ContainerState.MISSING

    def test_paused(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="Paused")
            assert check_container_state("test") == ContainerState.PAUSED


class TestHealthReport:
    def test_healthy(self) -> None:
        report = HealthReport(
            sandbox_name="test",
            container_state=ContainerState.RUNNING,
            gateway_state=GatewayState.RUNNING,
            ssh_reachable=True,
            recovery_action="none",
            details=[],
        )
        assert report.healthy is True

    def test_unhealthy_stopped(self) -> None:
        report = HealthReport(
            sandbox_name="test",
            container_state=ContainerState.STOPPED,
            gateway_state=GatewayState.RUNNING,
            ssh_reachable=False,
            recovery_action="container_restarted",
            details=[],
        )
        assert report.healthy is False


class TestDiagnose:
    def test_healthy_sandbox(self) -> None:
        with patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.RUNNING), patch(
            "sandboxctl.health.check_container_state", return_value=ContainerState.RUNNING
        ), patch("sandboxctl.health.check_ssh_connectivity", return_value=True):
            report = diagnose("test")
            assert report.healthy is True
            assert report.recovery_action == "none"

    def test_stopped_container_auto_recovers(self) -> None:
        with patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.RUNNING), patch(
            "sandboxctl.health.check_container_state", return_value=ContainerState.STOPPED
        ), patch("sandboxctl.health.recover_container", return_value=True), patch(
            "sandboxctl.health.check_ssh_connectivity", return_value=True
        ):
            report = diagnose("test", auto_recover=True)
            assert report.recovery_action == "container_restarted"

    def test_missing_container_needs_recreate(self) -> None:
        with patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.RUNNING), patch(
            "sandboxctl.health.check_container_state", return_value=ContainerState.MISSING
        ):
            report = diagnose("test")
            assert report.recovery_action == "container_missing_needs_recreate"
            assert not report.healthy

    def test_gateway_down_auto_recovers(self) -> None:
        with patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.STOPPED), patch(
            "sandboxctl.health.recover_gateway", return_value=True
        ), patch("sandboxctl.health.check_container_state", return_value=ContainerState.RUNNING), patch(
            "sandboxctl.health.check_ssh_connectivity", return_value=True
        ):
            report = diagnose("test", auto_recover=True)
            assert report.recovery_action == "gateway_restarted"

    def test_no_auto_recover(self) -> None:
        with patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.STOPPED):
            report = diagnose("test", auto_recover=False)
            assert report.recovery_action == "gateway_not_running"
            assert not report.healthy
