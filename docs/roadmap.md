# Roadmap

Estados: `pendiente` · `spec` · `plan` · `dev` · `validación` · `cerrada`

Flujo de cada fase: ver `CLAUDE.md` (Spec → Plan → Desarrollo → Validación, con 3 puertas de aprobación).

| # | Fase | Estado | Objetivo | Criterios clave (orientativos) | Docs |
|---|---|---|---|---|---|
| 00 | Fundaciones | cerrada (`v0.1`) | Monorepo, docs, ADR del stack, esqueleto FastAPI + Vite + Tauri, lint, scripts de CI local, i18n base | `dev` levanta backend y UI; Tauri abre la ventana con el sidecar; tests de humo en verde | [spec](phases/00-fundaciones/spec.md) · [plan](phases/00-fundaciones/plan.md) · [validación](phases/00-fundaciones/validacion.md) |
| 01 | Spike de CLIs | cerrada (`v0.2`) | Validar en Windows **Claude Code y Antigravity CLI (`agy`)**: PTY interactivo con prompt, inyección MCP, permisos, consumo, hooks. Gemini CLI, OpenCode y Codex más adelante | Matriz verificada por CLI en `spike.md`; prototipos funcionando | [spec](phases/01-spike-clis/spec.md) · [plan](phases/01-spike-clis/plan.md) · [spike](phases/01-spike-clis/spike.md) · [validación](phases/01-spike-clis/validacion.md) |
| 02 | Dominio y CRUD | cerrada (`v0.3`) | Agentes (con plantillas y catálogo de CLIs) y Proyectos (con git y memoria); SQLite + Alembic; API REST; pantallas de Agentes y Proyectos | CRUD completo desde la UI; tests de la API; persistencia en SQLite | [spec](phases/02-dominio-crud/spec.md) · [plan](phases/02-dominio-crud/plan.md) · [validación](phases/02-dominio-crud/validacion.md) |
| 03 | Terminales en vivo | cerrada (`v0.4`) | Ejecuciones lanzadas a mano en PTY, log a disco, WS multi-visor, xterm.js, tomar control (ADR 0003), confianza automática, página de ejecución, dock global y lista de ejecuciones | Sesión real de Claude Code y agy en vivo, interactiva, con scrollback recuperable y sin huérfanos | [spec](phases/03-terminales/spec.md) · [plan](phases/03-terminales/plan.md) · [validación](phases/03-terminales/validacion.md) |
| 04 | Adapters y MCP | cerrada (`v0.5`) | Adapters de los CLIs según ADR 0004 (Claude por flags aislados; `agy` por plugin de workspace), context builder, servidor MCP `agentic-os` con token por ejecución, hooks `Stop`, `fake_agent`; evaluar el SDK de Antigravity | Cada CLI recibe su contexto y su MCP; `complete_task`/`update_status` llegan a la BD | [spec](phases/04-adapters-mcp/spec.md) · [plan](phases/04-adapters-mcp/plan.md) · [validación](phases/04-adapters-mcp/validacion.md) |
| 05 | Scheduler y pipelines | cerrada (`v0.6`) | Modelos de Pipeline/Stage/Task, editor visual de pipeline, colas estrictas, concurrencia, Req→Dev→QA, workspaces (con carpeta directa, `agy` limitado a 1 ejecución por carpeta), memoria de proyecto, Kanban | Un agente encadena tareas de 2 proyectos sin compartir contexto; e2e del pipeline | [spec](phases/05-scheduler-pipelines/spec.md) · [plan](phases/05-scheduler-pipelines/plan.md) · [validación](phases/05-scheduler-pipelines/validacion.md) |
| 06 | Subagentes y human-in-the-loop | cerrada (`v0.7`) | `spawn_subagent`, `create_subtask`, árbol de ejecuciones, Inbox, `request_human`, notificaciones de Windows | La aprobación llega a la Inbox y a la notificación, y la respuesta desbloquea al agente | [spec](phases/06-subagentes-hitl/spec.md) · [plan](phases/06-subagentes-hitl/plan.md) · [validación](phases/06-subagentes-hitl/validacion.md) |
| 07 | Consumo | cerrada (`v0.8`) | Parsers de transcripts por CLI (ADR 0005; prototipo en `spikes/usage_probe.py`), coste equivalente API en Claude y solo tokens en `agy`, límite diario, panel por agente, proyecto y sesión | Las cifras coinciden con las del propio CLI | [spec](phases/07-consumo/spec.md) · [plan](phases/07-consumo/plan.md) · [validación](phases/07-consumo/validacion.md) |
| 08 | Empaquetado v1.0 (MVP) | cerrada (`v1.0`) | Instalador, ajustes, robustez (reinicios, ejecuciones huérfanas, reanudar sesiones) | El instalador funciona en una máquina limpia; los e2e completos pasan | [spec](phases/08-empaquetado/spec.md) · [plan](phases/08-empaquetado/plan.md) · [validación](phases/08-empaquetado/validacion.md) |
| 09 | Mejora de UX/UI | cerrada (`v1.1`) | Revisar la navegación y simplificar la interfaz tras la v1.0: menú y flujos principales, menos elementos por pantalla, jerarquía visual más clara y coherente | Las tareas habituales se hacen en menos pasos y cada pantalla se entiende de un vistazo (revisión con el usuario) | [spec](phases/09-ux-ui/spec.md) · [plan](phases/09-ux-ui/plan.md) · [validación](phases/09-ux-ui/validacion.md) |
| 10 | Equipos y cuentas de CLI | cerrada (`v1.2`) | Agrupar agentes en equipos y usar varias cuentas por CLI (cada agente con su cuenta; sesiones y avisos por cuenta), según el diseño v7 (`docs/design/v2/`) | Dos agentes del mismo CLI trabajan con cuentas distintas; Inicio los muestra por equipo | [spec](phases/10-equipos-cuentas/spec.md) · [plan](phases/10-equipos-cuentas/plan.md) · [validación](phases/10-equipos-cuentas/validacion.md) |
| 11 | Revisión de código | cerrada (`v1.3`) | Ver el código que ha cambiado cada agente: diff por tarea y por ejecución, por fichero y por línea (como `git diff`), con lista de ficheros, añadidos y borrados; visible al validar la tarea (etapa de revisión, Peticiones) y desde la ficha del agente | Al revisar una tarea se ven sus ficheros cambiados y el diff línea a línea antes de aprobar o rechazar | [spec](phases/11-revision-codigo/spec.md) · [plan](phases/11-revision-codigo/plan.md) · [validación](phases/11-revision-codigo/validacion.md) |
| 12 | Control de git | cerrada (`v1.4`) | Control total de git desde la app y proyectos con varios repositorios: repos detectados dentro del proyecto y vinculados de fuera, cada uno con su base; worktrees de tarea y diffs por repo; vista general y acciones en lote; cambios por línea, commit y enmienda, historial con grafo, blame, ramas (las `agentic/T-n` con su tarea y estado), merge, rebase interactivo, editor de conflictos de tres vías, stash, tags, cherry-pick, revert, reset, remotos y push forzado, submódulos, LFS, worktrees, reflog y deshacer, clonar e inicializar, terminal git; integrar la rama de una tarea en las bases (o al aprobarla); pull requests de GitHub y GitLab; claves SSH. Los agentes usan git sin restricciones ni preguntas de permiso, y cada ejecución registra lo que hizo con git | En un proyecto con dos repos, una tarea trabaja en ambos, se integra desde la app en sus bases y se sube o abre un pull request; un agente en modo `manual` hace rebase y push sin que nada lo pare, y su ejecución lo registra | [spec](phases/12-control-git/spec.md) · [plan](phases/12-control-git/plan.md) · [validación](phases/12-control-git/validacion.md) |
| 13 | Pipelines con ramas | cerrada (`v1.5`) | Flujos con varias vías: una etapa puede bifurcarse en ramas (p. ej. Dev backend y Dev frontend) y un LLM decide, según la tarea, qué rama o ramas tomar, explicando por qué; condiciones de cada rama, ramas en paralelo que se vuelven a unir, editor visual del grafo y registro de la decisión en el historial de la tarea | Una tarea de API va sola a Dev backend, una de UI a Dev frontend y una que toca ambas pasa por los dos en paralelo antes de QA, sin elegir la rama a mano | [spec](phases/13-pipelines-ramas/spec.md) · [plan](phases/13-pipelines-ramas/plan.md) · [validación](phases/13-pipelines-ramas/validacion.md) |
| 14 | Conocimiento | cerrada (`v1.6`) | Subida en 3 niveles, conversión, URLs, imágenes, RAG local, MCP `search_knowledge` | Un agente usa un PDF del proyecto para responder | [spec](phases/14-conocimiento/spec.md) · [plan](phases/14-conocimiento/plan.md) · [validación](phases/14-conocimiento/validacion.md) |
| 15 | Ampliación del conocimiento | cerrada (`v1.7`) | Los agentes proponen documentos de conocimiento nuevos (`propose_knowledge`), vinculados a los que los inspiraron, sin tocar los originales y solo con la confirmación del usuario en la Inbox; y un grafo visual de toda la biblioteca que distingue lo que subió el usuario de lo propuesto por agentes, enlaza lo relacionado (por origen y por parecido de contenido) y ayuda a la búsqueda con los vecinos de cada resultado | Un agente que usa el PDF de Celery propone una guía nueva; el usuario la acepta, aparece en el grafo unida al PDF y otro agente la encuentra buscando un tema relacionado | [spec](phases/15-ampliacion-conocimiento/spec.md) |
| 16 | Dictado por voz | cerrada (`v1.8`) | Voz a texto local en los campos donde se escribe mucho (descripción de tarea, instrucciones del agente, motivo de un rechazo, conversación con el Arquitecto): transcripción con Whisper en el backend sin enviar audio fuera, modelo elegible y descargable desde Ajustes (reutiliza la gestión de modelos locales de la fase 14), botón de micrófono y atajo de mantener pulsado, texto insertado en el cursor; validar pronto el permiso de micrófono en WebView2 | Se dicta en español una descripción de tarea de un par de párrafos sin conexión a internet y llega al campo en pocos segundos | [spec](phases/16-dictado-voz/spec.md) · [plan](phases/16-dictado-voz/plan.md) · [validación](phases/16-dictado-voz/validacion.md) |
| 17 | Skills | pendiente | Biblioteca SKILL.md en 3 niveles, autoselección, `propose_skill` | La skill relevante se carga sola; se registra una skill creada por un agente | |
| 18 | Conexiones MCP | pendiente | Conectar los agentes a servidores MCP externos (GitHub, bases de datos, navegador, servicios propios…): catálogo de conexiones (stdio o HTTP) con sus credenciales guardadas de forma segura, asignación por agente o por proyecto, inyección en la configuración de cada CLI por ejecución (junto al MCP `agentic-os`), prueba de conexión y lista de herramientas | Un agente usa en una tarea las herramientas de un MCP externo configurado desde la app, sin tocar a mano la configuración del CLI | |
| 19 | Meta-agentes | pendiente | Agente Arquitecto, propuestas en borrador, plantillas | Se crea un "Redactor" desde una conversación y ejecuta una tarea | |
| 20 | Avisos externos | pendiente | Telegram, email, Slack | Los avisos llegan al móvil | |
| 21 | Codex, OpenCode e instalación de CLIs | pendiente | Añadir **Codex CLI** y **OpenCode** como CLIs de primera clase, con su adapter (contexto y MCP `agentic-os` por ejecución, hooks o equivalente para cerrar la tarea), cuentas, lectura de consumo de sus transcripts y reanudación de sesiones; spike previo en Windows como el de la fase 01. Si el usuario no tiene ningún CLI (o le falta alguno), la app detecta cuáles faltan y los instala desde la propia app (Claude Code, `agy`, Codex, OpenCode), comprobando requisitos como Node, mostrando el progreso y guiando el inicio de sesión de cada uno | Un agente con Codex y otro con OpenCode completan una tarea del pipeline con su contexto y su MCP y su consumo aparece en el panel; en una máquina sin CLIs, el asistente inicial instala uno, el usuario inicia sesión y lanza su primera ejecución sin abrir una terminal | |
| 22 | Instaladores firmados | pendiente | Instaladores multiplataforma y firmados: Windows (NSIS/MSI con firma Authenticode, sin aviso de SmartScreen), macOS (`.dmg` firmado con Developer ID y notarizado, Intel y Apple Silicon) y Linux (AppImage, `.deb` y `.rpm` con firma GPG); sidecar del backend construido y firmado para cada plataforma; actualizaciones automáticas firmadas (updater de Tauri); builds y firma en CI | En una máquina limpia de cada sistema la app se instala sin avisos de seguridad, arranca con su backend y se actualiza sola a una versión nueva | |
| 23 | Modo servidor | pendiente | Docker, autenticación, Postgres, WS autenticado; el dictado por voz transcribe en el servidor o en el cliente | La app funciona desplegada en un servidor | |

## Historial
| Fecha | Cambio |
|---|---|
| 2026-10-08 | Roadmap inicial. Fase 00 en spec. |
| 2026-10-08 | Nombre "Agentic OS" confirmado. CLIs iniciales: Claude Code y Antigravity CLI. Diseño de la UI con Claude Design (`docs/design/`). |
| 2026-10-09 | Fase 00 cerrada (`v0.1`). Fase 01 en spec. |
| 2026-10-09 | Spike de CLIs completado: ADRs 0003 (modo de ejecución), 0004 (contexto y MCP por ejecución), 0005 (consumo); fases 03, 04, 05 y 07 ajustadas. |
| 2026-10-09 | Fase 01 cerrada (`v0.2`). Fase 02 en spec. |
| 2026-10-10 | Fase 02 cerrada (`v0.3`). Fase 03 en spec. |
| 2026-10-10 | Fase 03 en validación: ADR 0007 (procesos de las ejecuciones). |
| 2026-10-10 | Fase 03 cerrada (`v0.4`). Fase 04 en spec. |
| 2026-10-11 | Fase 04 en validación: ADR 0008 (coordinación de agentes). |
| 2026-10-11 | Fase 04 cerrada (`v0.5`). Fase 05 en spec. |
| 2026-10-11 | Fase 05 en validación: ADR 0009 (scheduler, colas y workspaces). |
| 2026-10-11 | Fase 05 cerrada (`v0.6`). Fase 06 en spec. |
| 2026-10-11 | Fase 06 en validación: ADR 0010 (human-in-the-loop y subagentes). |
| 2026-10-11 | Fase 06 cerrada (`v0.7`). La fase 07 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-12 | Nueva fase 09 (Mejora de UX/UI) tras la v1.0; las fases 09–13 pasan a ser 10–14. |
| 2026-10-12 | Fase 07 en spec. |
| 2026-10-12 | Spec de la fase 07 aprobada. Fase 07 en plan. |
| 2026-10-12 | Plan de la fase 07 aprobado. Fase 07 en dev. |
| 2026-10-12 | Fase 07 en validación: ADR 0011 (consumo y límites). |
| 2026-10-12 | Fase 07 cerrada (`v0.8`). La fase 08 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-12 | Fase 08 en spec. Auto-update y firma de código fuera de la v1.0. |
| 2026-10-12 | Spec de la fase 08 aprobada. Fase 08 en plan. |
| 2026-10-12 | Plan de la fase 08 aprobado. Fase 08 en dev. |
| 2026-10-12 | Fase 08 en validación: ADR 0012 (empaquetado y reanudación de sesiones). |
| 2026-10-12 | Fase 08 cerrada (`v1.0`, MVP). La fase 09 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-13 | Fase 09 en spec. |
| 2026-10-13 | Fase 09 basada en el diseño v7 de Claude Design (`docs/design/v2/`). Nueva fase 10 (Equipos y cuentas de CLI); las fases 10–14 pasan a ser 11–15. |
| 2026-10-13 | Spec de la fase 09 aprobada. Fase 09 en plan. |
| 2026-10-14 | Plan de la fase 09 aprobado. Fase 09 en dev. |
| 2026-10-14 | Fase 09 en validación: ADR 0013 (navegación, Inicio y atajos). |
| 2026-10-14 | Fase 09 cerrada (`v1.1`). La fase 10 queda pendiente hasta que el usuario decida empezarla. |
| 2026-10-14 | Nueva fase 15 (Instaladores firmados para Windows, macOS y Linux); Modo servidor pasa a ser la 16. |
| 2026-10-14 | Nueva fase 12 (Dictado por voz, local); las fases 12–16 pasan a ser 13–17. |
| 2026-10-14 | Fase 10 en spec. |
| 2026-10-14 | Spec de la fase 10 aprobada (incluye la cuota de las suscripciones, leída de la status line). Fase 10 en plan. |
| 2026-10-14 | Plan de la fase 10 aprobado. Fase 10 en dev. |
| 2026-10-14 | Ampliación de la fase 10 aprobada (CLI secundario por agente y alerta de cambio por cuota). |
| 2026-10-14 | Fase 10 cerrada (`v1.2`); queda anotada la prueba manual con una segunda cuenta real. |
| 2026-10-14 | Nueva fase 11 (Revisión de código: diff por agente y al validar la tarea); las fases 11–17 pasan a ser 12–18. |
| 2026-10-14 | Nueva fase 15 (Conexiones MCP), tras Skills; las fases 15–18 pasan a ser 16–19. |
| 2026-10-14 | Nueva fase 12 (Pipelines con ramas, decididas por un LLM), tras Revisión de código; las fases 12–19 pasan a ser 13–20. |
| 2026-10-15 | Fase 11 en spec. |
| 2026-10-15 | Nueva fase 12 (Control de git: el usuario lleva el repo desde la app y los agentes siguen commiteando), tras Revisión de código; las fases 12–20 pasan a ser 13–21. |
| 2026-10-15 | Spec de la fase 11 aprobada. Fase 11 en plan. |
| 2026-10-15 | Plan de la fase 11 aprobado. Fase 11 en dev. |
| 2026-10-17 | Fase 11 cerrada (`v1.3`); queda anotada la prueba manual con Claude Code y agy reales. |
| 2026-10-17 | Fase 12 en spec. |
| 2026-10-17 | Fase 12 ampliada a petición del usuario: control total de git, proyectos con varios repositorios y agentes sin restricciones de git. |
| 2026-10-17 | Spec de la fase 12 aprobada. Fase 12 en plan. |
| 2026-10-17 | Plan de la fase 12 aprobado. El desarrollo queda pendiente hasta que el usuario decida empezarlo. |
| 2026-10-17 | Fase 12 en dev: spikes (bloque 0) y proyectos con varios repositorios (bloque 1). ADR 0016. |
| 2026-10-18 | Fase 12 en validación: ADRs 0018 (pull requests y credenciales) y 0019 (agentes y git). Pendientes tres pruebas manuales con servicios reales y el OK del usuario. |
| 2026-10-18 | Fase 12 cerrada (`v1.4`); quedan anotadas las pruebas manuales con GitHub, Claude Code y errores de red reales. |
| 2026-10-18 | Fase 13 en spec. |
| 2026-10-18 | Spec de la fase 13 aprobada (decisor *headless*, carpeta y rama de git por vía, ramas en serie en carpeta directa). Fase 13 en plan. |
| 2026-10-18 | Plan de la fase 13 aprobado (vías como tareas hijas, decisor *headless*, rechazos desde una vía acotados a ella). Fase 13 en dev. |
| 2026-10-18 | Fase 13 en validación: ADR 0020 (pipelines con ramas). Pendientes una tarea con agentes reales, la revisión visual del editor y un e2e con ramas anidadas, y el OK del usuario. |
| 2026-10-18 | Fase 13 cerrada (`v1.5`); quedan anotadas la prueba con agentes reales, la revisión visual del editor y un e2e con ramas anidadas. |
| 2026-10-18 | Corregida la versión de la fase 12 en la tabla (`v1.4`). Fase 14 en spec; borrador de la spec de la fase 15, cuyo desarrollo espera al cierre de la 14. |
| 2026-10-18 | Spec de la fase 14 aprobada (ficheros por referencia, una sola pipeline con MarkItDown, búsqueda híbrida, OCR local y descripción de imágenes opcional con un CLI o `llama.cpp`). Fase 14 en plan. |
| 2026-10-18 | Plan de la fase 14 aprobado (imágenes sueltas por copia temporal, describidor bloqueado sin fallo, reprocesar conserva lo anterior). Fase 14 en dev. |
| 2026-10-18 | Fase 14 en dev: bloque 0 (spikes S1–S9, con cambios al diseño aprobados) y bloque 1 (documentos por referencia, migración `0016` y su API). Sigue el bloque 2 (pipeline y conversión). |
| 2026-10-19 | Fase 14, bloque 2: pipeline de conversión (MarkItDown con conversores propios), trabajador en un proceso de baja prioridad, cola, reprocesar, eventos en vivo y monitor de recursos; el sidecar pasa a 87 MB. Sigue el bloque 3 (modelos locales). |
| 2026-10-19 | Fase 14, bloque 3: catálogo fijado de modelos y motores locales con descargas reanudables y verificadas, elección por trabajo y *token* de Hugging Face. Decisión: los modelos de OCR (~18 MB) van dentro del instalador (el *sidecar* pasa a 102,8 MB). Sigue el bloque 4 (imágenes y OCR). |
| 2026-10-19 | Fase 14, bloque 4: imágenes y OCR (RapidOCR en el trabajador con los modelos incluidos en el instalador; las páginas escaneadas pasan a ser su texto); el *sidecar* pasa a 149 MB. Sigue el bloque 5 (índice y búsqueda). |
| 2026-10-19 | Fase 14, bloque 5: troceado, *embeddings* con ONNX en el trabajador, índice de trozos, vectores y palabras, búsqueda híbrida (significado + identificadores) y reindexado al cambiar de modelo; con el modelo real, acierto 0,93 en los 5 primeros. Sigue el bloque 6 (contexto y MCP). |
| 2026-10-19 | Fase 14, bloque 6: la ejecución recibe la sección «Conocimiento» (índice y documentos pequeños dentro del presupuesto) y las herramientas MCP `search_knowledge` y `read_knowledge`; un agente usa un PDF del proyecto para responder (CA1). Sigue el bloque 7 (describir imágenes con IA). |
| 2026-10-19 | Fase 14, bloque 7: descripción opcional de imágenes con IA, por CLI en modo *headless* o con `llama-server` local, y ajustes de conocimiento en la API. Sigue el bloque 8 (interfaz de la biblioteca). |
| 2026-10-19 | Fase 14, bloque 8: interfaz de la biblioteca (página general y pestañas de proyecto y agente), arrastrar y soltar, progreso en vivo, ficha con visor y reubicación, monitor de CPU/GPU/memoria y prueba de búsqueda. Sigue el bloque 9 (ajustes y modelos locales). |
| 2026-10-19 | Fase 14, bloque 9: Ajustes › Conocimiento (límites y descripción de imágenes con IA opcional) y Ajustes › Modelos locales (descargar, cancelar, borrar y elegir modelo, token de Hugging Face), y uso de disco de la biblioteca y los modelos. Sigue el bloque 10 (e2e, validación y cierre). |
| 2026-10-19 | Nueva fase 15 (Ampliación del conocimiento: propuestas de los agentes y grafo); Dictado por voz y las siguientes pasan a ser 16–22. Fase 15 en spec (borrador). |
| 2026-10-19 | Spec de la fase 15 aprobada con las recomendaciones para las cinco preguntas abiertas. Fase 15 en plan; su desarrollo espera al cierre de la 14. |
| 2026-10-19 | Estado de las fases: 00–13 cerradas; 14 en dev (bloques 0–9 hechos, falta el 10: e2e, validación y cierre); 15 en plan; 16–22 pendientes. |
| 2026-10-20 | Fase 14 cerrada (`v1.6`): bloque 10 (revisión de código resuelta, ADR 0021, README, e2e con el sidecar real y validación). Comprobaciones manuales pendientes anotadas en la validación. La fase 15 sigue en plan. |
| 2026-10-20 | Spec de la fase 15 reabierta: los agentes podrán buscar recorriendo el grafo (mapa de temas, exploración de varios saltos, caminos). Fase 15 en spec. |
| 2026-10-20 | Spec de la fase 15 reaprobada con el apartado D. Fase 15 en plan. |
| 2026-10-20 | Borrador del plan de la fase 15 y del ADR 0022 (pendientes de aprobación). |
| 2026-10-21 | Plan de la fase 15 aprobado. Fase 15 en dev (rama `phase/15-ampliacion-conocimiento`). |
| 2026-10-22 | Fase 15 en validación: bloques 0–9 hechos, revisión de código resuelta, validación redactada; espera el OK del usuario. |
| 2026-10-22 | Fase 15 cerrada (`v1.7`): OK del usuario, merge a `main`. Pendiente manual anotado: `agy` real e instalador en máquina limpia. |
| 2026-10-22 | Fase 16 en spec: borrador actualizado al estado tras las fases 14 y 15 (campos reales, catálogo con tipo `speech`, motor como proceso aparte). |
| 2026-10-22 | Spec de la fase 16 aprobada. Fase 16 en plan. |
| 2026-10-23 | Plan de la fase 16 aprobado. Fase 16 en dev (rama `phase/16-dictado-voz`). |
| 2026-10-23 | Fase 16 en validación: ADR 0023 (dictado por voz local), revisión de código resuelta y validación redactada. Pendientes las comprobaciones manuales con la app instalada (permiso del micrófono, atajo mantenido, `Ctrl+Z`, tiempo real con voz real) y el OK del usuario. |
| 2026-10-23 | Fase 16 cerrada (`v1.8`): OK del usuario, merge a `main`. Pendientes manuales anotados: permiso del micrófono en la app instalada, atajo mantenido, `Ctrl+Z`, tiempo real con voz real y descarga real. |
| 2026-10-23 | Nueva fase 21 (Codex, OpenCode e instalación de CLIs desde la app), antes de Instaladores firmados; las fases 21–22 pasan a ser 22–23 (referencias actualizadas en ADRs, visión y fases 14 y 16). |
