"""SSH keys and «Probar conexión» (phase 12, ADR 0018).

Uses the `ssh` and `ssh-keygen` that git itself uses (Git for Windows ships both), and the
person's own `~/.ssh` folder. A key is never overwritten.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel

from agentic_os.services import proc
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import executable

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$")
# GitHub: «Hi ana! You've successfully authenticated…»; GitLab: «Welcome to GitLab, @ana!»
GREETING = re.compile(
    r"Hi (?P<a>[\w.-]+)! You've successfully authenticated|Welcome to GitLab, @(?P<b>[\w.-]+)!"
)


class SshKey(BaseModel):
    name: str  # file name without `.pub`
    path: str  # the private key's path
    type: str  # ssh-ed25519, ssh-rsa…
    comment: str = ""
    fingerprint: str = ""
    public: str  # the whole public line, to copy
    # The private half is missing: the key cannot be used from here.
    orphan: bool = False


class Connection(BaseModel):
    ok: bool
    user: str | None = None
    message: str = ""


def ssh_dir() -> Path:
    return Path.home() / ".ssh"


def _tool(name: str) -> str:
    """git's own copy of the tool when there is one (Git for Windows), else the one on the PATH."""
    try:
        exec_path = Path(proc.run([executable(), "--exec-path"], 10).stdout.strip())
        for up in (exec_path.parents[1], exec_path.parents[2]):
            for candidate in (up / "usr" / "bin" / f"{name}.exe", up / "usr" / "bin" / name):
                if candidate.is_file():
                    return str(candidate)
    except (IndexError, OSError, subprocess.SubprocessError):
        pass
    found = shutil.which(name)
    if found is None:
        raise GitxError("ssh_missing", f"{name} is not installed", status=503)
    return found


def _fingerprint(path: Path) -> str:
    try:
        out = proc.run([_tool("ssh-keygen"), "-lf", str(path)], 15).stdout.split()
    except (OSError, GitxError, subprocess.SubprocessError):
        return ""
    return out[1] if len(out) > 1 else ""


def keys(folder: Path | None = None) -> list[SshKey]:
    """The public keys of the folder, with their fingerprint."""
    folder = folder or ssh_dir()
    found: list[SshKey] = []
    for pub in sorted(folder.glob("*.pub")) if folder.is_dir() else []:
        try:
            line = pub.read_text("utf-8").strip().splitlines()[0]
        except (OSError, IndexError, UnicodeDecodeError):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        private = pub.with_suffix("")
        found.append(
            SshKey(
                name=private.name,
                path=str(private),
                type=parts[0],
                comment=parts[2] if len(parts) > 2 else "",
                fingerprint=_fingerprint(pub),
                public=line,
                orphan=not private.is_file(),
            )
        )
    return found


def generate(name: str, email: str, passphrase: str = "", folder: Path | None = None) -> SshKey:
    """Makes an ed25519 key. Refuses a name that is taken: nothing is ever overwritten."""
    folder = folder or ssh_dir()
    if not NAME.match(name):
        raise GitxError("invalid_name", "that is not a valid key name", status=422)
    target = folder / name
    if target.exists() or target.with_suffix(target.suffix + ".pub").exists():
        raise GitxError("key_exists", f"a key named {name} already exists", status=409)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        result = proc.run(
            [
                _tool("ssh-keygen"),
                "-t",
                "ed25519",
                "-C",
                email,
                "-f",
                str(target),
                "-N",
                passphrase,
            ],
            30,
        )
    except subprocess.TimeoutExpired as error:
        raise GitxError("timeout", "ssh-keygen did not finish in time") from error
    if result.returncode != 0:
        raise GitxError("git_failed", "ssh-keygen failed", result.stderr)
    return next(k for k in keys(folder) if k.name == name)


def test(host: str, user: str = "git") -> Connection:
    """Can this machine authenticate to the host over SSH? Never waits for a password or a
    passphrase. GitHub and GitLab answer with the user's name (GitHub exits with 1)."""
    if not re.match(r"^[A-Za-z0-9.-]+$", host) or not re.match(r"^[A-Za-z0-9_.-]+$", user):
        raise GitxError("invalid_host", "that is not a valid host", status=422)
    try:
        result = proc.run(
            [
                _tool("ssh"),
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=10",
                f"{user}@{host}",
            ],
            25,
        )
    except subprocess.TimeoutExpired:
        return Connection(ok=False, message="timeout")
    text = f"{result.stdout}\n{result.stderr}".strip()
    match = GREETING.search(text)
    if match:
        return Connection(ok=True, user=match["a"] or match["b"], message=text.splitlines()[0])
    last = [line for line in text.splitlines() if line.strip()]
    return Connection(ok=False, message=last[-1] if last else f"exit code {result.returncode}")
