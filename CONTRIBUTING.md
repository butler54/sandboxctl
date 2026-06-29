# Contributing to sandboxctl

Thank you for your interest in contributing to sandboxctl. This guide covers
everything you need to get started.

## Development Setup

sandboxctl uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Clone the repository
git clone https://github.com/<org>/sandboxctl.git
cd sandboxctl

# Install dev dependencies
make dev          # runs uv sync

# Install pre-commit hooks
uv run pre-commit install
```

Requirements: Python 3.12 or 3.13.

## Running Tests

```bash
# Run tests with coverage (via uv)
make test

# Run tests across the Python matrix (3.12, 3.13)
hatch test

# Run a specific test file
uv run pytest tests/test_cli.py

# Run only integration tests
uv run pytest -m integration
```

Integration tests are marked with `@pytest.mark.integration` and may require
external services to be available.

## Code Quality

```bash
# Check linting and formatting
make lint

# Auto-format code and fix lint issues
make format
```

Pre-commit hooks enforce ruff linting, ruff formatting, and commitlint on every
commit. If you ran `uv run pre-commit install` during setup, these run
automatically.

## Commit Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/)
enforced by commitlint.

**Format:**

```
type(scope): description
```

or without a scope:

```
type: description
```

**Allowed types:** `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `ci`,
`build`, `style`, `perf`

Subject case is not enforced -- write whatever reads naturally.

**Examples:**

```
feat(cli): add sandbox list command
fix: resolve XDG config path on macOS
docs: update installation instructions
test(credentials): add keyring fallback tests
```

## Pull Request Process

1. Branch from `main`.
2. Keep changes focused -- one logical change per PR.
3. Ensure all tests pass (`make test`) and linting is clean (`make lint`).
4. Use a conventional commit style for the PR title.
5. Fill in the PR description with context on what changed and why.

## Project Structure

```
src/sandboxctl/
├── __init__.py      -- Version
├── cli.py           -- Typer CLI entry point
├── config.py        -- XDG-compliant configuration
├── credentials.py   -- Cross-platform credential storage
├── health.py        -- Container liveness and recovery
├── models.py        -- Pydantic data models
├── openshell.py     -- OpenShell CLI wrapper
├── profile.py       -- Profile management
└── scoped_tokens.py -- Scoped Git token generation
```

Key dependencies: [Typer](https://typer.tiangolo.com/) (CLI framework),
[Pydantic](https://docs.pydantic.dev/) (data models and settings).

## Makefile Reference

| Target           | Description                          |
| ---------------- | ------------------------------------ |
| `make install`   | Install globally via uv tool         |
| `make dev`       | Install in dev mode with all deps    |
| `make lint`      | Check code style                     |
| `make format`    | Auto-format code                     |
| `make test`      | Run tests with coverage              |
| `make clean`     | Remove build artifacts               |
| `make uninstall` | Remove from uv tools                 |
| `make help`      | Show all available targets           |

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE).
