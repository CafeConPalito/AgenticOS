"""The OAuth login of the connections that need one (phase 18, block 6 completes this).

The tokens live in the credential store under reserved keys (`_oauth_tokens`, `_oauth_client`),
never in the database. A run only ever receives the access token, never the refresh token.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from agentic_os.models import McpConnection, McpOAuth, OAuthStatus
from agentic_os.services.connections import secrets

TOKENS_KEY = "_oauth_tokens"
CLIENT_KEY = "_oauth_client"


class NeedsLogin(Exception):
    """The person has to connect the account (again). `message` says it in Spanish."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def stored_tokens(connection_id: str) -> dict | None:
    raw = secrets.get(connection_id, TOKENS_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def access_token(db: Session, connection: McpConnection) -> str:
    """The access token a run sends as `Authorization: Bearer`. Raises `NeedsLogin`."""
    login = db.get(McpOAuth, connection.id)
    if login is None or login.status == OAuthStatus.DISCONNECTED:
        raise NeedsLogin(f"Conecta la cuenta de «{connection.name}» para poder usarla.")
    if login.status == OAuthStatus.NEEDS_REAUTH:
        raise NeedsLogin(f"Hay que volver a conectar la cuenta de «{connection.name}».")
    tokens = stored_tokens(connection.id)
    if not tokens or not tokens.get("access_token"):
        raise NeedsLogin(f"Hay que volver a conectar la cuenta de «{connection.name}».")
    return str(tokens["access_token"])
