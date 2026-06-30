"""HTTP utilities for credential validation using stdlib."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def validate_github_token(token: str, timeout: int = 10) -> str | None:
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "sandboxctl",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
            return data.get("login")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError):
        return None


def validate_gitlab_token(server: str, token: str, timeout: int = 10) -> bool:
    url = f"https://{server}/api/v4/user"
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={
            "PRIVATE-TOKEN": token,
            "User-Agent": "sandboxctl",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False
