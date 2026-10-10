# Fase 03: Terminales en vivo · Spec

- **Estado**: borrador (pendiente de aprobación)
- **Rama**: `phase/03-terminales`

## Objetivo
Que Agentic OS pueda **lanzar un agente sobre un proyecto en una terminal real** y que puedas verla en vivo, desde varias vistas a la vez, **tomar el control** y devolvérselo al agente, pararla y revisar después lo que pasó. Es el corazón de la experiencia «agentes autónomos con un humano que puede entrar» (ADR 0003). Las tareas, las colas y la inyección de instrucciones y MCP llegan en las fases 04 y 05; aquí se lanza a mano con un prompt.

## Alcance
### Dentro
**Ejecuciones (backend)**
- Nueva entidad **Ejecución** (*Run*):
  - agente, proyecto, prompt y CLI;
  - estado: `starting` → `running` ⇄ `intervening` → `exited` | `stopped` | `failed` | `interrupted`;
  - actividad: `busy` / `idle`;
  - carpeta de trabajo, ID de sesión del CLI, código de salida, fechas, tamaño de la terminal y ruta del log.
- **Gestor de PTYs** en el backend (pywinpty/ConPTY en Windows, `ptyprocess` en Unix, con una interfaz común):
  - lanza el CLI en modo interactivo con su prompt;
  - entorno sin los marcadores de sesión de Claude Code (ADR 0004).
- **Lanzamiento por CLI** (mínimo, hasta los adapters de la fase 04):
  - **Claude Code**: `claude "<prompt>" --model … --session-id <uuid> --setting-sources project,local --strict-mcp-config --permission-mode manual`;
  - **agy**: `agy --model … -i "<prompt>"`;
  - en esta fase todas las ejecuciones usan el modo **Preguntar**: las peticiones de permiso aparecen en la terminal y las respondes tú. La traducción de los modos de permiso, las instrucciones del agente y el MCP llegan en la fase 04;
  - la carpeta de trabajo es la del proyecto (el modo worktree llega en la fase 05).
- **Diálogo de confianza en la carpeta**: se detecta en la pantalla emulada (`pyte`) y se acepta solo, con reintentos (hallazgo del spike).
- **Salida**:
  - un búfer de scrollback en memoria;
  - un log en disco (`<data_dir>/runs/<id>.log`);
  - difusión por **WebSocket** a todos los visores conectados.
- **WebSocket `/api/runs/{id}/terminal`**:
  - al conectar, reenvía el scrollback (o el log, si la ejecución terminó) y después la salida en vivo;
  - mensajes del cliente: `input` (solo si tiene el control) y `resize`.
- **Control**:
  - `POST /api/runs/{id}/control {take}`: envía Esc (interrumpe el turno), pasa a `intervening` y solo ese cliente puede escribir;
  - `{release}`: devuelve la ejecución al agente; si no escribiste nada mientras tenías el control, envía «Continúa con la tarea.» (ADR 0003).
- **Parar**: `POST /api/runs/{id}/stop` cierra de forma ordenada (Claude: `/exit`; agy: doble Ctrl+C) y, si no termina en 15 s, mata el proceso.
- **Actividad** (`busy`/`idle`): señal heurística a partir de la salida reciente y del pie de la TUI (spike P2). Los hooks llegan en la fase 04.
- **Ciclo de vida**:
  - al cerrar el backend se paran todas las ejecuciones activas;
  - al arrancar, las que quedaron «vivas» en la BD se marcan `interrupted`;
  - no deben quedar procesos de CLI huérfanos.

**Interfaz**
- **Lanzar**: botón en la cabecera del agente y del proyecto que abre un diálogo (agente, proyecto, prompt) y lleva a la página de la ejecución.
- **Página de ejecución** (`/ejecuciones/:id`), según `screens.md` §5 y las capturas `09a`/`09b`, sin árbol de subagentes ni eventos MCP (fases 04 y 06):
  - terminal xterm.js grande;
  - píldora «Solo lectura (observando)» / «Estás interviniendo» con el borde ámbar;
  - botones «Tomar control» / «Devolver al agente», Parar y Abrir carpeta;
  - panel lateral con agente, proyecto, estado, actividad, duración, ID de sesión y prompt.
- **Dock de terminal global** (Ctrl+` y botón «Terminal» de la cabecera), según la captura `13a`:
  - pestañas de las ejecuciones activas;
  - posición abajo o a la derecha;
  - botón para expandir a la página de la ejecución.
- **Lista de ejecuciones** (`/ejecuciones`): activas e históricas, con filtros por agente y proyecto. La pestaña **Historial** del agente muestra las suyas.
- Indicadores en vivo: punto pulsante en las ejecuciones `busy` y estado en tiempo real.

### Fuera
- Instrucciones del agente, MCP `agentic-os`, hooks y traducción de permisos (fase 04).
- Tareas, colas, pipelines y worktrees (fase 05).
- Árbol de subagentes, Inbox y notificaciones (fase 06).
- Consumo de la ejecución (fase 07).
- Reanudar una sesión terminada (`--resume`): se valorará en la fase 05.

## Historias de usuario
- Como usuario, quiero lanzar a «Dev» sobre «Tienda online» con un prompt y ver en directo lo que hace en su terminal.
- Como usuario, quiero tomar el control para corregir algo y devolvérselo al agente sin matar la sesión.
- Como usuario, quiero tener a la vista las terminales activas mientras navego por la app, y revisar mañana lo que hizo una ejecución que ya terminó.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Lanzar **Claude Code** desde la UI: la terminal muestra la sesión en vivo, el diálogo de confianza se acepta solo y el agente responde al prompt | Prueba manual con el CLI real + captura |
| CA2 | Lo mismo con **agy** | Prueba manual + captura |
| CA3 | **Tomar control**: Esc interrumpe el turno, puedes escribir y el agente responde; «Devolver» lo reanuda; los demás visores no pueden escribir (el backend rechaza su input) | Tests del backend con un CLI falso + prueba manual |
| CA4 | **Varios visores** (página + dock, o dos ventanas) ven la misma salida a la vez | Test del WebSocket con dos clientes + prueba manual |
| CA5 | **Scrollback**: al reabrir la página de una ejecución activa o terminada (también tras reiniciar la app) se ve todo lo anterior | Tests (reconexión, log de una ejecución terminada) + prueba manual |
| CA6 | **Parar**: cierre ordenado y, si no responde, forzado; estado y código de salida correctos | Tests con un CLI falso que ignora `/exit` |
| CA7 | **Sin huérfanos**: al cerrar la app con ejecuciones activas no queda ningún proceso de CLI; al reabrirla aparecen como `interrupted` | Prueba manual con la app empaquetada + test del arranque |
| CA8 | Lista de ejecuciones, Historial del agente y dock (Ctrl+`) funcionales y fieles al diseño | Tests de componentes + capturas comparadas con `09a`, `09b` y `13a` |
| CA9 | `check` en verde; ADR (si hay decisiones), README y roadmap actualizados | Salida del `check` + revisión |

## Riesgos y preguntas abiertas
- **Procesos huérfanos en Windows**: hay que confirmar que cerrar el ConPTY termina el CLI y sus hijos (Claude lanza Node; agy, su *language server*). Si no basta, se usa un Job Object con «kill on close» para cada ejecución.
- **Rendimiento**: TUIs muy verbosas pueden saturar el WebSocket. Se agrupa la salida cada ~16 ms y el scrollback en memoria se limita (p. ej. 2 MB por ejecución); el log completo queda en disco.
- **Coste**: las pruebas con CLIs reales gastan tokens. Los tests automáticos usan un **CLI falso** (un script que imita la TUI: diálogo de confianza, respuestas, Esc, `/exit`).
- **Sin aislamiento de instrucciones ni MCP hasta la fase 04**: el modo Preguntar fijo hace que nada se ejecute sin tu permiso.
- **Tamaño de la terminal**: un PTY tiene un solo tamaño. Manda el visor con el control o, sin control, el último que redimensionó; los demás ajustan su vista.
