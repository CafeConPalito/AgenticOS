# Fase 02: Dominio y CRUD (Agentes y Proyectos) · Spec

- **Estado**: aprobada (2026-10-09)
- **Rama**: `phase/02-dominio-crud`

## Objetivo
Dar a Agentic OS persistencia y sus dos entidades base: **agentes** (quién trabaja y cómo) y **proyectos** (dónde se trabaja). Al acabar podrás crear, editar y borrar agentes, también a partir de plantillas, y proyectos desde la app. Los datos quedan guardados en una base de datos local y las pantallas siguen el diseño de `docs/design/`. Todavía no se ejecuta ningún agente (fases 03–05).

## Alcance
### Dentro
**Persistencia**
- Base de datos SQLite en la carpeta de datos (`%APPDATA%\AgenticOS\agentic-os.db`), con SQLAlchemy 2 y migraciones Alembic que se aplican solas al arrancar el backend.
- Todas las entidades llevan `workspace_id` (un único workspace por ahora; preparado para multiusuario).

**Agentes**
- Campos:
  - identidad: nombre, rol, descripción, color, avatar (inicial);
  - ejecución: CLI (`claude` | `agy`), modelo e instrucciones (markdown);
  - permisos y capacidades: modo de permisos (Autónomo / Restringido / Preguntar), herramientas permitidas (Leer archivos, Editar archivos, Terminal, Git, Web, Navegador, MCP agentic-os), concurrencia máxima (1–5, por defecto 1), «Puede lanzar subagentes», «Puede crear tareas»;
  - estado: activo / borrador (el borrador servirá para las propuestas del Arquitecto en la fase 11).
- API REST: listar, obtener, crear, actualizar, borrar y duplicar.
- **Plantillas**: Analista, Desarrollador, QA, Redactor y Comercial, con rol, instrucciones de partida, color, CLI y permisos razonables. Se elige una al pulsar «Nuevo agente» (o «En blanco») y después todo es editable.
- **Catálogo de CLIs** (`GET /api/clis`):
  - si cada CLI está instalado, su ruta y su versión;
  - los modelos disponibles: alias de Claude y la lista de `agy models`, cacheada.

  Lo usa el selector de CLI y modelo del editor; un CLI no instalado aparece como «No detectado».
- Pantallas (según `screens.md` §2 y las capturas `02` y `03a`–`03c`):
  - **Lista de agentes**: nombre y rol con avatar, CLI, modelo y estado. Las columnas de cola y consumo muestran «—» hasta las fases 05 y 07.
  - **Editor en pestañas**: General, Instrucciones (editor markdown con vista previa) y Ejecución (CLI, modelo, permisos, herramientas, concurrencia e interruptores). Conocimiento, Skills e Historial aparecen como «Disponible en próximas fases».
  - Crear, guardar (con aviso si hay cambios sin guardar), duplicar y borrar con confirmación.
  - Estado vacío con plantillas.

**Proyectos**
- Campos: nombre, color, descripción, ruta de la carpeta, modo de workspace (carpeta directa | git worktree por tarea), memoria del proyecto (markdown) y fechas.
- **Git** detectado al vuelo (sin guardarlo): si la carpeta es un repo, la rama actual y si tiene cambios sin commitear.
- **Validación**:
  - la ruta existe y es una carpeta (con opción de crearla si no existe);
  - no hay dos proyectos con la misma ruta;
  - el modo «worktree» solo se permite si la carpeta es un repo git.
- **Selector de carpeta nativo** en la app de escritorio (diálogo del sistema vía Tauri); en el navegador, campo de texto.
- API REST: listar, obtener, crear, actualizar y borrar. Borrar el proyecto **no toca la carpeta**.
- Pantallas (según `screens.md` §3 y las capturas `05` y `06a`/`06c`):
  - **Lista de proyectos**: nombre con color, ruta, rama git y última actividad. Pipeline y tareas abiertas muestran «—».
  - **Detalle en pestañas**:
    - Resumen: datos, estado git y botón «Abrir carpeta» en el explorador;
    - Memoria del proyecto: editor markdown;
    - Ajustes: ruta, modo de workspace, nombre, color y borrar;
    - Tareas, Pipeline y Conocimiento: «Disponible en próximas fases».

**Transversal**
- Botones primarios de la cabecera activos: «Nuevo agente» y «Nuevo proyecto».
- Rutas: `/agentes`, `/agentes/nuevo`, `/agentes/:id/:tab`, `/proyectos`, `/proyectos/nuevo`, `/proyectos/:id/:tab`.
- Breadcrumb navegable (Agentes / Dev · Desarrollador).
- Toasts de confirmación y de error, y todos los textos en `es.json`.

### Fuera
- Pipelines, etapas y tareas, tanto modelos como UI (fase 05; el editor de pipeline se mueve también a la 05).
- Ajustes, nombre del usuario y saludo del Dashboard (fase 08 o cuando se decida).
- Conocimiento, Skills e Historial de ejecuciones (fases 09, 10 y 03–07).
- Arquitecto (fase 11) e importar o exportar agentes.
- Ejecutar agentes (fases 03–05).

## Historias de usuario
- Como usuario, quiero crear un agente «Desarrollador» a partir de una plantilla, ajustar su modelo y sus permisos, y encontrarlo igual al reiniciar la app.
- Como usuario, quiero registrar la carpeta de un proyecto existente, ver si es un repo git y en qué rama está, y escribir notas en su memoria.
- Como usuario, quiero que la app me impida errores evidentes: carpeta inexistente, proyecto duplicado o modo worktree sin git.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | La BD se crea y migra sola al arrancar; los datos sobreviven a un reinicio del backend y de la app empaquetada | Test (migración sobre una BD vacía y sobre una existente) + prueba manual con el ejecutable |
| CA2 | API de agentes: listar, crear (también desde plantilla), obtener, actualizar, duplicar y borrar, con validación (nombre obligatorio, CLI válido, concurrencia 1–5) y errores 404/422 coherentes | Tests de la API |
| CA3 | API de proyectos: CRUD con validación de ruta (existe / crear / duplicada) y de worktree sin git; git detectado (repo sí/no, rama, cambios) | Tests de la API con carpetas temporales y un repo git temporal |
| CA4 | `GET /api/clis` informa de la instalación, la versión y los modelos de Claude y agy; si un CLI no está, responde sin error | Tests con el CLI simulado + comprobación manual con los CLIs reales |
| CA5 | Pantallas de Agentes (lista, plantillas, editor de 3 pestañas, duplicar, borrar) funcionales y fieles al diseño | Tests de componentes (vitest) + comparación con las capturas `02` y `03a`–`03c` |
| CA6 | Pantallas de Proyectos (lista, alta con selector de carpeta, Resumen, Memoria, Ajustes, borrar) funcionales y fieles al diseño | Tests de componentes + comparación con las capturas `05`, `06a` y `06c` + prueba manual del selector nativo en la app de escritorio |
| CA7 | Aviso de cambios sin guardar al salir de un editor con cambios | Test de componente |
| CA8 | `check` en verde; README, roadmap y ADRs actualizados | Salida del `check` + revisión |

## Riesgos y preguntas abiertas
- **`agy models` tarda 2–5 s**: se cachea en el backend (TTL de 10 min), con un botón de refresco en el selector.
- **Concurrencia en SQLite**: un solo proceso de backend y sesiones cortas, sin problema en esta fase. Postgres llega en la fase 13.
- **Carpetas en red o con permisos limitados**: se validan al guardar; si no son accesibles, el error se muestra en el formulario.
- **Herramientas permitidas**: se guardan como capacidades genéricas; su traducción a los flags de cada CLI es de la fase 04 (ADR 0004).
