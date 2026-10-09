# Modo headless (P11)

Prompt: «Crea un archivo hola.txt que contenga la palabra hola y después responde LISTO»

## Claude Code

`claude -p Crea un archivo hola.txt que contenga la palabra hola y después responde LISTO --model haiku --output-format stream-json --verbose --strict-mcp-config --permission-mode acceptEdits --session-id 4627f82f-5655-497a-b49a-073cfc8c90ff --max-budget-usd 0.25`

- hola.txt creado: True
- Config global: SIN CAMBIOS

- `system`/hook_started: hook_event, hook_id, hook_name, session_id, uuid
- `system`/hook_started: hook_event, hook_id, hook_name, session_id, uuid
- `system`/hook_response: exit_code, hook_event, hook_id, hook_name, outcome, output, session_id, stderr, stdout, uuid
- `system`/hook_response: exit_code, hook_event, hook_id, hook_name, outcome, output, session_id, stderr, stdout, uuid
- `system`/init: agents, analytics_disabled, apiKeySource, capabilities, claude_code_version, cwd, fast_mode_disabled_reason, fast_mode_state, mcp_servers, memory_paths, messaging_socket_path, mode
- `assistant`: message, parent_tool_use_id, request_id, session_id, timestamp, uuid, wire_tool_inputs
- `rate_limit_event`: rate_limit_info, session_id, uuid
- `user`: message, parent_tool_use_id, session_id, timestamp, tool_result_meta, tool_use_result, uuid
- `assistant`: message, parent_tool_use_id, request_id, session_id, timestamp, uuid
- `result`/success: api_error_status, duration_api_ms, duration_ms, fast_mode_disabled_reason, fast_mode_state, first_content_frame_ms, is_error, modelUsage, num_turns, permission_denials, queued_turn

Resultado: {"session_id": "4627f82f-5655-497a-b49a-073cfc8c90ff", "total_cost_usd": 0.005933870000000001, "usage": {"input_tokens": 4, "cache_creation_input_tokens": 27969, "cache_read_input_tokens": 27717, "output_tokens": 125, "output_tokens_details": {"thinking_tokens": 0}, "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}, "service_tier": "standard", "cache_creation": {"ephemeral_1h_input_tokens": 27969, "ephemeral_5m_input_tokens": 0}, "inference_geo": "global", "iterations": [{"input_tokens": 2, "output_tokens": 6, "cache_read_input_tokens": 27717, "cache_creation_input_tokens": 252, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 252}, "type": "message"}], "speed": "standard", "fallback_credit": null}, "num_turns": 2}

## Antigravity CLI

`agy -p Crea un archivo hola.txt que contenga la palabra hola y después responde LISTO --model gemini-3.8-flash-low --output-format stream-json`

- hola.txt creado: False
- Config global: SIN CAMBIOS

- `?`: conversation_id, event, init
- `?`: event, step_update
- `?`: event, step_update
- `?`: event, step_update
- `?`: event, step_update
- `?`: event, result

Último evento: {"event": "result", "result": {"conversation_id": "2f697a6c-1744-49e5-8402-0ea802c2fc5a", "status": "SUCCESS", "response": "", "duration_seconds": 2.1502688, "num_turns": 1, "usage": {"input_tokens": 11697, "output_tokens": 106, "thinking_tokens": 0, "cache_read_tokens": 0, "total_tokens": 11803}, "denied_actions": [{"action": "write_file", "display_name": "WriteToFile"}]}}
