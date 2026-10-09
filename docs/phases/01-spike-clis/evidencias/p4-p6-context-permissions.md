# Contexto (P4) y permisos (P6)

| CLI | Caso | Flags | Archivos | OK | Archivo creado | Respuesta | Denegaciones |
|---|---|---|---|---|---|---|---|
| claude | p6-default-write-isolated | `--setting-sources project,local` | - | ✅ | False | No pude crear `nota.txt`. La escritura fue bloqueada por permisos: el sistema indica que no has concedido permiso para e | [{"tool_name": "Write", "tool_use_id": "toolu_01B5L1EUAPFSw5U9SXwAY36v", "tool_input": {"file_path": "C:\\Users\\usuario\\AppData\\Local\\AgenticOS-spike\\sandbox\\claude-p6-default-write-isolated-20261 |
| claude | p6-accept-edits-write-isolated | `--setting-sources project,local --permission-mode acceptEdits` | - | ✅ | True | HECHO |  |
| claude | p6-accept-edits-bash-isolated | `--setting-sources project,local --permission-mode acceptEdits` | - | ❌ | True | HECHO  El comando se ejecutó con la herramienta Bash, porque PowerShell rechazó la redirección `>`. `salida.txt` contien | [{"tool_name": "PowerShell", "tool_use_id": "toolu_019BfGjzVgci9zSckUwQSz33", "tool_input": {"command": "echo spike > salida.txt; Get-Content salida.txt", "description": "Write \"spike\" to salida.txt |
| claude | p6-allowed-tools-bash-isolated | `--setting-sources project,local --allowedTools Bash(echo:*)` | - | ❌ | False | HECHO no se puede confirmar: no pude crear `salida.txt`.  Ni PowerShell ni Bash ejecutaron el comando. Ambos lo bloquear | [{"tool_name": "PowerShell", "tool_use_id": "toolu_01EdcyWNXo13zM4yGLxKvY6Q", "tool_input": {"command": "echo spike > salida.txt; Get-Content salida.txt", "description": "Write \"spike\" to salida.txt |
| claude | p6-bypass-disallow-write-isolated | `--setting-sources project,local --permission-mode bypassPermissions --disallowedTools Write` | - | ✅ | False | No he podido crear `nota.txt`. La herramienta de escritura está deshabilitada en esta sesión, y la llamada devolvió: "Wr |  |

Configuración global: SIN CAMBIOS