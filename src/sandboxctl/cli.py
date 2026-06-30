"""CLI entry point."""

from __future__ import annotations

import re

import typer
from rich.table import Table

from sandboxctl.config import CONFIG_TEMPLATE, ensure_config_dir, load_config

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _validate_name(value: str) -> str:
    if not _NAME_RE.match(value):
        msg = (
            f"Invalid name '{value}': must start with alphanumeric, "
            "contain only alphanumeric, dots, hyphens, underscores"
        )
        raise typer.BadParameter(msg)
    return value


app = typer.Typer(
    name="sandboxctl",
    help="OpenShell sandbox management CLI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

config_app = typer.Typer(help="Manage sandboxctl configuration.")
app.add_typer(config_app, name="config")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    show_version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    """OpenShell sandbox management CLI."""
    if show_version:
        from sandboxctl import __version__

        typer.echo(f"sandboxctl {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@config_app.command("init")
def config_init() -> None:
    """Create default configuration file."""
    cfg = load_config()
    ensure_config_dir(cfg)
    config_file = cfg.config_dir / "config.toml"
    if config_file.exists():
        typer.echo(f"Config already exists: {config_file}")
        raise typer.Exit(1)
    config_file.write_text(CONFIG_TEMPLATE)
    typer.echo(f"Created {config_file}")


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    cfg = load_config()
    typer.echo(f"Config dir:    {cfg.config_dir}")
    typer.echo(f"Profiles dir:  {cfg.profiles_dir}")
    typer.echo(f"SSH key:       {cfg.ssh_key}")
    typer.echo(f"Git user:      {cfg.git_user_name or '(not set)'}")
    typer.echo(f"Git email:     {cfg.git_user_email or '(not set)'}")
    typer.echo(f"Model:         {cfg.default_model}")
    typer.echo(f"Theme:         {cfg.default_theme}")
    typer.echo(f"Vertex project:{cfg.vertex_project_id or '(not set)'}")


@config_app.command("path")
def config_path() -> None:
    """Print config file path."""
    cfg = load_config()
    typer.echo(cfg.config_dir / "config.toml")


@app.command("list")
def list_cmd() -> None:
    """List profiles and running sandboxes."""
    from sandboxctl import openshell as osh
    from sandboxctl.profile import list_profiles

    cfg = load_config()
    profiles = list_profiles(cfg)
    if profiles:
        typer.echo("Profiles:")
        for p in profiles:
            typer.echo(f"  {p}")
    else:
        typer.echo("No profiles found.")

    typer.echo()
    try:
        sandboxes = osh.sandbox_list()
        if sandboxes:
            table = Table(title="Running Sandboxes")
            table.add_column("Name")
            table.add_column("Created")
            table.add_column("Phase")
            for sb in sandboxes:
                table.add_row(sb["name"], sb["created"], sb["phase"])
            from rich.console import Console

            Console().print(table)
        else:
            typer.echo("No running sandboxes.")
    except Exception:
        typer.echo("Could not list sandboxes (is openshell running?).")


@app.command()
def status() -> None:
    """Show gateway and sandbox status."""
    from sandboxctl import openshell as osh

    try:
        gw = osh.gateway_status()
        table = Table(title="Gateway")
        table.add_column("Property")
        table.add_column("Value")
        for k, v in gw.items():
            table.add_row(k, v)
        from rich.console import Console

        Console().print(table)
    except Exception:
        typer.echo("Could not reach gateway.")


@app.command()
def create(
    profile: str = typer.Option(..., "--profile", "-p", help="Profile name.", callback=_validate_name),
    name: str | None = typer.Option(
        None, "--name", "-n",
        help="Sandbox name (defaults to profile name).",
        callback=lambda v: _validate_name(v) if v else v,
    ),
    ephemeral: bool = typer.Option(False, "--ephemeral", help="Delete sandbox on exit."),
    no_editor: bool = typer.Option(False, "--no-editor", help="Don't open editor after creation."),
) -> None:
    """Create a sandbox from a profile."""
    from sandboxctl.create import create_sandbox
    from sandboxctl.profile import list_profiles, load_profile

    cfg = load_config()
    try:
        prof = load_profile(profile, cfg)
    except FileNotFoundError:
        typer.echo(f"Profile not found: {profile}")
        typer.echo(f"Available: {', '.join(list_profiles(cfg)) or 'none'}")
        raise typer.Exit(1) from None

    create_sandbox(prof, cfg, sandbox_name=name, ephemeral=ephemeral, open_editor=not no_editor)


@app.command("open")
def open_cmd(
    name: str = typer.Argument(help="Sandbox name.", callback=_validate_name),
    shell: bool = typer.Option(False, "--shell", help="Open interactive shell."),
    code_only: bool = typer.Option(False, "--code-only", help="Open VS Code only."),
    claude_only: bool = typer.Option(False, "--claude-only", help="Open Claude Code only."),
    code: bool = typer.Option(False, "--code", help="Open both VS Code and Claude Code."),
) -> None:
    """Open a sandbox."""
    from sandboxctl.open_cmd import open_sandbox

    cfg = load_config()

    if shell:
        mode = "shell"
    elif code_only:
        mode = "code"
    elif code:
        mode = "both"
    else:
        mode = "claude"

    open_sandbox(name, cfg, mode=mode)


@app.command("delete")
def delete_cmd(name: str = typer.Argument(help="Sandbox name.", callback=_validate_name)) -> None:
    """Delete a sandbox."""
    from sandboxctl import openshell as osh

    typer.confirm(f"Delete sandbox '{name}'?", abort=True)
    osh.sandbox_delete(name)
    typer.echo(f"Deleted sandbox: {name}")


@app.command()
def validate(name: str = typer.Argument(help="Sandbox name.", callback=_validate_name)) -> None:
    """Run validation tests inside a sandbox."""
    from sandboxctl import openshell as osh
    from sandboxctl.health import diagnose

    report = diagnose(name, auto_recover=True)
    if not report.healthy:
        typer.echo(f"Sandbox '{name}' is not healthy. Run 'sandboxctl doctor {name}' for details.")
        raise typer.Exit(1)

    typer.echo(f"Running validation on sandbox: {name}\n")
    result = osh.sandbox_exec_pipe(name, "source /sandbox/.bashrc\nvalidate.sh")
    typer.echo(result)


@app.command("init")
def init_cmd(name: str = typer.Argument(help="Profile name.", callback=_validate_name)) -> None:
    """Create a new profile skeleton."""
    from sandboxctl.profile import init_profile

    cfg = load_config()
    try:
        path = init_profile(name, cfg)
        typer.echo(f"Created profile: {path}")
    except FileExistsError as e:
        typer.echo(str(e))
        raise typer.Exit(1) from e


@app.command()
def upgrade() -> None:
    """Upgrade OpenShell to latest version."""
    import subprocess

    typer.echo("Upgrading OpenShell...")
    subprocess.run(["openshell", "upgrade"], check=False)


@app.command()
def setup() -> None:
    """First-time setup: prerequisites, SSH key, credentials, providers."""
    from sandboxctl.setup_cmd import run_setup

    cfg = load_config()
    run_setup(cfg)


@app.command()
def restart(
    name: str = typer.Argument(help="Sandbox name (must match a profile).", callback=_validate_name),
    no_editor: bool = typer.Option(False, "--no-editor", help="Don't open editor after recreation."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete and recreate a sandbox from its profile."""
    from sandboxctl import openshell as osh
    from sandboxctl.create import create_sandbox
    from sandboxctl.profile import list_profiles, load_profile

    cfg = load_config()
    try:
        prof = load_profile(name, cfg)
    except FileNotFoundError:
        typer.echo(f"Profile not found: {name}")
        typer.echo(f"Available: {', '.join(list_profiles(cfg)) or 'none'}")
        raise typer.Exit(1) from None

    if not yes:
        typer.confirm(
            f"This will destroy sandbox '{name}' and all uncommitted work. Continue?",
            abort=True,
        )

    typer.echo(f"Restarting sandbox: {name}")
    osh.sandbox_delete(name)
    create_sandbox(prof, cfg, sandbox_name=name, open_editor=not no_editor)


@app.command()
def doctor(
    name: str | None = typer.Argument(
        None,
        help="Sandbox name (omit to check all running).",
        callback=lambda v: _validate_name(v) if v else v,
    ),
    fix: bool = typer.Option(False, "--fix", help="Re-inject credentials into running sandbox(es)."),
    no_recover: bool = typer.Option(False, "--no-recover", help="Skip auto-recovery, diagnose only."),
) -> None:
    """Diagnose sandbox health, credentials, and profile readiness."""
    from sandboxctl import openshell as osh
    from sandboxctl.doctor import (
        check_host_credentials,
        check_profile_readiness,
        fix_sandbox_credentials,
    )
    from sandboxctl.health import diagnose as health_diagnose

    cfg = load_config()

    # Section 1: Host Credentials
    typer.echo("\n--- Host Credentials ---")
    host_results = check_host_credentials(cfg)
    for r in host_results:
        symbol = "✓" if r.passed else "✗"
        typer.echo(f"  {symbol} {r.name}: {r.details}")
        if not r.passed and r.fix_hint:
            typer.echo(f"    Fix: {r.fix_hint}")

    # Section 2: Infrastructure
    typer.echo("\n--- Infrastructure ---")
    if name:
        sandbox_names = [name]
    else:
        try:
            sandboxes = osh.sandbox_list()
            sandbox_names = [sb["name"] for sb in sandboxes]
        except Exception:
            sandbox_names = []
            typer.echo("  Could not list sandboxes.")

    if not sandbox_names and not name:
        typer.echo("  No running sandboxes found.")
    else:
        for sname in sandbox_names:
            report = health_diagnose(sname, auto_recover=not no_recover)
            symbol = "✓" if report.healthy else "✗"
            typer.echo(f"  {symbol} {sname}:")
            for detail in report.details:
                typer.echo(f"      {detail}")
            if not report.healthy:
                typer.echo(f"      Recovery: {report.recovery_action}")

    # Section 3: --fix mode
    if fix:
        typer.echo("\n--- Fix: Credential Injection ---")
        targets = sandbox_names if sandbox_names else []
        if not targets:
            typer.echo("  No sandbox targets for --fix.")
        for sname in targets:
            typer.echo(f"\n  [{sname}]")
            fix_results = fix_sandbox_credentials(sname, cfg)
            for fr in fix_results:
                symbol = "✓" if fr.success else "✗"
                typer.echo(f"    {symbol} {fr.name}: {fr.details}")

    # Section 4: Profile Readiness
    typer.echo("\n--- Profile Readiness ---")
    readiness = check_profile_readiness(cfg)
    if not readiness:
        typer.echo("  No profiles found.")
    for profile_name, missing in readiness.items():
        if not missing:
            typer.echo(f"  ✓ {profile_name}: ready")
        else:
            typer.echo(f"  ✗ {profile_name}: missing {', '.join(missing)}")

    # Summary
    host_ok = all(r.passed for r in host_results)
    if host_ok:
        typer.echo("\nHost credentials: all checks passed.")
    else:
        failed = [r.name for r in host_results if not r.passed]
        typer.echo(f"\nHost credentials: {len(failed)} check(s) failed.")
