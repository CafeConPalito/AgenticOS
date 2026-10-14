from pathlib import Path

from agentic_os.models.agent import Cli
from agentic_os.services.runs.screen import PermissionDialog, ScreenState

# Screens captured in the phase 01 spike (docs/phases/01-spike-clis/evidencias).
CLAUDE_TRUST = (
    " Accessing workspace:\r\n\r\n"
    " Quick safety check: Is this a project you created or one you trust?\r\n\r\n"
    " ❯ No, exit\r\n"
    "   Yes, I trust this folder\r\n\r\n"
    " Enter to confirm · Esc to cancel\r\n"
)
AGY_TRUST = (
    "Accessing workspace:\r\n"
    "Do you trust the contents of this project?\r\n"
    "> Yes, I trust this folder\r\n"
    "  No, exit\r\n"
    "  ↑/↓ Navigate · enter Confirm\r\n"
)


def screen_with(cli: Cli, text: str) -> ScreenState:
    screen = ScreenState(cli, 120, 30)
    screen.feed(text)
    return screen


def test_claude_trust_dialog_with_no_selected():
    assert screen_with(Cli.CLAUDE, CLAUDE_TRUST).trust_dialog() == (True, False)


def test_claude_trust_dialog_after_moving_down():
    moved = CLAUDE_TRUST.replace(" ❯ No, exit", "   No, exit").replace(
        "   Yes, I trust", " ❯ Yes, I trust"
    )
    assert screen_with(Cli.CLAUDE, moved).trust_dialog() == (True, True)


def test_agy_trust_dialog_preselected():
    assert screen_with(Cli.AGY, AGY_TRUST).trust_dialog() == (True, True)


def test_no_dialog():
    assert screen_with(Cli.CLAUDE, "● UNO\r\n? for shortcuts\r\n").trust_dialog() == (
        False,
        False,
    )


def test_busy_footer_per_cli():
    assert screen_with(Cli.CLAUDE, "1\r\n2\r\nesc to interrupt\r\n").footer_busy()
    assert not screen_with(Cli.CLAUDE, "● UNO\r\n? for shortcuts\r\n").footer_busy()
    assert screen_with(Cli.AGY, "⡿  Generating...\r\nesc to cancel\r\n").footer_busy()
    assert not screen_with(Cli.AGY, "UNO\r\n? for shortcuts\r\n").footer_busy()


def test_agy_exit_armed_notice():
    # Text seen in the real agy log after the first Ctrl+C (phase 03 manual test).
    assert screen_with(Cli.AGY, "> \r\npress ctrl+c again to exit\r\n").exit_armed()
    assert not screen_with(Cli.AGY, "> \r\n? for shortcuts\r\n").exit_armed()


def test_exit_acknowledged_per_cli():
    # Texts seen in the real CLIs' logs once they accepted the exit (phase 03 manual test).
    claude = "Resume this session with:\r\nclaude --resume be7bcc14\r\n"
    agy = "Resume with -c (or command below):\r\nagy --conversation=74d1755d\r\n"
    assert screen_with(Cli.CLAUDE, claude).exit_acknowledged()
    assert screen_with(Cli.AGY, agy).exit_acknowledged()
    assert not screen_with(Cli.CLAUDE, "? for shortcuts\r\n").exit_acknowledged()
    assert not screen_with(Cli.AGY, "press ctrl+c again to exit\r\n").exit_acknowledged()


AGY_TOOL_DIALOG = (
    "MCP\r\n"
    "agentic-os_agentic-os/report_status\r\n"
    "Allow calling this tool?\r\n"
    "> 1. Yes, allow tool call\r\n"
    "  2. Yes, and always allow tool 'agentic-os_agentic-os/report_status' in this conversation\r\n"
    "  3. Yes, and always allow tool 'agentic-os_agentic-os/report_status'"
    " (Persist to settings.json)\r\n"
    "  4. No, deny tool call\r\n"
    "esc to cancel\r\n"
)


def test_agy_dialog_for_our_tools_only():
    # Text of the real dialog (spike p5-agy-mcp-connected.raw.log).
    screen = screen_with(Cli.AGY, AGY_TOOL_DIALOG)
    assert screen.agentic_os_tool_request() == ("agentic-os_agentic-os/report_status", False)
    moved = AGY_TOOL_DIALOG.replace("> 1.", "  1.").replace("  2. Yes", "> 2. Yes")
    assert screen_with(Cli.AGY, moved).agentic_os_tool_request()[1] is True
    other = AGY_TOOL_DIALOG.replace("agentic-os_agentic-os/", "github_github/")
    assert screen_with(Cli.AGY, other).agentic_os_tool_request() is None
    stale = AGY_TOOL_DIALOG + "".join(f"línea {n}\r\n" for n in range(20))
    assert screen_with(Cli.AGY, stale).agentic_os_tool_request() is None


def test_agy_ready_for_prompt():
    assert screen_with(Cli.AGY, ">\r\n? for shortcuts\r\n").ready_for_prompt()
    assert not screen_with(Cli.AGY, AGY_TRUST).ready_for_prompt()
    assert not screen_with(Cli.AGY, "Loading…\r\n").ready_for_prompt()


def test_claude_bypass_consent_is_left_to_the_human():
    # Real screen (phase 04 manual test): first start of Claude Code in bypassPermissions.
    consent = (
        "  WARNING: Claude Code running in Bypass Permissions mode\r\n"
        "  By proceeding, you accept all responsibility for actions taken while running in"
        " Bypass Permissions mode.\r\n"
        "  ❯ No, exit\r\n"
        "    Yes, I accept\r\n"
        "  Enter to confirm · Esc to cancel\r\n"
    )
    screen = screen_with(Cli.CLAUDE, consent)
    assert screen.waiting_for_human() == "bypass_permissions_consent"
    assert screen.trust_dialog() == (False, False)  # never auto-answered as a trust dialog
    assert screen_with(Cli.CLAUDE, "? for shortcuts\r\n").waiting_for_human() is None


# ---------------------------------------------------------------- permission dialogs (phase 06)
SCREENS = Path(__file__).parent / "fixtures" / "screens"


def real_screen(name: str, cli: Cli) -> ScreenState:
    """A screen fed with the raw output of a real CLI run (captured with Claude Code 2.1.296
    and agy 1.3.3, «Preguntar» mode, dialog still open)."""
    screen = ScreenState(cli, 120, 32)
    screen.feed((SCREENS / f"{name}.log").read_text("utf-8"))
    return screen


def test_claude_permission_dialogs_from_real_screens():
    write = real_screen("claude-write", Cli.CLAUDE).permission_dialog()
    assert write is not None and write.kind == "claude"
    command = real_screen("claude-subagent", Cli.CLAUDE).permission_dialog()
    assert command is not None
    # git --version needed no permission: the run went on, no dialog at the bottom.
    assert real_screen("claude-bash", Cli.CLAUDE).permission_dialog() is None


def test_agy_command_dialog_from_a_real_screen():
    dialog = real_screen("agy-command", Cli.AGY).permission_dialog()
    assert dialog is not None
    assert (dialog.kind, dialog.subject) == ("command", "git --version")


def test_agy_file_edit_dialog():
    """agy 1.3.5 asks «Accept this file edit?» (captured from a stuck QA run)."""
    screen = ScreenState(Cli.AGY, 120, 40)
    screen.feed(
        "F:\\test-front\\src\\Pages.test.tsx  +36 -1\r\n"
        "   4 +  import { Layout } from '../components/Layout';\r\n"
        "  … 12 more lines (f for full diff)\r\n"
        "shift+tab to auto-approve file edits\r\n"
        "Accept this file edit?\r\n"
        "> 1. Yes, accept this change\r\n"
        "  2. No, reject this change\r\n"
        "↑/↓ Navigate · tab Amend · f full diff\r\n"
        "esc to cancel\r\n"
    )
    assert screen.permission_dialog() == PermissionDialog(
        "edit", "F:\\test-front\\src\\Pages.test.tsx"
    )


def test_agy_dialogs_for_our_own_tools_are_not_permission_requests():
    screen = ScreenState(Cli.AGY, 100, 30)
    screen.feed(
        "MCP\r\nagentic-os_agentic-os/report_status\r\nAllow calling this tool?\r\n"
        "> 1. Yes, allow tool call\r\n  4. No, deny tool call\r\nesc to cancel\r\n"
    )
    assert screen.permission_dialog() is None
    other = ScreenState(Cli.AGY, 100, 30)
    other.feed(
        "MCP\r\ngithub_github/create_issue\r\nAllow calling this tool?\r\n"
        "> 1. Yes, allow tool call\r\n  4. No, deny tool call\r\nesc to cancel\r\n"
    )
    assert other.permission_dialog() == PermissionDialog("tool", "github_github/create_issue")


def test_claude_output_that_only_looks_like_a_dialog_is_not_one():
    screen = ScreenState(Cli.CLAUDE, 100, 30)
    screen.feed(
        "He hecho git commit --amend para corregir el mensaje.\r\n"
        "1. Yes, it works\r\nNo errors found.\r\n> \r\n"
    )
    assert screen.permission_dialog() is None
