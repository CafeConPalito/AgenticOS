"""Hides the secret values of a run from everything that is written or shown: the log, the
scrollback, the screen the backend reads and the live viewers (CA3).

The terminal output arrives in arbitrary pieces, so a secret can be cut between two of them. The
end of a piece that could be the start of a secret is held back until the next piece decides.
The terminal wraps long lines and mixes in escape sequences, so a secret that the CLI prints
broken by them is not caught: this is a safety net, not a guarantee (ADR 0025).
"""

from __future__ import annotations

MASK = "•••"
MIN_LENGTH = 6  # shorter values would hide ordinary words


class Redactor:
    def __init__(self, secrets: set[str] | frozenset[str] | list[str] | tuple[str, ...]) -> None:
        # Longest first, so a secret that contains another is hidden whole.
        self._secrets = sorted({s for s in secrets if len(s) >= MIN_LENGTH}, key=len, reverse=True)
        self._tail = ""

    @property
    def active(self) -> bool:
        return bool(self._secrets)

    def _mask(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        return text

    def _held(self, text: str) -> int:
        """Length of the longest end of `text` that is the start of a secret."""
        best = 0
        for secret in self._secrets:
            for size in range(min(len(secret) - 1, len(text)), best, -1):
                if text.endswith(secret[:size]):
                    best = size
                    break
        return best

    def feed(self, chunk: str) -> str:
        """The piece with the secrets hidden. May be shorter than what came in."""
        if not self._secrets:
            return chunk
        text = self._mask(self._tail + chunk)
        hold = self._held(text)
        self._tail = text[len(text) - hold :] if hold else ""
        return text[: len(text) - hold]

    def flush(self) -> str:
        """What is still held back, when the output ends."""
        text, self._tail = self._tail, ""
        return text
