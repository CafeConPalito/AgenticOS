# Fase 04: Adapters y MCP · Spec

- **Estado**: aprobada
- **Rama**: `phase/04-adapters-mcp`

## Objetivo
Que cada ejecución arranque con **el contexto de su agente**:
- sus instrucciones;
- la memoria del proyecto;
- su modo de permisos.

Y que esté **conectada al servidor MCP `agentic-os`**, para que el agente:
- informe de su progreso;
- termine por sí mismo dejando un resumen;
- apunte lo que aprende en la memoria del proyecto.

Todo ello sin tocar la configuración global del usuario ([ADR 0004](../../adr/0004-per-run-context-and-mcp.md)). Es la base que necesita el scheduler de la fase 05 para encadenar trabajo sin que nadie mire la terminal.

## Alcance
### Dentro
**Adapters de CLI** (sustituyen al lanzador mínimo de la fase 03), con una interfaz común:
- **Claude Code**, todo por flags:
  - `--settings` con nuestros hooks;
  - `--mcp-config` + `--strict-mcp-config`;
  - instrucciones con `--append-system-prompt-file`;
  - `--permission-mode` y `--allowedTools` según el agente;
  - se sigue ignorando la configuración del usuario.
- **agy**, por **plugin de workspace** `.agents/plugins/agentic-os/` en la carpeta del proyecto:
  - contenido: `plugin.json`, `mcp_config.json` con el token en la URL, `hooks.json` y `rules/AGENTS.md`;
  - la entrada se añade a `.git/info/exclude`, y el plugin se borra al terminar (y al arrancar, si quedó alguno de una ejecución interrumpida);
  - se lanza **sin `-i`**: se espera a que su MCP conecte y entonces se escribe el prompt;
  - **una sola ejecución de agy a la vez por carpeta**: un segundo lanzamiento recibe un error claro.
- Los archivos de cada ejecución viven en `<data_dir>\runs\<id>\`, nunca en el proyecto, salvo el plugin de agy.

**Context builder**: compone las instrucciones de la ejecución:
- rol e instrucciones del agente;
- memoria del proyecto;
- cómo usar las herramientas de `agentic-os`: informar del progreso, terminar con `complete_task`, apuntar en la memoria;
- carpeta de trabajo.

El prompt de la ejecución sigue siendo el mensaje inicial.

**Permisos por agente** (el campo `permission_mode` de la fase 02), traducidos a cada CLI según el spike (P6):

| Modo | Claude Code | agy |
|---|---|---|
| Autónomo | `bypassPermissions` | `--dangerously-skip-permissions` |
| Restringido | `acceptEdits` + herramientas permitidas | `--mode accept-edits` |
| Preguntar | `manual` | por defecto |

Las herramientas propias de `agentic-os` están siempre preaprobadas.

**Servidor MCP `agentic-os`** (Streamable HTTP en el propio backend):
- **Token por ejecución**: un token desconocido o de una ejecución terminada recibe 401. Un token solo puede leer o escribir su propia ejecución y la memoria de su proyecto.
- Herramientas:
  - `get_context`: instrucciones, prompt y memoria del proyecto;
  - `report_status(mensaje)`: progreso visible en la UI;
  - `complete_task(resumen)`: la ejecución queda **«Completada»** con su resumen y, al acabar el turno, Agentic OS cierra el CLI de forma ordenada;
  - `write_project_memory(nota)`: añade una nota fechada y firmada por el agente a la memoria del proyecto (pestaña Memoria).

**Hooks** de los dos CLIs, enviados al backend con el token de la ejecución:
- **fin de turno** (`Stop`): actividad «Esperando» fiable, y la señal para cerrar tras `complete_task`;
- **inicio de turno**: actividad «Trabajando»;
- **id de sesión de agy** (`conversationId`): se guarda, como ya se hace con Claude;
- un hook nunca puede bloquear ni romper el CLI, aunque el backend no responda.

La actividad pasa a leerse de los hooks, y la pantalla queda como respaldo (corrige el falso «Esperando» de agy durante el arranque).

**Eventos**:
- cada llamada MCP y cada hook relevante se guarda como evento de la ejecución;
- **panel «Eventos MCP»** en la columna derecha de la página de ejecución, según la captura `09a`: hora, función y argumento, en vivo y persistido;
- en el panel izquierdo, el **último estado** informado y el **resumen final**;
- estado «Completada» en la página, las listas y el dock.

**CLI falso de pruebas** ampliado para llamar al MCP y a los hooks como los CLIs reales: tests de extremo a extremo de los dos adapters sin gastar en modelos.

### Fuera
- Tareas, pipelines, colas, concurrencia por agente, workspaces de tipo worktree y memoria resumida automática (fase 05).
- `create_subtask`, `spawn_subagent`, `request_human`, Inbox y notificaciones (fase 06).
- Consumo y transcripts (fase 07). Los hooks ya traen la ruta del transcript, pero aquí no se usa.
- Adapters de Gemini CLI, Codex y OpenCode, y el SDK de Python de Antigravity.
- Modo headless.
- Editar los permisos de las herramientas MCP desde la UI.

## Historias de usuario
- Como usuario, quiero lanzar a «Dev» con sus instrucciones y que sepa qué rol tiene y qué hay en la memoria del proyecto, sin repetírselo en cada prompt.
- Como usuario, quiero que el agente me cuente en qué está y que, al terminar, deje un resumen y cierre su sesión solo.
- Como usuario, quiero que lo que un agente aprende de un proyecto quede en su memoria para las siguientes ejecuciones.
- Como usuario, quiero que un agente «Autónomo» no me pida permisos y uno en «Preguntar» sí, diga lo que diga mi configuración global de Claude.
- Como usuario, quiero que mi configuración de Claude Code y de agy quede intacta, y que en mi proyecto no queden restos de Agentic OS.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Claude Code real**: arranca con las instrucciones del agente y la memoria del proyecto (el agente las conoce sin que se las diga el prompt); `report_status`, `write_project_memory` y `complete_task` llegan a la BD; la ejecución acaba «Completada» con su resumen y el CLI se cierra solo | Prueba manual + capturas; tests con el CLI falso |
| CA2 | **agy real**: lo mismo mediante el plugin de workspace; el prompt se envía cuando el MCP está conectado; al terminar no queda `.agents/plugins/agentic-os/`, y git no lo ve mientras existe | Prueba manual + capturas; tests del adapter |
| CA3 | **Permisos**: los tres modos se traducen a cada CLI; con Claude en «Preguntar» la TUI pide permiso aunque la configuración global diga `auto`, y en «Autónomo» no lo pide | Tests de argv/plugin por modo + prueba manual con los dos CLIs |
| CA4 | **Seguridad del MCP**: token por ejecución; un token desconocido o de una ejecución terminada recibe 401; un token no puede tocar otra ejecución ni otro proyecto | Tests de la API MCP |
| CA5 | **Hooks**: el fin de turno marca «Esperando» y el inicio «Trabajando»; agy guarda su `conversationId`; con el backend caído el hook termina sin error y el CLI sigue | Tests con el CLI falso + prueba manual |
| CA6 | **Configuración del usuario intacta**: `~/.claude/settings.json`, `~/.claude.json` (servidores MCP) y la configuración de agy no cambian tras ejecuciones de los dos CLIs; en el proyecto solo queda la línea de `.git/info/exclude` | Comparación antes/después (como en el spike) |
| CA7 | **UI**: panel «Eventos MCP» en vivo y persistido, último estado, resumen y estado «Completada», fieles a `09a` | Tests de componentes + capturas |
| CA8 | Una segunda ejecución de agy en la misma carpeta se rechaza con un mensaje claro; un plugin huérfano de una ejecución interrumpida se limpia al arrancar | Tests |
| CA9 | `check` en verde; ADR (si hay decisiones), README y roadmap actualizados | Salida del `check` + revisión |

## Prerrequisitos
- Fase 03 cerrada (`v0.4`).
- Claude Code y agy instalados (ejecutables nativos) y con sesión iniciada.

## Riesgos y preguntas abiertas
- **agy pide permiso para cada llamada MCP** salvo en modo autónomo (spike P5). En «Preguntar» y «Restringido», cada `report_status` pediría aprobación en la TUI. En el plan se probará una regla que preapruebe solo las herramientas de `agentic-os`; si no existe, se documentará y la UI lo avisará.
- **Conexión asíncrona del MCP de agy**: hay que detectar que conectó (primera petición con su token), con un tiempo máximo y un plan B si no llega.
- **Coste de cada hook**: el ejecutable empaquetado tarda en arrancar. El plan elegirá un comando de hook ligero, sin comillas para agy y que siempre termine con éxito.
- **El plugin de agy escribe en la carpeta del proyecto**: es temporal, está excluido de git y se borra al terminar o en la recuperación, pero si el usuario abre agy a mano en esa carpeta mientras tanto, lo verá.
- **El modelo puede no llamar a `complete_task`**: la ejecución sigue abierta hasta que el usuario la pare. El fin de turno la deja en «Esperando», que se ve en las listas.
- **`--setting-sources project,local`** también ignora preferencias útiles del usuario (modelo por defecto, etc.). Agentic OS fija explícitamente lo que necesita.
