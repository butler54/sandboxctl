"""Tests for container health checks and recovery."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from sandboxctl.health import (
    _CONTAINER_PREFIX,
    ComputeState,
    ContainerState,
    GatewayApiState,
    GatewayState,
    HealthReport,
    check_compute_state,
    check_container_state,
    check_disk_usage,
    check_gateway_api_state,
    check_gateway_state,
    check_ssh_connectivity,
    diagnose,
    recover_container,
    recover_gateway,
    resolve_container_name,
    resolve_ssh_host,
)
from sandboxctl.openshell import SandboxError


class TestGatewayState:
    def test_running_on_darwin(self) -> None:
        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch("sandboxctl.health._run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            mock_run.return_value = MagicMock(returncode=0)
            assert check_compute_state() == ComputeState.RUNNING

    def test_stopped_on_darwin(self) -> None:
        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch("sandboxctl.health._run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            mock_run.return_value = MagicMock(returncode=1)
            assert check_compute_state() == ComputeState.STOPPED

    def test_running_on_linux(self) -> None:
        with patch("sandboxctl.health.sys") as mock_sys, patch("sandboxctl.health._run") as mock_run:
            mock_sys.platform = "linux"
            mock_run.return_value = MagicMock(returncode=0)
            assert check_compute_state() == ComputeState.RUNNING

    def test_missing(self) -> None:
        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch("sandboxctl.health._run", side_effect=FileNotFoundError),
        ):
            mock_sys.platform = "darwin"
            assert check_compute_state() == ComputeState.MISSING

    def test_timeout(self) -> None:
        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch("sandboxctl.health._run", side_effect=subprocess.TimeoutExpired("cmd", 10)),
        ):
            mock_sys.platform = "darwin"
            assert check_compute_state() == ComputeState.UNKNOWN

    def test_service_running_on_linux(self) -> None:
        with patch("sandboxctl.health.sys") as mock_sys, patch("sandboxctl.health._run") as mock_run:
            mock_sys.platform = "linux"
            mock_run.return_value = MagicMock(returncode=0, stdout="LoadState=loaded\nActiveState=active\n")
            assert check_gateway_state() == GatewayState.RUNNING

    def test_service_missing_on_linux(self) -> None:
        with patch("sandboxctl.health.sys") as mock_sys, patch("sandboxctl.health._run") as mock_run:
            mock_sys.platform = "linux"
            mock_run.return_value = MagicMock(returncode=0, stdout="LoadState=not-found\nActiveState=inactive\n")
            assert check_gateway_state() == GatewayState.MISSING

    def test_api_unreachable(self) -> None:
        with patch("sandboxctl.openshell.gateway_status", side_effect=SandboxError):
            assert check_gateway_api_state() == GatewayApiState.UNREACHABLE

    def test_api_disconnected(self) -> None:
        with patch("sandboxctl.openshell.gateway_status", return_value={"status": "Disconnected"}):
            assert check_gateway_api_state() == GatewayApiState.UNREACHABLE

    def test_api_connected(self) -> None:
        with patch("sandboxctl.openshell.gateway_status", return_value={"status": "Connected"}):
            assert check_gateway_api_state() == GatewayApiState.RUNNING


class TestDiskUsage:
    def test_warn_threshold(self) -> None:
        with patch(
            "sandboxctl.health._run",
            return_value=MagicMock(
                returncode=0,
                stdout="Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/vda 100 80 20 80% /\n",
            ),
        ):
            result = check_disk_usage()
        assert result is not None
        assert result.severity == "warn"

    def test_fail_threshold(self) -> None:
        with patch(
            "sandboxctl.health._run",
            return_value=MagicMock(
                returncode=0,
                stdout="Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/vda 100 90 10 90% /\n",
            ),
        ):
            result = check_disk_usage()
        assert result is not None
        assert result.severity == "fail"


class TestResolveContainerName:
    def test_matches_legacy_name(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout=f"{_CONTAINER_PREFIX}mybox\n")
            assert resolve_container_name("mybox") == f"{_CONTAINER_PREFIX}mybox"

    def test_matches_workspace_scoped_name(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(
                returncode=0,
                stdout="openshell-default--mybox-8b9c3917-fcf7-4b3a-bb20-273c0b9ef1d3\n",
            )
            assert resolve_container_name("mybox") == "openshell-default--mybox-8b9c3917-fcf7-4b3a-bb20-273c0b9ef1d3"

    def test_no_match_returns_none(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="some-unrelated-container\n")
            assert resolve_container_name("mybox") is None

    def test_podman_failure_returns_none(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="")
            assert resolve_container_name("mybox") is None

    def test_not_found_returns_none(self) -> None:
        with patch("sandboxctl.health._run", side_effect=FileNotFoundError):
            assert resolve_container_name("mybox") is None


class TestContainerState:
    def test_running(self) -> None:
        with (
            patch("sandboxctl.health.resolve_container_name", return_value=f"{_CONTAINER_PREFIX}test"),
            patch("sandboxctl.health._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=0, stdout="Up 2 hours")
            assert check_container_state("test") == ContainerState.RUNNING

    def test_uses_resolved_name(self) -> None:
        with (
            patch("sandboxctl.health.resolve_container_name", return_value=f"{_CONTAINER_PREFIX}mybox"),
            patch("sandboxctl.health._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=0, stdout="Up 2 hours")
            check_container_state("mybox")
            cmd = mock.call_args[0][0]
            assert f"name=^{_CONTAINER_PREFIX}mybox$" in " ".join(cmd)

    def test_stopped(self) -> None:
        with (
            patch("sandboxctl.health.resolve_container_name", return_value=f"{_CONTAINER_PREFIX}test"),
            patch("sandboxctl.health._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=0, stdout="Exited (0) 5 minutes ago")
            assert check_container_state("test") == ContainerState.STOPPED

    def test_missing_when_not_resolvable(self) -> None:
        with patch("sandboxctl.health.resolve_container_name", return_value=None):
            assert check_container_state("test") == ContainerState.MISSING

    def test_paused(self) -> None:
        with (
            patch("sandboxctl.health.resolve_container_name", return_value=f"{_CONTAINER_PREFIX}test"),
            patch("sandboxctl.health._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=0, stdout="Paused")
            assert check_container_state("test") == ContainerState.PAUSED


class TestHealthReport:
    def test_healthy(self) -> None:
        report = HealthReport(
            sandbox_name="test",
            container_state=ContainerState.RUNNING,
            compute_state=ComputeState.RUNNING,
            gateway_state=GatewayState.RUNNING,
            gateway_api_state=GatewayApiState.RUNNING,
            ssh_reachable=True,
            recovery_action="none",
            details=[],
        )
        assert report.healthy is True

    def test_unhealthy_stopped(self) -> None:
        report = HealthReport(
            sandbox_name="test",
            container_state=ContainerState.STOPPED,
            compute_state=ComputeState.RUNNING,
            gateway_state=GatewayState.RUNNING,
            gateway_api_state=GatewayApiState.RUNNING,
            ssh_reachable=False,
            recovery_action="container_restarted",
            details=[],
        )
        assert report.healthy is False


class TestDiagnose:
    def test_healthy_sandbox(self) -> None:
        with (
            patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.RUNNING),
            patch("sandboxctl.health.check_compute_state", return_value=ComputeState.RUNNING),
            patch("sandboxctl.health.check_gateway_api_state", return_value=GatewayApiState.RUNNING),
            patch("sandboxctl.health.check_container_state", return_value=ContainerState.RUNNING),
            patch("sandboxctl.health.check_ssh_connectivity", return_value=True),
        ):
            report = diagnose("test")
            assert report.healthy is True
            assert report.recovery_action == "none"

    def test_stopped_container_auto_recovers(self) -> None:
        with (
            patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.RUNNING),
            patch("sandboxctl.health.check_compute_state", return_value=ComputeState.RUNNING),
            patch("sandboxctl.health.check_gateway_api_state", return_value=GatewayApiState.RUNNING),
            patch("sandboxctl.health.check_container_state", return_value=ContainerState.STOPPED),
            patch("sandboxctl.health.recover_container", return_value=True),
            patch("sandboxctl.health.check_ssh_connectivity", return_value=True),
        ):
            report = diagnose("test", auto_recover=True)
            assert report.recovery_action == "container_restarted"

    def test_missing_container_needs_recreate(self) -> None:
        with (
            patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.RUNNING),
            patch("sandboxctl.health.check_compute_state", return_value=ComputeState.RUNNING),
            patch("sandboxctl.health.check_gateway_api_state", return_value=GatewayApiState.RUNNING),
            patch("sandboxctl.health.check_container_state", return_value=ContainerState.MISSING),
        ):
            report = diagnose("test")
            assert report.recovery_action == "container_missing_needs_recreate"
            assert not report.healthy

    def test_gateway_down_auto_recovers(self) -> None:
        with (
            patch(
                "sandboxctl.health.check_gateway_state",
                side_effect=[GatewayState.STOPPED, GatewayState.RUNNING],
            ),
            patch("sandboxctl.health.check_compute_state", return_value=ComputeState.RUNNING),
            patch("sandboxctl.health.recover_gateway", return_value=True),
            patch("sandboxctl.health.check_gateway_api_state", return_value=GatewayApiState.RUNNING),
            patch("sandboxctl.health.check_container_state", return_value=ContainerState.RUNNING),
            patch("sandboxctl.health.check_ssh_connectivity", return_value=True),
        ):
            report = diagnose("test", auto_recover=True)
            assert report.recovery_action == "gateway_restarted"

    def test_no_auto_recover(self) -> None:
        with (
            patch("sandboxctl.health.check_compute_state", return_value=ComputeState.RUNNING),
            patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.STOPPED),
        ):
            report = diagnose("test", auto_recover=False)
            assert report.recovery_action == "gateway_not_running"
            assert not report.healthy

    def test_gateway_recovery_failure(self) -> None:
        with (
            patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.STOPPED),
            patch("sandboxctl.health.check_compute_state", return_value=ComputeState.RUNNING),
            patch("sandboxctl.health.recover_gateway", return_value=False),
        ):
            report = diagnose("test", auto_recover=True)
            assert report.recovery_action == "gateway_recovery_failed"
            assert not report.healthy

    def test_container_recovery_failure(self) -> None:
        with (
            patch("sandboxctl.health.check_gateway_state", return_value=GatewayState.RUNNING),
            patch("sandboxctl.health.check_compute_state", return_value=ComputeState.RUNNING),
            patch("sandboxctl.health.check_gateway_api_state", return_value=GatewayApiState.RUNNING),
            patch("sandboxctl.health.check_container_state", return_value=ContainerState.STOPPED),
            patch("sandboxctl.health.recover_container", return_value=False),
        ):
            report = diagnose("test", auto_recover=True)
            assert report.recovery_action == "container_recovery_failed"


class TestSshConnectivity:
    def test_reachable(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="ok")
            assert check_ssh_connectivity("test") is True

    def test_prefers_workspace_scoped_alias(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="ok")
            check_ssh_connectivity("mybox")
            cmd = mock.call_args[0][0]
            assert "openshell-mybox.default" in cmd

    def test_falls_back_to_bare_alias(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            # First attempt (.default) fails, second (bare) succeeds
            mock.side_effect = [
                MagicMock(returncode=1, stdout=""),
                MagicMock(returncode=0, stdout="ok"),
            ]
            assert check_ssh_connectivity("mybox") is True
            assert mock.call_count == 2
            second_cmd = mock.call_args_list[1][0][0]
            assert "openshell-mybox" in second_cmd
            assert "openshell-mybox.default" not in second_cmd

    def test_unreachable(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="")
            assert check_ssh_connectivity("test") is False

    def test_timeout(self) -> None:
        with patch("sandboxctl.health._run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            assert check_ssh_connectivity("test") is False

    def test_not_found(self) -> None:
        with patch("sandboxctl.health._run", side_effect=FileNotFoundError):
            assert check_ssh_connectivity("test") is False

    def test_resolve_ssh_host_returns_none_when_unreachable(self) -> None:
        with patch("sandboxctl.health._run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="")
            assert resolve_ssh_host("test") is None


class TestRecoveryFunctions:
    def test_recover_gateway_success_on_darwin(self) -> None:
        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch("sandboxctl.health._run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            mock_run.return_value = MagicMock(returncode=0)
            assert recover_gateway() is True

    def test_recover_gateway_restarts_service_on_linux(self) -> None:
        with patch("sandboxctl.health.sys") as mock_sys, patch("sandboxctl.health._run") as mock_run:
            mock_sys.platform = "linux"
            mock_run.return_value = MagicMock(returncode=0)
            assert recover_gateway() is True
            assert mock_run.call_args.args[0] == ["systemctl", "--user", "restart", "openshell-gateway"]

    def test_recover_gateway_failure(self) -> None:
        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch("sandboxctl.health._run", side_effect=FileNotFoundError),
        ):
            mock_sys.platform = "darwin"
            assert recover_gateway() is False

    def test_recover_gateway_timeout(self) -> None:
        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch("sandboxctl.health._run", side_effect=subprocess.TimeoutExpired("cmd", 60)),
        ):
            mock_sys.platform = "darwin"
            assert recover_gateway() is False

    def test_recover_container_success(self) -> None:
        with (
            patch("sandboxctl.health.resolve_container_name", return_value=f"{_CONTAINER_PREFIX}test"),
            patch("sandboxctl.health._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=0)
            assert recover_container("test") is True

    def test_recover_container_uses_resolved_name(self) -> None:
        with (
            patch("sandboxctl.health.resolve_container_name", return_value=f"{_CONTAINER_PREFIX}mybox"),
            patch("sandboxctl.health._run") as mock,
        ):
            mock.return_value = MagicMock(returncode=0)
            recover_container("mybox")
            cmd = mock.call_args[0][0]
            assert f"{_CONTAINER_PREFIX}mybox" in cmd

    def test_recover_container_failure(self) -> None:
        with (
            patch("sandboxctl.health.resolve_container_name", return_value=f"{_CONTAINER_PREFIX}test"),
            patch("sandboxctl.health._run", side_effect=FileNotFoundError),
        ):
            assert recover_container("test") is False

    def test_recover_container_missing_returns_false(self) -> None:
        with patch("sandboxctl.health.resolve_container_name", return_value=None):
            assert recover_container("test") is False


class TestPodmanEnv:
    def test_darwin_sets_machine_provider(self) -> None:
        from sandboxctl.health import _podman_env

        with patch("sandboxctl.health.sys") as mock_sys:
            mock_sys.platform = "darwin"
            env = _podman_env()
            assert env is not None
            assert env["CONTAINERS_MACHINE_PROVIDER"] == "applehv"

    def test_darwin_preserves_existing_provider(self) -> None:
        from sandboxctl.health import _podman_env

        with (
            patch("sandboxctl.health.sys") as mock_sys,
            patch.dict("os.environ", {"CONTAINERS_MACHINE_PROVIDER": "libkrun"}),
        ):
            mock_sys.platform = "darwin"
            env = _podman_env()
            assert env is not None
            assert env["CONTAINERS_MACHINE_PROVIDER"] == "libkrun"

    def test_linux_returns_none(self) -> None:
        from sandboxctl.health import _podman_env

        with patch("sandboxctl.health.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert _podman_env() is None
