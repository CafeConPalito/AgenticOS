"""Tests for scripts/apply-replacements.py (phase 25, ADR 0031)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "apply-replacements.py"
spec = importlib.util.spec_from_file_location("apply_replacements", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules["apply_replacements"] = mod
spec.loader.exec_module(mod)

RULES = mod.parse_rules(
    "regex:el sobaxyz==>la costra\n"
    "regex:(?i)sobaxyz==>costra\n"
    "regex:(?i)xyz==>usuario\n"
    "me@mail.test==>user@example.com\n"
    "\n"
    "gone\n"
)


def test_rules_apply_in_order_and_case_insensitively() -> None:
    text = (
        b"C:\\Users\\xyz\\a  C:\\\\Users\\\\XYZ  C--Users-xyz-proj  166mme@mail.test\n"
        b"formar el sobaxyz, la capa. Sobaxyz. gone\n"
    )
    assert mod.apply(text, RULES) == (
        b"C:\\Users\\usuario\\a  C:\\\\Users\\\\usuario  C--Users-usuario-proj  "
        b"166muser@example.com\nformar la costra, la capa. costra. ***REMOVED***\n"
    )


def test_parsing_matches_git_filter_repo() -> None:
    # Literals first (even when listed later), split on the last ==>, no comments, globs.
    rules = mod.parse_rules("regex:b+==>R\nab==>L\n# note\na==>b==>c\nglob:x?z==>G\n")
    assert mod.apply(b"abb a==>b # note xyz", rules) == b"LR c ***REMOVED*** G"


def test_literal_replacement_keeps_backslashes() -> None:
    rules = mod.parse_rules("a==>C:\\x\\1\n")
    assert mod.apply(b"a", rules) == b"C:\\x\\1"


def test_main_skips_binaries_and_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    import subprocess

    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "t.txt").write_bytes(b"xyz\r\n")
    (tmp_path / "b.bin").write_bytes(b"\0xyz")
    (tmp_path / "rules").write_text("regex:xyz==>usuario\n", encoding="utf-8")
    subprocess.run(["git", "add", "t.txt", "b.bin"], check=True)
    assert mod.main(["rules"]) == 0
    assert (tmp_path / "t.txt").read_bytes() == b"usuario\r\n"
    assert (tmp_path / "b.bin").read_bytes() == b"\0xyz"
    assert "1 ficheros cambiados" in capsys.readouterr().err
