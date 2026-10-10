# Fase 03: Terminales en vivo · Validación

- **Rama**: `phase/03-terminales`
- **Fecha**: 2026-10-10

## Tests automáticos
`scripts/check.ps1`:

```
Step                            Result
----                            ------
Lint backend (ruff)             OK
Lint frontend (eslint+prettier) OK
Lint desktop (rustfmt)          OK
Lint spikes (ruff)              OK
Tests backend (pytest)          OK   94 passed  (+39 en esta fase)
Tests frontend (vitest)         OK   50 passed  (+16 en esta fase)
Tests desktop (cargo test)      OK    3 passed
Tests spikes (pytest)           OK   15 passed
```

Los tests del backend lanzan un **CLI falso** (`backend/tests/fake_cli.py`) en un ConPTY real. El CLI imita lo que el backend lee de las TUIs:
- el diálogo de confianza;
- el pie «esc to interrupt», y Esc para interrumpir;
- el doble Ctrl+C de agy;
- el modo `--deaf`, que pierde las teclas justo después de un turno;
- el aviso de reanudación al salir.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Lanzar **Claude Code** desde la UI: sesión en vivo, diálogo de confianza aceptado solo, responde al prompt | ✅ | Prueba manual con Claude Code 2.1.296 (`haiku`) desde «Lanzar» del agente y desde «Lanzar agente» de la cabecera: [`ca1-ca3-claude-interviniendo.jpg`](evidencias/ca1-ca3-claude-interviniendo.jpg) (arriba, la respuesta al prompt inicial). `test_launch_accepts_trust_and_streams_the_answer`, `test_launcher.py` |
| CA2 | Lo mismo con **agy** | ✅ | Prueba manual con agy 1.3.3 (Gemini 3.8 Flash): [`ca2-agy.jpg`](evidencias/ca2-agy.jpg). `test_agy_style_launch` |
| CA3 | **Tomar control** (Esc interrumpe, escribes, «Devolver» reanuda; los demás visores no pueden escribir) | ✅ | Manual con Claude: borde ámbar, «Estás interviniendo», se escribe una pregunta y Claude responde; al devolver, toast «Control devuelto a Dev» ([`ca1-ca3-claude-interviniendo.jpg`](evidencias/ca1-ca3-claude-interviniendo.jpg)). Tests: `test_two_viewers_and_control` (input rechazado, 409 `control_taken`), `test_take_interrupts_and_release_without_typing_nudges`, `TerminalPanel.test.tsx` |
| CA4 | **Varios visores** ven la misma salida | ✅ | Manual: página + dock a la vez ([`ca4-pagina-y-dock.jpg`](evidencias/ca4-pagina-y-dock.jpg)); la API cuenta 2 visores. `test_two_viewers_and_control`, `test_resize_is_broadcast_and_only_the_controller_resizes` |
| CA5 | **Scrollback** al reabrir una ejecución activa o terminada (también tras reiniciar) | ✅ | `test_reconnecting_viewer_gets_the_scrollback`, `test_graceful_stop_and_finished_run_replays_its_log`, reconexión en `TerminalPanel.test.tsx`. Manual: después de varios reinicios del backend, la página de la primera ejecución de Claude (ya «Interrumpida») vuelve a mostrar su sesión desde el log |
| CA6 | **Parar**: cierre ordenado y, si no, forzado; estado y código correctos | ✅ | Manual, sin ningún visor conectado (el caso que fallaba): Claude ×2 y agy ×2 terminan solos con código 0 (Claude ~11 s, agy ~7 s, o ~18 s si se le para a mitad de turno). Tests: `test_graceful_stop…`, `test_stop_retries_when_the_cli_was_not_listening`, `test_agy_graceful_stop_waits_for_the_exit_notice`, `test_forced_stop_when_the_cli_ignores_exit` |
| CA7 | **Sin huérfanos** al cerrar la app; al reabrirla, `interrupted` | ✅ / ⚠️ | **Sidecar empaquetado** (PyInstaller) con un Claude y un agy activos; se mata su proceso padre, como al cerrar la ventana. El backend sale en 5,4 s y no queda vivo ningún proceso creado durante la prueba (solo `mscorsvw.exe`, un servicio de Windows ajeno). Al rearrancar, las dos ejecuciones están `interrupted`. `test_job.py` (el nieto muere con el job) y `test_shutdown_stops_live_runs_and_recover_marks_leftovers`. **Falta repetirlo con la ventana real de la app instalada** (comprobación del usuario) |
| CA8 | Lista de ejecuciones, Historial del agente y dock (Ctrl+`) funcionales y fieles al diseño | ✅ | `runs.test.tsx` (9 tests), `TerminalDock.test.tsx` (3), `AppSidebar.test.tsx`. Manual: lista con filtros y dock con Ctrl+` en Chrome. Las capturas de la página (`09a`/`09b`) y del dock (`13a`) se compararon con el diseño. Fuera de alcance por spec: árbol de subagentes, eventos MCP y consumo |
| CA9 | `check` en verde; ADR, README y roadmap | ✅ | Salida de arriba; [ADR 0007](../../adr/0007-run-processes.md); README (ejecuciones, API, `AGENTIC_OS_CLI_COMMAND_OVERRIDES`); roadmap |

## Code review
`/code-review high` sobre `main...phase/03-terminales`. Los fallos de comportamiento tienen un test que **falla sin la corrección** (comprobado revirtiendo `session.py`):

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Si la vista que tenía el control se cerraba o recargaba, el control no se liberaba nunca: la ejecución se quedaba «Interviniendo», el agente parado y nadie podía escribir (la vista vuelve con otro id) | Alta | **Corregido**: `detach` devuelve el control (con el empujón «Continúa con la tarea.» si no se escribió nada); test `test_control_is_released_when_its_viewer_leaves` |
| Prompt en el argv de un shim `.cmd` de npm: `cmd.exe` vuelve a interpretar la línea (`&`, `"`, `%VAR%`), lo que permite ejecutar otros comandos | Alta | **Corregido**: se rechazan los shims `.cmd`/`.bat` con 422 `cli_shim_unsupported` y un texto que pide instalar el CLI nativo (Claude Code y agy lo son); test |
| El hilo lector moría sin terminar la ejecución si fallaba el log o pyte: la ejecución quedaba «viva» para siempre | Alta | **Corregido**: `try/except/finally` → termina el proceso y cierra la ejecución; test `test_reader_failure_ends_the_run` |
| Carreras de estado: un `take_control` tardío o el ticker podían sobrescribir el estado final (`intervening`/`busy` en una ejecución terminada) | Media | **Corregido**: los cambios de estado se serializan y se ignoran tras el final; test |
| Un prompt que empieza por `-` se interpretaba como opción del CLI (`--help…`) | Media | **Corregido**: se antepone un espacio; test para Claude y agy |
| Las sesiones terminadas se quedaban en memoria (scrollback de hasta 2 MB cada una) | Media | **Corregido**: se retiran del gestor al terminar (con lock); las terminadas se sirven desde el log; test |
| Dos «Parar» seguidos mezclaban sus teclas (`/exit/exit`) y la ejecución acababa matada | Media | **Corregido**: `stop()` es idempotente; test con doble stop que termina con código 0 |
| `kill()` sin tolerar la carrera «ya está saliendo»; en el cierre podía saltarse `engine.dispose()` | Media | **Corregido**: se ignora el `OSError` y `dispose()` va en `finally` |
| El log quedaba abierto (y bloqueado en Windows) si fallaba el arranque del proceso | Baja | **Corregido**: se cierra; test |
| `resize`/`input` del WebSocket hacían escrituras al PTY y commits de SQLite dentro del event loop | Baja | **Corregido**: `asyncio.to_thread` |
| Mensajes WebSocket mal formados tiraban la conexión | Baja | **Corregido**: se ignoran; test `test_malformed_frames_are_ignored` |
| Lista de estados activos duplicada en `TerminalPanel`; búsquedas de agente/proyecto duplicadas en `launch_run` | Baja | **Corregido**: `isActive` y los `_get` de cada API |
| Roadmap sin actualizar | Baja | **Corregido**: fase 03 en «validación» |

## Incidencias durante el desarrollo
La prueba manual con los CLIs reales encontró **cinco fallos que los tests con el CLI falso no veían**. Todos están corregidos y cada uno tiene ahora un test que lo reproduce:

1. **El WebSocket no funcionaba con el servidor real**: uvicorn no tenía ninguna librería de WebSocket y respondía 404 a la conexión (`TestClient` no pasa por uvicorn). Se añadió `websockets` y un test que conecta con el servidor real.
2. **La página y el dock se peleaban por el tamaño del PTY**: mientras nadie tenía el control, cada visor lo redimensionaba y la TUI se rompía en el otro. Ahora `state` lleva `cols`/`rows`, la página fija el tamaño y el dock es un visor pasivo que lo adopta y hace scroll.
3. **agy no se paraba de forma ordenada**: el segundo Ctrl+C, 0,5 s después del primero, se perdía. Ahora se espera al aviso «press ctrl+c again».
4. **Claude no se paraba de forma ordenada**: justo después de un turno descarta las teclas (sigue trabajando en segundo plano), así que `/exit` se perdía y siempre acababa matado por el timeout. Al principio parecía depender de si había un visor conectado; resultó ser cuestión de tiempos. Ahora cada intento se verifica con el aviso de reanudación del CLI y se reintenta. Una vez aceptada la salida, el CLI tiene 10 s para cerrarse solo (Claude y agy tardan ~6 s). Además, `terminate()` tolera un proceso que ya está saliendo («Acceso denegado» al matarlo).
5. **En la app empaquetada todas las ejecuciones morían al arrancar** (código `0xC000013A`, log vacío): PyInstaller no incluía `OpenConsole.exe` ni `winpty-agent.exe`, que `conpty.dll` necesita. Ahora el script de build los añade.

Otras:
- Los heredocs del entorno de desarrollo estropean `\x03` y las rutas con `\`; esos cambios se hicieron con el editor.
- En las pruebas automatizadas con Chrome, el primer clic tras navegar a veces no llega a la página. Es un artefacto de la herramienta: con un clic directo del DOM, el botón funciona.

## Retro
### Cambios respecto a la spec y al plan
- **«Ejecuciones» en la barra lateral**, con «Lanzar agente» como botón principal de la cabecera en esa sección.
- **Parar pide confirmación** (diálogo) y **el dock es solo lectura**, con el texto del diseño «Solo lectura · abre el detalle para tomar el control».
- **El dock no se puede redimensionar** (alturas y anchos fijos del diseño: 260 / 440 px). Se deja para más adelante.
- **Logs por intento de parada** (`requesting exit`, `exit acknowledged`, `exit timed out`) para diagnosticar CLIs reales.

### Impacto en fases futuras
- **Fase 04**: la actividad de agy marca `idle` durante el arranque, antes de que empiece el turno, y de esto dependerá la detección de «tarea terminada». Conviene apoyarse en el MCP (`complete_task`) y no en la pantalla.
- **Fase 04/05**: reanudar sesiones con `claude --resume <id>` / `agy -c` tras un reinicio (hoy quedan `interrupted`).
- **Fase 07**: el consumo de la sesión en el panel lateral de la ejecución.
- Los textos de las TUIs de los que depende el backend están centralizados en `services/runs/screen.py`. Si un CLI los cambia, se ajustan ahí y en sus tests.

## Comprobaciones pendientes del usuario
- Con la app instalada (`desktop/src-tauri/target/release/bundle/nsis/Agentic OS_0.1.0_x64-setup.exe`), lanzar un agente, ver la terminal y cerrar la ventana con la ejecución activa. Después, comprobar `Get-Process claude, agy` y que al reabrir aparece «Interrumpida».
- De fases anteriores: «Examinar…» con el diálogo nativo, F5 en una subruta de la app instalada y `uv run --project spikes python spikes/cleanup.py --claude` con Claude Code cerrado.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.4`
- [ ] `docs/roadmap.md` actualizado
