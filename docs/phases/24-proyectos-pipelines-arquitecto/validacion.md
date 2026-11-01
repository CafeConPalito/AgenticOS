# Fase 24: Proyectos, pipelines y Arquitecto · Validación

> **Estado (2026-11-01)**: cerrada (`v0.9.4`). El usuario dio el OK tras las suites en verde.

## Tests automáticos
```
Frontend (npm run test:frontend): 85 ficheros, 839 tests en verde; tras el code-review, los del
         editor del pipeline (33) otra vez en verde. Tipos (tsc) y lint en verde.
Backend  (uv run pytest, backend/.test-progress.log): el sistema paró la suite completa por falta
         de memoria en el test 1118 de 1728 (~62 %, en test_main.py), como ya pasó en la fase 23.
         Hasta ahí, dos fallos, ya corregidos (7f0eb61): test_agent_io y test_agents_api esperaban
         las 5 plantillas fijas de antes, y ahora son 11.
         De test_main.py al final (611 tests), por tandas de serie: 38, 20, 11 y 11 ficheros,
         todas en verde. La primera se colgó en test_main.py: el log de arranque, con las
         migraciones 0024 y 0025, ya pasa de los 4 KB de una tubería de Windows. El test no la
         leía y el watchdog esperaba el lock del log antes de su salida forzada; corregidos los
         dos (b1b599f). Probablemente es también lo que cortó la suite completa al ~62 %.
         Pasados aparte, en verde, los ficheros nuevos y los que toca la fase:
         test_project_avatar, test_pipeline_exits_graph, test_pipeline_exits, test_migration_0025,
         test_sdd, test_apply_development, test_architect_design_e2e, test_e2e_development,
         test_architect_sheet, test_pipelines, test_pipelines_graph_api, test_decider,
         test_lanes, test_lanes_api, más la tanda de Arquitecto, migraciones, pipelines, ramas,
         decisor, tareas, revisiones, Inbox y scheduler (bloques 2 y 3).
e2e      test_e2e_development (CLI falso en ConPTY): un proyecto nuevo con «Desarrollo» crea sus
         8 agentes; una tarea de desarrollo pasa por requisitos, validación, arquitectura, la
         rama Backend, QA e IT con las tres revisiones, y una de «solo requisitos» termina tras
         la validación (1 min 36 s).
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Foto propia del proyecto, sin búhos, en todas sus pantallas; se cambia y se quita | ✅ | `test_project_avatar.py`, `project-avatar.test.tsx` |
| CA2 | Varios finales: el decisor termina la tarea o la deja seguir; se guarda dónde y por qué; «Terminar aquí» y «Seguir» a mano; reglas del editor; pipelines sin salidas igual | ✅ | `test_pipeline_exits_graph.py`, `test_pipeline_exits.py`, `validate.test.ts`, `pipeline-exits.test.tsx`; spike S1 (12/12) |
| CA3 | Nuevo proyecto y pestaña Pipeline vacía con «Desarrollo», copiar, en blanco y el Arquitecto; las plantillas antiguas fuera | ✅ | `new-project.test.tsx`, `pipeline-editor.test.tsx`, `test_pipelines.py` |
| CA4 | «Desarrollo» con sus etapas, ramas, salidas, revisiones y rechazos | ✅ | `test_pipelines_graph_api.py`, `test_e2e_development.py` |
| CA5 | Decisión sobre SDD: con SDD en un proyecto que ya lo usa o en un trabajo grande, sin él en un cambio pequeño; en la tarea y en cada etapa; la persona lo cambia | ✅ automático · ⏳ prueba con `claude` real | `test_sdd.py`, `task-work-mode.test.tsx`; spike S2 (10/10) |
| CA6 | Ocho plantillas; al aplicar, los agentes que faltan se crean en un paso, en un equipo | ✅ | `test_apply_development.py`, `pipeline-editor.test.tsx` |
| CA7 | Un proyecto nuevo con «Desarrollo» completa una tarea de desarrollo y otra que termina tras la validación | ✅ e2e · ⏳ prueba con `claude` real | `test_e2e_development.py` |
| CA8 | Copiar el pipeline de otro proyecto con sus agentes y ajustes por etapa, con aviso por agentes archivados | ✅ | `test_apply_development.py`, `copy-pipeline.test.tsx` |
| CA9 | El Arquitecto diseña el pipeline de un proyecto vacío y un equipo sin pipeline | ✅ | `test_architect_design_e2e.py`, `architect-team.test.tsx` |
| CA10 | Suites completas, lint y `/code-review` | ✅ | arriba (backend por tandas) y en la tabla siguiente |

## Code review
`/code-review` sobre la rama frente a `main` (2026-11-01): 8 hallazgos; 7 corregidos (`35f8ace`) y 1 justificado.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| «Seguir con el pipeline» reabre una tarea ya entregada: la Inbox seguía avisando de la entrega | alta | Se retira el aviso. El worktree, si se liberó, lo vuelve a crear la siguiente ejecución; lo integrado se queda y lo nuevo se integra al terminar otra vez; test |
| Pasar a SDD a mano dejaba la spec «en `None`», sin comprobación y sin la pista del formato | alta | La toma de requisitos recibe que falta la carpeta (con la pista del formato) y no puede terminar sin marcarla; test |
| Cualquier etapa podía cambiar el modo de trabajo | media | Solo la primera etapa (o el agente de una tarea sin pipeline); test |
| Una etapa con salida siempre pregunta, aunque su camino no necesite decisión | media | Justificado: la salida es la pregunta. Sin decisor, decide la persona, como en una bifurcación con condiciones. Las ramas fijadas al crear la tarea se respetan cuando sigue |
| Un agente de otro *workspace* se podía asignar al aplicar «Desarrollo» | baja | Se comprueba el *workspace*; test |
| N+1 al leer el modo de las ramas en la lista de tareas | baja | Se busca en el mismo lote |
| Una salida vacía del Arquitecto bloqueaba la propuesta | baja | Vacía es «sin salida»; test |
| El editor y el servidor discrepaban con una salida fuera de los caminos analizados | baja | El editor la marca igual que el servidor |

## Retro
- **Cambios respecto a la spec y el plan**:
  - Las salidas se deciden con el decisor de ramas, solo en las etapas que las tienen. Terminar en una etapa sin revisión propia pasa por la revisión final (decidido con el usuario al aprobar el plan).
  - SDD: un cambio trivial va sin SDD aunque el proyecto lo use (confirmado tras el spike S2).
  - La migración se partió en dos: la `0024` para la foto y la `0025` para salidas, modo de trabajo y tipos de evento.
  - En Nuevo proyecto, la elección del pipeline se abre en la pestaña Pipeline del proyecto recién creado, con su diálogo ya abierto.
  - Una tarea sin pipeline también comprueba la carpeta de su spec, porque su único agente es quien toma los requisitos.
- **Lo aprendido**:
  - El decisor barato (haiku) acierta a la vez la salida y las ramas con un prompt en dos pasos, a 0,001 $ por llamada.
  - Las salidas encajan como atributo de la etapa porque el grafo ya sabe si una etapa está dentro de una bifurcación.
  - La suite completa del backend vuelve a no caber en memoria de una vez: hay que pasarla por partes de serie.
  - Un subproceso con `stderr=PIPE` que nadie lee se bloquea en cuanto su log pasa de 4 KB: el cuelgue de `test_main.py` no avisaba y parecía falta de memoria.
- **Impacto en fases futuras**:
  - Anotado para el futuro: salidas que terminen solo una rama, tareas que empiecen en una etapa intermedia y cambiar el modo SDD después de bifurcar.
  - Fase 25 (GitHub): el README puede explicar «Desarrollo», las salidas y SDD.

## Cierre
- [x] OK del usuario (2026-11-01)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v0.9.4`
- [x] Versión de la app a `0.9.4` (`package.json`, `tauri.conf.json`, `Cargo.toml`, `pyproject.toml`, `__init__.py`)
- [x] `docs/roadmap.md` actualizado
