"""Why a connection was not accepted or could not be used. The UI translates by `code` (with
`params`); `message` is the same reason in Spanish. It is an ApiError, so the API answers it as it
is (422; 409 when it clashes with another connection; 503 when the credential store is not
available)."""

from __future__ import annotations

from typing import Any

from agentic_os.errors import ApiError

CONFLICTS = frozenset({"name_taken"})
UNAVAILABLE = frozenset({"secrets_unavailable"})


class ConnectionError_(ApiError):
    def __init__(self, code: str, message: str, **params: Any) -> None:
        status = 409 if code in CONFLICTS else 503 if code in UNAVAILABLE else 422
        super().__init__(status, code, message, extra={"params": params})
        self.params = params

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "params": self.params}
