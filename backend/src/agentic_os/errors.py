"""Uniform API errors: `{"detail": {"code": "...", "message": "...", "field": "..."}}`.

The UI translates by `code`; `message` is a developer-facing English fallback.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        field: str | None = None,
        extra: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.extra = extra or {}
        self.status = status
        self.code = code
        self.message = message
        self.field = field


class NotFound(ApiError):
    def __init__(self, entity: str) -> None:
        super().__init__(404, f"{entity}_not_found", f"{entity} not found")


def _body(code: str, message: str, field: str | None = None, **extra) -> dict:
    detail = {"code": code, "message": message, **extra}
    if field:
        detail["field"] = field
    return {"detail": detail}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            _body(exc.code, exc.message, exc.field, **exc.extra), status_code=exc.status
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        first = errors[0] if errors else {"field": None, "message": "invalid request"}
        return JSONResponse(
            _body("validation_error", first["message"], first["field"], errors=errors), 422
        )
