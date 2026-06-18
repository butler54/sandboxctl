"""CLI entry point."""


import typer

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
