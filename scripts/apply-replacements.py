"""Applies a `git filter-repo --replace-text` file to the tracked text files of the working tree.

The same file is later given to `git filter-repo` (ADR 0031), so the tree and the rewritten
history end up identical. The rules are read and applied as filter-repo does (first every literal,
then every regex or glob, each group in file order), one per line:
    literal==>replacement            (`literal:` prefix optional)
    glob:pattern==>replacement
    regex:pattern==>replacement      (Python `re`, on bytes; `\\1` back references work)
The line is split on its last `==>`; without one the text becomes `***REMOVED***`. There are no
comments: filter-repo would take a `#` line as a literal. Binary files (a NUL in the first 8192
bytes) are skipped, as filter-repo skips them.

Usage: uv run --project backend python scripts/apply-replacements.py .public-replacements.local
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

Rule = tuple[re.Pattern[bytes], bytes]


def parse_rules(text: str) -> list[Rule]:
    literals: list[Rule] = []
    regexes: list[Rule] = []
    for line in text.splitlines():
        if "==>" in line:
            source, repl = line.rsplit("==>", 1)
        else:
            source, repl = line, "***REMOVED***"
        if source.startswith("regex:"):
            regexes.append(
                (re.compile(source[len("regex:") :].encode()), repl.encode())
            )
        elif source.startswith("glob:"):
            # The same translation as filter-repo's glob_to_regex (the replacement stays a
            # regex template, as there).
            regex = fnmatch.translate(source[len("glob:") :])
            if regex.startswith("(?s:") and regex.endswith(r")\Z"):
                regex = regex[4:-3]
            regexes.append((re.compile(regex.encode()), repl.encode()))
        else:
            source = source.removeprefix("literal:")
            if not source:
                continue
            # A literal is a plain bytes.replace in filter-repo: escape it for re.sub.
            literals.append(
                (
                    re.compile(re.escape(source.encode())),
                    repl.replace("\\", "\\\\").encode(),
                )
            )
    return literals + regexes


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
        if b"\0" in data[:8192]:
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
