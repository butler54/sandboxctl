"""Open an existing sandbox: OpenCode, Claude Code, VS Code, or shell."""

from __future__ import annotations

import subprocess

import typer

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig, find_vscode_bin
from sandboxctl.extensions import classify_remote_extensions, install_extensions
from sandboxctl.health import diagnose, resolve_ssh_host


def _get_default_repo(name: str, config: SandboxctlConfig) -> str:
    """Return profile.sandbox.default_repo, or empty string if no profile."""
    try:
        from sandboxctl.profile import load_profile

        profile = load_profile(name, config)
        return profile.sandbox.default_repo
    except FileNotFoundError:
        return ""


def _warn_policy_drift(name: str, config: SandboxctlConfig) -> None:
    """Echo a best-effort warning when the sandbox's profile policy has drifted."""
    try:
        from sandboxctl.policy import policy_drift_state, resolve_policy_profile

        profile_name = resolve_policy_profile(name, config)
        if profile_name is None:
            return
        state = policy_drift_state(name, profile_name, config)
        if state.status == "network-drift":
            typer.echo(
                "WARNING: profile policy differs from this sandbox (rule changes pending); "
                f"run 'sandboxctl policy sync {name}'"
            )
        elif state.status == "filesystem-drift":
            typer.echo(
                "WARNING: profile filesystem policy differs from this sandbox; "
                f"recreate with 'sandboxctl restart {name}'"
            )
    except Exception:  # noqa: BLE001, S110
        pass


def open_sandbox(
    name: str,
    config: SandboxctlConfig,
    mode: str = "opencode",
    new_session: bool = False,
) -> None:
    # VSCODE-04 Layer 2: Container-death recovery
    report = diagnose(name, auto_recover=True)
    if not report.healthy:
        for detail in report.details:
            typer.echo(f"  {detail}")
        typer.echo(f"Sandbox '{name}' is not healthy: {report.recovery_action}")
        raise typer.Exit(1)

    # Policy lifecycle (#207): surface profile policy drift made after create.
    _warn_policy_drift(name, config)

    # VSCODE-04 Layer 1: SSH keepalive for network-blip resilience
    osh.ensure_ssh_keepalive()

    if mode == "shell":
        osh.sandbox_connect(name)
        return

    # ── VS Code launch (shared by "code", "code-only", "both") ───────────────
    if mode in ("both", "code"):
        vscode_bin = find_vscode_bin()
        if not vscode_bin:
            typer.echo("WARNING: 'code' CLI not found. Skipping VS Code.")
        else:
            ssh_host = resolve_ssh_host(name) or f"openshell-{name}"

            # Install extensions before GUI launch (EXT-02, D-09, D-11)
            try:
                from sandboxctl.profile import load_profile

                profile = load_profile(name, config)
                remote = classify_remote_extensions(profile.extensions)
                if remote:
                    ext_report = install_extensions(ssh_host, remote, vscode_bin)
                    installed_count = len(ext_report.installed)
                    skipped_count = len(ext_report.skipped_invalid)
                    failed_count = len(ext_report.failed)
                    summary = f"Extensions: {installed_count} installed, {skipped_count} skipped, {failed_count} failed"
                    typer.echo(summary)
            except FileNotFoundError:
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

    # ── OpenCode (interactive) ────────────────────────────────────────────────
    if mode in ("both", "opencode"):
        default_repo = _get_default_repo(name, config)
        base_dir = f"/sandbox/workspace/{default_repo}" if default_repo else "/sandbox"

        if new_session:
            typer.echo(f"Launching OpenCode (new session) in: {base_dir}")
            result = osh.sandbox_exec_interactive(name, f"cd {base_dir} && opencode")
        else:
            # 003-opencode-open-continue: resume the most recent session by
            # default (FR-001); fall back to a fresh session when there is
            # nothing to resume (FR-003), mirroring the claude-mode pattern.
            typer.echo(f"Resuming OpenCode session in: {base_dir}")
            result = osh.sandbox_exec_interactive(name, f"cd {base_dir} && opencode -c")
            if result != 0:
                typer.echo("Starting new OpenCode session...")
                result = osh.sandbox_exec_interactive(name, f"cd {base_dir} && opencode")

        if result != 0:
            typer.echo("\nCould not start OpenCode. Connecting via shell.")
            typer.echo(f"  Run inside sandbox: cd {base_dir} && opencode")
            osh.sandbox_connect(name)
        return

    # ── OpenCode server mode ──────────────────────────────────────────────────
    if mode == "opencode-server":
        port = 4096
        ssh_host = resolve_ssh_host(name) or f"openshell-{name}"

        osh.sandbox_exec_pipe(
            name,
            f"nohup opencode serve --port {port} --hostname 0.0.0.0 > /sandbox/.opencode-server.log 2>&1 & echo $!",
        )

        subprocess.Popen(  # noqa: S603
            ["ssh", "-fNL", f"{port}:localhost:{port}", ssh_host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        typer.echo(f"OpenCode server started (port {port})")
        typer.echo("  Log: /sandbox/.opencode-server.log")
        typer.echo(f"  Connect with: opencode attach http://localhost:{port}")
        return

    # ── Claude Code (legacy / explicit --claude-only) ─────────────────────────
    if mode == "claude":
        default_repo = _get_default_repo(name, config)
        base_dir = f"/sandbox/workspace/{default_repo}" if default_repo else "/sandbox"

        if new_session:
            # 003-opencode-open-continue (FR-005): --new skips the resume attempt.
            typer.echo(f"Starting new Claude Code session in: {base_dir}")
            result = osh.sandbox_exec_interactive(name, f"cd {base_dir} && claude")
        else:
            typer.echo(f"Resuming Claude Code session in: {base_dir}")
            resume_cmd = f"cd {base_dir} && claude --continue"
            result = osh.sandbox_exec_interactive(name, resume_cmd)

            if result == 0:
                return

            typer.echo("Starting new Claude Code session...")
            fresh_cmd = f"cd {base_dir} && claude"
            result = osh.sandbox_exec_interactive(name, fresh_cmd)

        if result != 0:
            typer.echo("\nExisting session may be running. Reconnecting via shell.")
            typer.echo(f"  Resume with: cd {base_dir} && claude --continue")
            osh.sandbox_connect(name)
