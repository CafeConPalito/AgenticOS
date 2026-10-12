# Fase 08: Empaquetado v1.0 (MVP) · Validación

- **Rama**: `phase/08-empaquetado`
- **Fecha**: 2026-10-12

## Tests automáticos
`scripts/check.ps1`:

```
Step                                Result
----                                ------
Lint backend (ruff)                 OK
Lint frontend (eslint+prettier+tsc) OK
Lint desktop (rustfmt)              OK
Lint spikes (ruff)                  OK
Tests backend (pytest)              OK  310 passed  (+57 en esta fase)
Tests frontend (vitest)             OK   91 passed  (+17 en esta fase)
Tests desktop (cargo test)          OK    7 passed  (+4 en esta fase)
Tests spikes (pytest)               OK   15 passed
```

**e2e contra el sidecar empaquetado** (`npm run test:packaged`, [salida](evidencias/ca11-test-packaged.log)): `17 passed, 3 skipped in 448 s`. Cubre el scheduler, HITL, consumo y reanudación, con el `.exe` de PyInstaller lanzado como lo lanza la app. Los 3 omitidos necesitan el backend en el proceso de los tests (`@in_process_only`).

Tests nuevos:
- **Backend**:
  - `test_version.py`: la versión coincide en los cinco manifiestos;
  - `test_proc.py`: subprocesos sin ventana;
  - `test_backup.py`: copia de la base de datos solo con migraciones pendientes; se guardan 3;
  - `test_migration_0007.py`;
  - `test_resume.py`:
    - argv de reanudación de los dos adapters;
    - consumo con línea base tras un cierre limpio y tras un corte;
    - pantalla real de Claude con un ID inexistente, y la misma frase citada por el agente;
  - `test_resume_e2e.py` (CLI falso en ConPTY):
    - reanudar tras reiniciar el backend en los dos CLIs, con el consumo descontado;
    - transcript borrado (409);
    - CLI sin la conversación, que termina `failed` con `session_missing`;
  - `test_datadir.py`:
    - puntero;
    - tamaño;
    - validaciones del movimiento;
    - mover fuera y volver (también con un `logs` previo en la carpeta de inicio);
    - fallo a mitad, que deja los datos donde estaban;
    - API con reinicio y 409 con ejecuciones activas;
  - `test_maintenance.py`:
    - ramas reales: fusionadas, sin fusionar, en uso, sin tarea, y otra rama activa en el repositorio;
    - retención de logs, incluido un log bloqueado que se reintenta;
  - `test_housekeeping.py`: plugins de agy huérfanos, worktrees de tareas cerradas y un paso que falla sin parar los demás;
  - `test_clis.py` ampliado: sesión iniciada de Claude por `auth status` y de agy por `models`.
- **Frontend**:
  - `settings.test.tsx`: CLIs detectados, carpeta de datos y su movimiento, tema, retención y limpieza de ramas, «Acerca de»;
  - `reconnect.test.tsx`: shell de Tauri simulado. Cubre «Reconectando…» y la URL nueva tras un reinicio, y el abandono con «Reintentar» y «Abrir logs»;
  - `dashboard.test.tsx`: aviso de primer arranque sin CLIs;
  - «Reanudar sesión» en `runs.test.tsx`, `tasks.test.tsx` e `inbox.test.tsx`, y el aviso de log borrado.
- **Desktop** (`cargo test`): `next_action` (código 75, esperas 1-2-4 s, abandono), logs según el puntero, `restarting`.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Máquina limpia | ⏳ pendiente del usuario | Windows Sandbox no está activado en el equipo (activarlo requiere administrador y reiniciar). `scripts/clean-machine.ps1` abre el Sandbox con el instalador. En el equipo de desarrollo, la instalación sin administrador funciona y el Dashboard guía si no hay CLIs (`dashboard.test.tsx`) |
| CA2 | Actualizar encima conserva datos, migra y copia | ✅ | 0.1.0 con datos → 1.0.0: agente y proyecto intactos, migración `0002`→`0007` y `backups\agentic-os-0002-….db` ([evidencia](evidencias/app-instalada.md#ca2--actualizar-encima-de-una-versión-anterior-con-datos)). `test_backup.py` |
| CA3 | Desinstalar | ✅ / ⏳ | Desinstalación silenciosa: la app desaparece del registro y de `%LOCALAPPDATA%` y los datos se conservan. Falta la casilla «Borrar los datos», que solo se puede marcar en la interfaz del desinstalador (hook `windows/hooks.nsh`) |
| CA4 | Una sola instancia | ✅ | Abrir la app dos veces deja 1 proceso de la app y 1 backend ([evidencia](evidencias/app-instalada.md#ca4--una-sola-instancia)) |
| CA5 | Sidecar caído: «Reconectando…» y abandono tras 3 fallos | ✅ | Relanzado en otro puerto en 3,8 s; tras el 4.º fallo seguido no se relanza ([evidencia](evidencias/app-instalada.md#ca5--el-backend-se-cae)). `cargo test`, `reconnect.test.tsx` |
| CA6 | Sin huérfanos al cerrar con ejecuciones activas | ✅ | Claude y agy reales activos: al cerrar no queda ningún `agy`, ningún `claude` de Agentic OS ni backend; al reabrir, «Interrumpida». Prueba de humo sin procesos ni `_MEI` ([evidencia](evidencias/app-instalada.md#ca6-y-ca7--cerrar-con-ejecuciones-activas-y-reanudar-sesión-clis-reales)). Ver la limitación de `_MEI` tras una **caída** |
| CA7 | Reanudar sesión con Claude y agy reales | ✅ | Los dos recuerdan «GIRASOL» y completan la tarea; misma sesión, ejecución enlazada y consumo por separado ([evidencia](evidencias/app-instalada.md#ca6-y-ca7--cerrar-con-ejecuciones-activas-y-reanudar-sesión-clis-reales), [captura R1](evidencias/r1-reanudar.md)). Sesión inexistente: tests y e2e |
| CA8 | Ajustes fieles a `12-ajustes` | ✅ | [Captura 1](evidencias/ca8-ajustes-1.jpg) (CLIs con sesión, General, Notificaciones) y [captura 2](evidencias/ca8-ajustes-2.jpg) (Límites, Limpieza, Acerca de). `settings.test.tsx` |
| CA9 | Limpieza de ramas y logs | ✅ | `test_maintenance.py` con un repositorio real; limpieza al arrancar en `test_housekeeping.py` |
| CA10 | Pendientes de fases anteriores con la app instalada | ⏳ pendiente del usuario | Necesitan la ventana: F5 en una subruta, «Examinar…», notificación nativa con clic a la Inbox, «Exportar CSV» y ausencia de ventanas de consola. La app 1.0.0 queda instalada para comprobarlo. Los subprocesos sin ventana los cubre `test_proc.py` |
| CA11 | e2e empaquetados, prueba de humo y arranque < 5 s | ✅ | `test:packaged`: 17 passed. Prueba de humo: todo OK, arranque hasta `/api/health` en 3,3 s; sidecar solo, 2,3–2,9 s |
| CA12 | `check` en verde, ADR, README y roadmap | ✅ | Salida arriba; [ADR 0012](../../adr/0012-packaging-and-resume.md); README (instalar, actualizar, desinstalar, SmartScreen, comandos, API); roadmap |

## Code review
`/code-review high` sobre la rama:

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Volver los datos a la carpeta de inicio fallaba si había una carpeta `logs`, y el *rollback* la borraba | Alta | **Corregido**: `copytree(dirs_exist_ok=True)` y el *rollback* solo borra lo que creó. Test |
| Borrar ramas: un `GitError` daba un 500 tras un borrado parcial. Además, `git branch -d` comprueba la fusión contra lo que esté activo, no contra la rama base | Alta | **Corregido**: se comprueba contra la rama base y se borra con `-D`; los fallos se devuelven por rama (`failed`) y la UI los muestra. Test con otra rama activa |
| `session_missing` buscaba en toda la pantalla: un agente que citara la frase podía marcar como fallida una reanudación correcta | Alta | **Corregido**: solo en las últimas líneas y solo si el CLI salió con error. Test |
| Al reanudar, la tarea conservaba `waiting_reason` | Media | **Corregido**. El e2e lo comprueba |
| Dos «Reanudar» simultáneos podían lanzar dos CLIs sobre la misma sesión | Media | **Corregido**: `resume` serializado con un *lock* y recarga de la ejecución |
| La lectura final o el *backfill* de la ejecución antigua, sin límite superior, podía contar lo de la reanudada | Media | **Corregido**: antes de reanudar se cierra el consumo de la antigua (`final`), y el *backfill* omite las ejecuciones ya cerradas |
| El tamaño de la carpeta de datos no bajaba tras «Limpiar ahora» (caché de 60 s) | Baja | **Corregido**: la limpieza vacía la caché |
| `GET /runs` calculaba `resumable` con unas 4 consultas por fila | Baja | **Corregido**: solo en el detalle (`GET /runs/{id}` y la respuesta de `resume`), que es lo que usa la UI |
| Una tarea en cola podía arrancar entre la comprobación y el reinicio al mover los datos | Baja | **Corregido**: el scheduler se para antes de comprobar y se reanuda si la petición falla |
| Un log bloqueado se marcaba `log_purged` aunque no se hubiera borrado | Baja | **Corregido**: solo se marca si se borra todo, y si no se reintenta en la siguiente limpieza. Test |

Además, durante la validación:
- **la build de release fallaba con «SignTool not found»**: con `signCommand` configurado, Tauri exige `signtool` aunque no haya certificado. La firma pasó a `tauri.sign.conf.json`, que `scripts/build-desktop.ps1` solo aplica si existe `AGENTIC_OS_SIGN_CERT`;
- **el aviso del Dashboard rompía la página** si `/api/clis` devolvía algo que no fuera una lista (lo detectaron los tests con el *mock* genérico). Corregido.

## Retro
- **Cambios respecto a la spec y al plan**:
  - **agy sí permite reanudar una conversación concreta** (`--conversation <id>`), así que desaparece el riesgo de la spec;
  - **la `cost-state` de Claude es acumulada tras un cierre limpio y empieza de cero tras un corte**, de modo que restar un total no bastaba. La línea base guarda la posición en el transcript y la última `cost-state` (R1);
  - **con un ID que no existe, agy no falla**: abre otra conversación. Se detecta por el `conversationId` del primer hook;
  - «Reanudar» también se ofrece en ejecuciones paradas, fallidas o terminadas (no solo interrumpidas) si su tarea espera al usuario;
  - la API para borrar ramas es `POST /maintenance/branches/delete` (no `DELETE` con cuerpo), y devuelve las que fallan;
  - la firma de código va en `tauri.sign.conf.json`, porque Tauri exige `signtool` si hay `signCommand`;
  - el CLI falso termina por sí solo una sesión reanudada, para que el e2e funcione también contra el binario;
  - se añadió un aviso en el Dashboard cuando ningún CLI está listo (el «guía al usuario» de la spec);
  - `--onefile` se mantiene (arranque < 5 s).
- **Limitaciones conocidas**:
  - tras una **caída** del backend, PyInstaller `--onefile` puede dejar su carpeta `%TEMP%\_MEI*` (unos 15 MB cada vez); en un cierre normal no pasa;
  - el desinstalador no borra una carpeta de datos movida a otro sitio.
- **Pruebas que quedan para el usuario**: CA1 (Windows Sandbox o VM), la casilla de borrar datos al desinstalar y CA10 (F5, «Examinar…», notificación nativa y su clic, CSV y ausencia de ventanas de consola).
- **Restos de las pruebas**: la entrada de confianza de Claude para `%TEMP%\agentic-real-resume\claude` queda en `~/.claude.json`, porque no se debe tocar con Claude Code abierto. Se puede quitar con Claude Code cerrado. La de agy ya se quitó.
- **Impacto en fases futuras**:
  - **Fase 09 (UX/UI)**: recorrer Ajustes con el usuario, que ahora tiene seis secciones, y decidir el Dashboard completo;
  - **futuras**: actualizaciones automáticas (requieren publicar las versiones), firma con certificado, `--onedir` para las carpetas `_MEI`, idiomas además del español, y borrar una carpeta de datos movida al desinstalar.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v1.0`
- [ ] `docs/roadmap.md` actualizado
