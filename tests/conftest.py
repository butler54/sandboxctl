"""Shared pytest fixtures for the sandboxctl test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_cli_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the CLI backend for every test by default (004).

    The legacy suite asserts CLI invocation behavior; without this default a
    developer running tests with the `sdk` extra installed (and a live
    gateway) would flip routed operations onto the SDK path and break them
    non-deterministically. SDK-path tests opt in explicitly by setting
    ``SANDBOXCTL_OPENSHELL_BACKEND=auto`` (and injecting a fake client) via
    ``monkeypatch`` — which overrides this fixture's value.
    """
    monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "cli")
