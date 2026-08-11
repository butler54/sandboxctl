"""Open an existing sandbox: Claude Code, VS Code, or shell."""

from __future__ import annotations

import subprocess

import typer

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig, find_vscode_bin
from sandboxctl.extensions import classify_remote_extensions, install_extensions
from sandboxctl.health import diagnose, resolve_ssh_host


def open_sandbox(
    name: str,
    config: SandboxctlConfig,
    mode: str = "claude",
) -> None:
    # VSCODE-04 Layer 2: Container-death recovery
    report = diagnose(name, auto_recover=True)
    if not report.healthy:
        for detail in report.details:
            typer.echo(f"  {detail}")
        typer.echo(f"Sandbox '{name}' is not healthy: {report.recovery_action}")
        raise typer.Exit(1)

    # VSCODE-04 Layer 1: SSH keepalive for network-blip resilience
    osh.ensure_ssh_keepalive()

    if mode == "shell":
        osh.sandbox_connect(name)
        return

    if mode in ("both", "code"):
        vscode_bin = find_vscode_bin()
        if not vscode_bin:
            typer.echo("WARNING: 'code' CLI not found. Skipping VS Code.")
        else:
            # Resolve the live SSH alias — OpenShell has used both bare
            # openshell-<name> and workspace-scoped openshell-<name>.<workspace>
            # aliases across versions (health check above already confirmed
            # one of them is reachable).
            ssh_host = resolve_ssh_host(name) or f"openshell-{name}"

            # Install extensions before GUI launch (EXT-02, D-09, D-11)
            try:
                from sandboxctl.profile import load_profile

                profile = load_profile(name, config)
                remote = classify_remote_extensions(profile.extensions)
                if remote:
                    report = install_extensions(ssh_host, remote, vscode_bin)
                    installed_count = len(report.installed)
                    skipped_count = len(report.skipped_invalid)
                    failed_count = len(report.failed)
                    summary = f"Extensions: {installed_count} installed, {skipped_count} skipped, {failed_count} failed"
                    typer.echo(summary)
            except FileNotFoundError:
                # No profile, skip extension install
                pass

            workspace = f"/sandbox/workspace/{name}.code-workspace"
            has_ws = osh.sandbox_exec_pipe(
                name,
                f'test -f {workspace} && echo "yes" || echo "no"',
            )
            if "yes" in has_ws:
                typer.echo(f"Opening VS Code workspace: {name}")
                subprocess.run(
                    [str(vscode_bin), "--remote", f"ssh-remote+{ssh_host}", workspace],
                    check=False,
                )
            else:
                typer.echo(f"Opening VS Code: {name} (no workspace file)")
                osh.sandbox_connect(name, editor="vscode")

    if mode in ("both", "claude"):
        # Launch Claude Code in the current terminal session (inline, not a new window).
        # Determine the starting directory from the profile's default_repo if set.
        default_repo = ""
        try:
            from sandboxctl.profile import load_profile

            profile = load_profile(name, config)
            default_repo = profile.sandbox.default_repo
        except FileNotFoundError:
            pass

        if default_repo:
            typer.echo(f"Launching Claude Code in: {default_repo}")
            cmd = f"cd /sandbox/workspace/{default_repo} && claude"
        else:
            typer.echo(f"Launching Claude Code in sandbox: {name}")
            cmd = "claude"

        result = osh.sandbox_exec_interactive(name, cmd)
        if result != 0:
            typer.echo("\nAn existing session is running. Reconnecting via shell.")
            if default_repo:
                typer.echo(f"  Resume with: cd /sandbox/workspace/{default_repo} && claude --continue")
            else:
                typer.echo("  Resume with: claude --continue")
            osh.sandbox_connect(name)
