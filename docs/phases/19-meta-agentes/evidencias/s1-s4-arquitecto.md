# Fase 19 · Spikes S1–S4 del Arquitecto (2026-10-25)

Scripts en `spikes/architect/`; ficheros JSON con todos los datos junto a este documento. Claude Code 2.1.310 y `agy` 1.4.7 en Windows 11.

## S1 · Claude Code interactivo como Arquitecto
`s1_claude.py`, evidencias `s1-claude-sonnet-20261025-200953.json` y `s1-claude-opus-20261025-201116.json`. Un solo proceso en PTY para tres turnos, `/exit` y un cuarto turno retomando con `--resume`.

| Pregunta | Resultado |
|---|---|
| (a) Mensaje de varias líneas | ✅ Pegado *bracketed* (`ESC[200~ … ESC[201~` + Enter): **un solo turno** (un `UserPromptSubmit`) con todas las líneas. Claude lo envuelve en `<pasted_content>`; el modelo lo lee bien. |
| (b) Fin de turno y texto | ✅ Un `Stop` por turno. El transcript JSONL (`transcript_path` del *hook*) **crece durante el turno**, bloque a bloque (cambios a 0,3 s, 1,5 s, 15 s…); el texto de la respuesta son los bloques `text` de las entradas `assistant`. |
| (c) Solo nuestras herramientas | ✅ `--tools "" --mcp-config … --strict-mcp-config --allowedTools mcp__architect__*`: sin diálogos de permiso; al pedirle `dir` y leer un fichero responde que no puede, sin intentarlo (ningún `PreToolUse` que no sea MCP). |
| (d) Cerrar y retomar | ✅ `--resume <id>` con otro `mcp.json` (puerto y *token* nuevos): recuerda la conversación y llama al servidor nuevo. ⚠️ El servidor MCP debe estar escuchando al lanzar (en la app lo está: es el backend). |
| (e) Latencia y memoria | Sonnet: turnos de 2–10 s, arranque hasta la primera respuesta ~13 s (con el diálogo de confianza). Opus: turnos de 2–11 s, arranque ~16 s. Retomar: ~13–16 s hasta la respuesta. Memoria del árbol del proceso: **~285 MB** en reposo, ~295 MB tras tres turnos. |
| (f) Configuración del usuario | ✅ Sin cambios. |

## S2 · `agy` interactivo como Arquitecto
`s2_agy.py` + `agy_guard.py`, evidencia `s2-agy-20261025-201922.json` (la primera ejecución, `s2-agy-20261025-201544.json`, sin el paso `/mcp`, muestra el fallo).

| Pregunta | Resultado |
|---|---|
| Conexión al MCP | ⚠️ **Hace falta el paso `/mcp`** antes del primer mensaje (y tras retomar), como ya hace `RunSession._deferred_prompt_step`: sin él, el modelo no ve las herramientas en toda la sesión. Con él conecta en <1 s. |
| (a) Varias líneas | ✅ Pegado *bracketed*: un solo turno con todas las líneas (`lastUserInput`). |
| (b) Fin de turno y texto | ✅ Un `Stop` por turno. El transcript es `~/.gemini/antigravity-cli/brain/<conversación>/.system_generated/logs/transcript_full.jsonl` (`transcriptPath` del *hook*); crece por pasos durante el turno; el texto está en las entradas `PLANNER_RESPONSE` (`content`). |
| (c) Limitar sus herramientas | ✅ No hay flag, pero un *hook* `PreToolUse` (matcher `*`) que devuelve `{"decision": "deny"}` para todo lo que no sea `call_mcp_tool` con `ServerName` = `architect_architect` lo bloquea: intentó `read_file`, se le denegó y siguió con el MCP. Con `--dangerously-skip-permissions` las llamadas MCP no piden permiso. |
| (d) Cerrar y retomar | ✅ `--conversation <id>` conserva el contexto y usa el plugin nuevo (otro *token*). Avisa en el transcript de que «los subagentes se pararon». |
| (e) Latencia y memoria | Turnos de 10–22 s (uno de 52 s tras retomar); hasta la primera respuesta ~22 s; memoria **~250 MB**. |
| (f) Configuración del usuario | ⚠️ `agy` guarda los mensajes en su `history.jsonl` (como con cualquier agente) y **añade cada carpeta nueva a `trustedWorkspaces`**. |

## S3 · Calidad y coste (Sonnet, diez conversaciones)
`s3_quality.py` sobre un servidor MCP con validación real (`servers/architect_full.py`) y una instalación simulada (`fake_install.py`), con las instrucciones base de `instructions.md` + `modes.py`. Cada turno es `claude -p --resume` (mismo modelo, instrucciones y MCP que en interactivo; la mecánica ya la cubren S1/S2). Evidencia `s3-quality-sonnet-20261025-202520.json`.

| Conversación | Turnos | Preguntas 1.ª resp. | Ficha desde el 1.er turno | Referencias inventadas | Problemas finales | Pipeline válido (1.º / final) | Coste | Tiempo |
|---|---|---|---|---|---|---|---|---|
| Redactor | 3 | 3 | sí | 0 | 0 | — | 0,28 $ | 41 s |
| Comercial | 3 | 3 | sí | 0 | 0 | — | 0,24 $ | 36 s |
| QA estricto | 2 | 1 | sí | 0 | 0 | (se metió en un pipeline) | 0,17 $ | 29 s |
| Traductor (petición vaga) | 4 | 3 | sí | 0 | 0 | — | 0,36 $ | 46 s |
| Notion (no instalado) | 3 | 3 | sí | 0 | 0 | — | 0,24 $ | 35 s |
| Modelo inexistente (gpt-5) | 3 | 2 | sí | 0 | 0 | — | 0,18 $ | 24 s |
| Mejorar QA | 2 | 0 | sí | 0 | 0 | — | 0,11 $ | 20 s |
| Equipo de contenidos | 3 | 0 | sí | 0 | 0 | sí / sí (un intento intermedio con ciclo, corregido) | 0,58 $ | 54 s |
| Equipo dev back/front | 2 | 1 | sí | 0 | 0 | sí / sí | 0,19 $ | 33 s |
| Mejorar pipeline | 2 | 0 | sí | 0 | 0 | sí / sí | 0,16 $ | 27 s |

- **Ninguna skill, documento, conexión, modelo ni agente inventado.** Los únicos rechazos (8) fueron de la **cuenta**: la herramienta devolvía `id` y `name` y el modelo usaba el `id`, mientras el validador esperaba el nombre. Es un fallo del contrato de la herramienta, no del modelo.
- **Notion** (no instalado): lo buscó en el registro y lo **sugirió** con `suggest_connection`, sin ponerlo en la ficha. **gpt-5**: explicó que no existe y eligió `sonnet`.
- **Equipos**: reutilizó los agentes existentes (Analista, Dev, QA), eligió equipos existentes, y el pipeline back/front con bifurcación, unión y condiciones claras salió válido a la primera. En «contenidos», un intento intermedio puso un rechazo como enlace (ciclo); el aviso de la herramienta bastó para corregirlo en el mismo turno.
- **Mejorar QA**: solo cambió las conexiones (GitHub con dos herramientas de lectura) y las instrucciones pedidas, sin tocar el resto.
- ⚠️ **Fuera de su encargo**: en modo «un agente» llamó a `set_pipeline` dos veces (el «QA estricto» se metió en el pipeline de la Tienda). Las herramientas de equipo y pipeline no deben estar en ese modo.
- **Preguntas**: en peticiones vagas pregunta (≤ 3) y a la vez rellena lo que ya sabe; en peticiones claras no pregunta. Las instrucciones son de buena calidad (Markdown, «Tu trabajo», límites, formato de entrega y la sección común).
- **Coste**: 0,11–0,58 $ por conversación, **0,25 $ de media** con Sonnet; no hace falta Opus.

## S4 · Tamaño de las respuestas de las herramientas
`s4_sizes.py`, evidencia `s4-sizes-*.json`. Instalación grande: 200 skills, 300 documentos, 50 conexiones.

| Respuesta | Pequeña | Grande |
|---|---|---|
| Todas las skills | ~420 tokens | **~9 800 tokens** |
| Todos los documentos | ~220 | **~11 100** |
| Todas las conexiones con sus herramientas | ~215 | ~2 460 |
| Conexiones sin herramientas | ~110 | ~970 |
| Búsqueda (8 resultados) | ~290 | ~300 |

Listar catálogos enteros no es asumible (y cada respuesta se queda en el contexto de todos los turnos siguientes): skills y documentos se **buscan** (8 resultados); las conexiones se listan sin herramientas y se piden con `get_connection`. En S3 la búsqueda por palabras bastó con 12 skills; con bibliotecas grandes se usa la búsqueda híbrida que ya existe (fases 14 y 17).
