# Fase 24: Proyectos, pipelines y Arquitecto · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-11-01), con revisión final al terminar en una salida sin revisión propia, sonnet para IT / despliegue y cambio de modo SDD solo antes de bifurcar

## Lo que ya se sabe (revisado al escribir el plan)
- **Avatares** (`services/avatars.py`, fase 20):
  - El valor es `owl:<id>` o `photo:<digest>`. La foto se guarda en `<datos>/avatars/<digest>.webp` y `check()` valida el valor.
  - `remove_unused()` borra las fotos que no usa ningún agente ni ninguna plantilla.
  - En la interfaz, `AvatarDialog.tsx` tiene la galería y el recorte.
  - `ProjectChip` (`components/agentic/primitives.tsx`) pinta el proyecto con su color en siete pantallas.
- **Forma del pipeline** (`services/pipeline_graph.py`, repetido en `frontend/.../pipeline/validate.ts`):
  - `Graph._walk` asigna a cada etapa su **camino** (`_paths`): la tupla de bifurcaciones y ramas en las que está metida. Una etapa fuera de toda bifurcación abierta tiene el camino `()`.
  - Una etapa sin salida es un final.
- **Motor** (`services/lanes.py`):
  - `advance()` pasa a la siguiente etapa, abre una bifurcación (`start_fork`) o termina (`_end`). `tasks.stage_completed()` pone antes la revisión humana si la etapa la pide.
  - Una tarea que bifurca queda en `deciding`. El scheduler (`_decide_pending`) pide la decisión a `DecisionService`, que llama al CLI fuera del hilo del scheduler y aplica la respuesta con `lanes.take` (o `lanes.propose` si la etapa pide confirmar la decisión).
  - Si falla, la tarea espera con `CHOOSE_BRANCH` y la persona elige en `DecisionBlock.tsx`. La decisión queda en `BranchDecision` (`chosen` son ids de enlaces) y se ve en la tarea.
- **Decisor** (`services/decider.py`): `build_prompt` pide JSON `{"branches": [{"id", "take", "reason"}]}`, con un modelo barato. Cada llamada es una ejecución `decision` y cuenta en el consumo.
- **Plantillas de pipeline** (`services/pipelines.py`):
  - `PipelineTemplate.WEB` y `WEB_SPLIT`. `from_template()` asigna a cada etapa el primer agente activo creado desde la plantilla de agente que indica.
  - Lo usan `NewProjectDialog.tsx` y `PipelineTab.tsx`.
- **Plantillas de agentes** (`services/templates.py`): cinco fijas, todas con `cli=claude`, más las del usuario en `AgentTemplateRow` (fase 19).
- **Contexto de cada etapa** (`tasks.task_context` → `TaskContext`): título, descripción, historial de las etapas anteriores, motivo de un rechazo y rama. Llega al agente con `get_context` del MCP `agentic-os` (`services/mcp_server.py`).
- **Arquitecto** (`services/architect/`):
  - El modo `team` ya admite una propuesta **sin pipeline**: `sheet.ready` solo valida el pipeline si existe, y el servicio pide «agentes o pipeline».
  - `ConversationCreate` ya lleva `project_id`, pero el modo `team` lo ignora.
  - El único acceso al modo `team` es `ArchitectPage.tsx`.
- **Última migración**: `0023`. **Último ADR**: `0029`.

## Bloque 0 · Spikes (antes de programar)
| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Decisor con salida**: con el modelo barato del decisor y 12 tareas de ejemplo en la etapa de validación de requisitos y en la de arquitectura. Seis tareas acaban ahí («solo los requisitos de…», «revisa la arquitectura de…») y seis siguen (funcionalidades). ¿Acierta en ≥ 11 de 12? ¿Cuánto cuesta cada llamada? Con la arquitectura, ¿decide bien la salida **y** las ramas a la vez? | Prompt en dos pasos (primero la salida, luego las ramas) o modelo medio solo para las etapas con salida. |
| S2 | **Pautas de SDD**: las instrucciones del Analista de requisitos con 10 peticiones en 3 repositorios de prueba: uno con `.specify/`, uno con specs por fase como este y uno sin nada. Hay 4 peticiones pequeñas y 6 grandes o en proyecto con SDD. ¿Elige bien en ≥ 9 de 10? ¿Sigue el formato que ya tiene el repositorio? | Ajustar las pautas con ejemplos y repetir. Si sigue fallando en los casos frontera, inclinarse por SDD (la revisión humana lo corrige). |
| S3 | **Formatos de SDD que se detectan**: confirmar las carpetas y los ficheros de spec-kit (`.specify/`, `specs/NNN-*/spec.md`), Kiro (`.kiro/specs/*/requirements.md`, `design.md`, `tasks.md`) y OpenSpec (`openspec/`) en su documentación actual. | Detectar solo lo confirmado. Lo demás lo encuentra el agente leyendo el repositorio. |

## Resultados de los spikes (bloque 0, 2026-11-01)
- **S1 · decisor con salida** (`spikes/pipelines/s24_exit_decider.py`, `claude -p` con haiku, el modelo del decisor): ✅ **12 de 12**, a 0,001 $ por llamada y ~5 s.
  - Acierta en las seis tareas de la validación de requisitos (tres terminan ahí y tres siguen).
  - Acierta en las seis de la arquitectura: dos terminan, y en las cuatro que siguen elige exactamente las ramas esperadas (solo Frontend; Frontend y Backend; solo Datos; solo Backend).
  - → **Diseño**: un solo prompt con dos pasos (primero «¿termina aquí?», luego las ramas si sigue) y el esquema `{"exit": {"take", "reason"}, "branches": [...]}`. El prompt dice que la tarea no termina si pide además cualquier trabajo posterior.
- **S2 · pautas de SDD** (`spikes/pipelines/s24_sdd_decision.py`, `claude -p` con sonnet y herramientas de solo lectura en tres repositorios de prueba): ✅ **10 de 10**, a 0,02 $ de media.
  - En el proyecto con spec-kit, la carpeta siguiente es `specs/002-…`; en el de specs por fase, `docs/phases/03-…`; en el que no tiene nada, `specs/001-…`.
  - → **Pautas, en este orden** (concretan la spec, a confirmar con el usuario):
    1. Un cambio **trivial** (errata, renombrar, un ajuste de una línea) va **sin SDD aunque el proyecto lo use**.
    2. Si el proyecto ya usa SDD, va con SDD en su formato.
    3. Un trabajo grande (varias capas, un módulo nuevo, integraciones, decisiones de diseño) va con SDD en el formato de la app.
    4. Lo demás (un cambio acotado de una sola pieza en un proyecto sin SDD) va sin SDD.

    Van tal cual en las instrucciones del Analista de requisitos. **Confirmado con el usuario (2026-11-01).**
- **S3 · formatos de SDD**:
  - **spec-kit**: la marca es `.specify/` (sus comandos fallan sin ella: «not a Spec Kit project: no .specify/ directory found»). Dentro están `memory/constitution.md`, `templates/` y `extensions.yml`, y las specs van en `specs/NNN-nombre/` con `spec.md`, `plan.md` y `tasks.md` ([artefactos](https://github.github.io/spec-kit/reference/artifacts.html), [repositorio](https://github.com/github/spec-kit)).
  - **Kiro**: `.kiro/specs/<nombre>/` con `requirements.md` (o `bugfix.md`), `design.md` y `tasks.md` ([docs](https://kiro.dev/docs/specs/)). La carpeta solo la confirman guías de terceros, pero coinciden todas.
  - **OpenSpec**: `openspec/specs/` (las specs vivas) y `openspec/changes/<id>/` con `proposal.md`, `specs/`, `design.md` y `tasks.md`; lo terminado va a `changes/archive/` ([repositorio](https://github.com/Fission-AI/OpenSpec)).
  - **Specs por fase** (como este repositorio): `docs/phases/NN-nombre/spec.md`.
  - **Genérico**: `specs/*/spec.md`.
  - → `sdd.detect()` mira esas marcas en ese orden. El agente lee el resto del repositorio para seguir el formato al detalle.

## Diseño
### 1. Foto del proyecto
- **Migración `0024`**: `projects.avatar String(80) NULL` (las salidas y el modo SDD van en la `0025`, con su bloque).
- `avatars.check(..., owls=False)` solo acepta `photo:<digest>` para proyectos. `ProjectWrite`/`ProjectRead` ganan `avatar`, y la foto sube con el mismo `POST /avatars/crop` de la fase 20.
- `remove_unused()` cuenta también `Project.avatar`.
- **Interfaz**:
  - `AvatarDialog` gana el modo `photoOnly` (sin la pestaña de búhos).
  - `ProjectMark` (foto, inicial sobre el color desde 24 px o el cuadrado de color en pequeño) se usa en `ProjectChip`, la lista y la cabecera del proyecto, el Tablero, Inicio, las tareas y el selector de proyecto.
  - En Nuevo proyecto y en la ficha del proyecto: «Poner foto», «Cambiar» y «Quitar».

### 2. Varios finales (ADR 0030, amplía el 0020)
- **Modelo** (migración `0024`): `stages.exit_condition Text NULL` (sin condición, la etapa no tiene salida) y `stages.exit_x` / `exit_y` (sitio del nodo Fin en el lienzo). En la tarea, `tasks.exit_stage_id` (dónde terminó, para el Tablero).
- **Grafo** (Python y `validate.ts`, con los mismos tests):
  - `Graph` recibe las etapas con salida.
  - Errores nuevos:
    - `exit_no_condition`: condición vacía;
    - `exit_on_final`: la etapa ya es un final;
    - `exit_in_branch`: el camino de la etapa no es `()`, es decir, está dentro de una bifurcación abierta.
  - Una unión está fuera de las bifurcaciones, así que puede tener salida: es el caso de QA.
- **Motor**:
  - `lanes.advance()`: si la etapa tiene salida, la tarea pasa a `deciding`, igual que en una bifurcación, aunque la etapa no bifurque.
  - `start_fork` pasa a llamarse `start_decision`.
  - Si no queda nada que preguntar (no hay salida y todas las ramas son «siempre»), sigue como ahora.
- **Decisor**:
  - `DecisionRequest.exit: BranchView | None`.
  - Con salida, el prompt pregunta primero si la tarea **termina aquí** según la condición, y después, solo si sigue, por qué ramas va. Responde con `{"exit": {"take", "reason"}, "branches": [...]}`; en una etapa sin bifurcación, `branches` va vacío.
  - `DecisionResult.exit_taken`. La salida es excluyente: si `exit.take`, se ignoran las ramas.
  - La versión exacta del prompt sale de S1.
- **Aplicar**:
  - La decisión queda en `BranchDecision` con el id reservado `"exit"` en `chosen`, junto a su motivo.
  - Si termina, `lanes.finish_at_exit()`:
    - guarda un evento `EXITED` con la etapa, la condición y la explicación del decisor;
    - rellena `exit_stage_id`;
    - termina la tarea con el mismo `finish(DONE)` de un final normal, que integra las ramas según el proyecto (fase 12).
  - Si sigue, pasa a la siguiente etapa o abre las ramas.
  - `confirm_decision` sirve igual para la salida (la propuesta espera a que la persona la confirme).
- **Revisión al terminar en una salida** (concreta la spec): si la etapa de la salida **no** tiene revisión humana pero la última etapa del pipeline sí, la tarea pasa a revisión («Revisión final») antes de quedar hecha. Así una tarea que termina en QA no se salta la revisión del final. Si la etapa ya tiene revisión, no se repite.
- **A mano**:
  - `DecisionBlock` ofrece «Terminar aquí» además de las ramas, cuando el decisor falla o pide confirmación.
  - Una tarea terminada en una salida tiene «Seguir con el pipeline»: vuelve a `todo` en la etapa siguiente o abre las ramas como si el decisor hubiera dicho «sigue», con un evento que lo explica.
  - Si sus ramas ya se integraron, el trabajo sigue desde la rama base, con un espacio de trabajo nuevo.
- **Editor**:
  - Nodo **Fin** unido a la etapa con una flecha discontinua. Se añade con «Añadir salida» en el panel de la etapa, donde también se escribe la condición, y se quita con «Quitar salida».
  - `TryDecisionDialog` prueba también la salida.
  - Los errores nuevos se ven como los demás, en la etapa.
- **Tablero y tarea**:
  - La tarjeta de una tarea terminada en una salida dice «Terminó en <etapa>».
  - La tarea muestra dónde terminó y por qué, en su historial y en el bloque de decisiones.

### 3. Decisión sobre SDD
- **Modelo** (migración `0025`): `tasks.work_mode String(8) NULL` (`sdd` | `direct`), `tasks.work_mode_reason Text` y `tasks.spec_path Text NULL`. Las ramas paralelas leen los de la tarea raíz.
- **Detección** (`services/sdd.py`, formatos según S3): `detect(project_path) → SddFormat | None` (nombre, carpeta y ficheros de cada spec). El contexto de la **primera etapa** lo incluye: «El proyecto usa spec-kit en `.specify/`» o «El proyecto no usa SDD».
- **MCP**: herramienta nueva `set_work_mode(mode, reason, spec_path="")` en `agentic-os`.
  - Guarda la decisión con un evento `WORK_MODE`.
  - La puede llamar cualquier agente de una tarea, pero las instrucciones solo se la dan a la toma de requisitos.
  - Con `sdd` hace falta `spec_path`, una carpeta del proyecto. Se comprueba que exista al cerrar la etapa: si no, `complete_task` lo rechaza y lo explica.
- **Contexto**: `TaskContext.work_mode`, `work_mode_reason` y `spec_path`. `get_context` lo explica a cada etapa con un párrafo según el modo:
  - con SDD: dónde está la spec, el plan y las tareas, qué le toca a la etapa y que marque `tasks.md`;
  - sin SDD: que trabaje con los requisitos de la tarea, sin crear documentos de spec.
- **Formato propio de la app** (cuando el proyecto no tiene ninguno): `specs/NNN-nombre/` con `spec.md`, `plan.md` y `tasks.md`. Las plantillas de los tres ficheros van en las instrucciones del Analista, el Arquitecto de software y los desarrolladores.
- **Cambio a mano**: `PATCH /tasks/{id}/work-mode {mode}`.
  - Guarda el modo, anota un evento y devuelve la tarea a la primera etapa (`move_to_stage`), con el motivo «Modo de trabajo cambiado a …».
  - Solo se permite mientras la tarea no ha bifurcado (si no, `409 work_mode_forked`). En la interfaz se explica por qué está desactivado.
  - En la revisión de la validación de requisitos, el diálogo de revisión ofrece «Cambiar a SDD» o «Sin SDD», que hace lo mismo.
- **Interfaz**: chip «SDD» o «Directo» en la tarjeta del Tablero, y sección en la tarea con el motivo, el enlace a la carpeta de la spec y el botón de cambiar.

### 4. Plantilla «Desarrollo»
- `PipelineTemplate.DEVELOPMENT` sustituye a `WEB` y `WEB_SPLIT` (la API ya no acepta las antiguas; los pipelines guardados no se tocan).
- Etapas: `_development()` en `services/pipelines.py`:

  | # | Etapa | Plantilla de agente | Revisión | Rechaza a | Salida |
  |---|---|---|---|---|---|
  | 0 | Toma de requisitos | `analyst` | — | — | — |
  | 1 | Validación de requisitos | `requirements_validator` | sí | 0 | «La tarea solo pide definir o revisar requisitos» |
  | 2 | Arquitectura | `software_architect` | sí | 0 | «La tarea solo pide definir o revisar la arquitectura» |
  | 3 | Frontend | `frontend_developer` | — | — | — |
  | 4 | Backend | `backend_developer` | — | — | — |
  | 5 | Datos | `data_scientist` | — | — | — |
  | 6 | QA | `qa` | — | 3 (y 4, 5) | «La tarea no necesita despliegue» |
  | 7 | IT / despliegue | `devops` | sí | 6 | — |

  - Enlaces: 0→1→2. La bifurcación 2→3, 2→4 y 2→5 tiene las condiciones «La tarea toca la interfaz…», «… la API, la base de datos o el backend…» y «… análisis de datos, modelos o informes…». Después, 3, 4 y 5 →6, y 6→7.
  - La etapa 2 tiene salida **y** bifurca: la salida es excluyente.
- **Aplicar con los agentes que faltan**:
  - `GET /pipeline-templates/development/plan` devuelve, por etapa, el agente activo que ya existe desde su plantilla o «se creará».
  - `POST /projects/{id}/pipeline/from-template` recibe:

    ```json
    {"template": "development",
     "assign": {"<índice de etapa>": "<agent_id>"},
     "create": {"cli": "…", "account_id": "…", "model": null,
                "team": {"team_id": "…"} | {"name": "Desarrollo"}}}
    ```

  - Las etapas sin agente en `assign` reciben un agente nuevo, activo y creado desde su plantilla en el equipo indicado. Si el CLI elegido no es el de la plantilla, el modelo es el que se haya pedido o el de por defecto del CLI.
  - Todo va en **una transacción**: si algo falla, no se crea ni el pipeline ni los agentes.
  - Si `create` falta y queda alguna etapa sin agente, el pipeline se crea con esas etapas vacías, como ahora.
- **Interfaz**: `ApplyDevelopmentDialog`, que usan Nuevo proyecto y la pestaña Pipeline vacía:
  - la lista de etapas con su agente («ya existe» o «se creará», con un selector para cambiarlo por uno existente);
  - el CLI, la cuenta y el modelo para los agentes nuevos;
  - el equipo.

### 5. Plantillas de agentes
`services/templates.py` queda con once plantillas fijas: las ocho de «Desarrollo» más `developer`, `writer` y `sales`.

| id | Nombre | Modelo | Permisos | Notas |
|---|---|---|---|---|
| `analyst` | Analista de requisitos | sonnet | Restringido | + decisión sobre SDD y `set_work_mode` |
| `requirements_validator` | Validador de requisitos | haiku | Restringido, solo lectura y MCP | comprueba completos, coherentes, que se puedan probar y que SDD encaje |
| `software_architect` | Arquitecto de software | opus | Restringido | stack y nube (Azure, AWS o Google Cloud) o local; `docs/arquitectura.md` + ADRs, o el `plan.md` de la spec con SDD; respeta la arquitectura existente |
| `frontend_developer` | Desarrollador frontend | sonnet | Autónomo | |
| `backend_developer` | Desarrollador backend | sonnet | Autónomo | |
| `data_scientist` | Data analyst / data scientist | sonnet | Autónomo | notebooks, consultas, modelos e informes |
| `qa` | QA | sonnet | Restringido | criterios de aceptación de la spec, rechaza a la rama que falló |
| `devops` | IT / DevOps | sonnet | Restringido, pide permiso para desplegar | despliega según la arquitectura; sin destino, deja los scripts y los pasos y no inventa destinos |

- **Modelos**: el Validador va con un modelo barato. El de IT va con uno medio, porque escribe scripts de despliegue: es una desviación de la spec, que lo ponía entre los baratos, a confirmar.
- **Nombres**: el agente de plantilla se llama siempre «Arquitecto de software», y el meta-agente sigue siendo «el Arquitecto» con su icono. Se revisan los textos de `es.json` donde podrían confundirse.

### 6. Copiar el pipeline de otro proyecto
- `POST /projects/{id}/pipeline/copy {from_project_id}`. Usa la misma serialización que el editor (`PipelineWrite`) e incluye:
  - las salidas;
  - el decisor;
  - `max_rejections`;
  - los ajustes de skills y conexiones por etapa (fases 17 y 18).
- Los agentes archivados o en borrador se quitan de su etapa, y la respuesta lleva `warnings: [{stage, agent}]`. No se copian tareas, eventos ni consumo.
- Interfaz: `CopyPipelineDialog`, con los proyectos que tienen pipeline y la vista previa del grafo en solo lectura.

### 7. El Arquitecto
- **Modo `team` con proyecto**: si llega `project_id`, la conversación nace con el proyecto elegido y el prompt dice «Diseñas el pipeline del proyecto **X**, que todavía no tiene» (o «que ya tiene», si lo tiene).
- **Accesos**:
  - «Diseñar con el Arquitecto» en `PipelineTab` vacío y en `ApplyDevelopmentDialog`, como alternativa.
  - En Nuevo proyecto, después de crearlo, abre la conversación.
  - «Nuevo equipo con el Arquitecto» en la lista de equipos de Agentes y de Inicio (modo `team` sin proyecto).
- **Prompt del modo `team`**: el pipeline pasa a ser opcional, solo si el usuario lo pide o hay un proyecto elegido. Conoce:
  - la plantilla «Desarrollo», con una herramienta de solo lectura nueva, `get_pipeline_templates`;
  - las plantillas de agentes nuevas, que ya consulta con las herramientas de la fase 19;
  - las salidas: `set_pipeline` acepta `exit_condition` por etapa, y la hoja las valida con las mismas reglas del grafo.
- La vista del grafo de la propuesta pinta los nodos Fin.

## Archivos
| Archivo | Cambio |
|---|---|
| `docs/adr/0030-pipeline-exits-sdd-mode.md` | nuevo: salidas en el pipeline (amplía el 0020) y modo de trabajo SDD por tarea |
| `backend/src/agentic_os/db/migrations/versions/0024_project_avatar.py` | nuevo: `projects.avatar` (bloque 1) |
| `backend/src/agentic_os/db/migrations/versions/0025_pipeline_exits_sdd.py` | nuevo: `stages.exit_*`, `tasks.exit_stage_id`, `tasks.work_mode*`, `tasks.spec_path` |
| `backend/src/agentic_os/models/{project,pipeline,task}.py` | campos nuevos; `TaskEventKind.EXITED` y `WORK_MODE` |
| `backend/src/agentic_os/services/avatars.py`, `api/projects.py`, `schemas/project.py` | foto del proyecto |
| `backend/src/agentic_os/services/pipeline_graph.py` | reglas de las salidas |
| `backend/src/agentic_os/services/lanes.py`, `services/tasks.py` | `start_decision`, `finish_at_exit`, revisión final, «Seguir con el pipeline», cambio de modo |
| `backend/src/agentic_os/services/decider.py`, `services/scheduler.py` | pregunta de salida, aplicar la salida |
| `backend/src/agentic_os/services/pipelines.py`, `schemas/pipeline.py`, `api/pipelines.py` | salidas al guardar, plantilla «Desarrollo», aplicar con agentes nuevos, copiar |
| `backend/src/agentic_os/services/templates.py` | plantillas de agentes nuevas y ajustadas |
| `backend/src/agentic_os/services/sdd.py` | nuevo: detección de formatos de SDD |
| `backend/src/agentic_os/services/mcp_server.py`, `services/context.py` | `set_work_mode`, modo de trabajo en el contexto |
| `backend/src/agentic_os/services/architect/{service,prompts,sheet,tools}.py` | `team` con proyecto, pipeline opcional, salidas, `get_pipeline_templates` |
| `frontend/src/components/agentic/{AvatarDialog,primitives}.tsx`, `ProjectAvatar.tsx` | foto del proyecto |
| `frontend/src/pages/projects/{NewProjectDialog,ProjectFormFields}.tsx`, `tabs/PipelineTab.tsx` | opciones de pipeline, foto |
| `frontend/src/pages/projects/ApplyDevelopmentDialog.tsx`, `CopyPipelineDialog.tsx` | nuevos |
| `frontend/src/pages/projects/tabs/pipeline/{validate.ts,model.ts,PipelineCanvas.tsx,Panels.tsx,TryDecisionDialog.tsx}` | nodo Fin y salidas |
| `frontend/src/pages/tasks/{TaskPage,TaskBits}.tsx`, `lanes/DecisionBlock.tsx`, `BoardPage.tsx` | salida, «Seguir», modo SDD |
| `frontend/src/pages/architect/*`, `pages/agents/*`, `pages/home/*` | accesos al Arquitecto, nodos Fin en la propuesta |
| `frontend/src/i18n/es.json` | textos |

## Tareas (en orden)
1. [x] **Bloque 0**: spikes S1–S3 y resultados en este plan.
2. [x] **Bloque 1 · Foto del proyecto**: migración `0024` (solo `projects.avatar`), API, limpieza y `ProjectMark` en todas las pantallas.
3. [x] **Bloque 2 · Salidas en el grafo**: reglas en Python y en `validate.ts`, con los mismos casos en los dos; guardar y cargar las salidas (también en la hoja del Arquitecto, para que mejorar un pipeline no las pierda); migración `0025` con los campos de las salidas y del modo SDD; ADR 0030 y nota en el 0020.
4. [x] **Bloque 3 · Salidas en el motor**: `start_decision`, decisor con salida (prompt de S1 y su esquema), `exit_at`, revisión final, confirmación, «Terminar aquí» y «Seguir con el pipeline» (`POST /tasks/{id}/continue`); la tarea expone la salida de su etapa y dónde terminó.
5. [x] **Bloque 4 · Salidas en la interfaz**: nodo Fin en el editor (se mueve y se borra con su etapa), panel de la salida, «Probar» también para la salida (el backend de la vista previa la admite), `DecisionBlock` con «Terminar aquí» excluyente y «Seguir con el pipeline», y «Terminó en …» en las tarjetas del Tablero y de las colas.
6. [ ] **Bloque 5 · SDD**: detección, `set_work_mode`, contexto por etapa, cambio a mano y en la revisión, interfaz.
7. [ ] **Bloque 6 · Plantillas**: las ocho plantillas de agentes y la plantilla «Desarrollo»; fuera las antiguas.
8. [ ] **Bloque 7 · Aplicar y copiar**: plan de la plantilla, aplicar con agentes nuevos en una transacción, copiar; `ApplyDevelopmentDialog`, `CopyPipelineDialog`, Nuevo proyecto y pestaña Pipeline.
9. [ ] **Bloque 8 · Arquitecto**: `team` con proyecto, pipeline opcional, salidas en la hoja, `get_pipeline_templates`, accesos.
10. [ ] **Bloque 9 · e2e y cierre**: e2e con el CLI falso (CA7 y CA9), prueba manual con `claude` real (CA5 y CA7), suites completas, lint, `/code-review`, `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_project_avatar.py`: solo fotos (sin búhos), cambiar, quitar, limpieza con proyectos | CA1 |
| `project-avatar.test.tsx`: foto en `ProjectChip`, lista, Tablero y selector; diálogo sin galería | CA1 |
| `test_pipeline_graph.py` + `validate.test.ts`: salida sin condición, en un final, dentro de una rama (error); en una unión y antes de bifurcar (válida) | CA2 |
| `test_pipeline_exits.py`: decisor dice «termina» o «sigue»; salida excluyente con ramas; confirmación; revisión final; «Terminar aquí» y «Seguir con el pipeline»; pipelines sin salidas sin cambios | CA2 |
| `test_decider.py`: prompt y lectura de la respuesta con salida, con y sin ramas | CA2 |
| `pipeline-editor.test.tsx`: añadir y quitar el nodo Fin, condición, errores | CA2 |
| `test_pipeline_templates.py`: «Desarrollo» pasa la validación, con sus ramas, salidas, revisiones y rechazos; las plantillas antiguas ya no se aceptan | CA3, CA4 |
| `new-project.test.tsx`, `pipeline-tab.test.tsx`: opciones de pipeline | CA3 |
| `test_sdd.py`: detección de formatos; `set_work_mode`; contexto de cada etapa; ramas que leen el de la raíz; cambio a mano que devuelve la tarea; `409` si ha bifurcado | CA5 |
| `task-work-mode.test.tsx`: chip, sección y cambio de modo | CA5 |
| `test_apply_development.py`: agentes que faltan creados activos en el equipo, asignación, transacción completa o nada | CA6 |
| `apply-development.test.tsx`: diálogo con «ya existe» y «se creará» | CA6 |
| e2e con el CLI falso: tarea de desarrollo de principio a fin y tarea que termina en la validación | CA7 |
| `test_pipeline_copy.py`: copia completa con los mismos agentes, sin tareas; avisos por agentes archivados o en borrador | CA8 |
| `test_architect_team.py`: `team` con proyecto, sin pipeline, salidas en `set_pipeline`, `get_pipeline_templates`; e2e con el CLI falso | CA9 |
| Suites completas, lint, `/code-review` | CA10 |

## Decisiones (ADR)
- **ADR 0030 (nuevo)**:
  - La salida es un atributo de la etapa (`exit_condition`), no una etapa ni un enlace. Se decide con el decisor de ramas, junto con las ramas y de forma excluyente, y solo fuera de las bifurcaciones abiertas.
  - Terminar en una salida pasa por la revisión final si la etapa no tiene revisión propia.
  - El modo de trabajo (SDD o directo) es de la tarea, lo marca la toma de requisitos con una herramienta del MCP y llega a cada etapa en su contexto.
- **Amplía el ADR 0020** (pipelines con ramas): un pipeline puede terminar antes de su última etapa.

## Confirmado con el usuario (2026-11-01)
- **Revisión final al terminar en una salida sin revisión propia** (el caso de QA): sí.
- **Modelo del agente de IT / despliegue**: uno medio (sonnet).
- **Cambio de modo SDD**: solo mientras la tarea no ha bifurcado.
