# Contexto (P4) y permisos (P6)

| CLI | Caso | Flags | Archivos | OK | Archivo creado | Respuesta | Denegaciones |
|---|---|---|---|---|---|---|---|
| claude | p4-append-system-prompt | `--append-system-prompt Empieza SIEMPRE tu respuesta con la etiqueta [AOS-SYS].` | - | ✅ | None | [AOS-SYS] ¡Hola! ¿En qué puedo ayudarte hoy? |  |
| claude | p4-claude-md | `(ninguno)` | CLAUDE.md | ✅ | None | [AOS-MD] ¡Hola! ¿En qué puedo ayudarte hoy? |  |
| agy | p4-agents-md | `(ninguno)` | AGENTS.md | ✅ | None | [AOS-AGENTS] ¡Hola! ¿En qué puedo ayudarte hoy? |  |
| agy | p4-gemini-md | `(ninguno)` | GEMINI.md | ✅ | None | [AOS-GEMINI] ¡Hola! ¿En qué puedo ayudarte hoy? |  |
| agy | p4-agents-rules-dir | `(ninguno)` | .agents/rules/aos.md | ❌ | None | ¡Hola! ¿En qué puedo ayudarte hoy? |  |
| claude | p6-default-write | `(ninguno)` | - | ❌ | True | HECHO |  |
| claude | p6-accept-edits-write | `--permission-mode acceptEdits` | - | ✅ | True | HECHO |  |
| claude | p6-accept-edits-bash | `--permission-mode acceptEdits` | - | ❌ | True | HECHO |  |
| claude | p6-allowed-tools-bash | `--allowedTools Bash(echo:*)` | - | ✅ | True | HECHO |  |
| claude | p6-bypass-disallow-write | `--permission-mode bypassPermissions --disallowedTools Write` | - | ✅ | False | No puedo crear `nota.txt`: la herramienta de escritura está deshabilitada en esta sesión, y el sistema indica que tampoc |  |
| agy | p6-default-write | `(ninguno)` | - | ✅ | False |  | [{"action": "write_file", "display_name": "WriteToFile"}] |
| agy | p6-mode-accept-edits-write | `--mode accept-edits` | - | ✅ | True | HECHO. |  |
| agy | p6-mode-accept-edits-bash | `--mode accept-edits` | - | ✅ | False |  | [{"action": "command", "display_name": "RunCommand"}] |
| agy | p6-skip-permissions-bash | `--dangerously-skip-permissions` | - | ✅ | True | HECHO. |  |
| claude | p6-default-write-isolated | `--setting-sources project,local` | - | ✅ | False | No pude crear `nota.txt`. La escritura fue bloqueada por el sistema de permisos: la herramienta respondió que no se ha c | [{"tool_name": "Write", "tool_use_id": "toolu_01AsjL97rNNRhQS4TrvpSijP", "tool_input": {"file_path": "C:\\Users\\usuario\\AppData\\Local\\AgenticOS-spike\\sandbox\\claude-p6-default-write-isolated-20261 |
| claude | p6-accept-edits-write-isolated | `--setting-sources project,local --permission-mode acceptEdits` | - | ✅ | True | HECHO |  |
| claude | p6-accept-edits-bash-isolated | `--setting-sources project,local --permission-mode acceptEdits` | - | ❌ | True | HECHO | [{"tool_name": "PowerShell", "tool_use_id": "toolu_01UWXHZbTXZhxfFr8E9kirwC", "tool_input": {"command": "echo spike > salida.txt; Get-Content salida.txt", "description": "Write \"spike\" to salida.txt |
| claude | p6-allowed-tools-bash-isolated | `--setting-sources project,local --allowedTools Bash(echo:*)` | - | ❌ | False | HECHO no se pudo completar. No creé `salida.txt`.  Lo intenté de dos formas y ambas fueron bloqueadas por el sistema de  | [{"tool_name": "PowerShell", "tool_use_id": "toolu_01KM536KvsGJaxXX6VBM9tAk", "tool_input": {"command": "echo spike > salida.txt; Get-Content salida.txt", "description": "Write \"spike\" to salida.txt |
| claude | p6-bypass-disallow-write-isolated | `--setting-sources project,local --permission-mode bypassPermissions --disallowedTools Write` | - | ✅ | False | No puedo crear el archivo. La herramienta Write está deshabilitada en esta sesión, y el error indica que también lo está |  |

Configuración global: SIN CAMBIOS