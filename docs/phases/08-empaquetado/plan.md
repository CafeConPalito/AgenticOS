# Fase 08: Empaquetado v1.0 (MVP) · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: borrador

## Diseño

### Visión general
```
Instalador NSIS (por usuario) ──► Agentic OS.exe (Tauri, instancia única)
                                     │  lanza y vigila
                                     ▼
                     sidecar agentic-os-backend (--parent-pid, puerto libre)
                       │  al arrancar: puntero de datos → movimiento pendiente → copia de la BD
                       │               → migraciones → recover() → limpieza de restos y de logs
                       └─ se cae ──► Tauri lo relanza (3 intentos, espera creciente)
                                     la UI ve «Reconectando…» y pide la URL nueva

Ejecución interrumpida ──► «Reanudar sesión» ──► ejecución nueva (resumed_from) con
                           claude --resume <id> / agy --conversation <id> + contexto y token nuevos
```

### Comprobaciones previas (ya hechas al escribir el plan)
- **agy 1.3.3** tiene `--conversation <id>` («Resume a previous conversation by ID»), además de `-c`. El riesgo de la spec queda resuelto: se reanuda la conversación exacta (`runs.cli_session_id`, que ya guarda el `conversationId` del hook).
- **Claude Code 2.1.296**: `claude auth status` devuelve JSON con `loggedIn`. agy no tiene un comando así: su sesión se deduce de `agy models` (ya falla sin sesión: `models_error`).

### Instalador y versión
- **Versión `1.0.0`** en `backend/pyproject.toml`, `frontend/package.json`, `desktop/package.json`, `Cargo.toml` y `tauri.conf.json`. Un test comprueba que coinciden. `GET /health` ya devuelve la versión; la UI la muestra en «Acerca de».
- **`tauri.conf.json` > `bundle.windows.nsis`**:
  - `installMode: "currentUser"` (sin administrador);
  - `webviewInstallMode: downloadBootstrapper` (por defecto; se deja explícito);
  - `installerHooks: "windows/hooks.nsh"`: en `NSIS_HOOK_POSTUNINSTALL`, si está marcada la casilla «Borrar los datos de la aplicación» (`$DeleteAppDataCheckboxState`), se borra `%APPDATA%\AgenticOS` (la casilla estándar de Tauri solo borra las carpetas con el identificador del bundle, no la nuestra). Por defecto está desmarcada;
  - idioma del instalador: español (`languages: ["Spanish"]`).
- **Iconos**: `npm -w desktop run tauri icon` a partir de un PNG de 1024 px del logo del diseño (`docs/design/`), guardado en `desktop/src-tauri/icons/source.png`.
- **Sidecar**: se mide el arranque con la app instalada (de la ejecución del `.exe` al `AGENTIC_OS_READY`). Si supera los 5 s, `build-backend.ps1` pasa a `--onedir` y `tauri.release.conf.json` empaqueta la carpeta como recurso (`bundle.resources`) en lugar de `externalBin`; Rust la lanza desde `resource_dir()`. La decisión y la medida quedan en el ADR.
- **Firma**: `build-backend.ps1` y la build de Tauri llaman a `scripts/sign.ps1` si existe la variable `AGENTIC_OS_SIGN_CERT`; si no, no firman. Tauri: `bundle.windows.signCommand` apuntando a ese script, que sale sin hacer nada cuando no hay certificado.
- **Consolas**: el sidecar se lanza con `CREATE_NO_WINDOW` (tauri-plugin-shell). El backend ya lanza los CLIs en ConPTY (sin consola visible); el resto de subprocesos (`git`, `claude auth status`, `agy models`, `--version`) pasan a usar un `subprocess` común con `CREATE_NO_WINDOW` (`services/proc.py`), porque con el sidecar sin consola cada uno abriría una ventana.

### Shell de escritorio (Rust)
- **Instancia única**: `tauri-plugin-single-instance`, solo en release (`#[cfg(not(debug_assertions))]`), para poder tener a la vez `dev:desktop` y la app instalada. El callback muestra la ventana, la restaura si está minimizada y le da el foco.
- **Supervisor del sidecar** (`sidecar.rs`, nuevo módulo):
  - estado `Backend { url, error, generation }`; `generation` sube en cada arranque y la UI la usa para saber que la URL cambió;
  - al recibir `Terminated`: si el código es `75` (reinicio pedido por el backend, p. ej. tras «Cambiar carpeta de datos»), relanza enseguida y no cuenta como fallo; si no, relanza con espera de 1, 2 y 4 s. Tras 3 fallos seguidos sin llegar a `READY`, queda en error definitivo. Un arranque que llega a `READY` y aguanta 60 s pone el contador a cero;
  - mientras relanza, `backend_url` devuelve `starting`, como en el primer arranque;
  - comando nuevo `restart_backend`: lo usa «Reintentar» tras el error definitivo (pone el contador a cero y relanza);
  - comando `open_logs`: abre `<data_dir>/logs` con el explorador.
  - La lógica de reintentos es una función pura (`next_action(exit_code, failures) -> Restart(delay) | GiveUp`) con tests en `cargo test`.
- **Sin huérfanos**: no cambia el mecanismo (watchdog `--parent-pid` en el backend + Job Object de los CLIs, ADR 0002/0007). Se verifica con el guion de humo y a mano.

### UI: conexión con el backend
- `lib/api.ts`: cuando el health falla dentro de Tauri, se llama a `resetApiBaseUrl()` antes de reintentar, para pedir la URL nueva (el puerto cambia en cada arranque). Los WebSocket (terminal, ejecución) ya reconectan; pasan a resolver la URL de nuevo en cada intento.
- `BackendStatus` / `OfflineBanner`: estado nuevo **«Reconectando…»** (mientras `backend_url` devuelve `starting` tras haber estado conectado). En error definitivo: «Reintentar» (`restart_backend`) y «Abrir logs» (`open_logs`). En el navegador (modo dev) no hay «Abrir logs».

### Carpeta de datos
- **Puntero**: `%APPDATA%\AgenticOS\location.json` (`{"data_dir": "…", "pending_move": {"from", "to"} | null}`). `default_data_dir()` lo lee; `AGENTIC_OS_DATA_DIR` sigue mandando sobre él (tests y dev). La carpeta de `%APPDATA%\AgenticOS` siempre existe y contiene al menos el puntero y los logs del arranque.
- **Tamaño**: `GET /settings/data-dir` → ruta, bytes por apartado (base de datos y copias, logs de sesión `runs/`, logs del backend) y total. Se calcula en un hilo con caché de 60 s.
- **Abrir**: `POST /settings/data-dir/open` (`os.startfile`, como «Abrir carpeta» de los proyectos).
- **Cambiar** (`POST /settings/data-dir/move {"to"}`):
  1. valida: sin ejecuciones activas (409 `runs_active`), destino absoluto, escribible, vacío o inexistente, y que no esté dentro de la carpeta actual;
  2. escribe `pending_move` en el puntero, responde `202` y pide el apagado con código de salida `75`;
  3. Tauri relanza el sidecar; al arrancar, **antes de abrir la BD**, `services/datadir.py` copia la carpeta al destino, comprueba que la BD se abre, actualiza el puntero, reescribe las rutas absolutas guardadas en la BD que apunten a la carpeta vieja (`runs.log_path`, `runs.transcript_path` no: es del CLI) y borra la carpeta vieja. Si algo falla, deja el puntero en la carpeta vieja, borra la copia parcial y registra el error, que la UI muestra en Ajustes;
  4. fuera de Tauri (dev) el backend sale igual y el movimiento se hace al volver a lanzarlo a mano.
- Los **worktrees** viven junto al proyecto (`<proyecto>.wt\T-n`), no en la carpeta de datos: no se mueven. `trust-cleanup.json` sí está en la carpeta de datos y se mueve con ella.

### Arranque del backend (orden)
1. Puntero y movimiento pendiente (`datadir.apply_pending_move`).
2. **Copia de la BD** (`db/backup.py`): si hay migraciones pendientes (`alembic current` ≠ `head`), copia `agentic_os.db` con la API de *backup* de SQLite a `backups/agentic_os-<revisión>-<fecha>.db` y deja las 3 últimas. Sin migraciones pendientes no copia nada.
3. Migraciones (ya existe).
4. `RunManager.recover()` y `Scheduler.recover()` (ya existen).
5. **Limpieza de restos** (`services/housekeeping.py`, en un hilo, sin retrasar el `READY`):
   - plugins de agy de ejecuciones que ya no están activas (amplía `adapter.recover`, que hoy solo mira las que estaban activas: recorre también las carpetas de los proyectos en busca de `agentic-os-*` sin ejecución viva);
   - worktrees de tareas terminadas o canceladas que siguen en disco (`git worktree list`), con `WorktreeManager.release`;
   - confianza pendiente de `trust-cleanup.json` (ya se reintenta; se llama también aquí);
   - **logs de sesión** más antiguos que la retención (ver Limpieza).

### Reanudar sesión
- **Modelo** (migración `0007`): `runs.resumed_from_id` (FK a `runs`, nula) y `runs.usage_baseline` (JSON: el consumo del transcript en el momento de reanudar, para no contarlo dos veces). `WaitingReason` no cambia (`interrupted`).
- **Adapters**: `LaunchContext` gana `resume_session: str | None`.
  - Claude: `--resume <id>` en lugar de `--session-id <nuevo>`; el resto de flags igual (`--mcp-config`, `--settings` con los hooks y la *status line* nuevos, permisos). El `LaunchSpec.session_id` es el mismo ID.
  - agy: `--conversation <id>`; el plugin de workspace se vuelve a escribir con el token nuevo (el plugin viejo ya lo borró `recover`).
  - El **prompt** de una reanudación es un mensaje fijo: «La sesión anterior se interrumpió. Continúa con la tarea donde la dejaste.» (i18n del backend en `es`), no el de la tarea, que ya está en la conversación.
- **Servicio**: `RunManager.resume(run_id)`:
  - solo para ejecuciones `interrupted` (o `failed`/`stopped` con `cli_session_id`) sin otra ejecución viva en su tarea; si no, 409;
  - crea la ejecución nueva con el mismo agente, proyecto, tarea, etapa, carpeta de trabajo y padre; `resumed_from_id` = la interrumpida;
  - si la tarea esperaba al humano por `interrupted`, vuelve a «En ejecución» con la ejecución nueva (`task_ops`), y se resuelve su elemento «Atención» de la Inbox;
  - **sesión que no se puede retomar**: antes de lanzar se comprueba que el transcript existe (`transcript_path` o la ruta calculada, `usage/paths.py`); si no, 409 `session_unavailable` con «Reintentar» en la UI. Si el CLI arranca pero no encuentra la sesión (Claude: «No conversation found»; agy: el texto que se capture en la tarea R1), `screen.py` lo detecta, la ejecución termina `failed` con ese error y la tarea vuelve a «Esperando humano» (`interrupted`).
- **Consumo**: el `UsageReader` resta `usage_baseline` al leer una ejecución reanudada (Claude reescribe la `cost-state` acumulada de la sesión; agy añade pasos al mismo `transcript_full.jsonl`). En la tarea, el total suma las dos ejecuciones sin duplicar.
- **API**: `POST /runs/{id}/resume` → `RunRead` de la nueva. `RunRead` gana `resumed_from_id`, `resumed_by_id` y `resumable: bool`.
- **UI**: botón «Reanudar sesión» en la página de la ejecución (junto a «Reintentar»), en el detalle de tarea (estado «Esperando humano · interrumpida») y en el elemento «Atención» de la Inbox. En el historial de la tarea, la nueva aparece como «Reanudación de #n».

### Ajustes
- **CLIs detectados** (`/api/clis`, ya existe): `CliInfo` gana `logged_in: bool | None` (Claude: `claude auth status`; agy: `models_error is None`), `checked_at` e `install_hint` (comando de instalación y de inicio de sesión, por CLI). «Comprobar» llama con `refresh=true`; spinner y toast con el resultado. Logos de los CLIs del diseño.
- **General**: carpeta de datos (ruta mono, tamaño, «Abrir carpeta», «Cambiar…» con el diálogo nativo `@tauri-apps/plugin-dialog`, ya instalado, y un diálogo de confirmación que explica el reinicio); **Idioma** (`Select` con «Español», deshabilitado mientras solo haya uno; la lista sale de los recursos de i18n); **Tema** (segmentado Oscuro / Claro sobre el `ThemeProvider` actual, que ya lo guarda en `localStorage`).
- **Limpieza**:
  - **Ramas**: `GET /maintenance/branches` → por proyecto con git, las ramas `agentic/T-n` cuyas tareas están terminadas o canceladas (o sin tarea), con `merged` (`git branch --merged <rama base>`), último commit y fecha. `DELETE /maintenance/branches` con `{project_id, branches, force}`: sin `force` solo borra las fusionadas (`git branch -d`); con `force`, `-D`. Nunca se toca una rama con worktree vivo ni la de una tarea abierta (409).
  - **Logs de sesión**: `app_state.log_retention_days` (por defecto 90; `null` = nunca). `GET/PUT /settings/maintenance`. `POST /maintenance/logs/cleanup` → borra `runs/<id>/` de ejecuciones terminadas antes del corte y devuelve los bytes liberados; la ejecución queda con `log_purged = true` (columna nueva en `0007`) y la terminal muestra «Log borrado por la retención». Se ejecuta también al arrancar.
- **Acerca de**: versión, carpeta de datos, «Abrir logs», licencia (archivo `LICENSE` del repo, si existe; si no, se omite el enlace).
- La página `SettingsPage.tsx` se divide en secciones (`pages/settings/`), siguiendo el orden del diseño: CLIs · General | Notificaciones · Límites · Limpieza · Acerca de.

### e2e contra el sidecar empaquetado
- `tests/live_server.py` gana un modo «binario»: si existe `AGENTIC_OS_E2E_BINARY`, lanza ese `.exe` (con `--port 0`, la carpeta de datos temporal y `AGENTIC_OS_CLI_COMMAND_OVERRIDES` para el CLI falso) en lugar de uvicorn en proceso.
- `npm run test:packaged`: construye el sidecar y ejecuta los e2e (`test_scheduler_e2e.py`, `test_hitl_e2e.py`, consumo y reanudación) con esa variable. No entra en `check` (tarda); se ejecuta en la validación y antes de cada release.
- **El CLI falso** (`tests/fake_cli.py`) es un script de Python: con el binario, se lanza con el Python del entorno de tests, no con el del sidecar.
- `scripts/smoke-installed.ps1`: localiza la app instalada (`%LOCALAPPDATA%\Agentic OS`), la arranca, espera el sidecar (proceso hijo y `GET /health` en su puerto, leído del log), comprueba la carpeta de datos y la BD, cierra la ventana (`CloseMainWindow`) y verifica que no quedan procesos del backend ni de `claude`/`agy` lanzados por él, ni carpetas `_MEI*` nuevas. Imprime un resumen y el tiempo de arranque.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/pyproject.toml`, `frontend/package.json`, `desktop/package.json`, `desktop/src-tauri/Cargo.toml`, `tauri.conf.json` | versión `1.0.0`; NSIS por usuario, en español, con hooks |
| `desktop/src-tauri/windows/hooks.nsh` | nuevo: borrar datos al desinstalar si se marca |
| `desktop/src-tauri/icons/*` | iconos definitivos |
| `desktop/src-tauri/src/lib.rs`, `sidecar.rs` | instancia única, supervisor con reinicios, `restart_backend`, `open_logs` |
| `scripts/build-backend.ps1`, `scripts/sign.ps1`, `scripts/smoke-installed.ps1` | firma opcional, `--onedir` si hace falta, guion de humo |
| `package.json` | `test:packaged` |
| `backend/src/agentic_os/config.py`, `services/datadir.py` | puntero de datos y movimiento |
| `backend/src/agentic_os/db/backup.py`, `db/migrations/versions/0007_resume_and_retention.py` | copia antes de migrar; `resumed_from_id`, `usage_baseline`, `log_purged`, `log_retention_days` |
| `backend/src/agentic_os/services/proc.py` | subprocesos sin ventana |
| `backend/src/agentic_os/services/housekeeping.py` | restos de ejecuciones, worktrees, logs |
| `backend/src/agentic_os/services/adapters/*`, `runs/manager.py`, `runs/screen.py`, `usage/reader.py`, `tasks.py` | reanudar sesión |
| `backend/src/agentic_os/services/clis.py` | `logged_in`, `checked_at`, `install_hint` |
| `backend/src/agentic_os/api/settings.py`, `api/maintenance.py`, `api/runs.py`, schemas | endpoints nuevos |
| `backend/src/agentic_os/app.py`, `__main__.py` | orden de arranque, salida `75` |
| `backend/tests/live_server.py` | modo binario |
| `frontend/src/lib/api.ts`, `components/layout/BackendStatus.tsx`, `OfflineBanner.tsx` | «Reconectando…», URL nueva, «Abrir logs» |
| `frontend/src/pages/settings/*` | secciones de Ajustes |
| `frontend/src/pages/runs/*`, `pages/tasks/*`, `pages/InboxPage.tsx` | «Reanudar sesión» |
| `frontend/src/i18n/es.json` | textos |
| `README.md` | instalar, actualizar, desinstalar, SmartScreen y antivirus, datos |
| `docs/adr/0012-packaging-and-resume.md` | nuevo |

## Tareas (en orden)
1. [ ] **R1 · Captura de la reanudación**: con Claude y agy reales, interrumpir una sesión (matar el backend) y relanzarla a mano con `--resume` / `--conversation` y la configuración nueva. Confirmar: que recuerda la conversación, que usa el MCP y los hooks nuevos (no los guardados), cómo crecen el transcript y la `cost-state`, y el texto que muestra cada CLI con un ID inexistente. Evidencias en `evidencias/r1-reanudar.md`.
2. [ ] Versión `1.0.0` en todos los paquetes + test de coherencia.
3. [ ] `services/proc.py` (subprocesos sin ventana) y su uso en `git`, CLIs y `os.startfile`.
4. [ ] Copia de la BD antes de migrar (`db/backup.py`) + tests.
5. [ ] Migración `0007` y modelos.
6. [ ] Reanudar sesión en backend: adapters, `RunManager.resume`, tarea e Inbox, detección de sesión inexistente, `usage_baseline`; `fake_cli.py` con `--resume`/`--conversation` + tests y e2e.
7. [ ] Reanudar sesión en la UI (ejecución, tarea, Inbox, historial) + tests.
8. [ ] `CliInfo` con sesión, fecha e instrucciones + sección «CLIs detectados» + tests.
9. [ ] Carpeta de datos: puntero, tamaño, abrir, mover (backend con salida `75`) + tests; sección «General» con tema e idioma.
10. [ ] Limpieza: ramas y retención de logs (API, arranque, UI) + tests.
11. [ ] `housekeeping.py`: restos de agy, worktrees huérfanos y confianza al arrancar + tests.
12. [ ] Rust: instancia única y supervisor del sidecar con reinicios, `restart_backend`, `open_logs` + `cargo test`.
13. [ ] UI: «Reconectando…», URL nueva tras reinicio, «Abrir logs» + tests.
14. [ ] Sección «Acerca de» y reorganización de `SettingsPage` según el diseño.
15. [ ] Instalador: iconos, NSIS por usuario, español, hook de desinstalación, paso de firma opcional.
16. [ ] e2e contra el sidecar empaquetado (`live_server` en modo binario, `test:packaged`) y guion de humo.
17. [ ] Build de release, medida del arranque y, si supera 5 s, cambio a `--onedir`.
18. [ ] Pruebas manuales con la app instalada: máquina limpia (Windows Sandbox o VM), actualizar encima de `0.8` con datos, desinstalar, instancia única, matar el sidecar, cerrar con ejecuciones activas, reanudar con Claude y agy reales, y las pendientes de fases anteriores (F5, «Examinar…», notificación, CSV, consolas).
19. [ ] ADR 0012, README, `/code-review` y validación.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_version.py`: la versión coincide en los cinco archivos | CA12 |
| `test_backup.py`: copia solo con migraciones pendientes, nombre con la revisión, se quedan 3 | CA2 |
| `test_datadir.py`: puntero, prioridad de la variable de entorno, validaciones del movimiento (ejecuciones activas, destino no vacío o dentro de la actual), movimiento completo con reescritura de `log_path`, fallo a mitad que deja la carpeta vieja | CA8 |
| `test_resume.py`: argv de cada adapter al reanudar; `resume` crea la ejecución enlazada, la tarea vuelve a «En ejecución» y se resuelve la «Atención»; 409 si hay otra viva o si falta el transcript; sesión desconocida en pantalla → `failed` y tarea esperando; consumo con `usage_baseline` | CA7 |
| `test_resume_e2e.py`: con el CLI falso en ConPTY, interrumpir (reinicio del backend) y reanudar | CA6, CA7 |
| `test_clis.py` (ampliado): `logged_in` de Claude por `auth status` y de agy por `models`, CLI ausente con instrucciones | CA1, CA8 |
| `test_maintenance.py`: ramas listadas con `merged`; borrar fusionadas; 409 con no fusionadas sin `force` y con worktree vivo; retención de logs, `log_purged` y bytes liberados | CA9 |
| `test_housekeeping.py`: plugins de agy huérfanos, worktrees de tareas cerradas, confianza pendiente | CA6 |
| `test_proc.py`: los subprocesos llevan `CREATE_NO_WINDOW` en Windows | CA10 |
| `cargo test`: `next_action` (código 75, esperas 1-2-4 s, rendición tras 3 fallos, contador a cero tras 60 s) | CA5 |
| Frontend: `BackendStatus` con «Reconectando…» y «Abrir logs»; `api.ts` pide la URL nueva tras un fallo; secciones de Ajustes (CLIs, carpeta, tema, idioma, limpieza, acerca de); «Reanudar sesión» en ejecución, tarea e Inbox | CA5, CA7, CA8 |
| `npm run test:packaged`: e2e del scheduler, HITL, consumo y reanudación contra el sidecar de PyInstaller | CA11 |
| `scripts/smoke-installed.ps1` con la app instalada | CA6, CA11 |
| Manuales con evidencias (tarea 18) | CA1–CA7, CA10 |

## Decisiones (ADR)
- **ADR 0012 · Empaquetado y reanudación de sesiones**:
  - instalador NSIS por usuario, sin firma (con el paso preparado) y sin auto-update en la v1.0;
  - `--onefile` o `--onedir` según la medida del arranque;
  - instancia única solo en release; supervisor del sidecar con reinicios limitados y el código `75` para los reinicios pedidos;
  - la carpeta de datos se localiza con un puntero fijo en `%APPDATA%\AgenticOS` y se mueve al arrancar, con el backend sin la BD abierta;
  - copia de la BD antes de migrar (3 últimas);
  - «Reanudar sesión» como ejecución nueva enlazada (`resumed_from_id`) que retoma la conversación del CLI con un contexto y un token nuevos, y descuenta el consumo previo (`usage_baseline`); nunca se reanuda solo.
