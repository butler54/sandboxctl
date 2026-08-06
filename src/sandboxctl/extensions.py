"""VS Code extension management: classification, validation, and installation."""

from __future__ import annotations

from sandboxctl.models import Extensions


def classify_remote_extensions(ext: Extensions) -> list[str]:
    """Classify which extensions should be installed remotely in the sandbox.

    Returns the list of extension IDs to install remotely.
    For the tracer task, this is a simple pass-through; Task 2 adds denylist and validation.
    """
    return list(ext.extensions_list)
