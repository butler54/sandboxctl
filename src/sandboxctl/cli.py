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
