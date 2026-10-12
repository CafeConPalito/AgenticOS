import subprocess
import sys

import pytest

from agentic_os.services import clis, git, proc, trust


def test_run_captures_text_without_a_window(monkeypatch: pytest.MonkeyPatch):
    seen: dict = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs, argv=argv)
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(proc.subprocess, "run", fake_run)
    assert proc.run(("git", "--version"), 5).stdout == "ok"
    assert seen["argv"] == ["git", "--version"]
    assert seen["creationflags"] == proc.NO_WINDOW
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["timeout"] == 5


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW only exists on Windows")
def test_no_window_is_set_on_windows():
    assert proc.NO_WINDOW == subprocess.CREATE_NO_WINDOW


def test_helpers_go_through_proc(monkeypatch: pytest.MonkeyPatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(argv, timeout, cwd=None):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(proc, "run", fake_run)
    clis.run_command(["claude", "--version"], 5)
    git.detect(str(tmp_path))
    trust.process_running("claude.exe")
    assert calls[0] == ["claude", "--version"]
    assert any("rev-parse" in call for call in calls)
    assert calls[-1][0] == "tasklist"
