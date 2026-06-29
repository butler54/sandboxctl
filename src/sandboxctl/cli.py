"""CLI entry point."""

from __future__ import annotations

import typer
from rich.table import Table

from sandboxctl.config import CONFIG_TEMPLATE, ensure_config_dir, load_config

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
    profile: str = typer.Option(..., "--profile", "-p", help="Profile name."),
    name: str | None = typer.Option(None, "--name", "-n", help="Sandbox name (defaults to profile name)."),
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
    name: str = typer.Argument(help="Sandbox name."),
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
def delete_cmd(name: str = typer.Argument(help="Sandbox name.")) -> None:
    """Delete a sandbox."""
    from sandboxctl import openshell as osh

    typer.confirm(f"Delete sandbox '{name}'?", abort=True)
    osh.sandbox_delete(name)
    typer.echo(f"Deleted sandbox: {name}")


@app.command()
def validate(name: str = typer.Argument(help="Sandbox name.")) -> None:
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
def init_cmd(name: str = typer.Argument(help="Profile name.")) -> None:
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
def doctor(
    name: str = typer.Argument(help="Sandbox name to diagnose."),
    no_recover: bool = typer.Option(False, "--no-recover", help="Skip auto-recovery, diagnose only."),
) -> None:
    """Diagnose and recover sandbox issues."""
    from sandboxctl.health import diagnose

    report = diagnose(name, auto_recover=not no_recover)
    for detail in report.details:
        typer.echo(f"  {detail}")
    if report.healthy:
        typer.echo(f"\n[bold green]Sandbox '{name}' is healthy.[/bold green]")
    else:
        typer.echo(f"\n[bold red]Sandbox '{name}' is unhealthy.[/bold red]")
        typer.echo(f"  Recovery action: {report.recovery_action}")
        if "needs_recreate" in report.recovery_action:
            typer.echo("  Run 'sandboxctl restart' to recreate (will lose unsaved work).")
