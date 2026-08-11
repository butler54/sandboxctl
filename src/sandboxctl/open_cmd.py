"""Open an existing sandbox: Claude Code, VS Code, or shell."""

from __future__ import annotations

import subprocess

import typer

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig, find_terminal_app, find_vscode_bin
from sandboxctl.extensions import classify_remote_extensions, install_extensions
from sandboxctl.health import diagnose, resolve_ssh_host

_APPLE_EVENTS_AUTH_ERROR = "-1743"
_APPLE_EVENTS_HELP = (
    "Fix: System Settings → Privacy & Security → Automation\n     Allow the app running sandboxctl to control {app}."
)


def _run_osascript(script: str, app_display_name: str, command: str) -> None:
    """Run osascript, detect -1743 auth errors, and show actionable help."""
    result = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if _APPLE_EVENTS_AUTH_ERROR in stderr:
            typer.echo(
                f"ERROR: macOS blocked Apple Events to {app_display_name} ({_APPLE_EVENTS_AUTH_ERROR}).\n"
                + _APPLE_EVENTS_HELP.format(app=app_display_name),
                err=True,
            )
            typer.echo(f"\nRun manually:\n  {command}")
        elif stderr:
            typer.echo(f"WARNING: osascript error: {stderr}", err=True)
            typer.echo(f"\nRun manually:\n  {command}")


def spawn_terminal_with_claude(sandbox_name: str, terminal_app: str | None) -> None:
    """Spawn external terminal app running Claude Code session.

    Args:
        sandbox_name: Validated sandbox name (already validated at CLI boundary)
        terminal_app: "iTerm", "Terminal", or None (print manual command)
    """
    command = f"openshell sandbox connect {sandbox_name} && claude"

    if terminal_app == "iTerm":
        script = f'''
        tell application "iTerm2"
          set newWindow to (create window with default profile)
          tell current session of newWindow
            write text "{command}"
          end tell
        end tell
        '''
        _run_osascript(script, "iTerm2", command)
    elif terminal_app == "Terminal":
        script = f'''
        tell application "Terminal"
          do script "{command}"
        end tell
        '''
        _run_osascript(script, "Terminal", command)
    else:
        # Fallback: print manual command
        typer.echo("WARNING: No terminal app detected. Run manually:")
        typer.echo(f"  {command}")


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
        # Resolve terminal app: profile override or auto-detect
        terminal_app = None
        try:
            from sandboxctl.profile import load_profile

            profile = load_profile(name, config)
            terminal_app = profile.workspace.terminal_app or find_terminal_app()
        except FileNotFoundError:
            terminal_app = find_terminal_app()

        # Spawn external terminal running Claude Code
        typer.echo(f"Launching Claude Code in external terminal: {name}")
        spawn_terminal_with_claude(name, terminal_app)
