# Fase 11: Revisión de código · Validación

> Estado: **borrador, a la espera del OK del usuario.** Queda pendiente la prueba manual con Claude Code y agy reales (ver «Pendiente»).

## Tests automáticos
```
backend (pytest):   suite completa en verde, con nuevos
                    test_snapshots (11) · test_changes (24) · test_changes_api (6) ·
                    test_changes_e2e (4, backend real + CLI falso en ConPTY) ·
                    test_migration_0010 (1) · test_maintenance (+5, instantáneas)
frontend (vitest):  28 archivos · 239 tests en verde, con nuevos
                    components/changes/changes.test.tsx (9) · pages/changes-surfaces.test.tsx (10)
lint:               npm run lint (ruff, eslint, prettier, tsc, cargo fmt, spikes) en verde
```
Dos tests del frontend que renderizan la app entera (`agent-links` y, a veces, `runs`) agotan el tiempo de 15 s cuando toda la suite corre a la vez en esta máquina. **No es una regresión de la fase**: `main` falla igual, en el mismo test (`agent-links … creates the agent in a team and with the account chosen`), y aislados pasan.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Con worktree, el diff de la tarea coincide con `git diff <merge-base>..agentic/T-n`, también tras borrarse el worktree | ✅ | `test_changes.py::test_a_worktree_task_matches_git_diff_even_after_the_worktree_is_gone`; `test_changes_e2e.py::test_a_worktree_task_with_a_rejection…` compara con `git diff --numstat` real |
| CA2 | El diff de cada ejecución muestra solo lo que cambió en ella, aunque el agente commitee a mitad o deje trabajo sin commitear | ✅ | `test_each_run_only_shows_what_it_changed`; e2e con 4 ejecuciones (Dev, QA que rechaza, Dev, QA) y el CLI falso con `ANADE` y `COMMIT` |
| CA3 | En carpeta directa incluye lo que dejó el agente (commiteado y no) y no lo que el usuario ya tenía sin commitear | ✅ | `test_a_direct_folder_task_leaves_out_what_the_user_had_before`; e2e `test_a_direct_folder_leaves_out…` |
| CA4 | Tomar las instantáneas no cambia índice, rama ni ficheros, y sobreviven a `git gc --prune=now` | ✅ | `test_snapshots.py` (estado, `HEAD`, ramas y `write-tree` idénticos; `gc`; worktree borrado); e2e: `git status` limpio y rama `main` al final |
| CA5 | Al revisar una tarea se ve la lista de ficheros y el diff línea a línea, y se aprueba o rechaza desde el mismo panel | ✅ | `changes-surfaces.test.tsx` (aprobar, rechazar con motivo, marcar entrega); **comprobado en el navegador** con un backend de demostración: panel, lista con barras, hunks con números de línea, colores y botones «Mostrar más», acciones al pie |
| CA6 | La pestaña «Cambios» del agente lista sus ejecuciones y abre el diff de cada una | ✅ | `changes-surfaces.test.tsx` (lista, filtro por proyecto, panel), `test_changes_api.py::test_the_changes_of_an_agent` |
| CA7 | Binarios, renombrados, borrados y diffs grandes se muestran sin bloquear, con su aviso | ✅ | `test_changes.py` (binarios con tamaños, renombrados, borrados, CRLF, truncado, **6 000 líneas y 601 ficheros** en menos de 10 s), `changes.test.tsx` (plegado de generados y grandes, `too_large`, «Mostrar más») |
| CA8 | Sin git y las ejecuciones anteriores a la fase muestran su estado vacío, sin errores | ✅ | `test_changes.py::test_states_without_data`, e2e sin git, `changes.test.tsx` (los tres estados) |
| CA9 | Las referencias se borran con la purga de logs y al borrar el proyecto | ✅ | `test_maintenance.py` (purga, «Borrar instantáneas», borrar proyecto, dos proyectos en un mismo repositorio) |
| CA10 | Lint, tests de backend y de frontend en verde; `/code-review` resuelto | ✅ | arriba y abajo |

## Pendiente
- **Prueba manual con Claude Code y agy reales** (plan, tarea 11): un proyecto real en modo worktree y en carpeta directa, con un diff de más de 5 000 líneas. No se ha hecho: lanzaría sesiones reales y gastaría suscripción. Los mismos escenarios están cubiertos con el CLI falso en un backend real y con repositorios git reales; lo que no se ha visto es el comportamiento de los CLIs reales alrededor de las instantáneas (p. ej. el plugin de agy, que va excluido de git).

## Code review
Diez hallazgos, todos resueltos o justificados.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| `str.splitlines` troceaba las líneas con formfeed, U+2028… y `diff.suppressBlankEmpty` desalineaba los números | alta | corregido: se trocea solo por `\n` y cada hunk se lee por los contadores de su cabecera · `test_lines_with_form_feeds_…`, `test_blank_context_lines_printed_without_a_space_still_count` |
| En una ejecución viva, cada petición hacía una instantánea nueva: lista, fichero y líneas comparaban estados distintos y se recorría la carpeta cada 5 s | alta | corregido: la instantánea del «ahora» se reutiliza 4 s · `test_a_live_snapshot_is_reused_for_a_few_seconds` |
| El diff de un fichero abierto no se releía en una ejecución viva, y su clave de caché no incluía sus contadores | media | corregido: se relee cada 5 s si la ejecución está viva y la clave lleva estado y contadores |
| «Borrar instantáneas» y borrar un proyecto quitaban las referencias de todo el repositorio (otro proyecto con el mismo repositorio perdía las suyas) | alta | corregido: cada proyecto borra solo las de sus ejecuciones; el recuento sale de la base de datos · `test_forgetting_a_projects_snapshots_leaves_another_projects…` |
| Los tamaños de los binarios se pedían uno a uno antes de truncar a 500 ficheros | media | corregido: solo de los ficheros que se listan |
| El límite de 5 MB se aplicaba después de que `git add` ya hubiera leído y guardado el fichero | alta | corregido: los ficheros grandes se excluyen del propio `add` con pathspecs por la entrada estándar · `test_new_files_over_the_limit_are_left_out` |
| El diff de una tarea con worktree usaba el final de la última ejecución que tuviera uno, saltándose una posterior que cayó | alta | corregido: si la última ejecución no dejó final, se usa la punta de la rama · `test_a_task_whose_last_run_left_no_snapshot_…` |
| La instantánea final y la recuperación al arrancar son síncronas (hasta 30 s por ejecución); si falla el arranque del CLI quedaba una referencia huérfana | media | referencia huérfana: corregido. Lo síncrono: **justificado** y documentado en el ADR 0015 (la instantánea final debe tomarse antes de que el scheduler cierre la tarea y borre el worktree; en la práctica tarda décimas de segundo) |
| El caché de totales de Peticiones era un `dict` sin candado, tocado desde varios hilos, y su clave no incluye la punta de la rama | media | candado: corregido. Clave: **justificado** y documentado en el ADR (solo afecta a quien commitea a mano en la rama de una tarea ya cerrada) |
| `_merge_base` duplicado y el resumen +/− de una ejecución construido en tres sitios | baja | corregido: `git.merge_base` y `changes.run_totals` |

## Retro
- **Cambios respecto a la spec**:
  - La sección «Cambios» de la tarea y de la ejecución es un botón con el +/− que abre el panel lateral (el mismo de las revisiones), no un bloque fijo: las páginas ya tienen tres columnas. No ocupa sitio si no hay diff.
  - Se añadió `runs.snapshot_skipped` para avisar de los ficheros nuevos de más de 5 MB que se dejaron fuera.
  - Una tarea en carpeta directa cuya primera ejecución ya no tiene instantáneas (anterior a la fase o purgada) no ofrece diff de la tarea, para que uno parcial no pase por el total.
  - La instantánea cubre la carpeta de la ejecución: en un proyecto que es una subcarpeta de un repositorio, lo que cambie fuera no aparece.
- **Impacto en fases futuras**:
  - **Fase 12 (Control de git)**: reutiliza `services/git.py` (nuevos `env`, `input` y `merge_base`) y el panel de diff. Las referencias `refs/agentic-os/` salen en `git log --all`; conviene filtrarlas en su historial.
  - **Fase 13 (Pipelines con ramas)**: el diff por ejecución y por tarea puede alimentar la decisión del LLM sobre qué rama tomar.
  - Comentar líneas del diff y pasárselas al agente como motivo de rechazo queda anotado para una fase futura.
- **Deuda de pruebas**: `test_maintenance.setup_branches` tenía una carrera latente (sus tareas con agente se lanzaban solas); ahora pausa el scheduler. Los tests del frontend que renderizan la app entera agotan 15 s con la suite completa en esta máquina (también en `main`).

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v1.3`
- [ ] `docs/roadmap.md` actualizado
