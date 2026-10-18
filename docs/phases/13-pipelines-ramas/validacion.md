# Fase 13: Pipelines con ramas · Validación

> Estado: **cerrada** (`v1.5`, OK del usuario el 2026-10-18). Tres comprobaciones con servicios o pantallas reales quedan anotadas (ver «Pendiente»).

## Tests automáticos
```
backend (pytest):   90 archivos · 792 tests (787 antes de la revisión de código), todos en verde en la última suite completa, lanzada sola
                    nuevos de la fase:
                    test_pipeline_graph (15) · test_pipelines_graph_api (8) · test_migration_0015 (2) ·
                    test_lanes (18) · test_lanes_api (7) · test_decider (19) ·
                    test_lanes_git (11, repositorios git reales) ·
                    test_e2e_branching (2, backend real + CLI falso en ConPTY + decisor simulado) ·
                    test_worktrees (+1, 12 en total)
frontend (vitest):  42 archivos · 366 tests en verde
                    nuevos: validate (11) · pipeline-editor (9) · task-path (6) · task-lanes (8) ·
                    tareas (+3 del tablero y del diálogo de nueva tarea)
lint:               npm run lint (ruff, eslint, prettier, tsc, cargo fmt, spikes) en verde
spikes:             S1 (Claude Code `-p`) · S2 (agy `-p`) · S3 (ramas de las vías en git), en `evidencias/`
```
Los tests de git usan **repositorios reales** en carpetas temporales. El e2e arranca el backend de verdad con su scheduler y el CLI falso en una ConPTY real; solo el decisor es un ejecutor simulado que contesta como lo haría el modelo (la llamada real se probó aparte, M1).

**Tests intermitentes vistos durante la fase** (pasan en solitario; fallan solo cuando se lanzan dos suites a la vez y la máquina va cargada): `test_runs_review::test_each_memory_write_is_its_own_note` (ya anotado en la fase 04), `test_resume_e2e[agy]`, `switching.test` y `agent-links.test` (esperas de 15 s). La suite final se ha lanzado **sola**.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Con la plantilla «Backend y frontend», una tarea de API va solo a Dev backend, una de UI a Dev frontend y una que toca ambas pasa por las dos y llega a QA cuando terminan, sin elegir la rama a mano | ✅ | `test_e2e_branching::test_each_task_goes_only_to_the_branches_that_fit` (backend real, CLI falso, tres tareas; ramas, etapas, eventos y consumo); `test_lanes` (ramas «siempre», elegidas, en paralelo y en serie); decisor real con los dos CLIs: [`m1-decisor-real.md`](evidencias/m1-decisor-real.md) (6 de 6) |
| CA2 | La decisión queda en el historial con ramas tomadas y descartadas, motivo, modelo y coste; el consumo del decisor aparece en el panel | ✅ | `test_decider` (la llamada se guarda como `Run` de tipo `decision` con tokens y coste; cuenta en el consumo de la tarea), `test_e2e_branching` («Decisor» en el desglose de consumo por agente y fuera de las sesiones), `task-lanes.test` (decisión con sus motivos en el detalle) |
| CA3 | Si el decisor falla o no elige ninguna rama, la tarea espera con «Hay que elegir la rama» y la elección del usuario la desbloquea; con «Confirmar la decisión» espera en revisión y se puede cambiar | ✅ | `test_decider` (fallo tras un reintento, cuenta sin sesión, sin decisor, propuesta aceptada, rechazada y cambiada), `test_lanes_api` (`/decision`), `task-lanes.test` (elegir y confirmar) |
| CA4 | Ramas fijadas al crear la tarea, añadir una rama en curso y cancelar una en marcha; la unión espera exactamente a las tomadas que siguen vivas | ✅ | `test_lanes` (`preset_lanes`, `add_lane`, `cancel_lane`, todas canceladas), `test_lanes_api`, `new-task.test` (ramas a mano), `task-lanes.test` (añadir y cancelar) |
| CA5 | En worktree, cada rama paralela trabaja en su carpeta y su rama; en la unión se integran en `agentic/T-n` de cada repo; con conflictos la tarea espera y se resuelven con el editor o un agente | ✅ | `test_lanes_git` (carpeta y rama por vía desde la de la tarea, lo suelto se commitea, un *merge* por vía, ramas conservadas, conflicto → `join_conflict`, resolver en una carpeta de trabajo, resolver con un agente, reabrir una vía, cancelar una vía, el diff de la tarea incluye lo de sus vías). **«Resolver aquí» muestra la carpeta y los ficheros, como en la fase 12, y no usa el `ConflictEditor` de la app** (ver «Cambios respecto a la spec») |
| CA6 | En carpeta directa las ramas van una detrás de otra y nunca hay dos ejecuciones del proyecto a la vez | ✅ | `test_lanes::test_branches_marked_always…` (serie y orden), `test_e2e_branching` (proyecto en carpeta directa), aviso en el editor (`pipeline-editor.test`) |
| CA7 | Un rechazo de QA a Dev backend repite solo esa rama y vuelve a QA; al superar el máximo la tarea espera | ✅ | `test_lanes` (rechazo a la rama con `reject_to`, al destino por defecto, máximo de rechazos en la tarea raíz y reintento), `test_e2e_branching::test_qa_sends_the_task_back_only_to_the_branch_that_failed` |
| CA8 | El editor crea, conecta y valida el grafo, impide guardar con errores, no deja quitar una etapa o conexión con ramas activas, y «Probar» muestra la decisión sin crear tarea | ✅ | `test_pipeline_graph` + `validate.test` (las mismas reglas en Python y en TypeScript), `test_pipelines_graph_api` (422 con la lista de problemas, `validate`, `link_in_use`, plantilla), `pipeline-editor.test` (conectar desde el panel, condiciones, problemas en vivo, «Siempre», guardar bloqueado, etapa con tareas, «Probar» por bifurcación), `test_lanes_api` (`decide-preview` sin crear tarea) |
| CA9 | Los pipelines y tareas existentes siguen funcionando igual tras la migración | ✅ | `test_migration_0015` (cadena de enlaces, subida y bajada, no baja con una bifurcación), los tests de la fase 05 (`test_scheduler`, `test_scheduler_e2e`, `test_pipelines`) siguen en verde sin cambios de comportamiento |
| CA10 | El detalle muestra el grafo con su camino y el estado de cada rama; el tablero muestra la tarea en cada columna de sus ramas | 🟡 | Automatizado ✅: `task-path.test`, `task-lanes.test`, `tasks.test` («Por estado» una vez con su estado derivado, «Por etapa» y colas con las ramas). **Capturas y comprobación visual en un navegador real: pendiente** (los tests usan jsdom) |
| CA11 | Lint, tests de backend y de frontend en verde; ADR escrito; `/code-review` resuelto | ✅ | arriba; [ADR 0020](../../adr/0020-branching-pipelines.md); revisión abajo |

## Pendiente
1. **Una tarea con agentes reales de principio a fin** en la plantilla «Backend y frontend» y en modo worktree (Claude Code y agy como agentes de las ramas): comprobar que cada agente trabaja en su carpeta, que la unión mezcla sus ramas y que QA rechaza a una rama con `reject_to`. Los tests lo cubren con el CLI falso y el decisor se probó con los CLIs reales (M1), pero no una sesión completa con coste.
2. **Mirar el editor y el detalle de la tarea en la app**: la disposición del lienzo, los nodos y los paneles, los textos y el tema oscuro, y el uso con teclado (Tab entre nodos, Supr). En los tests solo se ejercita la lista de etapas y los paneles.
3. **Ramas anidadas con agentes reales**: el motor y el grafo las admiten (tests unitarios), pero no hay un e2e con una bifurcación dentro de una rama.

## Code review
Diez hallazgos; los diez corregidos.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Al bifurcar tras elegir (o reabrir una rama) la tarea conservaba su motivo de espera (`choose_branch`, `max_rejections`) y su petición en la Inbox: el formulario de elegir ramas reaparecía y daba 409 | alta | corregido: `_forked_at` limpia el motivo y cierra las peticiones de atención; test |
| La página mostraba «Aprobar/Reintentar/Terminar» en la tarea que bifurcó con el estado prestado de su rama; el servidor las rechaza con 409 | media | corregido: sus acciones se hacen sobre las ramas; test |
| Una unión resuelta después (editor o agente) podía terminar la tarea sin liberar su carpeta ni integrarla en la base | alta | corregido: `retry` y el editor liberan al terminar, y el scheduler barre cada minuto las tareas terminadas que aún tienen carpeta (`release_orphans`); test |
| Cerrar la carpeta de la madre para el editor de la unión borraba su rama y su fila en un repo donde solo había trabajado una rama: la unión se saltaba ese repo y el trabajo se perdía | alta | corregido: una tarea con ramas no borra sus ramas vacías al soltar sus carpetas; test |
| Cancelar una rama y la unión hacían los *merge* de git con la transacción abierta (bloqueo de escritura de SQLite durante segundos) | media | corregido: se confirma el estado antes de mezclar |
| La decisión se pedía dos veces si el trabajador acababa justo entre dos pasos del scheduler (dos llamadas de pago) | media | corregido: la llamada sigue «en curso» hasta que el scheduler aplica la respuesta; test |
| Se podían crear varias tareas de resolución para la misma unión, peleando por la misma rama | media | corregido: 409 `resolution_exists` si ya hay una abierta; test |
| `next_stage` quedó sin llamadas tras el motor de ramas | baja | corregido: eliminada |
| «Probar» solo servía para la primera bifurcación | baja | corregido: un botón por bifurcación; test |
| La validación del editor no se memorizaba y se recalculaba al arrastrar un nodo | baja | corregido: depende del borrador |

**Defecto previo de la fase 12 que ha salido al probar las ramas**: la tarea de resolución de conflictos de la integración se creaba por la primera etapa del pipeline e ignoraba el agente elegido en proyectos con pipeline. Ahora es una tarea suelta (`create_task(standalone=True)`), también en la fase 12.

## Retro
- **Cambios respecto a la spec**:
  - **Varios destinos de rechazo por etapa** (`reject_to` + `reject_also`) y un parámetro `reject_to` en `complete_task`: sin ellos QA no podía devolver la tarea a Dev backend *o* a Dev frontend, que es lo que pide la historia de usuario. Fue un hueco de la spec, resuelto al planificar.
  - **Dentro de una rama solo se rechaza a etapas de esa rama** (acordado al aprobar el plan); tras la unión, a cualquier rama o a antes de la bifurcación.
  - **Una rama no puede ser vacía** (un enlace directo a la unión): el motor trata cada rama como una tarea con al menos una etapa.
  - **Resolver conflictos de la unión «en el editor»** abre una carpeta de trabajo con los conflictos y se marca resuelto, igual que la integración de la fase 12. La spec decía «el editor de tres vías»; ese editor trabaja sobre los repos del proyecto y aquí la carpeta es temporal. Queda como mejora conjunta con la fase 12.
  - **Peticiones**: «Hay que elegir la rama» usa el tipo «necesita atención» y «Confirmar la decisión» el de revisión, ya existentes; no se han añadido tipos nuevos a la Inbox.
  - **El decisor se pide desde el scheduler** y no con un gancho global (el plan lo describía así al principio): cubre solo los reinicios y los reintentos.
  - **Filtrar los diffs y las ejecuciones por rama** dentro de la tarea madre no se ha hecho: cada rama es una tarea con su página, sus ejecuciones y su diff, y el de la madre incluye lo unido.
  - El límite de etapas sube a 30.
- **Impacto en fases futuras**:
  - Una tarea que bifurca son varias filas `Task`: todo código nuevo que cuente o liste tareas debe decidir si quiere las ramas (el listado general las oculta; el de un agente, las colas y «Por etapa» las incluyen).
  - La fase 14 (Conocimiento) y la 16 (Skills) cargan contexto por ejecución: las ramas heredan el de su tarea sin cambios.
  - La fase 15 (Dictado por voz) puede usar el mismo patrón de llamada breve a un CLI sin herramientas que el decisor, pero ahí hace falta Whisper local, no un CLI.
  - Si se quiere que decida un agente con herramientas (que lea el código para elegir), el punto de extensión es `DecisionService.request`.
  - Etapas que solo deciden (sin agente) y bifurcar al principio del pipeline quedan para una fase futura.

## Cierre
- [x] OK del usuario
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v1.5`
- [x] `docs/roadmap.md` actualizado
