"""Applies a `git filter-repo --replace-text` file to the tracked text files of the working tree.

The same file is later given to `git filter-repo` (ADR 0031), so the tree and the rewritten
history end up identical. Rules, applied in order, one per line:
    literal==>replacement
    regex:pattern==>replacement      (Python `re`, on bytes; `\\1` back references work)
A line without `==>` is replaced with `***REMOVED***`, as filter-repo does.

Usage: uv run --project backend python scripts/apply-replacements.py .public-replacements.local
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

Rule = tuple[re.Pattern[bytes], bytes]


def parse_rules(text: str) -> list[Rule]:
    rules: list[Rule] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        source, sep, repl = line.partition("==>")
        if not sep:
            repl = "***REMOVED***"
        if source.startswith("regex:"):
            pattern = re.compile(source[len("regex:") :].encode())
        else:
            source = source.removeprefix("literal:")
            pattern = re.compile(re.escape(source.encode()))
            repl = repl.replace("\\", "\\\\")
        rules.append((pattern, repl.encode()))
    return rules


def apply(data: bytes, rules: list[Rule]) -> bytes:
    for pattern, repl in rules:
        data = pattern.sub(repl, data)
    return data


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    rules = parse_rules(Path(argv[0]).read_text(encoding="utf-8"))
    files = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True
    ).stdout
    changed = 0
    for raw in files.split(b"\0"):
        path = Path(raw.decode()) if raw else None
        if path is None or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:
            continue
        new = apply(data, rules)
        if new != data:
            path.write_bytes(new)
            changed += 1
            print(path.as_posix())
    print(f"{changed} ficheros cambiados", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
