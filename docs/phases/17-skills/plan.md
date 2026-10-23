# Fase 17: Skills · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-23) · en desarrollo (bloque 0)

## Lo que ya se sabe (revisado al escribir el plan)
- **Niveles**: `KnowledgeScope` (`general` · `project` · `agent`) y el `CHECK` que exige `project_id` o `agent_id` según el nivel (`models/knowledge.py`) se reutilizan tal cual. Última migración: `0018_knowledge_graph`.
- **Contexto**: `build_instructions` (`services/context.py`) recibe ya hechos los bloques (`knowledge=` de `knowledge_context.knowledge_section`). Lo llama `RunManager._instructions` (`services/runs/manager.py`), que conoce la ejecución, el agente, el proyecto, la tarea y el agente padre de un subagente. La sección «Skills» entra igual, como un parámetro `skills=`.
- **Etapa**: `Run.stage_id` y `Task.stage_id` apuntan a `stages`. Las vías de la fase 13 también son etapas, así que los modos por etapa sirven igual para ellas.
- **MCP**: cada herramienta es un método del protocolo `AgentBackend` (`mcp_server.py`) que implementa el `RunManager` con el `run_id` del token y deja el evento `mcp`. `propose_knowledge` (`knowledge/proposals.py`) es el modelo para `propose_skill`: comprobaciones con motivo en palabras, elemento en la Inbox, aceptar y rechazar, y rechazos registrados.
- **Adapters**:
  - Claude escribe en `<run_dir>` su `settings.json`, `mcp.json` e `instructions.md`, y lanza con `--setting-sources project,local` y `--add-dir` para cada carpeta extra.
  - `agy` escribe su plugin en `<cwd>/.agents/plugins/agentic-os/` (`rules/AGENTS.md`, `mcp_config.json`, `hooks.json`) y lo borra al terminar.
  - Los *hooks* de herramienta ya llegan al backend (`PreToolUse` con su *matcher*).
- **Vectores**: `knowledge/embeddings.embed(worker, spec, texts, kind)` pide los vectores al trabajador. El modelo activo y su reindexado ya existen (fase 14). Sin modelo, la búsqueda de la fase 14 usa FTS5.
- **Diffs**: el visor `components/changes/FileDiffView.tsx` pinta `FileChange` + `Hunk`/`DiffLine` (`schemas/changes.py`). El backend saca esos datos de git, pero el formato no depende de git.
- **Credenciales**: `gitx/credentials.token_for("github.com")` da el *token* que tenga git (fase 12). Sirve para la API de GitHub sin pedir otro.
- **Inbox**: `InboxKind` cerrado con `CHECK`; la fase 15 añadió `knowledge` con su FK. Se añade `skill` igual.
- **Dependencias**: `httpx` y `numpy` ya están. `pyyaml` está solo como dependencia transitiva y se declara como directa.
- **Diseño**:
  - `KnowledgePanel` con `section="skills"`: rejilla de tarjetas con interruptor, chip «Autoseleccionada», «Usada N veces», propuestas con borde violeta y contador «N activas de M» (`docs/design/screens.md` §10);
  - pestaña Skills del agente;
  - «Conocimiento y skills» en la navegación.

## Bloque 0 · Spikes (antes de programar)
Scripts en `spikes/skills/`; evidencias en `evidencias/`.

| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Claude Code nativo**: (a) ¿`--plugin-dir <run_dir>/plugin` (o `--add-dir` con `.claude/skills/` dentro) carga skills por ejecución sin escribir en `~/.claude`? (b) Con `--setting-sources project,local`, ¿se cargan o no las skills de `~/.claude/skills` y las de los plugins del usuario? Si se cargan, ¿hay un *flag* o ajuste que las apague para la sesión? (c) ¿Llega a `PreToolUse` la herramienta `Skill` con el nombre de la skill, para registrarla? (d) ¿Los *scripts* de la skill se ejecutan con los permisos de cada modo? | (a) solo la vía común; (b) se documenta como límite en la ficha del agente y el ADR, sin tocar `~/.claude`; (c) se registra solo la vía común |
| S2 | **`agy` nativo**: ¿un `skills/<nombre>/SKILL.md` dentro del plugin de workspace se carga como skill? ¿`agy` lee también las skills globales del usuario y se pueden apagar? ¿Hay *hook* que diga qué skill cargó? | Solo la vía común para `agy` |
| S3 | **Registros**: para skills.sh, `anthropics/skills`, SkillsMP y ClawHub: API pública o no, búsqueda y orden «más usadas», instalaciones o estrellas, de dónde se descargan los ficheros (casi todos apuntan a un repo de GitHub), versión o *commit*, licencia, análisis de seguridad, límites de peticiones y condiciones de uso | La fuente se lee a través de GitHub (repos indexados), o se cambia por otra de las más usadas (LobeHub, agentskill.sh) |
| S4 | **Autoselección**: corpus de 20 skills reales (de `anthropics/skills` y propias) y 50 tareas de prueba en español e inglés. Acierto en las 3 primeras con `multilingual-e5-small`, EmbeddingGemma 2 y bge-m3 sobre «nombre + descripción», frente a palabras clave (BM25 propio). Umbral mínimo por modelo, y si añadir el primer apartado del cuerpo mejora | Ranking híbrido (RRF de vectores y palabras), como la búsqueda de la fase 14 |
| S5 | **Formato real**: parsear 100 `SKILL.md` de los registros: rarezas de la cabecera YAML (campos extra, `allowed-tools`, multilínea, BOM, CRLF), tamaños típicos y tipos de fichero de apoyo | Parser tolerante: solo `name` y `description` son obligatorios y el resto se conserva tal cual |

## Diseño ([ADR 0024](../../adr/0024-skills.md), nuevo, borrador)

### 1. Modelo de datos (migración `0019_skills`)
- **`Skill`** (`skills`):
  - identidad: `name` (*slug* `a-z0-9-`, máx. 64 caracteres) y el nivel (`scope`, `project_id`, `agent_id`, con el mismo `CHECK` que el conocimiento). Es única por nivel, con un índice único de `(scope, project_id, agent_id, name)`;
  - estado: `enabled`, `review` (`none` · `proposed`: una skill nueva propuesta por un agente que aún no se ha aprobado) y `origin` (`user` · `agent` · `import` · `registry`);
  - versión: `current_version_id` y `description`, copia de la versión actual para listar y seleccionar;
  - vector: `vector` (BLOB) y `vector_model`, el vector de «nombre + descripción» (S4);
  - `created_at` y `updated_at`.
- **`SkillVersion`** (`skill_versions`):
  - `skill_id` y `number` (1, 2, 3…);
  - `status` (`accepted` · `proposed` · `rejected`);
  - `manifest` (JSON: `{ruta: {sha256, size, executable}}`, con `SKILL.md` incluido), `description` y `tokens`;
  - autor: `author_kind` (`user` · `agent` · `import` · `registry` · `restore`), `author_label`, y `agent_id`, `run_id` y `task_id` con `SET NULL`, además de `task_title` (copia);
  - `note`, un resumen del cambio (lo da el agente o se genera: «+12 −3 en SKILL.md, nuevo scripts/x.py»);
  - `base_version_id`, la versión sobre la que se hizo (para las diferencias de una propuesta);
  - `restored_from_id` y `created_at`.

  Las versiones aceptadas no se borran nunca. Rechazar una propuesta deja la versión como `rejected`, sin ficheros si nadie más los usa.
- **Almacén de ficheros** `<data_dir>/skills/blobs/<aa>/<sha256>`: cada fichero se guarda una vez por contenido, así que diez versiones de una skill que solo cambian el `SKILL.md` comparten el resto. Una limpieza borra los *blobs* sin referencias al borrar una skill o rechazar una propuesta. El uso de disco entra en `datadir.disk_usage`.
- **`SkillMode`** (`skill_modes`): `skill_id`, y un `agent_id` **o** un `stage_id` (`CHECK`: uno de los dos), con `mode` (`auto` · `always` · `never`). Sin fila, el modo es `auto`. Las dos FK son `CASCADE`.
- **`SkillOrigin`** (`skill_origins`, 1:1, solo las instaladas desde un registro): `registry`, `ref` (identificador en la fuente), `repo_url`, `path`, `commit` instalado, `license`, `security` (JSON del análisis de la fuente, si lo hay), `latest_commit`, `checked_at` y `installed_version_id`.
- **`RunSkill`** (`run_skills`):
  - `run_id` (`CASCADE`), `skill_id` (`CASCADE`: borrar una skill borra sus cifras, con aviso) y `version_id` (`SET NULL`), más `skill_name` (copia);
  - `offered` (`always` · `candidate`), `rank`, `score`, `loaded_via` (nulo · `context` · `tool` · `native`) y `loaded_at`;
  - copias para las estadísticas (apartado E de la spec), que se guardan al crear la fila: `stage_name`, `pipeline_id` y `pipeline_name`, y `team_id` y `team_name` del agente. El agente, el proyecto, el CLI, el modelo, la cuenta, el estado, el veredicto, el coste y los *tokens* ya están en `Run`, con sus nombres copiados (`agent_name`, `project_name`, `account_label`). Así las cifras sobreviven al borrado (CA21);
  - índices por `(skill_id, loaded_at)` y `(run_id)`.

  De aquí salen «Usada N veces», la fecha de la última vez, el chip «Autoseleccionada» y las estadísticas.
- **`SkillRejection`** (`skill_rejections`): `name`, `sha256` del `SKILL.md`, `vector`, `agent_id`, `reason` y `rejected_at`.
- `InboxKind.SKILL` (`skill`) con `skill_version_id` en el elemento (`SET NULL`).
- `downgrade` borra lo nuevo (y la carpeta `skills/` no se toca).

### 2. Biblioteca (`services/skills/`)
- **`store.py`**: guardar y leer *blobs*, y `materialize(version, dest)`, que escribe la carpeta de una versión. El marcado de ejecutable va por extensión (`.py .sh .ps1 .bat .cmd .js .mjs .ts .rb .pl .exe`…) o por *shebang*.
- **`format.py`**: parser de `SKILL.md` (S5): cabecera YAML con `name` y `description` obligatorios, y el resto de campos conservados tal cual. Tolera BOM y CRLF. Validación con motivo en palabras: nombre válido y único en su nivel, descripción de 1 a 1 024 caracteres, `SKILL.md` ≤ `skills.max_tokens` (8 000), como mucho 50 ficheros, cada uno ≤ 1 MB y el total ≤ 5 MB (CA1).
- **`library.py`**: crear, editar (cada guardado = versión nueva con su resumen), activar o apagar, mover de nivel, borrar y listar por nivel con «N activas de M» y su uso. Al cambiar la descripción se recalcula el vector.
- **`history.py`**:
  - lista de versiones;
  - `diff(a, b)` con `difflib`, que devuelve `FileChange` + `Hunk` + `DiffLine` (el esquema de `schemas/changes.py`), con renombrados por mismo `sha256` y binarios por tamaño;
  - `restore(version)`, que crea una versión nueva `author_kind=restore` (CA12).
- **`importer.py`**:
  - importar una carpeta, un `.zip` (con protección contra rutas que se salen de la carpeta y los mismos topes que la validación) o un `SKILL.md` suelto;
  - `scan_cli_skills()` lista las skills de `~/.claude/skills`, del `.claude/skills` de cada proyecto y de la carpeta de skills de `agy` (S2), cada una con su nombre, descripción, ruta y si ya está importada;
  - importar en lote, cada skill con su nivel, solo lee el original (CA2);
  - si el nombre choca, propone `nombre-2`.
- **`export.py`**: el `.zip` de la versión actual.
- **Vectores**: al guardar, y al cambiar de modelo (lo engancha el `reindex` de la fase 14), «nombre + descripción» (+ lo que decida S4) se envía al trabajador. Sin modelo, la skill no tiene vector.

### 3. Selección y contexto (`services/skills/selection.py`, `context.py`)
- **Visibles** para una ejecución: `enabled`, `review = none` y con versión actual, de los niveles general, proyecto y agente (también los del agente padre en un subagente, como el conocimiento). Si dos tienen el mismo nombre, queda la del nivel más concreto (CA3).
- **Modo efectivo** de cada skill: el de la etapa de la ejecución (`Run.stage_id`), si lo tiene; si no, el del agente; si no, `auto`. `never` la quita (CA4).
- **Candidatas** entre las `auto`:
  - la consulta es el título y la descripción de la tarea, el nombre de la etapa y el rol del agente (en una ejecución manual, su *prompt*);
  - con modelo, el coseno con el vector de cada skill; sin modelo, BM25 sobre nombre y descripción; o el híbrido que decida S4;
  - se quedan las que superan el umbral (S4), hasta `skills.candidates` (5).
- **Sección «Skills»** del contexto, dentro de `skills.index_tokens` (600):
  - una cabecera de dos líneas que explica `use_skill`;
  - las candidatas en orden (`- nombre: descripción`, recortada a una línea);
  - las `always` enteras (su `SKILL.md`), hasta `skills.always_tokens` (6 000). Las que no caben pasan a la lista con «(fijada; cárgala con `use_skill`)».
- **Ficheros en disco**: cada ejecución materializa sus skills (candidatas y `always`) en `<run_dir>/skills/<nombre>/` para que los *scripts* tengan una ruta real. Claude recibe `--add-dir <run_dir>/skills`; `agy` las tiene dentro de su plugin (S2) o en `--add-dir`. La carpeta se borra con la ejecución.
- **MCP**:
  - **`use_skill(name)`**: el `SKILL.md`, la ruta de la carpeta materializada y la lista de ficheros (con «ejecutable»). Puede pedir cualquier skill visible que no esté en `never`, aunque no sea candidata; la materializa al vuelo si hace falta. Registra `loaded_via=tool`.
  - **`read_skill_file(name, path)`**: solo ficheros del `manifest` de una skill visible, normalizando la ruta. Nunca sale de la carpeta (CA7).
- **Registro**: al preparar el contexto se crean las filas `RunSkill` (`offered`, `rank`, `score`). Las `always` quedan `loaded_via=context`. `use_skill` y el *hook* nativo (S1) rellenan `loaded_via` y `loaded_at`, y dejan el evento `mcp` o `skill` en la ejecución.
- **Probador**: `POST /api/skills/try` (texto de tarea, agente y etapa opcional) devuelve lo mismo que vería la ejecución: candidatas con su puntuación, las fijadas, las excluidas y la sección renderizada.

### 4. Mecanismo nativo (según S1 y S2)
- `LaunchContext` gana `skills_dir` (la carpeta materializada) y `native_skills` (bool por CLI, decidido por el spike).
- **Claude**: si S1(a) sale bien, `<run_dir>/plugin/` con su `plugin.json` y `skills/` (enlaces o copia de lo materializado) y `--plugin-dir`. Para la herramienta `Skill`, la regla de permisos se añade a `claude_permissions`. El *hook* `PreToolUse` con `tool_name == "Skill"` registra `loaded_via=native`.
- **`agy`**: si S2 sale bien, `skills/` dentro de `.agents/plugins/agentic-os/`, que ya se borra al terminar.
- **Sin doble carga**: con el mecanismo nativo, la sección del contexto lista las candidatas como «disponibles como skills de tu CLI», y las `always` siguen en el contexto, que es lo garantizado. `use_skill` sigue funcionando.
- **Aislamiento** (decisión 1 de la spec): lo que S1(b) y S2 permitan. Si un CLI carga las skills del usuario de todos modos, la ficha del agente lo avisa y el ADR lo recoge. Nunca se toca su configuración (CA8: *snapshots* de `~/.claude` y de la carpeta de `agy` antes y después).

### 5. Propuestas (`services/skills/proposals.py`)
**`propose_skill(name, description, body, files={}, level="", replaces="", note="")`** (MCP):
1. Comprobaciones, cada una con motivo en palabras (CA10):
   - ajuste `skills.proposals.enabled`;
   - máximo `skills.proposals.per_run` (1) por ejecución;
   - formato y topes de §2. Los `files` son de texto (`{ruta: contenido}`);
   - `replaces`: una skill visible para el agente (de cualquier autor);
   - parecidas: mismo `sha256`, mismo nombre en el nivel, o coseno ≥ `skills.proposals.duplicate_threshold` contra las visibles, las pendientes y los rechazos → «Ya existe una skill muy parecida: «X» (…)». Sin modelo, solo el `sha256` y el nombre.
2. Sin `replaces`: una `Skill` con `review=proposed` y `origin=agent`, en el nivel sugerido o, si no lo hay, el del agente, más su versión 1 `proposed`. Con `replaces`: una `SkillVersion` `proposed` sobre esa skill, con `base_version_id` = su versión actual. La skill sigue igual hasta aprobarla (CA11).
3. Elemento de la Inbox («Skill propuesta: nombre», con el agente, el proyecto y «versión nueva de…» si lo es) y evento. El agente recibe «Propuesta registrada (pendiente de revisión)». No espera.

**Aprobar** (`POST /api/skills/proposals/{version_id}/accept`, con ediciones opcionales de nombre, descripción, cuerpo y ficheros, nivel y `opened_files`):
- si la versión tiene ficheros ejecutables, todos tienen que estar en `opened_files`; si no, 409 «Abre antes los *scripts*: …» (CA13; la UI lo exige también);
- con ediciones, la versión aprobada guarda los cambios y su nota dice «editada al aprobar»;
- skill nueva: `review=none` y `current_version_id`. Versión nueva: pasa a ser la actual y la anterior se queda en el historial;
- resuelve el elemento de la Inbox.

**Rechazar** (`…/reject`, motivo opcional): `SkillRejection`, la versión queda `rejected` (si era una skill nueva, se borra la skill), limpieza de *blobs* y elemento resuelto.

Las reglas de Agentic OS explican en una línea cuándo proponer: una forma de trabajar comprobada y reutilizable, no un resumen de la tarea.

### 6. Registros públicos (`services/skills/registries/`)
- Protocolo **`RegistrySource`**:
  - `popular(page)` y `search(query, category, page)` → tarjetas (id, nombre, descripción, autor, instalaciones o estrellas, actualizado, categoría);
  - `detail(id)` → repo, ruta, *commit* actual, licencia, seguridad y la lista de ficheros;
  - `fetch(id, commit)` → los ficheros.
- Implementaciones según S3:
  - `skills_sh.py`;
  - `anthropic.py` (`anthropics/skills` por la API de GitHub);
  - `skillsmp.py`;
  - `clawhub.py`;
  - `github_url.py`, para una URL cualquiera de un repo, que busca sus `SKILL.md`.

  Las que bajan de GitHub comparten `github.py`: lista del árbol, descarga del *tarball* de un *commit* filtrado a la carpeta de la skill, *token* opcional de `credentials.token_for("github.com")` y topes de §2.
- **Lo que se revisa es lo que se instala**: `detail` baja los ficheros de un *commit* fijo a una carpeta temporal y devuelve un `preview_id`; la ficha muestra esos ficheros, e `install(preview_id, nivel)` instala exactamente eso (CA16). La vista previa caduca a la hora.
- **Instalar**: `Skill` con `origin=registry`, versión 1 `author_kind=registry` («instalada desde skills.sh · repo@commit») y su `SkillOrigin`. Si hay ejecutables, `opened_files` como al aprobar.
- **Actualizaciones**: `check_updates()` a demanda y una vez al día en segundo plano, solo para las instaladas, con pausa ante el límite de peticiones. Si `latest_commit` ≠ `commit`, la tarjeta avisa. «Ver cambios» baja la versión nueva como vista previa y muestra el diff contra la actual. «Actualizar» crea una versión nueva `author_kind=registry`. Si el usuario había editado la skill, sus versiones siguen en el historial y la nueva parte del registro, con un aviso de que reemplaza sus ediciones (que se pueden restaurar) (CA17).
- **Caché**: búsquedas y listados 10 minutos en memoria. Una fuente que falla o va lenta (tiempo máximo 8 s) devuelve su error sin tirar las demás. Sin red, el explorador dice «Sin conexión» (CA18).
- **Fuentes**: ajuste `skills.registries` con cada fuente activada o no. ClawHub queda apagado por defecto si S3 no encuentra un análisis de seguridad fiable.

### 7. Estadísticas de uso (`services/skills/stats.py`)
- **Una consulta agregada** sobre `run_skills` ⋈ `runs` (más `skills` para el nivel y el origen), en SQL y sin cargar filas en Python:
  - `offered`, `loaded` (`loaded_via` no nulo) y `rate`;
  - `runs` y `tasks` (`COUNT DISTINCT`);
  - resultado de las ejecuciones con la skill cargada: `done`, `failed`, `approved` y `rejected` (estado y `verdict`);
  - `avg_cost` y `avg_tokens` sobre las ejecuciones con consumo leído;
  - `last_used` y las cargas por vía.
- **Filtros** (todos opcionales y combinables):
  - `from` y `to` (sobre el inicio de la ejecución);
  - `agent_id`, `team_id`, `project_id`, `pipeline_id`, `stage_id`, `cli`, `account_id` y `model`;
  - `scope`, `origin`, `via` y `unused` (`never_loaded` · `never_offered`; la segunda une con `skills` para incluir las que no tienen filas).
- **Agrupar** (`group_by`: `agent` · `team` · `project` · `pipeline` · `stage` · `cli` · `account` · `model`): `GROUP BY skill, clave`, con la clave por id cuando exista y por el nombre copiado cuando el original ya no esté (CA21).
- **Orden** por cualquier métrica (`sort`, `desc`) y paginación.
- **Serie diaria** (`GET …/stats/daily`): cargas por día para las skills elegidas, con los mismos filtros. Se agrupa por la fecha local, como el panel de consumo de la fase 07.
- **Ejecuciones de una cifra** (`GET …/stats/runs`): la lista con los mismos filtros más la skill (y el grupo), con la versión usada y el enlace.
- **CSV** (`GET …/stats.csv`): la tabla filtrada, con cabeceras en español.
- **Rendimiento** (CA20): índices de §1 más `runs(started_at)`. Si con 20 000 ejecuciones no baja de 1 s, se añade una tabla diaria precalculada (`skill_usage_daily`) que se actualiza al cerrar cada ejecución.

### 8. API (`api/skills.py`, `schemas/skills.py`)
- `GET/POST /api/skills` (filtros de nivel, proyecto, agente y `review`), `GET/PATCH/DELETE /api/skills/{id}`, `POST /api/skills/{id}/versions` (guardar = versión nueva), `GET /api/skills/{id}/versions`, `GET /api/skills/{id}/diff?from=&to=`, `POST /api/skills/{id}/restore/{version_id}`, `GET /api/skills/{id}/files/{path}` y `GET /api/skills/{id}/export`.
- `POST /api/skills/import` (multipart: carpeta como ficheros, `.zip` o `SKILL.md`), `GET /api/skills/cli-scan` y `POST /api/skills/cli-import` (lista con nivel por skill).
- `GET/PUT /api/agents/{id}/skill-modes` y `GET/PUT /api/stages/{id}/skill-modes`.
- `POST /api/skills/try`.
- `POST /api/skills/proposals/{version_id}/accept|reject`.
- `GET /api/skills/registries`, `GET /api/skills/registries/search`, `POST /api/skills/registries/preview`, `POST /api/skills/registries/install` y `POST /api/skills/updates/check`.
- `GET /api/runs/{id}/skills`.
- `GET /api/skills/stats`, `GET /api/skills/stats/daily`, `GET /api/skills/stats/runs` y `GET /api/skills/stats.csv` (§7).
- `GET/PUT /api/settings/skills`.
- Eventos en `/api/knowledge/events` (o en uno propio `/api/skills/events`, lo que sea más simple al llegar): `skill_changed` y `skill_proposed`.

### 9. Frontend
- **API** (`api/skills.ts`): consultas y mutaciones de §7, y los tipos.
- **Navegación**: «Conocimiento y skills» (`/conocimiento`) con las pestañas **Documentos · Skills · Explorar**.
- **Biblioteca** (`components/skills/SkillLibrary.tsx`), en Ajustes (general), Proyecto › Conocimiento y Agente › Skills, según el diseño:
  - tarjetas con interruptor, chips de nivel y de origen («Creada por agente», «Instalada desde…», «Importada»), «Usada N veces · hace 2 días», «Actualización disponible» y la propuesta con borde violeta;
  - contador y arrastrar y soltar para importar.
- **Editor** (`SkillEditor.tsx`): hoja con nombre, descripción (con contador y consejo: «di cuándo usarla»), `MarkdownEditor` del cuerpo y ficheros (añadir, ver, quitar, con «ejecutable» marcado). «Guardar» abre un campo opcional «¿Qué has cambiado?» para la nota.
- **Historial** (`SkillHistory.tsx`): lista de versiones (número, fecha, autor y origen, nota, «actual»), con dos selectores para comparar, `FileDiffView` y «Restaurar».
- **Importar** (`SkillImportDialog.tsx`): carpeta (`FolderPicker`), `.zip` o `SKILL.md`, y la pestaña «De mis CLIs» con la lista de `cli-scan`, una casilla y un selector de nivel por fila (CA2).
- **Modos**:
  - en Agente › Skills, cada tarjeta lleva un selector Automática / Siempre / Nunca para ese agente;
  - en el editor de pipeline, el panel de la etapa (`pipeline/Panels.tsx`) gana una sección «Skills» con las visibles para el agente de la etapa y su modo («hereda del agente» por defecto).
- **Probador** (`SkillTester.tsx`): texto de tarea, agente y etapa → candidatas con su puntuación, fijadas y excluidas (con el motivo: «Nunca en la etapa QA»).
- **Ejecución**: sección «Skills» en la página de la ejecución (ofrecidas, cargadas, vía y versión, con el chip «Autoseleccionada»), y etiquetas para `use_skill`, `read_skill_file` y `propose_skill` en el registro.
- **Propuestas** (`SkillProposalReview.tsx`): hoja con el texto, los ficheros (los ejecutables marcados, y «Aprobar» deshabilitado hasta abrirlos todos), el diff contra la versión actual si es una versión nueva, la procedencia, el nivel (el sugerido por defecto) y Aprobar / Rechazar. Se abre desde la Inbox (clase `skill`, botón «Revisar») y desde la tarjeta.
- **Explorador** (`components/skills/registry/`):
  - buscador con filtros de fuente y categoría, y por defecto «Más usadas»;
  - tarjetas con fuente, autor, instalaciones o estrellas y fecha;
  - ficha (hoja) con el `SKILL.md` renderizado, ficheros con ejecutables, licencia, seguridad de la fuente, enlace al repo y el aviso fijo sobre código de terceros;
  - «Instalar en…» con el selector de nivel;
  - estados «Sin conexión» y «Fuente no disponible»;
  - «Ver cambios» y «Actualizar» en las instaladas.
- **Uso** (`components/skills/stats/`):
  - pestaña «Uso» en Skills: barra de filtros (periodo, agente, equipo, proyecto, pipeline, etapa, CLI, cuenta, modelo, nivel, origen, vía, «nunca usadas»), con los filtros en la URL para poder compartir o volver;
  - tabla ordenable (`TanStack Table`, como las sesiones de CLI) con skill, ofrecida, cargada, tasa, ejecuciones, tareas, resultado, coste y *tokens* medios, última vez y vía;
  - selector «Agrupar por», que desglosa cada skill en filas por grupo;
  - gráficos con `recharts` (como `pages/usage/DailyChart.tsx`): barras de las 10 más usadas y línea diaria de las elegidas;
  - clic en una cifra → hoja con sus ejecuciones; botón «Exportar CSV»;
  - pestaña «Uso» en la ficha de la skill, con el mismo componente filtrado a esa skill y sus últimas ejecuciones (con la versión).
- **Ajustes** (`SkillsSection.tsx`): propuestas (activar, máximo), presupuestos, fuentes de registros (activar cada una, estado del *token* de GitHub) y uso de disco de las skills.
- i18n en `es.json` y `test/fake-backend.ts` ampliado.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0019_skills.py` | nuevo |
| `backend/src/agentic_os/models/skill.py`, `models/__init__.py`, `models/inbox.py` | nuevo / modificado |
| `backend/src/agentic_os/services/skills/` (`store.py`, `format.py`, `library.py`, `history.py`, `importer.py`, `export.py`, `selection.py`, `context.py`, `proposals.py`, `stats.py`, `agent_tools.py`, `config.py`, `events.py`) | nuevo |
| `backend/src/agentic_os/services/skills/registries/` (`base.py`, `github.py`, `skills_sh.py`, `anthropic.py`, `skillsmp.py`, `clawhub.py`, `github_url.py`, `cache.py`) | nuevo |
| `backend/src/agentic_os/services/context.py`, `services/runs/manager.py`, `services/mcp_server.py`, `services/hooks.py`, `services/inbox.py`, `services/datadir.py` | modificado |
| `backend/src/agentic_os/services/adapters/base.py`, `claude.py`, `agy.py` | modificado |
| `backend/src/agentic_os/services/knowledge/service.py` (reindexado de los vectores de las skills al cambiar de modelo) | modificado |
| `backend/src/agentic_os/api/skills.py`, `schemas/skills.py`, `api/agents.py`, `api/pipelines.py`, `api/runs.py`, `api/settings.py`, `app.py` | nuevo / modificado |
| `backend/pyproject.toml` | `pyyaml` como dependencia directa |
| `backend/tests/test_skills_*.py` (ver tests) | nuevo |
| `frontend/src/api/skills.ts` | nuevo |
| `frontend/src/components/skills/` (`SkillLibrary`, `SkillCard`, `SkillEditor`, `SkillHistory`, `SkillImportDialog`, `SkillModeSelect`, `SkillTester`, `SkillProposalReview`, `registry/RegistryExplorer`, `registry/RegistrySkillSheet`, `stats/SkillStats`, `stats/StatsFilters`, `stats/StatsCharts`, `stats/StatsRunsSheet`) | nuevo |
| `frontend/src/pages/knowledge/KnowledgePage.tsx`, `pages/agents/tabs/*`, `pages/projects/tabs/pipeline/Panels.tsx`, `pages/runs/*`, `pages/InboxPage.tsx`, `pages/settings/SkillsSection.tsx`, `SettingsPage.tsx`, navegación | nuevo / modificado |
| `frontend/src/i18n/es.json`, `test/fake-backend.ts` | modificado |
| `docs/adr/0024-skills.md` | nuevo |
| `spikes/skills/` | nuevo |

## Tareas (en orden)
1. [ ] **Bloque 0 · Spikes** S1–S5, con evidencias y cambios al diseño anotados aquí.
2. [ ] **Bloque 1 · Datos y almacén**: migración `0019`, modelos, `InboxKind.SKILL`, `store.py`, `format.py` y uso de disco.
3. [ ] **Bloque 2 · Biblioteca (backend)**: CRUD con versiones, validación, historial y diff, restaurar, importar (carpeta, `.zip`, CLIs), exportar, vectores y su reindexado, API.
4. [ ] **Bloque 3 · Selección y uso (backend)**: visibles y precedencia, modos por agente y etapa, candidatas, sección «Skills», materialización, `use_skill` y `read_skill_file`, `RunSkill`, probador, API de modos y de la ejecución.
5. [ ] **Bloque 4 · Nativo**: lo que confirmen S1 y S2 en los adapters, *hook* de la herramienta `Skill` y *snapshots* de la configuración del usuario.
6. [ ] **Bloque 5 · Propuestas (backend)**: `propose_skill`, controles, Inbox, aprobar (con `opened_files`) y rechazar, versión nueva sobre una existente, reglas.
7. [ ] **Bloque 6 · Registros (backend)**: protocolo, `github.py`, las fuentes que deje S3, vista previa fijada, instalar, actualizaciones, caché y errores por fuente, ajustes.
8. [ ] **Bloque 7 · Biblioteca (frontend)**: navegación y pestañas, tarjetas, editor, historial con diff, importar, ajustes.
9. [ ] **Bloque 8 · Uso y propuestas (frontend)**: modos en el agente y en la etapa, probador, sección de la ejecución y etiquetas, revisión de propuestas e Inbox.
10. [ ] **Bloque 9 · Explorador (frontend)**: búsqueda, filtros, ficha, instalar en un nivel, actualizaciones, estados sin conexión.
11. [ ] **Bloque 10 · Estadísticas de uso**: copias en `RunSkill`, `stats.py` (agregados, filtros, agrupación, serie diaria, ejecuciones, CSV), API, vista «Uso» y pestaña en la ficha, test de rendimiento.
12. [ ] **Bloque 11 · Calidad y e2e**: corpus de S4 como test (CA5), e2e con CLI falso y MCP real (CA6, CA9), prueba manual con `claude` y `agy` reales (CA6, CA8).
13. [ ] **Bloque 12 · Cierre**: e2e con el binario empaquetado (CA15), `/code-review`, ADR 0024 definitivo, README, validación.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_skills_library.py`: crear, editar, apagar, mover, exportar y borrar en cada nivel; cabecera mala, nombre repetido, topes → error en palabras | CA1 |
| `test_skills_import.py`: carpeta, `.zip` (también con rutas que se salen, que se rechazan), `SKILL.md` suelto, `cli-scan` sobre un `~/.claude/skills` falso con nivel por skill; *hash* del original igual | CA2 |
| `test_skills_selection.py`: visibles por nivel y en un subagente, precedencia por nombre, `always` y `never`, presupuesto de la sección | CA3 |
| ídem: la etapa manda sobre el agente (`always` y `never` en los dos sentidos), también en una vía de la fase 13 | CA4 |
| `test_skills_quality.py`: corpus de S4 (20 skills, 50 tareas), relevante en las 3 primeras ≥ 90 % con modelo y sin modelo | CA5 |
| `test_skills_e2e.py`: CLI falso con cliente MCP real recibe la sección, llama a `use_skill` y `read_skill_file`; `RunSkill` y eventos | CA6 |
| `test_skills_tools.py`: `read_skill_file` con `..`, rutas absolutas, skill no visible o en `never` → negado | CA7 |
| `test_skills_isolation.py`: *snapshot* de `~/.claude` y de la carpeta de `agy` (falsos) antes y después de preparar y limpiar una ejecución con skills; manual con los CLIs reales | CA8 |
| `test_skills_e2e.py`: `propose_skill` → skill `proposed` en la Inbox, invisible para otra ejecución; aprobar editada y en otro nivel → la siguiente la recibe con «Creada por agente» y procedencia | CA9 |
| `test_skills_proposals.py`: máximo por ejecución, topes, parecida, rechazada antes, desactivado → motivos en palabras | CA10 |
| ídem: versión nueva propuesta no cambia la actual; el diff contra la actual sale en la API | CA11 |
| `test_skills_history.py`: versión por cada clase de cambio con autor y origen, diff entre dos cualesquiera (texto, renombrado, binario), restaurar crea versión, la ejecución guarda su versión, *blobs* compartidos | CA12 |
| `test_skills_proposals.py` (409 sin `opened_files`) + `skill-proposal.test.tsx` (Aprobar deshabilitado hasta abrir los *scripts*) | CA13 |
| `skills.test.tsx` + `test_skills_selection.py`: uso y última fecha en la tarjeta, chip en la ejecución | CA14 |
| `test_skills_e2e.py` con `AGENTIC_OS_E2E_BINARY`: importar → ejecución que carga → proponer → Inbox → aprobar | CA15 |
| `test_skills_registries.py` con fuentes simuladas (`httpx.MockTransport`): más usadas, búsqueda, vista previa fijada, instalar al nivel con su primera versión «instalada desde…» + `registry-explorer.test.tsx` + manual con las fuentes reales | CA16 |
| ídem: `commit` nuevo → aviso y diff; sin confirmación no cambia; con ediciones previas el historial queda entero | CA17 |
| ídem: ejecutables sin abrir → 409; sin red → «Sin conexión» y la biblioteca va; una fuente que falla no tira las demás | CA18 |
| `test_skills_stats.py`: ejecuciones de prueba con varios agentes, equipos, pipelines, etapas, CLIs, cuentas y modelos → cifras exactas por skill, con filtros combinados, cada `group_by`, `unused`, serie diaria y CSV | CA19 |
| `skill-stats.test.tsx` (orden por columna, filtros en la URL, agrupar, gráficos, hoja de ejecuciones, exportar) + `test_skills_stats_perf.py` (50 skills, 20 000 ejecuciones, < 1 s) | CA20 |
| `test_skills_stats.py`: borrar agente, etapa, pipeline y cuenta → las cifras siguen con su nombre | CA21 |

## Decisiones (ADR)
- [ADR 0024](../../adr/0024-skills.md) (borrador):
  - skills como carpetas versionadas en un almacén por contenido, sin git;
  - autoselección propia y común a todos los CLIs (contexto + `use_skill`), con el mecanismo nativo como añadido;
  - modos con la etapa por encima del agente;
  - propuestas como versiones `proposed`;
  - registros detrás de un protocolo, con vista previa fijada a un *commit*.
- **Por qué no git para el historial**: funcionaría (diffs y deduplicación gratis), pero haría depender las skills de tener git y de su rendimiento en Windows con muchos repos pequeños. `difflib` y el almacén por contenido bastan con los topes de tamaño, y el diff sale en el mismo formato que el visor de la fase 11.
- Pendiente de los spikes: plugin o `--add-dir` en Claude y su aislamiento (S1), skills en el plugin de `agy` (S2), qué fuentes y cómo (S3), vectores, palabras o híbrido y umbrales (S4).
