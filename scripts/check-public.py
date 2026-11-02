"""Checks that the repository can be published: no personal data, no secrets, no forbidden files.

Usage (from the repo root):
    uv run --project backend python scripts/check-public.py            # working tree (tracked files)
    uv run --project backend python scripts/check-public.py --history  # every blob, identity and message

Personal patterns come from `.public-check.local` (never committed, so the repo does not publish
what it looks for): one literal per line, matched as a case-insensitive substring anywhere,
including binary files, file names, identities and messages. They admit no exceptions.

Generic secret patterns are versioned below. Their known false positives (fake tokens in tests)
go to `scripts/public-allowlist.txt` as `path<TAB>pattern name<TAB>reason`.

Exit code 0 when clean, 1 with findings, 2 on usage errors. See ADR 0031.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

SECRET_PATTERNS: dict[str, re.Pattern[bytes]] = {
    "anthropic-key": re.compile(rb"sk-ant-[A-Za-z0-9_-]{16,}"),
    "openai-key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9]{32,}"),
    "github-token": re.compile(
        rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"
    ),
    "aws-access-key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "slack-token": re.compile(rb"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    "google-api-key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private-key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
    ),
}

FORBIDDEN_FILES = [
    ".env",
    ".env.*",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.pfx",
    "*.p12",
    "*.pem",
    "*.key",
    "spikes/out/*",
    ".public-*.local",
]

PERSONAL_FILE = ".public-check.local"
ALLOWLIST_FILE = "scripts/public-allowlist.txt"
BINARY_SNIFF = 8192  # the same window git filter-repo uses to skip binaries


@dataclass
class Report:
    findings: list[str] = field(default_factory=list)
    binaries: int = 0
    scanned: int = 0

    def add(self, where: str, what: str) -> None:
        self.findings.append(f"{where}: {what}")


def load_personal(root: Path) -> list[bytes]:
    path = root / PERSONAL_FILE
    if not path.exists():
        print(
            f"aviso: falta {PERSONAL_FILE}; solo se buscan secretos genéricos",
            file=sys.stderr,
        )
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    literals = [
        ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")
    ]
    if any(not lit.isascii() for lit in literals):
        # bytes.lower() only folds ASCII: a non-ASCII pattern only matches with its own casing.
        print(
            f"aviso: {PERSONAL_FILE} tiene patrones no ASCII; en ellos no se ignoran las mayúsculas",
            file=sys.stderr,
        )
    # UTF-8 and UTF-16LE (Windows strings inside binaries such as executables or metadata).
    return [enc for lit in literals for enc in (lit.encode(), lit.encode("utf-16-le"))]


def load_allowlist(root: Path) -> set[tuple[str, str]]:
    path = root / ALLOWLIST_FILE
    if not path.exists():
        return set()
    allowed = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not parts[2].strip():
            raise SystemExit(
                f"{ALLOWLIST_FILE}:{n}: se espera ruta<TAB>patrón<TAB>motivo"
            )
        if parts[1] not in SECRET_PATTERNS:
            raise SystemExit(f"{ALLOWLIST_FILE}:{n}: patrón desconocido {parts[1]!r}")
        allowed.add((parts[0], parts[1]))
    return allowed


def personal_hits(data: bytes, personal: list[bytes]) -> bool:
    low = data.lower()
    return any(p in low for p in personal)


def is_forbidden(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(name, pat)
        for pat in FORBIDDEN_FILES
    )


def scan_content(
    report: Report,
    where: str,
    paths: set[str],
    data: bytes,
    personal: list[bytes],
    allowed: set[tuple[str, str]],
) -> None:
    """`paths`: every path the content had; an exception applies only if it covers all of them."""
    report.scanned += 1
    if b"\0" in data[:BINARY_SNIFF]:
        report.binaries += 1
    # Personal data is searched in binaries too (EXIF, PNG text chunks, embedded paths).
    if personal_hits(data, personal):
        report.add(where, "dato personal")
    if b"\0" in data[:BINARY_SNIFF]:
        return
    for name, pattern in SECRET_PATTERNS.items():
        if all((path, name) in allowed for path in paths):
            continue
        for m in pattern.finditer(data):
            line = data.count(b"\n", 0, m.start()) + 1
            report.add(f"{where}:{line}", f"posible secreto ({name})")


def scan_path_name(report: Report, path: str, personal: list[bytes]) -> None:
    if personal_hits(path.encode(), personal):
        report.add(path, "dato personal en el nombre del fichero")
    if is_forbidden(path):
        report.add(path, "fichero que no debe publicarse")


def git(root: Path, *args: str, stdin: str | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        input=stdin.encode() if stdin is not None else None,
    ).stdout


def scan_tree(
    root: Path, personal: list[bytes], allowed: set[tuple[str, str]]
) -> Report:
    report = Report()
    for raw in git(root, "ls-files", "-z").split(b"\0"):
        if not raw:
            continue
        path = raw.decode()
        scan_path_name(report, path, personal)
        file = root / path
        if file.is_file():
            scan_content(report, path, {path}, file.read_bytes(), personal, allowed)
    return report


def scan_history(
    root: Path,
    personal: list[bytes],
    allowed: set[tuple[str, str]],
    expect_identity: str | None,
) -> Report:
    report = Report()
    blobs = history_blobs(root)
    kinds = git(
        root,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype)",
        stdin=input_lines(blobs),
    )
    blob_ids = [
        ln.split()[0] for ln in kinds.decode().splitlines() if ln.endswith(" blob")
    ]
    for path in sorted(set().union(*blobs.values())):
        scan_path_name(report, path, personal)
    for sha, data in cat_blobs(root, blob_ids):
        paths = blobs[sha]
        where = f"{min(paths)} (blob {sha[:10]})"
        scan_content(report, where, paths, data, personal, allowed)

    identities = (
        git(root, "log", "--all", "--format=%an <%ae>%n%cn <%ce>").decode().splitlines()
    )
    identities += [
        ln
        for ln in git(
            root, "for-each-ref", "refs/tags", "--format=%(taggername) %(taggeremail)"
        )
        .decode()
        .splitlines()
        if ln.strip()
    ]
    for ident in sorted(set(identities)):
        if personal_hits(ident.encode(), personal):
            report.add(f"identidad {ident!r}", "dato personal")
        if expect_identity and ident != expect_identity:
            report.add(f"identidad {ident!r}", f"distinta de {expect_identity!r}")

    messages = git(root, "log", "--all", "--format=%H%x01%B%x00").split(b"\0")
    messages += git(
        root, "for-each-ref", "refs/tags", "--format=%(refname:short)%01%(contents)%00"
    ).split(b"\0")
    for entry in messages:
        ref, _, body = entry.strip().partition(b"\x01")
        if body and personal_hits(body, personal):
            report.add(f"mensaje de {ref.decode()[:12]}", "dato personal")
    return report


def history_blobs(root: Path) -> dict[str, set[str]]:
    """Every blob of every reachable commit with every path it ever had.

    `rev-list --objects` names each object once, so a blob reused under another name (a rename,
    two empty files) would hide that name. The raw diffs of every commit (merges against each
    parent, root commits in full) list every path a commit added or changed.
    """
    out = git(
        root,
        "log",
        "--all",
        "--root",
        "-m",
        "--no-renames",
        "--raw",
        "--no-abbrev",
        "-z",
        "--format=",
    )
    blobs: dict[str, set[str]] = {}
    fields = out.split(b"\0")
    i = 0
    while i < len(fields):
        meta = fields[i].strip(b"\n")
        if not meta.startswith(b":"):
            i += 1
            continue
        new_sha = meta.split()[3].decode()
        path = fields[i + 1].decode()
        i += 2
        if set(new_sha) != {"0"}:  # a deletion has no new blob
            blobs.setdefault(new_sha, set()).add(path)
    return blobs


def input_lines(blobs: dict[str, set[str]]) -> str:
    return "".join(f"{sha}\n" for sha in blobs)


def cat_blobs(root: Path, ids: list[str]):
    proc = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert proc.stdin and proc.stdout
    stdin = proc.stdin

    def feed() -> None:
        # In a thread: writing every id before reading would deadlock once the output pipe fills.
        stdin.write("".join(f"{sha}\n" for sha in ids).encode())
        stdin.close()

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    for _ in ids:
        header = proc.stdout.readline().split()
        size = int(header[2])
        data = proc.stdout.read(size)
        proc.stdout.read(1)
        yield header[0].decode(), data
    writer.join()
    proc.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--history", action="store_true", help="revisa todo el historial"
    )
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="raíz del repositorio"
    )
    parser.add_argument(
        "--expect-identity",
        help="con --history: identidad «Nombre <email>» que deben tener todos los commits y etiquetas",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    personal = load_personal(root)
    allowed = load_allowlist(root)
    if args.history:
        report = scan_history(root, personal, allowed, args.expect_identity)
        scope = "historial"
    else:
        report = scan_tree(root, personal, allowed)
        scope = "árbol"
    for finding in report.findings:
        print(finding)
    print(
        f"{scope}: {report.scanned} ficheros revisados ({report.binaries} binarios), "
        f"{len(personal)} patrones personales, {len(report.findings)} hallazgos",
        file=sys.stderr,
    )
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
