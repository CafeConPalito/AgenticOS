"""Why a skill was not accepted. The UI translates by `code` (with `params`); `message` is the same
reason in Spanish, which is what an agent reads when its proposal is refused (spec CA1, CA10).
It is an ApiError, so the API answers it as it is (422; 409 when it clashes with another)."""

from __future__ import annotations

from typing import Any

from agentic_os.errors import ApiError

CONFLICTS = frozenset({"name_taken", "no_changes"})


class SkillError(ApiError):
    def __init__(self, code: str, message: str, **params: Any) -> None:
        super().__init__(409 if code in CONFLICTS else 422, code, message, extra={"params": params})
        self.params = params

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "params": self.params}
