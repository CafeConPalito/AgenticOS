"""The third-party licenses shown in «Acerca de» (phase 20).

Lists what the app ships: the production dependencies of the frontend and the desktop shell
(npm), the backend's runtime packages (uv, without the dev group) and the shell's crates for
Windows (cargo). Writes `frontend/src/generated/third-party-licenses.json` with a hash of each
lockfile, so a test can tell when the list is behind them.

    uv run --project backend python scripts/licenses.py          # write the list
    uv run --project backend python scripts/licenses.py --check  # exit 1 if it is behind
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "src" / "generated" / "third-party-licenses.json"
LOCKFILES = ("package-lock.json", "backend/uv.lock", "desktop/src-tauri/Cargo.lock")
OWN = {"agentic-os", "@agentic-os/frontend", "@agentic-os/desktop"}


def lock_hashes() -> dict[str, str]:
    """Hashes of the lockfiles, newlines normalized (git may check them out with CRLF)."""
    return {
        name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in LOCKFILES
    }


# --------------------------------------------------------------------------------- npm
def _npm_license(pkg: dict) -> str:
    value = pkg.get("license")
    if isinstance(value, dict):
        value = value.get("type")
    if not value and isinstance(pkg.get("licenses"), list):
        value = " OR ".join(
            str(item.get("type")) for item in pkg["licenses"] if isinstance(item, dict)
        )
    return str(value or "UNKNOWN")


def _npm_url(pkg: dict) -> str:
    repo = pkg.get("repository")
    url = repo.get("url") if isinstance(repo, dict) else repo
    url = str(url or pkg.get("homepage") or "")
    url = re.sub(r"^git\+", "", url).removesuffix(".git")
    if url.startswith("github:"):
        url = "https://github.com/" + url.removeprefix("github:")
    return url if url.startswith("http") else ""


def npm_packages() -> list[dict]:
    """The production dependency tree of the frontend and the desktop shell."""
    seen: dict[str, dict] = {}

    def visit(name: str, base: Path) -> None:
        if name in seen:
            return
        folder = base / "node_modules" / name
        if not (folder / "package.json").is_file():
            folder = ROOT / "node_modules" / name
        manifest = folder / "package.json"
        if not manifest.is_file():
            return
        pkg = json.loads(manifest.read_text(encoding="utf-8"))
        seen[name] = {
            "ecosystem": "npm",
            "name": name,
            "version": str(pkg.get("version") or ""),
            "license": _npm_license(pkg),
            "url": _npm_url(pkg),
        }
        for dep in pkg.get("dependencies") or {}:
            visit(dep, folder)

    for workspace in ("frontend", "desktop"):
        pkg = json.loads((ROOT / workspace / "package.json").read_text(encoding="utf-8"))
        for dep in pkg.get("dependencies") or {}:
            visit(dep, ROOT / workspace)
    return list(seen.values())


# ------------------------------------------------------------------------------ python
def _py_license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    if meta.get("License-Expression"):
        return meta["License-Expression"].strip()
    classifiers = sorted(
        {
            c.split(" :: ")[-1]
            for c in meta.get_all("Classifier") or []
            if c.startswith("License ::")
        }
        - {"OSI Approved"}
    )
    if classifiers:
        return " / ".join(classifiers)
    raw = re.sub(r"\s+", " ", (meta.get("License") or "").strip())
    return raw[:60] if raw and len(raw) <= 60 else "UNKNOWN"


def _py_url(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in {"source", "repository", "homepage", "home", "source code"}:
            return url.strip()
    return str(meta.get("Home-page") or "")


def python_packages() -> list[dict]:
    """The backend's runtime packages: what `uv export --no-dev` lists, read from the venv."""
    exported = subprocess.run(
        [
            "uv",
            "export",
            "--project",
            "backend",
            "--no-dev",
            "--no-hashes",
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    wanted = {
        re.split(r"[=<>; ]", line.strip(), maxsplit=1)[0].lower().replace("_", "-")
        for line in exported.splitlines()
        if line.strip() and not line.startswith(("#", "-", " "))
    }
    result = []
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        key = name.lower().replace("_", "-")
        if key in wanted and key not in OWN:
            wanted.discard(key)
            result.append(
                {
                    "ecosystem": "python",
                    "name": name,
                    "version": dist.version,
                    "license": _py_license(dist),
                    "url": _py_url(dist),
                }
            )
    return result


# ------------------------------------------------------------------------------- rust
def rust_packages() -> list[dict]:
    """The crates of the desktop shell for Windows."""
    out = subprocess.run(
        [
            "cargo",
            "metadata",
            "--format-version",
            "1",
            "--filter-platform",
            "x86_64-pc-windows-msvc",
            "--manifest-path",
            str(ROOT / "desktop" / "src-tauri" / "Cargo.toml"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    data = json.loads(out)
    used = {node["id"] for node in data["resolve"]["nodes"]}
    return [
        {
            "ecosystem": "rust",
            "name": pkg["name"],
            "version": pkg["version"],
            "license": pkg.get("license") or "UNKNOWN",
            "url": pkg.get("repository") or pkg.get("homepage") or "",
        }
        for pkg in data["packages"]
        if pkg["id"] in used and pkg["name"] not in OWN
    ]


def main() -> int:
    if "--check" in sys.argv:
        current = (
            json.loads(OUT.read_text(encoding="utf-8")).get("lockfiles") if OUT.exists() else None
        )
        if current != lock_hashes():
            print("third-party-licenses.json is behind the lockfiles: run scripts/licenses.py")
            return 1
        print("third-party-licenses.json is up to date")
        return 0
    packages = npm_packages() + python_packages() + rust_packages()
    # One entry per name and version (a crate may come in twice).
    unique = {(p["ecosystem"], p["name"], p["version"]): p for p in packages}
    rows = sorted(unique.values(), key=lambda p: (p["ecosystem"], p["name"].lower(), p["version"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"lockfiles": lock_hashes(), "packages": rows}, ensure_ascii=False, indent=1)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    counts = {e: sum(1 for p in rows if p["ecosystem"] == e) for e in ("npm", "python", "rust")}
    print(f"{len(rows)} packages {counts} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
