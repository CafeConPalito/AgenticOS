"""Forgetting the trust of removed worktrees, on fake config files (never the real ones)."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_os.services.trust import TrustCleaner

CLAUDE = {
    "numStartups": 7,
    "projects": {
        "D:/web": {"hasTrustDialogAccepted": True},
        "D:/web.wt/T-7": {"hasTrustDialogAccepted": True},
        "D:/web.wt/T-8": {"hasTrustDialogAccepted": True},
    },
}
AGY = {"theme": "dark", "trustedWorkspaces": ["D:\\web", "D:\\web.wt\\T-7", "d:\\WEB.wt\\t-8"]}


def setup(tmp_path: Path, running: set[str]) -> tuple[TrustCleaner, Path, Path]:
    claude, agy = tmp_path / ".claude.json", tmp_path / "settings.json"
    claude.write_text(json.dumps(CLAUDE), "utf-8")
    agy.write_text(json.dumps(AGY), "utf-8")
    cleaner = TrustCleaner(
        tmp_path / "data" / "trust-cleanup.json",
        {"claude": claude, "agy": agy},
        is_running=lambda image: image in running,
    )
    return cleaner, claude, agy


def test_only_the_worktree_entries_go(tmp_path: Path):
    cleaner, claude, agy = setup(tmp_path, running=set())
    cleaner.forget("D:\\web.wt\\T-7")
    cleaner.forget("D:\\web.wt\\T-8")
    assert json.loads(claude.read_text("utf-8")) == {
        "numStartups": 7,
        "projects": {"D:/web": {"hasTrustDialogAccepted": True}},
    }
    assert json.loads(agy.read_text("utf-8")) == {"theme": "dark", "trustedWorkspaces": ["D:\\web"]}
    assert cleaner.flush() == {}


def test_a_running_cli_postpones_its_file(tmp_path: Path):
    running = {"claude.exe"}
    cleaner, claude, agy = setup(tmp_path, running)
    cleaner.forget("D:/web.wt/T-7")
    assert json.loads(claude.read_text("utf-8")) == CLAUDE  # untouched while Claude is open
    assert "D:\\web.wt\\T-7" not in json.loads(agy.read_text("utf-8"))["trustedWorkspaces"]
    assert cleaner.flush() == {"claude": 1}

    running.clear()  # e.g. on a later housekeeping round
    assert cleaner.flush() == {}
    assert "D:/web.wt/T-7" not in json.loads(claude.read_text("utf-8"))["projects"]


def test_missing_or_broken_files_are_never_rewritten(tmp_path: Path):
    cleaner, claude, agy = setup(tmp_path, running=set())
    claude.unlink()
    agy.write_text("{not json", "utf-8")
    cleaner.forget("D:/web.wt/T-7")
    assert not claude.exists()
    assert agy.read_text("utf-8") == "{not json"
    assert cleaner.flush() == {"agy": 1}  # kept for later, in case the file gets repaired


def test_the_trust_of_every_accounts_folder_is_cleaned_too(tmp_path: Path):
    """Phase 10: an account with its own login folder keeps its trust in `<folder>/.claude.json`."""
    from agentic_os.services.trust import account_claude_config

    cleaner, claude, _ = setup(tmp_path, running=set())
    folder = tmp_path / "accounts" / "a1"
    folder.mkdir(parents=True)
    own = account_claude_config(folder)
    own.write_text(json.dumps(CLAUDE), "utf-8")
    cleaner = TrustCleaner(
        tmp_path / "data" / "trust-cleanup.json",
        {"claude": claude, "agy": tmp_path / "settings.json"},
        is_running=lambda image: False,
        extra_configs=lambda: {"claude": [own, tmp_path / "accounts" / "gone" / ".claude.json"]},
    )
    cleaner.forget("D:/web.wt/T-7")
    for path in (claude, own):  # the system file and the account's
        assert "D:/web.wt/T-7" not in json.loads(path.read_text("utf-8"))["projects"]
        assert "D:/web.wt/T-8" in json.loads(path.read_text("utf-8"))["projects"]
    assert not (tmp_path / "accounts" / "gone").exists()  # a missing file is never created


def test_a_bad_account_file_does_not_hold_back_the_rest(tmp_path: Path, monkeypatch):
    from agentic_os.services import trust as trust_module
    from agentic_os.services.trust import account_claude_config

    cleaner, claude, _ = setup(tmp_path, running=set())
    locked, fine = tmp_path / "a" / ".claude.json", tmp_path / "b" / ".claude.json"
    for path in (locked, fine):
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(CLAUDE), "utf-8")
    real = trust_module.forget_claude

    def forget(path: Path, folders: list[str]) -> list[str]:
        if path == locked:
            raise PermissionError("locked")
        return real(path, folders)

    monkeypatch.setattr(trust_module, "forget_claude", forget)
    cleaner = TrustCleaner(
        tmp_path / "data" / "trust-cleanup.json",
        {"claude": claude, "agy": tmp_path / "settings.json"},
        is_running=lambda image: False,
        extra_configs=lambda: {"claude": [locked, fine]},
    )
    cleaner.forget("D:/web.wt/T-7")
    assert "D:/web.wt/T-7" not in json.loads(claude.read_text("utf-8"))["projects"]
    assert "D:/web.wt/T-7" not in json.loads(fine.read_text("utf-8"))["projects"]
    assert cleaner.flush() == {}  # the main file got it: the folder is not retried for ever
    assert account_claude_config(tmp_path / "a") == locked
