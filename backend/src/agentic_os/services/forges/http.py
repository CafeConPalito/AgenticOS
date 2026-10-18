"""One HTTP call to a code host's API, with its failures as stable codes."""

from __future__ import annotations

from typing import Any

import httpx

from agentic_os.services.gitx.errors import GitxError

TIMEOUT = 15.0


def new_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True)


class Api:
    def __init__(self, client: httpx.Client, base: str, token: str) -> None:
        self._client = client
        self._base = base.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "User-Agent": "agentic-os"}

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            response = self._client.request(
                method, f"{self._base}{path}", headers=headers, **kwargs
            )
        except httpx.TimeoutException as error:
            raise GitxError("timeout", "the code host did not answer in time") from error
        except httpx.HTTPError as error:
            raise GitxError("network", f"could not reach the code host: {error}") from error
        if response.is_success:
            return response.json() if response.content else None
        raise _error(response)

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})


def _detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(data, dict):
        message = data.get("message") or data.get("error") or data.get("error_description")
        return str(message or "")[:300]
    return ""


def _error(response: httpx.Response) -> GitxError:
    status, detail = response.status_code, _detail(response)
    limited = response.headers.get("x-ratelimit-remaining") == "0" or status == 429
    if limited:
        return GitxError("rate_limited", detail or "rate limit reached", status=429)
    if status in (401, 403):
        return GitxError("auth_failed", detail or "the code host refused the token", status=401)
    if status == 404:
        return GitxError("not_found", detail or "not found on the code host", status=404)
    if status in (405, 406, 409, 422):
        return GitxError("conflict", detail or "the code host refused this change", status=409)
    return GitxError("forge_failed", detail or f"the code host answered {status}", status=502)
