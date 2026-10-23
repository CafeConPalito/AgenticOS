"""Why a skill was not accepted. The UI translates by `code` (with `params`); `message` is the same
reason in Spanish, which is what an agent reads when its proposal is refused (spec CA1, CA10)."""

from __future__ import annotations

from typing import Any


class SkillError(Exception):
    def __init__(self, code: str, message: str, **params: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.params = params

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "params": self.params}
