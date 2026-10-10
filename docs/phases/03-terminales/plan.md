# Fase 03: Terminales en vivo · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: borrador (pendiente de aprobación, Puerta 2)
- **Rama**: `phase/03-terminales`

## Diseño

### Backend
**Dependencias nuevas**:
- `pywinpty` 3 (Windows) y `ptyprocess` 0.7 (Unix), elegidos por marcador de plataforma;
- `pyte` 0.8 (pantalla emulada para detectar diálogos y actividad).

```
backend/src/agentic_os/
  models/run.py                Run (migración 0002)
  schemas/run.py               RunCreate, RunRead, ControlAction
  services/pty/
    base.py                    PtyProcess (interfaz): spawn, read, write, resize, alive, terminate, pid
    windows.py, posix.py       implementaciones (pywinpty / ptyprocess)
    job.py                     Windows Job Object «kill on close» para todo el árbol del backend
  services/runs/
    launcher.py                argv + entorno por CLI (claude / agy) y SESSION_MARKERS
    screen.py                  pyte + reglas por CLI: diálogo de confianza, actividad (pie de la TUI), salida
    session.py                 RunSession: hilo lector, scrollback, log, difusión, control, parar
    manager.py                 RunManager: registro de sesiones, persistencia de estado, apagado y recuperación
  api/runs.py                  REST + WebSocket
```

**Modelo `runs`** (migración `0002`):
- `id`, `workspace_id`, `agent_id` (FK, ON DELETE SET NULL) y `project_id` (FK, ON DELETE SET NULL);
- copia de `agent_name`, `project_name` y `cli`, para que el historial sobreviva a un borrado;
- `prompt`, `cwd`, `status`, `activity`, `cli_session_id`, `exit_code`, `cols`, `rows`, `log_path`;
- `started_at`, `ended_at`, `created_at`, `updated_at`.

**Lanzamiento** (`launcher.py`):
- Claude:
  ```
  claude "<prompt>" --model <m> --session-id <uuid> --setting-sources project,local --strict-mcp-config --permission-mode manual
  ```
  El prompt va primero (spike: las opciones variádicas se tragan el posicional). El `uuid` es `cli_session_id`.
- agy: `agy [--model <m>] -i "<prompt>"`. El ID de conversación se obtendrá con los hooks en la fase 04.
- Entorno: `os.environ` sin `SESSION_MARKERS` (ADR 0004).
- El ejecutable sale de `shutil.which`. Para los tests, `Settings.cli_command_overrides` permite sustituirlo por el CLI falso.

**`RunSession`**:
- **Hilo lector** del PTY (bloqueante). Cada fragmento:
  1. se añade al log en disco (`<data_dir>/runs/<id>.log`, UTF-8);
  2. se añade al **scrollback** en memoria (máximo 2 MB, recortando por el principio);
  3. alimenta la **pantalla pyte**;
  4. se publica en el bucle asyncio con `loop.call_soon_threadsafe`, agrupado cada ~16 ms para cada visor.
- **Reglas de pantalla** (de cada CLI, sacadas del spike):
  - confianza en la carpeta (Claude: ↓ + Enter hasta ver «❯ Yes, I trust»; agy: Enter con reintentos);
  - actividad `busy` si el pie dice «esc to interrupt» (Claude) o «esc to cancel» (agy), o si hubo salida en los últimos 1,5 s; `idle` en otro caso.
- **Visores**: conjunto de colas asyncio, una por WebSocket. Si un visor se queda atrás (más de 1 MB en su cola), se le desconecta y él se reconecta y recibe un snapshot.
- **Control**: `controller: str | None` (id de cliente).
  - `take` → Esc + `intervening` + `typed=False`.
  - `input` → solo si `client_id == controller`; marca `typed=True`.
  - `release` → si `typed` es falso, envía «Continúa con la tarea.» + Enter; vuelve a `running`.
- **Parar**:
  1. Claude: Esc, `/exit` + Enter; agy: Ctrl+C dos veces.
  2. Espera hasta 15 s y, si sigue vivo, `terminate(force)`.
  3. Resultado: `stopped`. Si sale solo: `exited` con su código. Si falla al lanzar: `failed`.
- **Tamaño**: `resize` lo acepta del controlador o, si no hay controlador, del último visor que lo envía.

**`RunManager`** (en `app.state`):
- `launch(agent, project, prompt)`: crea la fila y la sesión.
- `get(id)`, `stop(id)`, `shutdown()` (para todas en el lifespan, con espera corta).
- `recover()` al arrancar: las filas `starting`/`running`/`intervening` sin sesión pasan a `interrupted`.
- Las actualizaciones de estado se escriben en la BD con sesiones cortas desde el hilo de eventos.

**Sin huérfanos** (ADR 0007):
- Al arrancar, el backend crea un **Job Object** con `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` y se asigna a sí mismo. Todos los procesos que lanza (los CLIs y sus hijos: Node, el language server de agy) heredan el job.
- Si el backend muere, aunque sea de forma brusca, Windows cierra el handle y mata todo el árbol.
- Complementa el apagado ordenado del lifespan y el watchdog del ADR 0002.

**API**:
| Método | Ruta | |
|---|---|---|
| POST | `/api/runs` | `{agent_id, project_id, prompt}` → 201 `RunRead` (422 si el CLI no está instalado o el proyecto no tiene carpeta) |
| GET | `/api/runs?agent_id=&project_id=&active=` | lista (más recientes primero) |
| GET | `/api/runs/{id}` | detalle con `controller` y `viewers` |
| POST | `/api/runs/{id}/control` | `{action: "take"\|"release", client_id}` (409 si otro tiene el control) |
| POST | `/api/runs/{id}/stop` | 202; el estado final llega por WS / GET |
| WS | `/api/runs/{id}/terminal?client_id=` | servidor → `{type:"snapshot",data}` y después `output` / `state` / `exit`; cliente → `{type:"input",data}` / `{type:"resize",cols,rows}` |

### Frontend
**Dependencias**: `@xterm/xterm` 6, `@xterm/addon-fit`, `@xterm/addon-web-links` y `zustand` (estado del dock).

```
frontend/src/
  api/runs.ts                 useRuns(filtros), useRun(id) (refetch mientras esté activa), useLaunchRun, useStopRun, useRunControl
  lib/terminal-socket.ts      TerminalSocket: URL ws a partir de la base, reconexión con backoff, input/resize, eventos
  lib/client-id.ts            id de visor por pestaña (sessionStorage)
  components/terminal/
    XtermView.tsx             xterm + fit + web-links; tema XTERM_THEME del diseño; solo lectura salvo con el control
    TerminalPanel.tsx         marco del diseño: cabecera, píldora «Solo lectura»/«Estás interviniendo», Tomar/Devolver, pie
    TerminalDock.tsx          dock global: pestañas de las ejecuciones activas, abajo/derecha, expandir, cerrar
    dock-store.ts             zustand: open, position, activeRunId (persistido con try/catch)
  pages/runs/
    RunsPage.tsx              /ejecuciones: tabla + filtros (agente, proyecto, activas)
    RunPage.tsx               /ejecuciones/:id: cabecera (título, estado, agente, proyecto, Parar, Abrir carpeta) + terminal + panel lateral
    LaunchRunDialog.tsx       diálogo Lanzar (agente, proyecto, prompt); se abre desde el agente y el proyecto
    RunStatusBadge.tsx        estado → tono (running = punto pulsante)
  pages/agents/tabs/HistoryTab.tsx   ejecuciones del agente (sustituye al «próximamente»)
```
- **Atajo Ctrl+`** y botón «Terminal» de la cabecera (ya activo) abren el dock.
- Breadcrumb: Ejecuciones / `<agente> · <prompt recortado>`.
- **Textos** en `es.json` (`runs.*`, `terminal.*`); la terminal muestra lo que emite el CLI tal cual.

### Escritorio
- La CSP ya permite `ws://127.0.0.1:*`; se verifica en la app empaquetada.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/{models/run.py,schemas/run.py,services/pty/**,services/runs/**,api/runs.py}` | nuevos |
| `backend/src/agentic_os/{app.py,config.py,__main__.py}` | lifespan (manager, recover, shutdown), override de CLIs, Job Object |
| `backend/src/agentic_os/db/migrations/versions/0002_runs.py` | nuevo |
| `backend/tests/fake_cli.py`, `backend/tests/test_{pty,launcher,screen,runs_api,runs_ws,job}.py` | nuevos |
| `frontend/src/{api/runs.ts,lib/*,components/terminal/**,pages/runs/**}`, `HistoryTab.tsx`, `routes.tsx`, `AppShell.tsx`, `AppHeader.tsx`, `es.json` | nuevos / modificados |
| `docs/adr/0007-run-processes.md`, `README.md`, `docs/roadmap.md` | nuevo / modificados |

## Tareas (en orden, cada una en su commit)
1. [ ] Rama. Abstracción PTY (Windows / Unix) + tests con un proceso simple.
2. [ ] CLI falso (`tests/fake_cli.py`) que imita la TUI: confianza, respuesta, Esc → «Interrupted», «Continúa», `/exit`, `--ignore-exit`.
3. [ ] Modelo `Run` + migración `0002` + schemas; `launcher.py` + tests (argv por CLI, entorno sin marcadores).
4. [ ] `screen.py` (confianza y actividad) + `RunSession` + `RunManager` (lanzar, scrollback, log, visores, control, parar, recover y shutdown) + tests con el CLI falso.
5. [ ] API REST + WebSocket + tests (dos visores, input rechazado, take/release, stop forzado, reconexión, log de una ejecución terminada, recover).
6. [ ] Job Object (ADR 0007) + test (el hijo muere al cerrar el job).
7. [ ] Frontend: dependencias, `runs.ts`, `TerminalSocket`, `XtermView`, `TerminalPanel`.
8. [ ] Página de ejecución + diálogo Lanzar + lista + Historial del agente; tests.
9. [ ] Dock global (Ctrl+`) + store; tests.
10. [ ] Pruebas manuales con Claude y agy reales (CA1, CA2) y con la app empaquetada (CA7); capturas.
11. [ ] ADR 0007, README, `validacion.md` y `/code-review`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_pty.py`: spawn/read/write/resize/terminate con un script Python | base |
| `test_launcher.py`: argv de Claude (prompt primero, aislamiento, `--session-id`) y de agy; sin `SESSION_MARKERS` en el entorno | CA1, CA2 |
| `test_screen.py`: detección del diálogo de confianza y de la actividad con pantallas reales del spike | CA1, CA2 |
| `test_runs_api.py` con el CLI falso: lanzar → `running`, confianza aceptada, respuesta en la salida | CA1 |
| `test_runs_ws.py`: dos visores reciben lo mismo; el input de quien no tiene el control se ignora; take → «Interrupted»; release sin escribir → «Continúa»; reconexión → snapshot | CA3, CA4, CA5 |
| `test_runs_api.py`: stop ordenado (`exited`/`stopped`), stop forzado con `--ignore-exit`, ejecución terminada → log; `recover()` marca `interrupted` | CA5, CA6, CA7 |
| `test_job.py`: proceso hijo dentro de un job que muere al cerrar el handle | CA7 |
| `RunPage.test.tsx`, `TerminalPanel.test.tsx`, `TerminalDock.test.tsx`, `LaunchRunDialog.test.tsx`, `RunsPage.test.tsx` (WebSocket simulado) | CA3, CA8 |
| Manual: Claude y agy reales con capturas; app empaquetada cerrada con dos ejecuciones activas → `Get-Process` sin CLIs → al reabrir, `interrupted` | CA1, CA2, CA7 |

## Decisiones (ADR)
- **0007: Procesos de las ejecuciones.** PTY gestionado por el backend, scrollback + log en disco, WebSocket por ejecución con un único controlador, Job Object «kill on close» para todo el árbol de procesos del backend, y recuperación (`interrupted`) al arrancar.

## Riesgos
- **pywinpty y los hilos**: la lectura bloqueante va en su propio hilo y la escritura se protege con un lock.
- **Job Object y PyInstaller `--onefile`**: el bootloader no está en el job, pero el intérprete (que lanza los CLIs) sí. Se verifica en CA7.
- **xterm.js 6** es una versión mayor reciente: si hay incompatibilidades con React 19 o con el addon fit, se baja a 5.x.
