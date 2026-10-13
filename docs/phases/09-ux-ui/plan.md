# Fase 09: Mejora de UX/UI · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Diseño**: [`docs/design/v2/`](../../design/v2/README.md) · [revisión](../../design/v2/revision.md)
- **Estado**: borrador

## Diseño

### Visión general
```
AppShell (sin sidebar)
├─ fondo atmosférico (bg-atmos, capa fija detrás de todo)
├─ AppHeader v7 (56 px, vidrio): logo · Volver · migas · TopNav (Tablero n · Ejecuciones n · Ajustes)
│                                 · buscador → Ctrl+K · terminal · conexión · tema
├─ OfflineBanner (igual que ahora)
├─ <main> rutas  ──  «/» = HomePage (Inicio)
└─ TerminalDock (igual que ahora)
   + diálogos globales montados una vez: CommandPalette · ShortcutsDialog · NewTaskDialog
     · NewAgentDialog · NewProjectDialog  (se abren desde un store, no desde cada página)
```
Lo que hoy funciona (rutas, TanStack Query con sondeo, WebSockets de las ejecuciones, i18n) no cambia de mecanismo. La fase es casi toda de frontend; en el backend solo hay **un endpoint nuevo de lectura** y un filtro de búsqueda. **Sin migraciones.** Decisiones en el **ADR 0013** (navegación, Inicio y atajos).

### Backend
- **`GET /api/home`** (`services/home.py`, `api/home.py`, `schemas/home.py`): todo lo que Inicio necesita y hoy no da ningún endpoint, en una sola consulta que se sondea cada 3 s (como la Inbox):
  - `agents[]`: id, nombre, rol, color, CLI, `status` (activo/borrador), **`state`** (`running` · `waiting` · `idle` · `draft`), tareas en cola, peticiones pendientes y **`sessions[]`** (ejecuciones vivas o reanudables: run, tarea `T-n` y título, proyecto y color, estado de la ejecución, inicio). `waiting` = alguna tarea suya en «Esperando humano» o alguna petición pendiente; `running` = alguna ejecución activa.
  - `projects[]`: id, nombre, color, tareas abiertas y `workers[]` (agente y título de la tarea en curso).
  - `counts`: sesiones vivas, agentes trabajando, tareas abiertas del Tablero y ejecuciones activas (contadores de la navegación).
  - El gasto de hoy, los límites por CLI y las peticiones **no se repiten**: siguen saliendo de `/usage/today`, `/inbox` y `/inbox/summary`, que la UI ya sondea.
- **`GET /api/tasks?q=&limit=`**: búsqueda para Ctrl+K. `q` busca en el título (sin distinguir mayúsculas ni acentos, `LIKE`) o, si es `T-n` / `n`, por número. `limit` por defecto 20, máximo 50. El resto de filtros no cambia.
- Crear un agente como borrador y activarlo ya es posible (`status` en `AgentCreate`/`AgentUpdate`). Crear un proyecto con pipeline son dos llamadas que ya existen (`POST /projects` + `POST /projects/{id}/pipeline/template`).

### Acabado visual (tokens y primitivas)
- `frontend/src/styles/tokens.css` ← `docs/design/v2/tokens.css` (radios, `--sep`, `--glass`, `--glass-pop`, `--card-grad`, sombras, `--atmos`, animaciones `rise-in`, `sheet-in`, `fade-in`, `sweep`). Ningún color cambia.
- `styles/index.css`: utilidades `bg-atmos`, `glass`, `glass-pop`, `bg-card-grad`, `shadow-card`, `shadow-pop`, `border-sep`, y retraso escalonado de `rise-in` (`[--rise-delay]`). Con `prefers-reduced-motion: reduce` se anulan `rise-in`, `sheet-in`, `sweep`, el pulso y el `scale` al pulsar.
- Primitivas de shadcn (`components/ui`): `button` (`active:scale-[.97]`, variante píldora), `dialog`/`alert-dialog`/`sheet` (overlay con blur, contenido `glass-pop`, radio 20, `sheet-in`), `card` (`bg-card-grad`, `border-sep`, `shadow-card`, radio xl), `sonner` (abajo en el centro, `glass-pop`, 2,6 s; 6 s si el toast lleva acción), `tooltip`, `select`, `dropdown-menu` (`glass-pop`). Así todas las pantallas heredan el acabado sin tocarlas una a una.
- **Rendimiento**: con el Tablero lleno y una terminal en vivo se mide en WebView2 (Performance de DevTools). Si `backdrop-filter` baja de 60 fps, se quita el blur del fondo atmosférico y de las superficies que quedan sobre la terminal (la cabecera mantiene el vidrio).

### Esqueleto y navegación
- **`AppShell`**: fuera `SidebarProvider`/`AppSidebar`; columna única con `AppHeader` absoluto y el contenido con `padding-top: 56px`. El dock no cambia.
- **`AppHeader` v7**: según `v2/code/components/agentic/app-header.tsx`. `TopNav` con Tablero (tareas abiertas), Ejecuciones (activas) y Ajustes; activo con `aria-current`. «Volver» = `navigate(-1)`, o a la ruta padre si no hay historial. Desaparecen las acciones principales de la cabecera (`nav.ts` > `primary`).
- **`nav.ts`**: pasa a describir la navegación superior y las rutas «de segundo nivel» (Inbox, Consumo, Agentes, Proyectos), que siguen en `routes.tsx` y salen en Ctrl+K y en las migas.
- Las páginas que perdían su acción principal la recuperan en su propia cabecera de página: Tablero («Nueva tarea»), Agentes («Nuevo agente»), Proyectos («Nuevo proyecto»), Ejecuciones («Lanzar ejecución»), Consumo («Exportar CSV»).
- **Tarea ↔ ejecuciones**: el detalle de la tarea ya enlaza sus ejecuciones; se añade en `RunPage` el enlace a su tarea en la cabecera (si tiene).

### Stores de UI (zustand)
- **`stores/dialogs.ts`**: `openNewTask({ agentId?, projectId?, stageId? })`, `openNewAgent()`, `openNewProject()`, `openPalette()`, `openShortcuts()`. Los diálogos se montan una vez en `AppShell`. Las rutas `/agentes/nuevo` y `/proyectos/nuevo` redirigen a su lista y abren el diálogo (enlaces y atajos antiguos siguen funcionando).
- **`stores/ui-prefs.ts`** (persistido en `localStorage`, como el tema y el dock): `singleKeyShortcuts` (por defecto sí), `lastTaskTarget` (`{ projectId, agentId }`), avisos de CLI pospuestos (**no** persistidos: solo en la sesión).

### Atajos (`lib/shortcuts.ts`)
- Un único listener de `keydown` en `window` (`useGlobalShortcuts`, montado en `AppShell`):
  - `Ctrl+K` → paleta. **No actúa si el foco está en la terminal** (`.xterm` o dentro del dock): Ctrl+K es «borrar hasta el final de la línea» en las shells y en los CLIs.
  - `N` → nueva tarea; `?` → ayuda de atajos.
  - Las teclas de un carácter no actúan si: `singleKeyShortcuts` está apagado, hay un modificador pulsado, el foco está en `input`/`textarea`/`select`/`[contenteditable]`/terminal, o hay un diálogo abierto (`[role=dialog]`).
  - `Ctrl+\`` (dock) y `Esc` siguen como ahora.
- La tabla de atajos es un único array que usan el listener, la ayuda (`?`) y las pistas de Ctrl+K.

### Inicio (`pages/home/`)
Sustituye a `DashboardPage`. Rejilla `minmax(0,1fr) 300px` (en < 1280 px la columna de resumen baja debajo).
- **`Greeting`**: fecha (`Intl`, es-ES), sesiones en vivo (`home.counts`), H1 con saludo por franja horaria (sin nombre: la app no sabe cómo se llama el usuario; «Buenos días»), chips trabajando / esperan respuesta (`inbox/summary.pending`) / gastado hoy (`usage/today`).
- **`NeedsYouPanel`**: peticiones pendientes (`useInbox('pending')`) ordenadas aprobación → pregunta → bloqueo → atención/interrumpida → resto, y luego los avisos de CLI. 3 visibles; «Ver todas · n» / «Ver menos» en el sitio. Enlace «Resueltas» → `/inbox?status=resolved`. Vacío: línea «Nada pendiente…». Hover sobre una petición resalta la tarjeta de su agente (estado compartido en el panel por `agentId`).
- **`RequestItem` + `RequestActions`**: se extraen de `InboxPage` (hoy las acciones de cada tipo están dentro de la página) a `components/requests/`. Los usan Inicio, la página de Inbox y el detalle de la tarea, con las mismas mutaciones (`usePermissionItem`, `useAnswerItem`, `useReviewItem`, `useDismissItem`, reanudar).
- **`CliAlertItem`**: se genera en el cliente a partir de:
  - peticiones `quota` y `limit` (ya existen desde la fase 07): se pintan con la anatomía de aviso del sistema en lugar de como petición normal;
  - `/api/clis`: CLI sin sesión o no detectado;
  - `/usage/today` > `limits`: un CLI al 95 % o más de su límite diario (aviso previo; al llegar al 100 % ya existe la petición `limit`).
  Acciones: «Revisar CLIs» → `/ajustes#clis`; «Posponer» → lo oculta en la sesión (store) y toast «Aviso pospuesto». Las peticiones `quota`/`limit` conservan además sus acciones actuales.
- **`AgentGrid` + `AgentCard` v7**: una rejilla (`auto-fill, minmax(250px,1fr)`) con los agentes de `home.agents`; borradores al final. Badge de peticiones, línea `sweep` si `running`, una fila por sesión (estado «esperándote», «reanudable», «iniciando» o cronómetro con `use-now`), secundario «Rol · CC · n en cola» y, al hover/foco, coste y tokens de hoy (de `usage/today.agents`) y «+» → `openNewTask({ agentId })`. Clic/Enter → ficha del agente. Cabecera de la sección: «Agentes · n» y «Nuevo agente».
- **`SummaryAside`**: Proyectos (`home.projects`, «Ver todos» → `/proyectos`, «+» → `openNewProject`), Gasto de hoy (`SpendMeter` con el límite diario de coste; ámbar desde el 80 %; clic → `/consumo`), CLIs (una fila por CLI: tag, nombre, barra con el % de su límite diario y estado de la sesión; «Gestionar» → `/ajustes#clis`). Sin «Conocimiento» ni cuentas.
- Estados: cargando (skeletons), desconectado (el banner global + contenido atenuado con los últimos datos), sin agentes (EmptyState con «Nuevo agente» y plantillas), tema claro.
- `CliReadinessBanner` desaparece de Inicio: sus casos pasan a ser `CliAlertItem`.

### Diálogos
- **`NewTaskDialog`** (reescrito según `v2/code/.../new-task-dialog.tsx`): «Qué hay que hacer» (autofocus), proyecto y agente (sin borradores); si el proyecto tiene pipeline, el selector de agente ofrece también las etapas (como hoy). «Añadir descripción» plegado. Pie: «Guardar en backlog» (ghost) · «Crear y encolar» (primario). Valores iniciales: lo que pase quien lo abre → si no, `lastTaskTarget` → si no, el primero. Toast «T-n en la cola de <agente>» con «Ver tarea».
- **`NewAgentDialog`** (sustituye a `NewAgentPage`, reutiliza `TemplatePicker` y `agent-form.ts`): plantillas en rejilla de 4 + «En blanco»; nombre, rol, CLI, modelo, permisos (segmented) e instrucciones. Crea con `status: draft` y navega a la ficha. Sin equipo ni cuenta.
- **`NewProjectDialog`** (sustituye a `NewProjectPage`, reutiliza `ProjectFormFields` y `FolderPicker`): carpeta (el nombre se propone a partir de ella), nombre, pipeline (plantillas existentes o «Sin pipeline») y color (6 muestras). Crea el proyecto y, si se eligió, su pipeline; si el segundo paso falla, el proyecto queda creado y se avisa.
- **`CommandPalette`**: shadcn `command` (dependencia nueva **`cmdk`**). Grupos de la spec. Agentes y proyectos de las listas ya cacheadas; tareas con `GET /tasks?q=` (debounce 150 ms, `keepPreviousData`). Máximo 14 resultados. Acciones: nueva tarea, nuevo agente, nuevo proyecto, abrir terminal, cambiar tema, pausar/reanudar el scheduler, atajos.
- **`ShortcutsDialog`**: tabla de atajos en dos columnas.

### Otras pantallas
- **Ficha de agente**: nueva pestaña por defecto **«Resumen»** (`/agentes/:id` → `resumen`): cabecera v7 (avatar 52, nombre, rol, estado; «Asignar tarea», «Activar» si es borrador, «Editar» → pestaña General), peticiones del agente (`RequestItem`), tareas (`useTasks({ agentId })`), consumo (`useUsageBreakdown` del agente, referencia `UsageBreakdown.dc.html`) y `ConfigDisclosure` plegado (CLI, modelo, permisos, concurrencia). Las pestañas de edición actuales siguen igual.
- **Detalle de tarea**: los datos de la sesión salen de la columna izquierda a `SessionFactsLine` bajo la terminal. Las peticiones de la tarea usan `RequestItem`.
- **Ejecuciones**: columnas y jerarquía de la v7 (sin cuenta).
- **Ajustes**: índice lateral fijo (`sticky`) con las seis secciones, anclas `#clis`, `#general`… y resaltado de la sección visible (`IntersectionObserver`). En General, interruptor «Atajos de una tecla».
- **Inbox**: sigue como página (ruta `/inbox`, título «Peticiones»), con `RequestItem`, acabado v7 y filtro por `?status=`.
- Tablero, Proyectos, Consumo y la terminal: solo heredan el acabado y recuperan su acción principal en la cabecera de página.

### Textos
Claves nuevas en `frontend/src/i18n/es.json` (`home.*`, `palette.*`, `shortcuts.*`, `requests.*`, `dialogs.*`); se borran las de la sidebar y del Dashboard antiguo que queden sin uso.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/api/home.py`, `services/home.py`, `schemas/home.py` | nuevos: `GET /api/home` |
| `backend/src/agentic_os/api/tasks.py` | modificado: `q` y `limit` en `GET /tasks` |
| `backend/src/agentic_os/api/__init__.py` | modificado: router `home` |
| `backend/tests/test_home_api.py`, `test_tasks_api.py` | nuevo / modificado |
| `frontend/package.json` | modificado: `cmdk` |
| `frontend/src/styles/tokens.css`, `styles/index.css` | modificados: tokens y utilidades v7 |
| `frontend/src/components/ui/{button,dialog,alert-dialog,sheet,card,sonner,select,dropdown-menu,tooltip}.tsx` | modificados: acabado v7 |
| `frontend/src/components/ui/command.tsx` | nuevo (shadcn) |
| `frontend/src/components/layout/AppShell.tsx`, `AppHeader.tsx`, `nav.ts`, `crumbs.tsx` | modificados |
| `frontend/src/components/layout/TopNav.tsx` | nuevo |
| `frontend/src/components/layout/AppSidebar.tsx` (+ test) | borrado |
| `frontend/src/stores/dialogs.ts`, `stores/ui-prefs.ts`, `lib/shortcuts.ts` | nuevos |
| `frontend/src/components/palette/CommandPalette.tsx`, `ShortcutsDialog.tsx` | nuevos |
| `frontend/src/components/requests/RequestItem.tsx`, `RequestActions.tsx`, `CliAlertItem.tsx` | nuevos (extraídos de `InboxPage`) |
| `frontend/src/pages/home/{HomePage,Greeting,NeedsYouPanel,AgentCard,AgentGrid,SummaryAside}.tsx` | nuevos |
| `frontend/src/pages/DashboardPage.tsx`, `components/CliReadinessBanner.tsx` | borrados (sustituidos por Inicio) |
| `frontend/src/api/home.ts`, `api/tasks.ts`, `api/types.ts` | nuevo / modificados |
| `frontend/src/pages/tasks/NewTaskDialog.tsx` | reescrito |
| `frontend/src/pages/agents/NewAgentDialog.tsx`, `pages/projects/NewProjectDialog.tsx` | nuevos; borrados `NewAgentPage.tsx`, `NewProjectPage.tsx` |
| `frontend/src/pages/agents/AgentEditorPage.tsx`, `tabs/SummaryTab.tsx`, `ConfigDisclosure.tsx` | modificado / nuevos |
| `frontend/src/pages/tasks/TaskPage.tsx`, `SessionFactsLine.tsx` | modificado / nuevo |
| `frontend/src/pages/runs/RunsTable.tsx`, `RunPage.tsx` | modificados |
| `frontend/src/pages/settings/SettingsPage.tsx`, `GeneralSection.tsx` | modificados: índice y atajos |
| `frontend/src/pages/InboxPage.tsx` | modificado: usa `RequestItem` |
| `frontend/src/pages/BoardPage.tsx`, `agents/AgentsPage.tsx`, `projects/ProjectsPage.tsx`, `runs/RunsPage.tsx`, `UsagePage.tsx` | modificados: acción principal en la página |
| `frontend/src/routes.tsx` | modificado: Inicio, redirecciones de `nuevo`, pestaña `resumen` |
| `frontend/src/i18n/es.json` | modificado |
| `docs/adr/0013-navigation-home-shortcuts.md` | nuevo |

## Tareas (en orden)
1. [ ] **Línea base de CA1**: contar en la app actual los pasos de los cuatro flujos y anotarlos en `validacion.md`. Capturas «antes» de Inicio y Ajustes.
2. [ ] **Acabado v7**: tokens, utilidades, `prefers-reduced-motion` y primitivas de shadcn. Tests existentes en verde.
3. [ ] **Backend**: `GET /api/home` y `GET /tasks?q=&limit=`, con tests.
4. [ ] **Stores y atajos**: `dialogs`, `ui-prefs`, `lib/shortcuts.ts` con sus tests (guardas de foco, terminal, diálogo y preferencia).
5. [ ] **Esqueleto**: `AppShell` sin sidebar, `AppHeader` v7 con `TopNav`, migas y «Volver»; acciones principales a las páginas; enlace ejecución → tarea; diálogos globales montados.
6. [ ] **Peticiones**: extraer `RequestItem`/`RequestActions` de `InboxPage` y usarlos en Inbox y en el detalle de la tarea (sin cambio de comportamiento; los tests de la Inbox siguen en verde).
7. [ ] **Inicio**: `Greeting`, `NeedsYouPanel` con `CliAlertItem`, `AgentGrid`/`AgentCard`, `SummaryAside`, estados; borrar `DashboardPage` y `CliReadinessBanner`.
8. [ ] **Diálogos**: `NewTaskDialog` reescrito; `NewAgentDialog` y `NewProjectDialog` con las redirecciones de `nuevo`.
9. [ ] **Ctrl+K y `?`**: `cmdk`, `CommandPalette`, `ShortcutsDialog`.
10. [ ] **Ficha de agente** (pestaña Resumen, «Activar», `ConfigDisclosure`), **detalle de tarea** (`SessionFactsLine`) y **Ejecuciones**.
11. [ ] **Ajustes**: índice lateral y «Atajos de una tecla».
12. [ ] **Repaso de pantallas** (Tablero, Proyectos, Consumo, Inbox, terminal) en los dos temas; medida de rendimiento con terminal en vivo y ajuste del vidrio si hace falta.
13. [ ] **ADR 0013**, i18n sin claves huérfanas, `npm run check` y suites del backend en verde; `/code-review`.
14. [ ] **Validación**: tabla antes/después de CA1, capturas comparadas con `v2/screenshots`, prueba manual de atajos con una ejecución real y **revisión con el usuario** (CA11).

## Tests previstos
| Test | Cubre |
|---|---|
| `test_home_api.py`: estados del agente (running, waiting por tarea y por petición, idle, draft), sesiones vivas y reanudables, proyectos con tareas abiertas y quién trabaja, contadores | CA3 |
| `test_tasks_api.py`: `q` por título (mayúsculas y acentos), por `T-n` y por número, `limit` | CA8 |
| e2e existente de HITL (`test_hitl_e2e.py`) sin cambios: las acciones de Inicio usan los mismos endpoints | CA4 |
| `lib/shortcuts.test.ts`: Ctrl+K, `N`, `?`; no actúan en input, terminal, con diálogo abierto, con modificador ni con la preferencia apagada | CA8 |
| `layout/AppHeader.test.tsx`: navegación superior con contadores, activo con `aria-current`, «Volver», sin sidebar | CA2 |
| `routes.test.tsx`: `/inbox`, `/consumo`, `/agentes`, `/proyectos` siguen funcionando; `/agentes/nuevo` y `/proyectos/nuevo` abren el diálogo | CA2, CA7 |
| `home/home.test.tsx`: saludo y chips, «Te necesitan» (orden, 3 + «Ver todas», vacío), aprobar/rechazar/responder desde Inicio, avisos de CLI (cuota, límite ≥ 95 %, sin sesión) y «Posponer», tarjetas (estados, sesiones, hover con consumo y «+»), columna de resumen, estados cargando/desconectado/sin agentes | CA3, CA4, CA5 |
| `tasks/new-task.test.tsx`: apertura con `N`, Ctrl+K y desde una tarjeta (agente preseleccionado), última elección recordada, «Crear y encolar» vs backlog, toast | CA6 |
| `agents.test.tsx` / `projects.test.tsx`: diálogos nuevos, agente creado como borrador y «Activar» en su ficha, proyecto con pipeline | CA7 |
| `palette/palette.test.tsx`: grupos, búsqueda de agentes/proyectos/tareas (`T-12`), acciones, navegación con teclado, sin resultados; ayuda `?` | CA8 |
| `settings.test.tsx`: índice con las seis secciones y anclas, interruptor de atajos | CA9 |
| `inbox.test.tsx`, `tasks.test.tsx`, `runs.test.tsx` existentes, adaptados a `RequestItem` y `SessionFactsLine` | CA4, CA12 |
| Tabla antes/después de pasos (manual) | CA1 |
| Capturas en los dos temas y con `prefers-reduced-motion` (manual) | CA3, CA10 |
| Revisión con el usuario (manual) | CA11 |

## Decisiones (ADR)
- **ADR 0013 · Navegación, Inicio y atajos**:
  - navegación en la cabecera, sin barra lateral; Inicio como centro y las páginas de segundo nivel por ruta y Ctrl+K;
  - un endpoint agregado de solo lectura (`/api/home`) sondeado, en lugar de componer Inicio con N consultas o de añadir un canal de eventos (se puede pasar a WebSocket más adelante sin cambiar la UI);
  - diálogos globales con un store en lugar de páginas `nuevo`;
  - un único gestor de atajos con guardas (terminal, campos, diálogos) y Ctrl+K desactivado dentro de la terminal;
  - los avisos de CLI se derivan en el cliente de datos existentes, sin modelo nuevo; la cuota por cuenta queda para la fase 10.
