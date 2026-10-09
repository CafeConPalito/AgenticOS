from pty_run import agy_permission_request as permission_request

PROMPT_ECHO = (
    "> Usa la herramienta report_status del servidor agentic-os con el mensaje 'empezando'. "
    "Después usa complete_task con el\n  resumen 'listo'. Finalmente responde FIN.\n"
)

# Screens captured during the spike (p5-agy-mcp-connected.md, p5-agy-mcp-pretrusted.md).
MCP_DIALOG = PROMPT_ECHO + (
    "● Called 1 MCP tool (agentic-os_agentic-os/report_status) (ctrl+o to expand)\n"
    "MCP\n"
    "────────────────────────────────────────\n"
    "agentic-os_agentic-os/report_status\n"
    "Allow calling this tool?\n"
    "> 1. Yes, allow tool call\n"
    "  4. No, deny tool call\n"
)
COMMAND_DIALOG = PROMPT_ECHO + (
    "● Ran (Get-ChildItem -Force) (ctrl+o to expand)\n"
    "Command\n"
    "────────────────────────────────────────\n"
    "Requesting permission for:\n"
    "   Get-ChildItem -Force\n"
    "Run this command?\n"
    "> 1. Yes, run command\n"
    "  4. No, cancel\n"
)


def test_mcp_dialog_names_the_tool():
    assert permission_request(MCP_DIALOG) == ("mcp", "agentic-os_agentic-os/report_status")


def test_mcp_dialog_with_blank_padding():
    # Partially repainted screen captured in the rerun: blank lines around the tool id.
    screen = "MCP\n\n\n   agentic-os_agentic-os/report_status\n\n      Allow calling this tool?\n"
    assert permission_request(screen) == ("mcp", "agentic-os_agentic-os/report_status")


def test_command_dialog_is_not_mistaken_for_mcp_despite_the_echoed_prompt():
    # The prompt on screen mentions agentic-os/report_status/complete_task: irrelevant.
    assert permission_request(COMMAND_DIALOG) == ("command", "Get-ChildItem -Force")


def test_no_dialog():
    assert permission_request(PROMPT_ECHO + "? for shortcuts\n") is None
