"""Subscription windows (5 h, weekly…) as the CLIs report them in their status line JSON
(evidence S1/S2 of phase 10).

- Claude Code: `rate_limits.five_hour` / `seven_day`, each with `used_percentage` (0-100) and
  `resets_at` (epoch seconds). Only for Pro and Max subscribers, after the first response.
- agy: `quota.<bucket>` (`gemini-5h`, `gemini-weekly`, `3p-5h`, `3p-weekly`), each with
  `remaining_fraction` (0-1) and `reset_time` (ISO, UTC). Its payload also names the account.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from agentic_os.models import Cli

CLAUDE_WINDOWS = ("five_hour", "seven_day")


@dataclass(frozen=True)
class QuotaWindow:
    id: str
    used_pct: float  # 0-100
    resets_at: datetime  # timezone-aware UTC


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _clamp(percent: float) -> float:
    return max(0.0, min(100.0, percent))


def _claude_windows(payload: dict) -> list[QuotaWindow]:
    limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        return []
    windows = []
    for window_id in CLAUDE_WINDOWS:
        data = limits.get(window_id)
        if not isinstance(data, dict):
            continue
        used, resets = _number(data.get("used_percentage")), _number(data.get("resets_at"))
        if used is None or resets is None:
            continue
        try:
            at = datetime.fromtimestamp(resets, UTC)
        except (OverflowError, OSError, ValueError):
            continue
        windows.append(QuotaWindow(window_id, _clamp(used), at))
    return windows


def _agy_windows(payload: dict) -> list[QuotaWindow]:
    buckets = payload.get("quota")
    if not isinstance(buckets, dict):
        return []
    windows = []
    for bucket_id, data in buckets.items():
        if not isinstance(bucket_id, str) or not isinstance(data, dict):
            continue
        remaining, reset = _number(data.get("remaining_fraction")), data.get("reset_time")
        if remaining is None or not isinstance(reset, str):
            continue
        try:
            at = datetime.fromisoformat(reset.replace("Z", "+00:00"))
        except ValueError:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        windows.append(QuotaWindow(bucket_id, _clamp((1 - remaining) * 100), at.astimezone(UTC)))
    return windows


def windows_from_status_line(cli: Cli, payload: object) -> list[QuotaWindow]:
    """The subscription windows in a status line payload (none if it carries no quota)."""
    if not isinstance(payload, dict):
        return []
    return _claude_windows(payload) if cli == Cli.CLAUDE else _agy_windows(payload)
