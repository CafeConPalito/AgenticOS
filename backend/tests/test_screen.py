from agentic_os.models.agent import Cli
from agentic_os.services.runs.screen import ScreenState

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
