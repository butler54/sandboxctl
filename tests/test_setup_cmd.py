"""Tests for setup_cmd module (onboarding steps, including MLflow)."""

from __future__ import annotations

import pytest


def test_setup_mlflow_prompted() -> None:
    """Setup prompts for optional MLflow tracking server installation."""
    from unittest.mock import MagicMock, patch
    from pathlib import Path
    import tempfile

    from sandboxctl.config import MlflowConfig, SandboxctlConfig
    from sandboxctl.setup_cmd import _setup_mlflow

    # Scenario 1: user opts in, container not running → start called
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=True, port=5050, data_dir=Path(tmpdir))
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)

        with (
            patch("sandboxctl.setup_cmd.typer.confirm", return_value=True) as mock_confirm,
            patch("sandboxctl.mlflow_cmd.is_mlflow_running", return_value=False),
            patch("sandboxctl.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.setup_cmd.typer.echo") as mock_echo,
        ):
            _setup_mlflow(config)

            # Confirm was called
            mock_confirm.assert_called_once()
            # Start was called
            mock_start.assert_called_once_with(Path(tmpdir), 5050)

    # Scenario 2: user opts in, container already running → skip start
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=True, port=5050, data_dir=Path(tmpdir))
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)

        with (
            patch("sandboxctl.setup_cmd.typer.confirm", return_value=True),
            patch("sandboxctl.mlflow_cmd.is_mlflow_running", return_value=True),
            patch("sandboxctl.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.setup_cmd.typer.echo") as mock_echo,
        ):
            _setup_mlflow(config)

            # Start was not called
            mock_start.assert_not_called()

    # Scenario 3: user declines → no start
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=True, port=5050, data_dir=Path(tmpdir))
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)

        with (
            patch("sandboxctl.setup_cmd.typer.confirm", return_value=False),
            patch("sandboxctl.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.setup_cmd.typer.echo") as mock_echo,
        ):
            _setup_mlflow(config)

            # Start was not called
            mock_start.assert_not_called()

    # Scenario 4: external mode (managed=False) → skip without prompting
    with tempfile.TemporaryDirectory() as tmpdir:
        mlflow_cfg = MlflowConfig(managed=False, tracking_uri="https://external.mlflow.example.com")
        config = SandboxctlConfig(config_dir=Path(tmpdir), mlflow=mlflow_cfg)

        with (
            patch("sandboxctl.setup_cmd.typer.confirm") as mock_confirm,
            patch("sandboxctl.mlflow_cmd.start_mlflow_container") as mock_start,
            patch("sandboxctl.setup_cmd.typer.echo") as mock_echo,
        ):
            _setup_mlflow(config)

            # No prompt
            mock_confirm.assert_not_called()
            # No start
            mock_start.assert_not_called()
