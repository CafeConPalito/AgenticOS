# ADR 0012: Empaquetado, robustez y reanudación de sesiones

- **Estado**: aceptado
- **Fecha**: 2026-10-12
- **Contexto de decisión**: fase 08 ([`spec.md`](../phases/08-empaquetado/spec.md), [`plan.md`](../phases/08-empaquetado/plan.md), [captura R1](../phases/08-empaquetado/evidencias/r1-reanudar.md))
- **Amplía**: [ADR 0002](0002-sidecar-protocol.md) (protocolo del sidecar) y [ADR 0007](0007-run-processes.md) (procesos de las ejecuciones)

## Contexto
La v1.0 tiene que instalarse y usarse a diario: actualizar sin perder datos, sobrevivir a cierres y caídas, no dejar procesos colgados y permitir retomar el trabajo de un agente cortado. Hasta ahora una ejecución interrumpida solo se podía reintentar desde cero. El sidecar tampoco se reiniciaba si se caía (ADR 0002).

## Decisión
### Instalador
- **NSIS por usuario** (`installMode: currentUser`), sin permisos de administrador, en español. Si falta **WebView2**, lo descarga el *bootstrapper*.
- **Versión única** `1.0.0` en los cinco manifiestos. Un test comprueba que coinciden.
- **Desinstalar**: la casilla «Borrar los datos de la aplicación» de Tauri solo borra las carpetas con el identificador del bundle. Un *hook* (`windows/hooks.nsh`) borra también `%APPDATA%\AgenticOS`. Una carpeta de datos movida por el usuario se deja donde está.
- **Sin firma de código** en la v1.0: el README explica el aviso de SmartScreen. `scripts/sign.ps1` firma el sidecar, la app y el instalador en cuanto existe `AGENTIC_OS_SIGN_CERT`; sin ella no hace nada.
- **Sin actualizaciones automáticas**: requieren publicar las versiones en un sitio remoto. Instalar encima conserva los datos.
- **PyInstaller `--onefile`**: el sidecar arranca en 2,3–2,9 s con una base de datos nueva, por debajo del umbral de 5 s fijado en la fase 00. No hace falta `--onedir`.

### Shell de escritorio
- **Instancia única** (`tauri-plugin-single-instance`), solo en release: dos backends sobre la misma base de datos la corromperían. Así la build de desarrollo y la instalada pueden convivir.
- **Supervisor del sidecar** (`sidecar.rs`): si el backend termina, se relanza:
  - al momento si ha salido con el **código 75** (reinicio pedido por el propio backend, p. ej. al mover la carpeta de datos);
  - si no, tras 1, 2 y 4 s;
  - tras tres fallos seguidos, error definitivo, con «Reintentar» (`restart_backend`) y «Abrir logs» (`open_logs`) en la UI;
  - un backend que lleva 60 s listo pone el contador a cero.
- **Nuevo puerto en cada arranque**: el *health check* de la UI pide la URL al shell cada vez. Mientras el shell responde `starting` tras haber estado conectado, la UI muestra «Reconectando…».
- El sidecar sigue sin matarse desde Rust (ADR 0002): sale solo cuando muere su proceso padre. Sus CLIs mueren con él (Job Object, ADR 0007) y, al volver, aparecen «Interrumpidas».

### Carpeta de datos
- Un **puntero fijo**, `%APPDATA%\AgenticOS\location.json`, dice dónde están los datos. Si no hay puntero, están en esa misma carpeta. `AGENTIC_OS_DATA_DIR` manda sobre el puntero (tests y desarrollo) y en ese caso no se pueden mover.
- **Moverla** se hace en dos pasos, porque la base de datos y los logs están abiertos mientras el backend funciona:
  1. la API valida el destino (sin ejecuciones activas, vacío, sin anidar, con espacio), anota `pending_move` en el puntero y pide el reinicio (código 75);
  2. al arrancar, antes de leer los ajustes o abrir nada, el backend copia los datos, comprueba la copia con `PRAGMA quick_check`, reescribe las rutas absolutas guardadas (`runs.log_path`), actualiza el puntero y borra la carpeta vieja.
  Si algo falla, los datos se quedan donde estaban y el error se guarda en el puntero para mostrarlo en Ajustes.
- Los **worktrees** viven junto a cada proyecto, no en la carpeta de datos, así que no se mueven.

### Arranque del backend
1. Movimiento pendiente de la carpeta de datos.
2. **Copia de la base de datos** si hay migraciones pendientes: `backups/agentic-os-<revisión>-<fecha>.db`, hecha con la API de *backup* de SQLite (incluye el WAL). Se guardan las 3 últimas.
3. Migraciones y recuperación (`RunManager.recover`, `Scheduler.recover`).
4. **Restos de caídas anteriores**: los plugins de agy cuya ejecución ya no vive se borran antes de que arranque el scheduler. En segundo plano se liberan los worktrees de tareas cerradas, se limpia la confianza pendiente y se borran los logs que superan la retención (90 días por defecto; la ejecución y su consumo se conservan).
- Los subprocesos auxiliares (`git`, `claude auth status`, `agy models`, `tasklist`) se lanzan con `CREATE_NO_WINDOW` (`services/proc.py`): con el sidecar sin consola, cada uno abriría una ventana.

### «Reanudar sesión»
- **Una ejecución nueva**, enlazada a la interrumpida (`runs.resumed_from_id`), que retoma la conversación del CLI con `claude --resume <id>` o `agy --conversation <id>`. Recibe un contexto, un token de MCP y unos hooks nuevos: la captura R1 confirmó que los CLIs no guardan esa configuración en la sesión.
- El prompt es un mensaje fijo («La sesión anterior se interrumpió. Continúa…»), porque la conversación ya contiene la tarea.
- **Se ofrece** en ejecuciones interrumpidas, paradas, fallidas o terminadas con un ID de sesión, que no sean subagentes, y solo si su tarea espera al usuario y no hay una ejecución posterior. **Nunca se reanuda sola**: la recuperación al arrancar sigue dejando la tarea en «Esperando humano · interrumpida».
- **Sesión que ya no existe**:
  - antes de lanzar, si falta el transcript, se responde 409 `session_unavailable`;
  - si el CLI arranca igualmente: Claude escribe `No conversation found with session ID` y termina; agy no falla, abre otra conversación, y se detecta porque el primer `conversationId` de sus hooks no es el pedido.
  En los dos casos la ejecución termina `failed` con el error `session_missing`, y la tarea queda esperando con «Reintentar».
- **Consumo**: los dos CLIs siguen escribiendo en el mismo transcript. La `cost-state` de Claude es acumulada tras un cierre limpio y empieza de cero tras un corte, que no deja ninguna. Al reanudar se guarda `runs.usage_baseline = {offset, subagents, cost_state}`, y la ejecución nueva:
  - lee las filas del transcript, y de los subagentes nativos, solo desde ese punto;
  - resta la `cost-state` que había (también al coste de la *status line*).

## Consecuencias
- ✅ El trabajo cortado por un cierre o una caída se retoma sin repetirlo, y el consumo no se cuenta dos veces.
- ✅ Una caída del backend se recupera sola; un fallo persistente se explica en la UI con acceso a los logs.
- ✅ Actualizar es seguro: hay copia de la base de datos antes de cada migración nueva.
- ⚠️ Sin firma, SmartScreen y algunos antivirus avisan al instalar o al lanzar el sidecar.
- ⚠️ Mover la carpeta de datos reinicia el backend: en desarrollo (sin el shell) hay que relanzarlo a mano.
- ⚠️ La reanudación depende de opciones de los CLIs (`--resume`, `--conversation`) y de un texto de Claude que pueden cambiar. Están centralizados en los adapters y en `screen.py`.
