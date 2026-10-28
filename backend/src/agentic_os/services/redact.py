"""Hiding secrets in log text (phase 20, ADR 0027; spike S4).

Two uses: a logging filter hides the patterns below before a line is written (run tokens in
URLs, credentials in headers or query strings, well-known key formats), and the support bundle
runs the same patterns again over the files, plus the actual secret values of this
installation, e-mail addresses and the user's name in paths. It is a best effort: the person
sees and can open the bundle before sending it.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

HIDDEN = "«oculto»"
# What a query or a `key=value` may carry that must not be written.
_SECRET_KEYS = (
    r"api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|"
    r"client[_-]?secret|password|passwd|pwd|auth|authorization|code|state|session|sig|"
    r"signature|credential|credentials|private[_-]?key|email"
)

# In `key=value` text (not in a query) the generic words are too common to hide whatever follows
# (`state=running`, `code=ENOENT`, `session=resumed`).
_ASSIGN_KEYS = (
    r"api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|"
    r"client[_-]?secret|password|passwd|pwd|authorization|credential|credentials|"
    r"private[_-]?key|email"
)

# (kind, pattern, replacement); applied in order.
PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # The run's and the Architect's MCP/hook tokens live in the path: /r/<token>/…, /a/<token>/…
    # (only tokens live under /r/ and /a/, so a short minimum is safe).
    ("run_token", re.compile(r"(/[ra]/)[A-Za-z0-9_\-]{8,}(?=[/?\s\"']|$)"), rf"\1{HIDDEN}"),
    (
        # A cookie header carries several `name=value` pairs separated by `;`.
        "cookie",
        re.compile(r"(?i)\b((?:set-)?cookie[\"']?\s*[:=]\s*[\"']?)(?!«)[^\r\n\"']+"),
        rf"\1{HIDDEN}",
    ),
    (
        "header",
        re.compile(
            r"(?i)\b(proxy-authorization|authorization|x-api-key)"
            # (what is already hidden is not hidden, nor counted, again)
            r"([\"']?\s*[:=]\s*[\"']?)(?:(?:bearer|basic|token)\s+)?(?!«)[^\s\"',;]+"
        ),
        rf"\1\2{HIDDEN}",
    ),
    (
        "query",
        re.compile(rf"(?i)([?&](?:{_SECRET_KEYS})=)(?!«)[^&\s#\"']+"),
        rf"\1{HIDDEN}",
    ),
    (
        "assignment",
        re.compile(
            rf"(?i)([\"']?(?<![A-Za-z0-9])(?:{_ASSIGN_KEYS})[\"']?\s*[:=]\s*[\"']?)(?!{HIDDEN})[^\s\"',;&}}]{{4,}}"
        ),
        rf"\1{HIDDEN}",
    ),
    (
        "key",
        re.compile(
            r"\b(?:sk-(?:ant-)?[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
            r"|xox[abprs]-[A-Za-z0-9\-]{10,}|AIza[0-9A-Za-z_\-]{35}|glpat-[A-Za-z0-9_\-]{20,}"
            r"|hf_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,})"
        ),
        HIDDEN,
    ),
]
EMAIL = re.compile(r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b")
USER_PATH = re.compile(r"(?i)\b([a-z]:[\\/]+users[\\/]+|/home/|/users/)([^\\/\s\"']+)")


def redact(text: str, counts: Counter[str] | None = None) -> str:
    """The patterns above (what the log filter hides before writing)."""
    for kind, pattern, replacement in PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n and counts is not None:
            counts[kind] += n
    return text


class Redactor:
    """For the support bundle: the patterns, this installation's secrets, e-mails and paths."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        # Longest first, so a secret that contains another is hidden whole.
        values = sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True)
        self._secrets = re.compile("|".join(re.escape(v) for v in values)) if values else None
        self.counts: Counter[str] = Counter()

    def line(self, text: str) -> str:
        if self._secrets is not None:
            text, n = self._secrets.subn(HIDDEN, text)
            self.counts["secret"] += n
        text = redact(text, self.counts)
        text, n = EMAIL.subn("«correo»", text)
        self.counts["email"] += n
        text, n = USER_PATH.subn(r"\1<usuario>", text)
        self.counts["user_path"] += n
        return text


def stored_secrets(db) -> list[str]:
    """The values the credential store keeps for the MCP connections (phase 18): their keys,
    and the OAuth tokens and client secret inside their JSON."""
    from agentic_os.models import McpConnection
    from agentic_os.services.connections import oauth, secrets

    values: list[str] = []
    for connection in db.query(McpConnection).all():
        for key in [*connection.secret_keys, oauth.TOKENS_KEY, oauth.CLIENT_KEY]:
            try:
                raw = secrets.get(connection.id, key)
            except Exception:  # an unavailable store: nothing to add
                continue
            if not raw:
                continue
            values.append(raw)
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if isinstance(data, dict):
                values.extend(str(v) for v in data.values() if isinstance(v, str))
    return values


class RedactingFilter(logging.Filter):
    """Hides secrets in every record before a handler writes it (spike S4: uvicorn's access
    log wrote run tokens and whole query strings)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and record.args:
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        elif isinstance(record.msg, dict):  # structlog's event dict
            record.msg = {k: redact(v) if isinstance(v, str) else v for k, v in record.msg.items()}
        return True


def home_hint(text: str) -> str:
    """The user's home folder as `~` (for info.txt)."""
    home = str(Path.home())
    return text.replace(home, "~").replace(home.replace("\\", "/"), "~")
