"""Smoke test for CLI entry point."""

from typer.testing import CliRunner

from sandboxctl.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "sandboxctl" in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sandboxctl" in result.output
