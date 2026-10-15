# Fase 11: Revisión de código · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-15) · en desarrollo

## Lo que ya se sabe (revisado al escribir el plan)
- **Fin de una ejecución**: `RunManager._on_end` se llama desde el hilo del PTY cuando el CLI ya ha terminado, **antes** de `on_run_ended`, que es cuando el scheduler mueve la tarea y, si termina, `Worktrees.release` commitea lo que quedó suelto y borra el worktree. Por tanto, la instantánea final se toma con el worktree todavía en su sitio.
- **Arranque de una ejecución**: `_launch` crea la `Run` y lanza el PTY. La instantánea inicial va justo antes del `session.start()`, cuando la carpeta ya es la de la ejecución (el worktree ya existe: `Worktrees.prepare` corre antes).
- **Ejecuciones interrumpidas**: `RunManager.recover()` las marca `interrupted` al arrancar. Ahí se toma su instantánea final.
- **Los worktrees comparten las referencias** con el repositorio principal. Una referencia escrita desde `<proyecto>.wt\T-142` existe en el repo del proyecto y sigue al borrar el worktree.
- **El plugin de agy** está excluido con `.git/info/exclude` (ADR 0009), así que `git add -A` no lo recoge en las instantáneas.
- **`services/git.py`**: `run()` no acepta variables de entorno, pero `proc.run` sí. Hay que añadir `env`.
- **Purga de logs** (`maintenance.purge_logs`, fase 08): marca `log_purged` en las ejecuciones antiguas. Ahí se engancha la limpieza de sus instantáneas.
- **El CLI falso** (`tests/fake_cli.py`) no toca ficheros. Necesita dos órdenes nuevas para los tests e2e.

## Resultados del spike S1 (git 2.55, Windows)
- **Índice copiado frente a vacío**: en este repo (675 ficheros), 0,41 s frente a 1,31 s; en uno sintético de 10 000 ficheros con un cambio y un fichero nuevo, **0,27 s frente a 0,80 s**. Se confirma copiar el índice.
- **`--ignore-cr-at-eol`** se aplica tanto a `--numstat` como a `--name-status`: un fichero que solo cambia de LF a CRLF desaparece de las dos salidas. No hace falta filtrarlos a mano.
- No se midió un `node_modules` real sin ignorar; el límite de 5 MB por fichero nuevo y el tiempo máximo de 30 s cubren ese caso.

## Diseño

### Instantáneas (`services/snapshots.py`, nuevo)
`take(folder, label) -> str | None` devuelve el sha de un commit que representa la carpeta tal como está:
1. `git rev-parse --git-path index` → se copia el índice real a un fichero temporal en la carpeta de datos.
   - Copiarlo, en vez de partir de uno vacío, conserva la información de `stat` de git: `git add` solo vuelve a leer los ficheros que han cambiado, como un `git status`. Partir de un índice vacío obligaría a leer todo el repo.
   - Si la carpeta no tiene índice (repo recién creado), se parte de uno vacío.
2. Con `GIT_INDEX_FILE=<temporal>`: `git add -A` (respeta `.gitignore` y `info/exclude`) y `git write-tree`.
3. `git commit-tree <tree> [-p HEAD] -m "agentic-os snapshot <run> <label>"`, con la identidad de reserva de los worktrees si el repo no tiene ninguna.
4. Se borra el temporal.

- **Nada de esto toca** el índice real, `HEAD`, las ramas ni los ficheros (CA4).
- **Referencias**: `refs/agentic-os/runs/<run_id>/start` y `.../end`, con `git update-ref`.
  - No son ramas ni tags: `git branch`, `git tag` y un `git push` normal no las ven, y protegen los commits del `git gc`.
  - **Contrapartida**: aparecen en `git log --all` y en vistas como `gitk --all`. Queda en el ADR.
- **Tiempo máximo**: 30 s. Un error o un timeout no impiden lanzar ni terminar la ejecución: el sha queda nulo, se registra el evento de sistema `snapshot_failed` con el motivo y el diff mostrará «No hay datos».
- **Límite de tamaño**: los ficheros nuevos de más de 5 MB no se añaden (se pasan como `:(exclude)` a `git add`) y se avisa en el diff («n ficheros grandes sin incluir»). Así un `node_modules` sin ignorar no llena el repo de golpe.
- `delete(repo, run_ids)`: borra las referencias con `git update-ref --stdin`, en una sola llamada.
- `delete_all(repo)`: borra todas las de `refs/agentic-os/`.

### Modelo de datos (migración `0010_run_snapshots`)
- **`runs`**:
  - `snapshot_start` y `snapshot_end` (sha, nulos);
  - `changes_files`, `changes_added` y `changes_deleted` (enteros, nulos = sin datos): el resumen que se calcula al terminar la ejecución.
- **`tasks`**: `base_commit` (sha, nulo), el commit de la rama base del que salió el worktree. `Worktrees.prepare` lo guarda al crearlo.
- Las filas existentes quedan a nulo: son las «anteriores a la fase».

### Captura en el ciclo de vida
- `RunManager._launch`: si `cwd` está dentro de un repo git, `snapshot_start = take(cwd)` antes de arrancar el PTY.
- `RunManager._on_end`, después de `adapter.cleanup`:
  1. `snapshot_end = take(cwd)`;
  2. se calcula el resumen (`git diff --numstat` de inicio a fin) y se guarda en la ejecución;
  3. se llama a `on_run_ended`.
- `RunManager.recover()`: hace lo mismo para las ejecuciones que pasan a `interrupted` y tienen `snapshot_start` pero no `snapshot_end`. El diff lo marca como parcial: «tomado al reabrir la app; puede incluir cambios posteriores».
- Las ejecuciones reanudadas (fase 08) son ejecuciones nuevas y tienen sus propias instantáneas.

### Diffs (`services/changes.py`, nuevo)
- **`Range`**: los dos extremos que se comparan, con su etiqueta para la cabecera.
  - **Ejecución**: `snapshot_start` → `snapshot_end`. Si la ejecución está viva, el extremo final es una instantánea en el momento, sin referencia.
  - **Tarea con worktree**:
    - origen: `base_commit` o, en tareas anteriores a la fase, `merge-base(base_branch, branch)`;
    - final: el `snapshot_end` de su última ejecución o, si no lo hay, la punta de `task.branch`. Con una ejecución viva, una instantánea en el momento.
  - **Tarea en carpeta directa**: del `snapshot_start` de su primera ejecución con instantánea al `snapshot_end` de la última. La cabecera avisa de que también incluye lo que cambiara en la carpeta entre medias.
  - **Sin datos**: estado `no_git`, `no_snapshots` o `snapshot_missing` (la referencia ya no está: repo borrado, clonado de nuevo o purgado).
- **`summary(range)`**:
  - `git diff -z --numstat -M --ignore-cr-at-eol` junto con `--name-status`, unidos por ruta;
  - por fichero: `path`, `old_path`, `status` (`added` · `modified` · `deleted` · `renamed`), `additions` y `deletions`;
  - en los binarios (`-` en numstat), `binary` con `old_size` y `new_size` (`git cat-file -s`);
  - `generated`, marcado con una lista fija: `*.lock`, `package-lock.json`, `pnpm-lock.yaml`, `uv.lock`, `dist/`, `build/` y `*.min.*`;
  - los ficheros que solo cambian de CRLF a LF (0/0 y `modified`) se descartan (lo hace `--ignore-cr-at-eol`);
  - máximo 500 ficheros: el resto se resume en `truncated_files`.
- **`file_diff(range, path)`**:
  - `git diff -U3 --ignore-cr-at-eol -M <a> <b> -- <path>` (y `old_path` si es un renombrado), convertido a hunks: `old_start`, `old_lines`, `new_start`, `new_lines` y `header` (la función que da git);
  - cada línea con `kind` (`context` · `add` · `del`), `old_no`, `new_no` y `text`;
  - más de 20 000 líneas → `too_large` sin contenido.
- **`file_lines(range, path, start, end)`**: líneas de la versión final (`git show <b>:<path>`), para el «Mostrar n líneas más» entre hunks. Son contexto, así que el número antiguo se calcula con el desfase del hunk anterior.
- Todo pasa por `git.run` con timeout. Los diffs no se guardan: se recalculan al pedirlos. Solo el resumen de la ejecución queda en la BD.

### Limpieza
- `maintenance.purge_logs`: además de los logs, borra las referencias de las ejecuciones que purga, agrupadas por proyecto, y pone a nulo sus `snapshot_*` (el resumen +/− se conserva).
- `DELETE /api/projects/{id}`: `delete_all` antes de borrar el proyecto. Si la carpeta ya no existe, no hace nada.
- **Ajustes › Limpieza** (`CleanupSection`): una fila por proyecto con «n instantáneas» y «Borrar instantáneas», que llama a `POST /api/maintenance/snapshots/{project_id}/delete`. Sigue el patrón de «Ramas de tareas» de la fase 08.

### API
- `GET /api/runs/{id}/changes`:
  - `state` (`ok` · `no_git` · `no_snapshots` · `snapshot_missing`), `live`, `partial` y `direct_folder`;
  - `from_label`, `to_label` y `totals` (`files`, `additions`, `deletions`);
  - `files[]`, `truncated_files` y `skipped_large`.
- `GET /api/runs/{id}/changes/file?path=` → `{hunks, too_large, binary}`.
- `GET /api/runs/{id}/changes/lines?path=&start=&end=` → `{lines}`.
- `GET /api/tasks/{id}/changes` (mismo formato, con `runs[]` para el selector: `id`, etapa, intento, `started_at` y totales), más `.../changes/file` y `.../changes/lines`.
- `GET /api/agents/{id}/changes?project_id=&limit=50`: sus ejecuciones con `changes_files > 0`, con tarea, proyecto, fecha y totales.
- `RunOut` gana `changes: {files, additions, deletions} | null`.
- `InboxItemOut` gana `changes` para los items `review` y `delivery` con tarea: los totales de la tarea, calculados al leer, con caché por `(task_id, extremo final)` en memoria.
- `path` se valida contra la lista de ficheros del rango; una ruta que no está devuelve 404, de modo que no se puede leer un fichero cualquiera del repo.

### Frontend
- **`components/changes/`** (nuevo):
  - `ChangesViewer`: cabecera (n ficheros · +a −b, «de → a» y avisos: viva, parcial, carpeta directa, truncado), `FileList` y la lista de `FileDiff`;
  - `FileList`: ruta, estado (A · M · D · R, con `old_path → path`), +/−, barra proporcional y clic que hace scroll al fichero;
  - `FileDiff`:
    - cabecera plegable;
    - el contenido se pide al desplegar (`useChangesFile`), de modo que un diff grande no carga todo a la vez (CA7);
    - plegados por defecto: los `generated` y los de más de 800 líneas cambiadas, con «Cargar diff (n líneas)»;
    - binarios con «Binario · 24 KB → 31 KB»; `too_large` con su aviso;
  - `Hunk`: tabla de dos columnas de número y texto monoespaciado; colores `--diff-add-bg`, `--diff-del-bg` y `--diff-*-fg`, nuevos tokens del tema en claro y oscuro; «Mostrar n líneas más» entre hunks y al final;
  - `ChangesBadge`: «4 ficheros · +120 −35» (12 px, muted, + en verde y − en rojo), reutilizado en enlaces y tablas;
  - `ChangesSheet`: el `Sheet` lateral ancho con `ChangesViewer` y un pie opcional de acciones.
- **`api/changes.ts`**: tipos y hooks `useRunChanges`, `useTaskChanges`, `useChangesFile`, `useChangesLines` y `useAgentChanges`. Con una ejecución viva, refresco cada 5 s.
- **Detalle de tarea** (`TaskPage`): sección «Cambios» con un selector «Toda la tarea» o cada ejecución («Etapa Dev · intento 2 · hace 1 h») y `ChangesViewer`.
- **Revisión y entrega** (`RequestActions` / `RequestItem`, que se usan en Peticiones, «Te necesitan» y el detalle de tarea): enlace «Ver cambios · `ChangesBadge`» que abre `ChangesSheet`. En `review`, el pie lleva «Aprobar» y «Rechazar» (el mismo formulario de motivo); en `delivery`, «Marcar como revisado». Al decidir, se cierra el panel.
- **Página de ejecución** (`RunPage`): sección «Cambios».
- **Ficha del agente**: pestaña nueva `ChangesTab` («Cambios»), detrás de Historial. Muestra la lista de ejecuciones con tarea, proyecto, fecha y `ChangesBadge`, y un filtro por proyecto. Al hacer clic se abre `ChangesSheet` con el diff de la ejecución.
- **Ejecuciones** (`RunsTable`): columna «Cambios» con `ChangesBadge` compacto (+/−) o «—».
- **i18n**: claves `changes.*` en `es.json`.

### CLI falso
- Órdenes nuevas en el prompt: `ESCRIBE: ruta=texto` (crea o sobrescribe un fichero) y `COMMIT: mensaje` (`git add -A` + `git commit`). Así los e2e reproducen un agente que commitea a mitad y deja trabajo sin commitear.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0010_run_snapshots.py` | nuevo |
| `backend/src/agentic_os/models/run.py`, `models/task.py` | modificado: `snapshot_*`, `changes_*`, `base_commit` |
| `backend/src/agentic_os/services/git.py` | modificado: `env` en `run()` |
| `backend/src/agentic_os/services/snapshots.py` | nuevo |
| `backend/src/agentic_os/services/changes.py` | nuevo |
| `backend/src/agentic_os/services/runs/manager.py` | modificado: instantáneas en `_launch`, `_on_end` y `recover` |
| `backend/src/agentic_os/services/worktrees.py` | modificado: guarda `base_commit` |
| `backend/src/agentic_os/services/maintenance.py` | modificado: limpieza de instantáneas |
| `backend/src/agentic_os/api/changes.py` | nuevo: endpoints de ejecución, tarea y agente |
| `backend/src/agentic_os/api/projects.py`, `api/maintenance.py`, `api/runs.py`, `api/inbox.py` | modificado |
| `backend/src/agentic_os/schemas/changes.py` | nuevo |
| `backend/src/agentic_os/schemas/run.py`, `schemas/inbox.py` | modificado: `changes` |
| `backend/tests/fake_cli.py` | modificado: `ESCRIBE` y `COMMIT` |
| `backend/tests/test_snapshots.py`, `test_changes.py`, `test_changes_api.py`, `test_changes_e2e.py`, `test_migration_0010.py` | nuevos |
| `frontend/src/api/changes.ts` | nuevo |
| `frontend/src/components/changes/*` | nuevos |
| `frontend/src/pages/tasks/TaskPage.tsx`, `pages/runs/RunPage.tsx`, `pages/runs/RunsTable.tsx` | modificado |
| `frontend/src/components/requests/RequestActions.tsx`, `RequestItem.tsx` | modificado |
| `frontend/src/pages/agents/AgentEditorPage.tsx`, `pages/agents/tabs/ChangesTab.tsx` | modificado / nuevo |
| `frontend/src/pages/settings/CleanupSection.tsx` | modificado |
| `frontend/src/styles/tokens.css` | modificado: tokens del diff |
| `frontend/src/i18n/es.json` | modificado |
| `frontend/src/components/changes/changes.test.tsx` | nuevo |
| `docs/adr/0015-change-snapshots.md` | nuevo |

## Tareas (en orden)
1. [x] **Spike corto** (S1): medir `take()` en este repo y en uno grande (p. ej. un clon de un proyecto con miles de ficheros y un `node_modules` sin ignorar), con el índice copiado frente a uno vacío. Confirmar que `--ignore-cr-at-eol` se aplica a `--numstat` en la versión de git del equipo. Resultados en este plan.
2. [ ] `git.run` con `env`; `services/snapshots.py` con tests sobre repos temporales: worktree, carpeta directa, repo vacío, sin identidad, ficheros grandes y `git gc --prune=now` (CA4).
3. [ ] Migración `0010` y modelos, con su test de migración.
4. [ ] Instantáneas en `RunManager` (`_launch`, `_on_end`, `recover`) y `base_commit` en `Worktrees.prepare`; resumen +/− al terminar.
5. [ ] `services/changes.py`: rangos, `summary`, `file_diff` y `file_lines`, con tests de renombrados, binarios, borrados, CRLF, truncado y estados vacíos (CA1, CA3, CA7, CA8).
6. [ ] API de cambios, `changes` en ejecuciones e Inbox, y validación de `path`.
7. [ ] CLI falso con `ESCRIBE`/`COMMIT` y e2e: tarea de dos etapas con commit a mitad y trabajo sin commitear entre ejecuciones (CA2), en worktree y en carpeta directa.
8. [ ] Limpieza: purga de logs, borrado del proyecto y «Borrar instantáneas» en Ajustes (CA9).
9. [ ] Frontend: tokens del diff, `components/changes/*` y `api/changes.ts`, con tests del visor.
10. [ ] Frontend: superficies (detalle de tarea, revisión y entrega con `ChangesSheet`, página de ejecución, pestaña «Cambios» del agente, columna en Ejecuciones y Ajustes) (CA5, CA6).
11. [ ] ADR 0015, prueba manual con Claude Code y agy en un proyecto real (worktree y carpeta directa, diff de más de 5 000 líneas) y `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_snapshots.py`: la instantánea no cambia `git status`, `HEAD` ni el índice; recoge lo sin commitear y lo nuevo no ignorado; respeta `.gitignore` e `info/exclude`; sobrevive a `git gc --prune=now` y al borrado del worktree; funciona sin `HEAD` y sin identidad; omite ficheros > 5 MB; un fallo devuelve `None` | CA4 |
| `test_changes.py`: el diff de la tarea con worktree coincide con `git diff <merge-base>..agentic/T-n` (ficheros, estados, +/−), también después de borrar el worktree; renombrados, borrados, binarios con tamaños, CRLF ignorado, truncado de ficheros y de líneas, ficheros generados | CA1, CA7 |
| `test_changes.py`: en carpeta directa no aparecen los cambios del usuario anteriores al inicio; aparecen lo commiteado y lo sin commitear del agente | CA3 |
| `test_changes.py`: estados `no_git`, `no_snapshots` y `snapshot_missing`; ejecuciones anteriores a la fase | CA8 |
| `test_changes_e2e.py` (CLI falso): Dev commitea a mitad y deja cambios sin commitear; QA rechaza; el segundo intento de Dev solo muestra sus cambios; la tarea muestra el total | CA2 |
| `test_changes_api.py`: endpoints de ejecución, tarea y agente; `changes` en `/api/runs` y en los items `review`/`delivery`; `path` fuera de la lista → 404 | CA5, CA6 |
| `test_maintenance.py` (ampliado): la purga de logs y el borrado del proyecto quitan las referencias; «Borrar instantáneas» | CA9 |
| `test_migration_0010.py`: columnas nuevas a nulo sobre una BD de la v1.2 | CA8 |
| `changes.test.tsx`: cabecera y totales, lista de ficheros, plegado de generados y grandes, binarios, `too_large`, «Mostrar n líneas más», estados vacíos | CA7, CA8 |
| Tests de `TaskPage`, `RequestActions` (aprobar y rechazar desde el panel), `ChangesTab`, `RunsTable` | CA5, CA6 |
| CI local (lint, formato, tipos, tests) y `/code-review` | CA10 |

## Decisiones (ADR)
- **ADR 0015, Instantáneas de cambios**:
  - commits sin rama creados con un índice temporal copiado del real;
  - referencias `refs/agentic-os/runs/<id>/{start,end}` en el repo del proyecto, frente a un almacén aparte en la carpeta de datos. Se descarta el almacén aparte porque dependería de objetos del repo del usuario que un `gc` puede borrar;
  - qué extremos usa cada diff;
  - límites (5 MB por fichero nuevo, 500 ficheros, 20 000 líneas);
  - limpieza;
  - la contrapartida de `git log --all`.
