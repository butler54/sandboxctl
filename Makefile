.PHONY: install dev lint format test clean uninstall help

install:           ## Install globally via uv tool
	uv tool install --force -e .

dev:               ## Install in dev mode with all deps
	uv sync

lint:              ## Check code style
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:            ## Auto-format code
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

test:              ## Run tests with coverage
	uv run pytest

clean:             ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info .ruff_cache .pytest_cache __pycache__ .coverage htmlcov/

uninstall:         ## Remove from uv tools
	uv tool uninstall sandboxctl

help:              ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
