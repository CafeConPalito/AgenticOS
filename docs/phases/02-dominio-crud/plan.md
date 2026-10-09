# Fase 02: Dominio y CRUD · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: borrador (pendiente de aprobación, Puerta 2)
- **Rama**: `phase/02-dominio-crud`

## Diseño

### Backend
**Dependencias nuevas**: `sqlalchemy` 2.1, `alembic` 1.20.

```
backend/src/agentic_os/
  db/
    base.py            DeclarativeBase, TimestampMixin (created_at/updated_at UTC), ids UUID en texto
    session.py         engine SQLite (<data_dir>/agentic-os.db, PRAGMA foreign_keys=ON, WAL), get_session()
    migrate.py         upgrade_to_head(engine): Alembic programático, se llama en el lifespan del app
    migrations/        env.py + versions/0001_agents_projects.py
  models/
    agent.py           Agent
    project.py         Project
  schemas/             Pydantic: AgentCreate/Update/Read, ProjectCreate/Update/Read, CliInfo, Template
  services/
    templates.py       las 5 plantillas (datos)
    git.py             detect(path) → {is_repo, branch, dirty} | None (timeout 5 s; sin git instalado → None)
    paths.py           normalize(path) (resolve + normcase en Windows), validate_folder(path, create)
    clis.py            catálogo: which + --version + modelos (agy: `agy models`, caché TTL 10 min)
  api/
    agents.py          /api/agents · /api/agents/{id} · /api/agents/{id}/duplicate · /api/agent-templates
    projects.py        /api/projects · /api/projects/{id} · /api/projects/{id}/open
    clis.py            /api/clis?refresh=true
```

**Modelo de datos** (migración `0001`):

| Tabla | Columnas |
|---|---|
| `agents` | `id`, `workspace_id` (=`"default"`), `name`, `role`, `description`, `color`, `cli` (`claude`\|`agy`), `model`, `instructions` (markdown), `permission_mode` (`autonomous`\|`restricted`\|`ask`), `allowed_tools` (JSON: `read`, `edit`, `terminal`, `git`, `web`, `browser`, `mcp_agentic_os`), `max_concurrency` (1–5), `can_spawn_subagents`, `can_create_tasks`, `status` (`active`\|`draft`), `template`, `created_at`, `updated_at` |
| `projects` | `id`, `workspace_id`, `name`, `color`, `description`, `path`, `path_key` (normalizada; único por workspace), `workspace_mode` (`direct`\|`worktree`), `memory` (markdown), `created_at`, `updated_at` |

**API**:
- `GET/POST /api/agents`. `POST` admite `{"template": "developer"}` para crear desde una plantilla; el resto de campos sobrescribe los de la plantilla.
- `GET/PATCH/DELETE /api/agents/{id}`, `POST /api/agents/{id}/duplicate` (nombre «… (copia)»), `GET /api/agent-templates`.
- `GET/POST /api/projects`. `POST` admite `create_folder: true`. Errores: ruta inexistente → **422** `folder_not_found`; duplicada → **409** `project_exists`; worktree sin git → **422** `worktree_requires_git`.
- `GET/PATCH/DELETE /api/projects/{id}`. La respuesta incluye `git` detectado al vuelo.
- `POST /api/projects/{id}/open`: abre la carpeta en el explorador del sistema (`os.startfile`). Lo hace el backend porque es local; en el modo servidor (fase 13) se desactivará.
- `GET /api/clis` → `[{id, name, installed, path, version, models[], models_error}]`.
- Errores con forma uniforme `{"detail": {"code": "...", "message": "..."}}` para que la UI traduzca por `code`.

**Empaquetado**: Alembic carga las migraciones como archivos, así que `build-backend.ps1` añade `--add-data "src/agentic_os/db/migrations;agentic_os/db/migrations"` y lo comprueba en CA1 con el ejecutable.

### Frontend
**Dependencias nuevas**: `react-hook-form`, `zod`, `@hookform/resolvers`, `react-markdown` + `remark-gfm` (vista previa), `@tauri-apps/plugin-dialog`. Componentes shadcn: `input textarea select switch tabs dialog alert-dialog card table label radio-group dropdown-menu`.

```
frontend/src/
  api/
    types.ts            tipos del dominio (espejo de los schemas)
    errors.ts           ApiError {status, code}; apiFetch lanza ApiError
    agents.ts           useAgents, useAgent, useCreateAgent, useUpdateAgent, useDuplicateAgent, useDeleteAgent, useTemplates
    projects.ts         useProjects, useProject, useCreateProject, useUpdateProject, useDeleteProject, useOpenFolder
    clis.ts             useClis
  components/
    agentic/            AgentAvatar, CliTag, StatusBadge, ProjectChip (a partir de docs/design/code/…/primitives.tsx)
    MarkdownEditor.tsx  pestañas Editar / Vista previa (textarea + react-markdown)
    FolderPicker.tsx    Tauri → diálogo nativo; navegador → campo de texto
    UnsavedChangesGuard.tsx  useBlocker de React Router + diálogo «Descartar cambios»
    ConfirmDialog.tsx
  pages/agents/
    AgentsPage.tsx      tabla + estado vacío con plantillas
    NewAgentPage.tsx    selector de plantilla (5 + «En blanco») → POST → redirige al editor
    AgentEditorPage.tsx cabecera (avatar, nombre, estado, CLI·modelo, Guardar) + pestañas por ruta
    tabs/GeneralTab.tsx, InstructionsTab.tsx, ExecutionTab.tsx, ComingSoonTab.tsx
  pages/projects/
    ProjectsPage.tsx, NewProjectPage.tsx, ProjectDetailPage.tsx
    tabs/SummaryTab.tsx, MemoryTab.tsx, SettingsTab.tsx (+ ComingSoonTab)
```
- **Formularios**: un único `useForm` por editor con esquema zod, compartido entre las pestañas (se guardan todas a la vez con «Guardar cambios»). Los errores del API (`code`) se muestran en el campo afectado.
- **Breadcrumb**: `handle.crumb` en las rutas + `useMatches()`; el nombre del agente o proyecto se lee de la caché de TanStack Query.
- **Cabecera**: «Nuevo agente» → `/agentes/nuevo` y «Nuevo proyecto» → `/proyectos/nuevo`.
- **Textos**: todo en `es.json` (`agents.*`, `projects.*`, `errors.<code>`). Las plantillas tienen las instrucciones en español.

### Escritorio
- `tauri-plugin-dialog` (Rust + JS) con la capability `dialog:allow-open`, solo para elegir carpeta.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/{db,models,schemas,services}/**`, `api/{agents,projects,clis}.py`, `app.py` (lifespan) | nuevos / modificado |
| `backend/tests/test_{migrations,agents_api,projects_api,clis,git,paths}.py`, `conftest.py` | nuevos |
| `scripts/build-backend.ps1` | `--add-data` de las migraciones |
| `frontend/src/{api,components,pages}/**`, `routes.tsx`, `AppHeader.tsx`, `es.json` | nuevos / modificados |
| `desktop/src-tauri/{Cargo.toml,src/lib.rs,capabilities/default.json}` | plugin dialog |
| `docs/adr/0006-persistence.md`, `README.md`, `docs/roadmap.md` | nuevo / modificados |

## Tareas (en orden, cada una en su commit)
1. [ ] Rama. BD: `base`, `session`, Alembic, migración `0001`, `upgrade_to_head` en el lifespan; `conftest` con carpeta de datos temporal; tests de migración (BD vacía, BD existente, idempotencia).
2. [ ] Agentes: modelo, schemas, plantillas, API y tests (CRUD, plantilla, duplicar, validaciones, 404/422).
3. [ ] Proyectos: `paths`, `git`, modelo, schemas, API, abrir carpeta y tests (ruta inexistente / crear / duplicada con mayúsculas distintas, worktree sin git, repo git temporal con rama y cambios).
4. [ ] Catálogo de CLIs y tests (CLI simulado; ausente; caché y `refresh`).
5. [ ] Frontend base: dependencias, componentes shadcn, `api/` con ApiError, primitivas del diseño, MarkdownEditor, ConfirmDialog, UnsavedChangesGuard, breadcrumb por rutas, botones de la cabecera.
6. [ ] Pantallas de Agentes: lista, nueva (plantillas) y editor con 3 pestañas + «próximamente»; tests.
7. [ ] Pantallas de Proyectos: lista, nuevo (FolderPicker), detalle con Resumen / Memoria / Ajustes; tests.
8. [ ] Escritorio: plugin dialog; empaquetado con migraciones; prueba manual de persistencia y del selector nativo.
9. [ ] ADR 0006, README, `validacion.md`, `/code-review`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_migrations.py`: BD nueva → tablas; segunda ejecución sin cambios; BD con datos → se conservan | CA1 |
| `test_agents_api.py`: CRUD, crear desde plantilla (+ sobrescritura), duplicar, validaciones (nombre vacío, CLI desconocido, concurrencia 0/6), 404 | CA2 |
| `test_projects_api.py`: ruta inexistente (422), `create_folder`, duplicada (409, también con otra capitalización), worktree sin git (422), git detectado en un repo temporal (rama + dirty), borrar no toca la carpeta | CA3 |
| `test_clis.py`: CLI instalado (ejecutable falso que imprime versión y modelos), ausente (`installed: false`), caché y `refresh` | CA4 |
| `AgentsPage.test.tsx`, `NewAgentPage.test.tsx`, `AgentEditorPage.test.tsx`: lista, estado vacío, crear desde plantilla, editar y guardar (PATCH con los campos), borrar con confirmación, cambios sin guardar | CA5, CA7 |
| `ProjectsPage.test.tsx`, `NewProjectPage.test.tsx`, `ProjectDetailPage.test.tsx`: alta, error 422/409 mostrado en el campo, Resumen con git, memoria guardada, borrar | CA6 |
| Manual: crear agente y proyecto en la app empaquetada → cerrar → reabrir → siguen ahí; selector de carpeta nativo; comparación visual con las capturas | CA1, CA5, CA6 |

## Decisiones (ADR)
- **0006: Persistencia.** SQLite en la carpeta de datos, SQLAlchemy 2, Alembic programático al arrancar, ids UUID en texto, `workspace_id` en todas las tablas, migraciones incluidas en el ejecutable. Postgres se podrá usar en el modo servidor (fase 13) cambiando la URL.

## Riesgos
- **Alembic dentro del ejecutable de PyInstaller**: se verifica en la tarea 8. Plan B: migraciones con `MigrationContext` y operaciones embebidas, sin archivos.
- **`agy models` lento**: caché + carga diferida en el selector.
- **Fidelidad visual**: se usan las primitivas de `docs/design/code` adaptadas (tokens en lugar de hex, i18n).
