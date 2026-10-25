"""A connection with its placeholders resolved: what a test or a run really starts or calls.

The secret values it used are collected in `secret_values`: whoever shows output from the server
(a test's `stderr`, the run's terminal) hides them first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentic_os.models import McpConnection
from agentic_os.services.connections import secrets


@dataclass
class Rendered:
    name: str
    transport: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    secret_values: set[str] = field(default_factory=set)


def render(connection: McpConnection) -> Rendered:
    """Raises `secret_missing` (in words) if a placeholder has no value."""
    seen: set[str] = set()

    def text(value: str) -> str:
        return secrets.resolve_text(value, connection.id, connection.name, seen)

    return Rendered(
        name=connection.name,
        transport=connection.transport,
        command=text(connection.command),
        args=[text(a) for a in connection.args],
        cwd=text(connection.cwd),
        url=text(connection.url),
        env={k: text(v) for k, v in connection.env.items()},
        headers={k: text(v) for k, v in connection.headers.items()},
        secret_values=seen,
    )
