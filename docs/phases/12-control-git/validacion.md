# Fase 12: Control de git · Validación

> Estado: **en validación**. El desarrollo está terminado y el `/code-review` resuelto; faltan **tres pruebas manuales con servicios reales** (ver «Pendiente») y el OK del usuario.

## Tests automáticos
```
backend (pytest):   82 archivos · 709 tests, todos en verde en la última suite completa
                    nuevos de la fase, entre otros:
                    test_repos (16) · test_runrepos (5) · test_changes_multirepo (5) ·
                    test_gitx_read (24) · test_gitx_write (19) · test_gitx_merge (22) ·
                    test_gitx_extras (24) · test_gitx_jobs (11) · test_git_api (15) ·
                    test_git_api_merge (10) · test_git_api_more (12) · test_integration (14) ·
                    test_integration_api (5) · test_forges (28) · test_git_agents (13) ·
                    test_git_agents_review (6) ·
                    test_git_agents_e2e (1, backend real + CLI falso en ConPTY) ·
                    test_migration_0011 (1) · test_migration_0012 (1)
frontend (vitest):  38 archivos · 330 tests en verde, con nuevos
                    git-tab · git-integration · git-more · forges · integration · run-git ·
                    git-section · repos · conflict-parse · graph
lint:               npm run lint (ruff, eslint, prettier, tsc, cargo fmt, spikes) en verde
```
Los tests usan **repositorios git reales** en carpetas temporales (con remotos *bare* donde hace falta), el CLI falso en una ConPTY real para el e2e, y un transporte HTTP simulado (`httpx.MockTransport`) para GitHub y GitLab.

**Fragilidades que ya existían y que esta fase ha tocado:**
- `test_agy_status` sustituía `shutil.which` para **toda la suite** sin restaurarlo, y rompía todo lo que usa git después de él (los 6 tests de `test_git_api` fallaban solo en la suite completa). Corregido con `monkeypatch`.
- `test_memory_notes::test_notes_crud` falló una vez en una suite completa anterior (no en la última) y pasa aislado: dos notas creadas en el mismo tic del reloj de Windows salen en orden distinto. No es de la fase y no se ha tocado.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Proyecto cuya raíz no es un repo, con dos repos y uno vinculado: los detecta o admite, vista general y fetch, pull, push y commit en lote | ✅ | `test_repos.py` (raíz sin repo con dos dentro, vinculado, profundidad, carpetas ignoradas, submódulos); `test_git_api.py::test_overview_lists_every_repository_with_its_state`, `::test_batch_runs_the_action_in_each_repository_on_its_own`; `git-tab.test.tsx` (vista general y lotes) |
| CA2 | Tarea en worktree: una carpeta con un worktree por repo, cada uno en su `agentic/T-n` desde su base; el diff de la tarea y de cada ejecución se agrupa por repo y coincide con `git diff` | ✅ | `test_worktrees.py`; `test_changes_multirepo.py` (un diff por repo, repo no tocado no se lista, snapshots excluyen repos anidados); `test_changes_e2e.py::test_a_task_in_two_repositories…` con el CLI falso |
| CA3 | Integrar la rama de una tarea aprobada en las bases (merge, squash, rebase) y subir o abrir un pull request; con conflictos: resolver, pasar a un agente o deshacer lo integrado | 🟡 | Integrar, subir, abrir pull request, pasar a un agente y deshacer: ✅ `test_integration.py` (merge con la carpeta de la base y sin ella, squash, rebase, conflictos, carpeta sucia, deshacer, varios repos y deshacer en grupo, **remoto *bare***, tarea de resolución, al aprobar), `test_integration_api.py`, `test_forges.py` (pull requests por repo y enlazados, `pull_request` al aprobar), `integration.test.tsx`. **«Resolver aquí» no usa el `ConflictEditor` de la app** (ver «Cambios respecto a la spec»). GitHub real: pendiente (manual) |
| CA4 | Desde la app: stage y descarte por fichero, bloque y línea; commit y enmienda; stash; tags; cherry-pick, revert, reset; ramas; rebase interactivo; remotos; push forzado con confirmación; submódulos; LFS; worktrees; clean y gc | ✅ | `test_gitx_write.py` (por fichero, bloque, línea, CRLF, sin salto final, selección obsoleta), `test_gitx_merge.py` (rebase interactivo: reordenar, juntar, `reword`, descartar, `fixup`, `edit`), `test_git_api_more.py` (stash, tags, remotos y push forzado, submódulos, LFS, worktrees, clean, gc), `git-more.test.tsx`, `git-integration.test.tsx`. «Partir» un commit es la acción `edit`: el rebase se detiene y se parte a mano. LFS se prueba si `git-lfs` está instalado |
| CA5 | Historial con grafo, *blame* y ramas coinciden con `git log --graph`, `git blame` y `git branch -vv` (sin `refs/agentic-os/`); los commits de cada agente aparecen con su agente, tarea y ejecución | ✅ | `test_gitx_read.py` (orden de git, páginas, historial de todas las ramas sin las referencias de la app, *blame* por grupos, ramas con su distancia), `graph.test.ts`; atribución: `test_git_agents_e2e.py` (agente, tarea y ejecución en el historial) y `run-git.test.tsx` |
| CA6 | El editor de tres vías resuelve los conflictos de un merge, un rebase y un cherry-pick, y se puede continuar o abortar | ✅ | `test_gitx_merge.py` (rebase con conflicto: continuar, saltar, abortar; cherry-pick con conflicto abortado); `git-integration.test.tsx` (editor: bloque a bloque, a mano, lado entero, abortar tras preguntar, «Continuar» deshabilitado con marcas). El editor y la barra de la operación son los mismos para los tres |
| CA7 | «Deshacer» devuelve la rama tras reset `--hard`, rebase, merge y borrado de rama | ✅ | `test_gitx_merge.py::test_undo_a_merge…`, `::test_undo_a_hard_reset_brings_back_the_lost_files`, `::test_undo_a_deleted_branch_and_a_rebase`, `::test_undo_is_refused_when_the_branch_moved_since`; `test_git_api_merge.py`; `git-integration.test.tsx` |
| CA8 | Un agente de Claude Code en modo `manual` commitea, crea una rama, hace rebase y push (también forzado) sin que el CLI pregunte ni la app lo impida; la ejecución registra commits, ramas y pushes | 🟡 | Automatizado ✅: `test_git_agents.py` (las dos reglas `Bash(git:*)` y `PowerShell(git *)` en el `argv` de Claude en `manual` y `restringido`, sin duplicarlas, y no en `autónomo`; sección «Git» en las instrucciones), `test_git_agents_e2e.py` (tarea real: commit, rama, tag y push; registro, atribución, evento de la tarea y deshacer), `test_git_agents.py` (push forzado y enmienda detectados). **Que el CLI real no pregunte: pendiente (manual)**; el CLI falso no tiene diálogos de git |
| CA9 | Clonar desde una URL crea el proyecto; inicializar o clonar dentro de un proyecto añade el repo; los proyectos existentes conservan su repo y su base | ✅ | `test_gitx_extras.py` (clonar con progreso, destinos validados, `init`), `test_git_api_more.py::test_clone_and_init_through_the_api`, `git-more.test.tsx` (clonar desde URL: crea el proyecto, falla sin crear nada, pide la URL), `repos.test.tsx` («Inicializar repositorio» en un proyecto sin repos), `test_migration_0011.py` |
| CA10 | Las operaciones largas muestran progreso, se cancelan y no bloquean la UI; los errores se ven con un mensaje claro y git nunca espera una contraseña | 🟡 | Automatizado ✅: `test_gitx_jobs.py` (progreso leído de stderr, cancelación matando el árbol de procesos, candado exclusivo, remoto inalcanzable → código claro), `test_git_api.py` (trabajos con eventos y cancelación), `git-tab.test.tsx` (progreso por eventos y «Cancelar»), `test_forges.py` (códigos de la API de los servicios). Git corre con `GIT_TERMINAL_PROMPT=0` y `ssh -o BatchMode=yes`. **Con red, credenciales y un push rechazado reales: pendiente (manual)** |
| CA11 | Lint, tests de backend y de frontend en verde; `/code-review` resuelto | ✅ | arriba y abajo |

## Pendiente
Tres pruebas con servicios reales que no se pueden hacer desde aquí (sin credenciales y sin lanzar sesiones reales con coste):
1. **Pull request en un repo real de GitHub** (CA3): Ajustes › Git (token, claves SSH, «Probar conexión»), «Abrir pull request» desde una tarea con dos repos, fusionarlo y cerrarlo. Los tests cubren GitHub y GitLab con un transporte simulado; lo que no se ve es la respuesta de los servicios reales.
2. **Claude Code real en modo `manual`** (CA8): una tarea que pida un commit, una rama, un rebase y un push (también forzado); comprobar que Claude no muestra ningún diálogo y que la sección «Git» de la ejecución lo registra. Es la comprobación de las dos reglas del spike S2 en el flujo completo.
3. **Errores de red y credenciales reales** (CA10): un `fetch` sin red, un `push` a un remoto sin credenciales y un push rechazado por no ser *fast-forward*; ver el mensaje y que nada se quede esperando.

También quedan sin comprobar en un navegador real los textos y la disposición de las pantallas nuevas (los tests de interfaz usan jsdom).

## Code review
Diez hallazgos; ocho corregidos, dos justificados.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Un mismo commit podía salir dos veces del reflog y romper la restricción única de `commit_attributions`, perdiendo el cierre de la ejecución | alta | corregido: se deduplican y se anotan los ya vistos; test |
| Un *fast-forward* traía un commit ajeno y se atribuía al agente | media | corregido: se ignoran los *fast-forward*; test |
| Una rama movida sin ningún commit de la ejecución se le atribuía (y «Deshacer» podía resetear trabajo ajeno) | media | corregido: solo cuenta si la ejecución metió commits en ella; test |
| «Deshacer» una ejecución fallaba a medias si faltaba un repo, tras tocar otros | media | corregido: se comprueban todos antes de tocar ninguno; test |
| «Deshacer» repetido marcaba las ramas ya devueltas como «movidas después» y la ejecución nunca contaba como deshecha | media | corregido: se reconocen como ya hechas; test |
| Una ejecución sin instantánea no registraba su actividad de git | media | corregido |
| La detección de pushes lanzaba un proceso por commit y referencia | baja | corregido: una consulta por referencia |
| Las búsquedas de atribución podían superar el límite de variables de SQLite | baja | corregido: trozos de 500; test |
| La sección «Git» de las instrucciones se da a todos los agentes aunque solo Claude aplica el permiso | baja | justificado: hoy solo existen Claude y agy, y agy no pregunta por git (spike S1). Revisar al añadir otro CLI |
| Anotar las referencias de cada repo al empezar cuesta unos procesos git | baja | justificado: es acotado; un fallo queda ahora en el log en lugar de pasar en silencio |

Además, la revisión de los bloques anteriores y los tests destaparon: la ventana de tiempo del reflog colaba commits anteriores (se cuenta ahora por posición), la sección Ramas enlazaba a `/tareas/:id` que no existe, y un test de otra fase rompía git para el resto de la suite.

## Retro
- **Cambios respecto a la spec**:
  - **«Resolver aquí» no abre el `ConflictEditor`.** La spec y el plan decían que el editor de conflictos trabajaría sobre un worktree de integración. Sus rutas trabajan por `repo_id` y el worktree no es un repo del proyecto, así que se hizo al revés (la base se fusiona en la rama de la tarea, en una carpeta propia) y los ficheros se resuelven con las herramientas del propio usuario; «Marcar resuelto» hace el commit. Con la tarea de resolución por agente y «Deshacer» del grupo, las tres salidas de CA3 existen, pero la primera no usa el editor de la app.
  - El editor de conflictos usa un `<textarea>` y no CodeMirror 6, y el rebase interactivo usa flechas y no `@dnd-kit` (menos dependencias y comprobable en jsdom).
  - Los commits de una ejecución se detectan **contando** el reflog, no por una ventana de tiempo.
  - No se atribuyen los commits anteriores a la fase.
  - Los pull requests se ven y se gestionan, pero no se editan sus comentarios ni se responde a revisiones desde la app (solo lectura).
- **Impacto en fases futuras**:
  - `integration.py`, `forges/` y `gitx/activity.py` son la base de cualquier automatización que integre trabajo (p. ej. pipelines con ramas).
  - Un agente nuevo (Gemini CLI, Codex CLI, OpenCode) tendrá que aplicar `LaunchContext.git_authorized` en su adapter; la sección «Git» de las instrucciones ya se le da.
  - Abrir el `ConflictEditor` sobre el worktree de integración es una mejora pendiente.
  - `httpx` ya es dependencia de la app (antes solo de desarrollo).

## Cierre
- [ ] Pruebas manuales con servicios reales (GitHub, Claude Code, red)
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v1.4`
- [ ] `docs/roadmap.md` actualizado
