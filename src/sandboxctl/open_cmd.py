"""Open an existing sandbox: Claude Code, VS Code, or shell."""

from __future__ import annotations

import subprocess

import typer

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig, find_vscode_bin
from sandboxctl.health import diagnose


def open_sandbox(
    name: str,
    config: SandboxctlConfig,
    mode: str = "claude",
) -> None:
    report = diagnose(name, auto_recover=True)
    if not report.healthy:
        for detail in report.details:
            typer.echo(f"  {detail}")
        typer.echo(f"Sandbox '{name}' is not healthy: {report.recovery_action}")
        raise typer.Exit(1)

    if mode == "shell":
        osh.sandbox_connect(name)
        return

    if mode in ("both", "code"):
        vscode_bin = find_vscode_bin()
        if not vscode_bin:
            typer.echo("WARNING: 'code' CLI not found. Skipping VS Code.")
        else:
            workspace = f"/sandbox/workspace/{name}.code-workspace"
            has_ws = osh.sandbox_exec_pipe(
                name,
                f'test -f {workspace} && echo "yes" || echo "no"',
            )
            if "yes" in has_ws:
                typer.echo(f"Opening VS Code workspace: {name}")
                subprocess.run(
                    [str(vscode_bin), "--remote", f"ssh-remote+openshell-{name}", workspace],
                    check=False,
                )
            else:
                typer.echo(f"Opening VS Code: {name} (no workspace file)")
                osh.sandbox_connect(name, editor="vscode")

    if mode in ("both", "claude"):
        default_repo = ""
        try:
            from sandboxctl.profile import load_profile

            profile = load_profile(name, config)
            default_repo = profile.sandbox.default_repo
        except FileNotFoundError:
            pass

        if default_repo:
            base_dir = f"/sandbox/workspace/{default_repo}"
        else:
            base_dir = "/sandbox"

        # Try --continue first to resume existing session
        typer.echo(f"Resuming Claude Code session in: {base_dir}")
        resume_cmd = f"cd {base_dir} && claude --continue"
        result = osh.sandbox_exec_interactive(name, resume_cmd)

        if result == 0:
            return

        # Fallback to fresh session
        typer.echo("Starting new Claude Code session...")
        fresh_cmd = f"cd {base_dir} && claude"
        result = osh.sandbox_exec_interactive(name, fresh_cmd)

        if result != 0:
            typer.echo("\nExisting session may be running. Reconnecting via shell.")
            typer.echo(f"  Resume with: cd {base_dir} && claude --continue")
            osh.sandbox_connect(name)
