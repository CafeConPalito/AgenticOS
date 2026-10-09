"""P12: detect installed CLIs, version, login state and models.

Usage: uv run python cli_probe.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field

from common import HOME, evidence


@dataclass
class CliInfo:
    name: str
    path: str | None
    version: str | None = None
    logged_in: bool | None = None
    login_evidence: str = ""
    models: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run(argv: list[str], timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


def probe_claude() -> CliInfo:
    info = CliInfo("claude", shutil.which("claude"))
    if not info.path:
        return info
    info.version = run([info.path, "--version"]).stdout.strip()
    status = run([info.path, "auth", "status"])
    if status.returncode == 0 and status.stdout.strip():
        info.login_evidence = f"`claude auth status` -> {status.stdout.strip()[:200]}"
        info.logged_in = '"loggedIn": true' in status.stdout or "logged in" in status.stdout.lower()
    else:
        creds = HOME / ".claude" / ".credentials.json"
        info.logged_in = creds.exists()
        info.login_evidence = (
            f"`auth status` rc={status.returncode}; credentials file={creds.exists()}"
        )
    info.notes.append("Models: aliases (haiku, sonnet, opus) or full IDs via --model")
    return info


def probe_agy() -> CliInfo:
    info = CliInfo("agy", shutil.which("agy"))
    if not info.path:
        return info
    info.version = run([info.path, "--version"]).stdout.strip()
    models = run([info.path, "models"])
    out = models.stdout + models.stderr
    info.models = [line.split("\t")[0] for line in models.stdout.splitlines() if "\t" in line]
    info.logged_in = bool(info.models) and "not logged" not in out.lower()
    info.login_evidence = f"`agy models` rc={models.returncode}, {len(info.models)} models"
    return info


def main() -> None:
    infos = [probe_claude(), probe_agy()]
    report = json.dumps([asdict(i) for i in infos], indent=2, ensure_ascii=False)
    print(report)
    evidence("p12-cli-probe.json").write_text(report, "utf-8")


if __name__ == "__main__":
    main()
