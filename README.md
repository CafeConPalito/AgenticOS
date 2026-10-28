# Agentic OS

App de escritorio para orquestar un equipo de agentes de IA (Claude Code, Antigravity CLI…) que trabajan como empleados: colas por agente, pipelines (Requisitos → Desarrollo → QA), terminales en vivo con *human-in-the-loop*, conocimiento y skills.

- Visión: [`docs/vision.md`](docs/vision.md)
- Roadmap y estado de las fases: [`docs/roadmap.md`](docs/roadmap.md)
- Diseño de la interfaz: [`docs/design/`](docs/design/)
- Flujo de trabajo (Spec → Plan → Desarrollo → Validación): [`CLAUDE.md`](CLAUDE.md)
- Licencia: GNU GPLv3 o posterior ([`LICENSE`](LICENSE))

## Instalar
1. Ejecuta `Agentic OS_0.9.0_x64-setup.exe`. Se instala **para tu usuario**, sin permisos de administrador, en `%LOCALAPPDATA%\Agentic OS`. Si falta WebView2, el instalador lo descarga.
2. **SmartScreen**: el instalador no está firmado, así que Windows puede mostrar «Windows protegió su PC». Pulsa «Más información» → «Ejecutar de todas formas». Si el antivirus bloquea `agentic-os-backend.exe`, añádelo como excepción: es el backend de la app, empaquetado con PyInstaller.
3. Instala y abre los CLIs que quieras usar: Claude Code (`irm https://claude.ai/install.ps1 | iex` en PowerShell, luego `claude` y `/login`) y Antigravity CLI (`agy`). En **Ajustes › CLIs detectados** verás si los encuentra y si tienen sesión iniciada.

- **Actualizar**: instala la versión nueva encima. Se conservan la base de datos, los logs y los ajustes; antes de migrar la base de datos se guarda una copia en `<carpeta de datos>\backups\` (las 3 últimas).
- **Desinstalar**: desde «Aplicaciones instaladas» de Windows. La casilla «Borrar los datos de la aplicación» (desmarcada por defecto) borra también `%APPDATA%\AgenticOS`. Si moviste la carpeta de datos a otro sitio, esa carpeta hay que borrarla a mano.
- **Una sola instancia**: abrir la app otra vez trae al frente la ventana que ya está abierta.
- **Si el backend se cae**, la app lo vuelve a abrir sola («Reconectando…»). Si falla tres veces seguidas, muestra «Reintentar» y «Abrir logs».
- **Ejecuciones cortadas** (cierre de la app, caída, reinicio del equipo): quedan «Interrumpidas» y su tarea en «Esperando humano». Con **«Reanudar sesión»** el CLI retoma la misma conversación (`claude --resume` / `agy --conversation`) con un contexto nuevo ([ADR 0012](docs/adr/0012-packaging-and-resume.md)).

## Arquitectura
```
desktop/   Tauri 2 (Rust): ventana nativa; en release lanza el backend como sidecar
frontend/  Vite + React 19 + TypeScript + Tailwind 4 + shadcn/ui
backend/   Python 3.12 + FastAPI (uv)
scripts/   build del sidecar y check local
docs/      visión, roadmap, ADRs, fases y diseño
```

## Requisitos (Windows)
| Herramienta | Versión |
|---|---|
| Python | 3.12 |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.12 |
| Node.js / npm | ≥ 22 / ≥ 10 |
| Rust (rustup, toolchain MSVC) | stable |
| Visual Studio 2022 Build Tools (C++) | necesarias para Tauri |
| WebView2 | incluido en Windows 11 |

## Puesta en marcha
```powershell
npm install                     # dependencias de frontend y desktop + hook pre-commit
uv sync --project backend       # dependencias del backend
```

## Comandos
| Comando | Qué hace |
|---|---|
| `npm run dev` | Backend (`http://127.0.0.1:8765`, con recarga) + UI en el navegador (`http://localhost:5173`) |
| `npm run dev:desktop` | Backend + ventana de Tauri en modo desarrollo |
| `npm run test` | pytest + vitest + cargo test |
| `npm run lint` | ruff + ESLint + Prettier + rustfmt |
| `npm run check` | lint y todos los tests (puerta mínima antes de integrar). `scripts/check.ps1` muestra un resumen |
| `npm run build:backend` | Empaqueta el backend con PyInstaller como sidecar (`desktop/src-tauri/binaries/`) |
| `npm run build:desktop` | Sidecar + frontend + instalador NSIS (`desktop/src-tauri/target/release/bundle/nsis/`) |
| `npm run test:packaged` | Construye el sidecar y pasa los e2e (scheduler, HITL, consumo, reanudación) contra él |
| `npm run smoke:installed` | Prueba de humo de la app instalada: arranca, el backend responde, los datos están en su sitio y al cerrar no queda ningún proceso |

**Firma de código**: `scripts/sign.ps1` firma el sidecar, la app y el instalador si existe `AGENTIC_OS_SIGN_CERT` (huella SHA-1 de un certificado del almacén del usuario; `signtool` del Windows SDK). Sin esa variable no firma nada.

El hook pre-commit (husky + lint-staged) pasa el lint y el formato a los archivos en stage.

## Configuración del backend
Variables de entorno con prefijo `AGENTIC_OS_` (o un archivo `backend/.env`):

| Variable | Por defecto |
|---|---|
| `AGENTIC_OS_HOST` | `127.0.0.1` |
| `AGENTIC_OS_PORT` | `8765` |
| `AGENTIC_OS_DATA_DIR` | La carpeta de `%APPDATA%\AgenticOS\location.json` (si la moviste desde Ajustes) o `%APPDATA%\AgenticOS`. Con esta variable no se puede mover |
| `AGENTIC_OS_LOG_LEVEL` | `INFO` |
| `AGENTIC_OS_LOG_JSON` | `false` |
| `AGENTIC_OS_LOG_FILE` | (en la app empaquetada: `<data_dir>\logs\backend.log`) |
| `AGENTIC_OS_DATABASE_URL` | SQLite en `<data_dir>\agentic-os.db` |
| `AGENTIC_OS_CLI_COMMAND_OVERRIDES` | `{}` (JSON `{"claude": [...], "agy": [...]}` con el comando de cada CLI) |
| `AGENTIC_OS_CLAUDE_CONFIG_FILE`, `AGENTIC_OS_AGY_SETTINGS_FILE` | Los reales (`~/.claude.json`, `~/.gemini/antigravity-cli/settings.json`): de dónde se borra la confianza de los worktrees de tareas. Los tests los apuntan a archivos temporales |

En la app empaquetada, el backend usa un puerto libre asignado al arrancar (ver [ADR 0002](docs/adr/0002-sidecar-protocol.md)).

## Datos y migraciones
- La base de datos es SQLite en la carpeta de datos y se migra sola al arrancar el backend ([ADR 0006](docs/adr/0006-persistence.md)). Antes de aplicar migraciones nuevas se copia en `<carpeta de datos>\backups\`.
- **Ajustes › General** muestra la carpeta de datos y cuánto ocupa, y permite moverla: el backend se reinicia y mueve los datos antes de abrirlos. **Ajustes › Limpieza** borra las ramas `agentic/T-n` ya fusionadas y los logs de terminal más antiguos que la retención (90 días por defecto).
- Para probar sin tocar tus datos reales: `AGENTIC_OS_DATA_DIR=<carpeta temporal>` (vale también para la app empaquetada, que lo pasa al sidecar).
- Nueva migración tras cambiar modelos (revísala antes de hacer commit):
  ```powershell
  uv run --project backend python backend/scripts/new_migration.py "describe el cambio"
  ```

## Ejecuciones (terminales en vivo)
- Cada ejecución es el CLI del agente en una terminal real (ConPTY) que gestiona el backend ([ADR 0007](docs/adr/0007-run-processes.md)). La salida se guarda en `<data_dir>\runs\<id>.log`.
- Cada ejecución arranca con el **contexto de su agente**:
  - su rol e instrucciones;
  - la memoria del proyecto;
  - su modo de permisos («Autónomo», «Restringido» o «Preguntar»);
  - el servidor MCP `agentic-os` con un token propio.

  Lo recibe así ([ADR 0004](docs/adr/0004-per-run-context-and-mcp.md), [ADR 0008](docs/adr/0008-agent-coordination.md)):
  - **Claude Code**: por opciones, aislado de tu configuración global (`--setting-sources project,local --strict-mcp-config`). Sus archivos van en `<data_dir>\runs\<id>\`.
  - **agy**: por un plugin temporal en `.agents/plugins/agentic-os/` del proyecto, excluido de git y borrado al terminar. Solo puede haber una ejecución de agy a la vez por carpeta.
- Herramientas del MCP `agentic-os`:
  - `report_status`: el agente cuenta en qué está;
  - `write_project_memory`: añade notas a la memoria del proyecto;
  - `complete_task`: deja el resumen (y, en las etapas que revisan, el veredicto y, si pueden devolver la tarea a varias etapas, a cuál); Agentic OS cierra el CLI y la ejecución queda «Completada»;
  - `get_context`.

  Los eventos se ven en vivo en la columna «Eventos MCP».
- La primera vez que lances un agente de Claude en modo «Autónomo», Claude Code pide aceptar ese modo. Agentic OS no lo acepta por ti: toma el control de la terminal y respóndelo una vez.
- Los CLIs tienen que estar instalados como ejecutable nativo (`claude.exe`, `agy.exe`): un shim `.cmd` de npm se rechaza, porque `cmd.exe` reinterpretaría el prompt.
- Al cerrar la app, las ejecuciones activas se cortan (no queda ningún CLI vivo) y aparecen como «Interrumpida» al volver a abrirla.
- Para probar con un CLI falso o con otra ruta: `AGENTIC_OS_CLI_COMMAND_OVERRIDES='{"claude": ["ruta\\a\\claude.exe"]}'`.

## Tareas, colas y pipelines
- Una **tarea** (`T-142`) pertenece a un proyecto y la hace el agente de su **etapa** actual o, si el proyecto no tiene pipeline, el agente que elijas ([ADR 0009](docs/adr/0009-scheduler-and-workspaces.md)).
- **Colas**:
  - cada agente recorre la suya en orden: por prioridad y después por posición. Puedes reordenarla en el tablero, en «Colas por agente»;
  - un agente trabaja a la vez en tantas tareas como diga su concurrencia;
  - cada tarea es una sesión nueva del CLI, con el contexto de su proyecto y nada más.
- **Pipeline** (pestaña «Pipeline» del proyecto):
  - etapas en orden, cada una con su agente;
  - una etapa puede **requerir revisión** (la tarea espera en «En revisión» a que la apruebes o la rechaces) o **rechazar** y devolver la tarea a una etapa anterior. El agente lo hace con `complete_task(summary, verdict="rejected")`, hasta un máximo de rechazos;
  - plantillas «Desarrollo web» (Requisitos → Desarrollo → QA) y «Backend y frontend» (Requisitos → Dev backend | Dev frontend → QA).
- **Ramas** ([ADR 0020](docs/adr/0020-branching-pipelines.md)): el pipeline es un **grafo**. Una etapa con varias salidas es una bifurcación y cada salida es una rama con su condición («la tarea toca la API…») o «siempre»:
  - **quién elige las ramas**: una llamada corta a un modelo barato (Claude Code o agy, sin herramientas) que dice qué ramas toma la tarea y por qué; se registra en el historial y su consumo cuenta como el de cualquier sesión. Si falla, eliges tú. Puedes fijar las ramas al crear la tarea, confirmar la decisión antes de empezar, añadir una rama en curso o cancelar otra, y «Probar» las condiciones con una tarea de ejemplo en el editor;
  - **a la vez, y juntas después**: cada rama tomada es una tarea hija (`T-142·backend`) con su cola, su agente y su estado; la tarea que bifurcó espera y sigue cuando llegan todas. En una carpeta directa las ramas van una detrás de otra;
  - **un rechazo repite solo la rama que falló**: tras la unión, la etapa que rechaza nombra la rama a la que devuelve la tarea (`complete_task(summary, verdict="rejected", reject_to="Dev backend")`);
  - **git**: en modo worktree cada rama trabaja en su carpeta y su rama (`agentic/T-142-backend`, desde la de la tarea); al unirse se mezclan en `agentic/T-142`. Si chocan, la tarea espera y los conflictos se resuelven en una carpeta de trabajo o se pasan a un agente.
- **Cuando algo falla**, la tarea queda **«Esperando humano»** con el motivo, y el agente sigue con su cola. Desde la tarea puedes reintentarla, darla por terminada con un resumen o cancelarla. Una ejecución cortada por un reinicio nunca se relanza sola.
- **Workspaces**, según el modo del proyecto:
  - **Carpeta directa**: como mucho una tarea a la vez por proyecto; mientras, el agente adelanta trabajo de otros proyectos.
  - **Git worktree por tarea**: `<carpeta>.wt\T-142` en la rama `agentic/T-142`, creada desde la rama base. Al terminar, lo que quede sin commitear se commitea en la rama y se borra la carpeta. **La rama se conserva** y el merge lo haces tú.
- **Confianza de las carpetas**: la de los worktrees se borra de la configuración de Claude Code y de agy **solo cuando ese CLI no está abierto**, porque los CLIs reescriben esos archivos. Lo pendiente espera en `<data_dir>\trust-cleanup.json`.
- **Pausar el scheduler** (botón del tablero): no arranca tareas nuevas; las que están en marcha siguen.
- **Memoria del proyecto**: son notas con autor. A los agentes les llegan las más recientes hasta unos 12 000 caracteres, y la pestaña avisa cuando no caben todas.

## Inbox y subagentes
- **La Inbox** recoge lo que los agentes necesitan de ti ([ADR 0010](docs/adr/0010-human-in-the-loop.md)):
  - **aprobaciones** de los diálogos de permiso de Claude Code y agy, que se responden desde la Inbox sin tomar el control;
  - **preguntas y bloqueos** (`request_human`): tu respuesta le llega al agente como un mensaje en su terminal;
  - **revisiones**, tareas **sin terminar** (10 minutos esperando sin `complete_task`), tareas que necesitan **atención** porque algo falló, y **entregas**.
- **Notificaciones**: de Windows en la app de escritorio, o del navegador. En Ajustes eliges de qué tipos y si suenan.
- **Subagentes**:
  - un agente con «Puede lanzar subagentes» reparte trabajo con `spawn_subagent`: una ejecución hija en la misma carpeta, cuyo resultado le llega como un mensaje;
  - los subagentes nativos de cada CLI (`Agent` en Claude Code, `invoke_subagent` en agy) también se ven en el **árbol de ejecución** de la tarea.
- **Subtareas**: con «Puede crear tareas», `create_subtask` deja trabajo en cola, ligado a la tarea.
- Depuración: `AGENTIC_OS_HOOK_LOG=<archivo>` guarda en JSONL las cargas de los hooks de los CLIs.

## Consumo y límites
- **Consumo de cada ejecución** ([ADR 0011](docs/adr/0011-usage-and-limits.md)), leído de lo que escribe el propio CLI:
  - **Claude Code**: coste en vivo por su *status line* y cifras exactas (`cost-state`) al cerrar la sesión; el coste es el **equivalente API** en USD;
  - **agy**: solo tokens, de `transcript_full.jsonl`, incluidos los de sus subagentes nativos.
- Se ve en **Consumo** (KPIs, coste o tokens diarios por agente o proyecto, reparto y sesiones, con exportación a CSV), en el **Dashboard** («Consumo de hoy»), en el detalle de la tarea y de la ejecución, y en las listas de agentes, proyectos y ejecuciones.
- **Límites diarios** (Ajustes): USD para Claude Code y tokens para agy. Al superar el de un CLI, el scheduler deja de lanzar tareas de ese CLI hasta el día siguiente; lo que está en marcha sigue.
- **Cuota agotada**: si un CLI avisa de que se ha quedado sin cuota, aparece en la Inbox, la tarea espera y el scheduler frena ese CLI hasta que pulses «Reanudar».

## Conocimiento
La biblioteca da a los agentes documentos tuyos ([ADR 0021](docs/adr/0021-knowledge.md)). Tres niveles: **general** (`/conocimiento`), de un **proyecto** y de un **agente** (pestañas «Conocimiento»).
- **Por referencia**: la app guarda la ruta, no una copia. Si el original se borra o se mueve, la ficha lo avisa («No encontrado») y puedes reubicarlo o quitarlo; si cambia, marca «Ha cambiado» y puedes reprocesarlo.
- **Qué acepta**: PDF, Word, Excel, PowerPoint, Markdown, texto, código, CSV, HTML, imágenes y páginas web. Todo se convierte a Markdown con la misma pipeline; en la ficha puedes ver el original y el Markdown.
- **Imágenes**: las de los documentos se extraen y el OCR (incluido en la app, sin conexión) lee su texto; las páginas escaneadas se leen por OCR. Opcionalmente una IA las describe, con un CLI en modo headless o con un modelo de visión local.
- **Búsqueda**: por significado (modelo local, descargable en Ajustes › Modelos locales) y por palabras para identificadores. Sin modelo, busca solo por palabras.
- **Lo que ve un agente**: un índice de los documentos visibles y el texto entero de los pequeños (hasta un presupuesto), más las herramientas MCP `search_knowledge` y `read_knowledge`.
- **Mientras procesa** se ve el progreso de cada documento y el uso de CPU, GPU y memoria; la cola se puede pausar.
- Ajustes › **Conocimiento** (límites y descripción de imágenes) y › **Modelos locales** (descargar, elegir y borrar; `llama.cpp` no viene en el instalador, se descarga aquí).

### Propuestas de los agentes y grafo
Los agentes también pueden **ampliar** la biblioteca y recorrerla como un grafo ([ADR 0022](docs/adr/0022-knowledge-graph.md)).
- **Proponer**: con `propose_knowledge`, un agente de cualquier CLI propone un documento Markdown nuevo, vinculado a los que usó («derivado de»). **Nunca modifica** un documento existente. Queda «Propuesto»: nadie lo lee hasta que lo aceptes. Aparece en la **Inbox** («Conocimiento propuesto») y en la biblioteca (filtro «Propuestos»).
- **Revisar**: puedes editar el texto, elegir el nivel (el agente solo sugiere) y **Aceptar** (se indexa sin conversión y queda marcado «Generado por agente», con su procedencia en la ficha) o **Rechazar** (se borra; el agente es avisado si repite la propuesta). Una versión nueva de lo que propuso el mismo agente convive con la anterior hasta que pulses «Reemplazar».
- **Controles**: máximo de propuestas por ejecución, tamaño máximo, aviso de duplicados (mismo texto o título, o el mismo contenido con otras palabras) y un interruptor para apagarlas, en Ajustes › Conocimiento.
- **Grafo**: pestaña «Grafo» de cada biblioteca. Un nodo por documento (su aspecto dice si es un fichero, una web, una imagen, algo generado por un agente o una propuesta pendiente; el borde, el nivel), flechas «derivado de» y líneas discontinuas «relacionado» (parecido de contenido, calculado en local con los vectores que ya existen). Filtros, interruptor «Toda la biblioteca», resaltado de lo que responde a una pregunta, clic para abrir y doble clic para ver un vecindario.
- **El grafo ayuda a buscar**: `search_knowledge` lista los vecinos de cada resultado y añade los que también responden; y los agentes tienen `knowledge_map` (temas), `related_knowledge`, `explore_knowledge` (hasta 3 saltos) y `knowledge_path`, todas de solo lectura y limitadas a lo que ese agente puede leer. El probador de búsqueda tiene los modos «Búsqueda», «Explorar» y «Mapa».

## Skills
Instrucciones probadas para tareas concretas (un `SKILL.md` y sus ficheros), en «Conocimiento y skills» ([ADR 0024](docs/adr/0024-skills.md)).
- **Biblioteca en tres niveles**: general (pestaña «Skills»), de un proyecto (Proyecto › Conocimiento) y de un agente (pestaña «Skills» del agente). Si dos se llaman igual, gana la más concreta. Se crean y editan en la app, se apagan, se mueven de nivel y se exportan a `.zip`.
- **Importar**: una carpeta, un `.zip` o un `SKILL.md`, y «De mis CLIs»: las de `~/.claude/skills`, las globales de `agy` y las de los repositorios de tus proyectos, cada una al nivel que elijas. El original no se toca. Las ejecuciones no cargan tus skills personales de Claude; las del repositorio las carga el CLI como parte del proyecto.
- **Historial**: cada cambio es una versión con su autor (tú, un agente, una importación o un registro); diferencias entre dos versiones cualesquiera y «Restaurar».
- **En cada ejecución** se eligen solas las que encajan con la tarea (por significado con el modelo local, o por palabras sin él) y el agente recibe una sección «Skills» con ellas. Las carga con `use_skill` (y sus ficheros con `read_skill_file`), o el CLI las carga por su cuenta: Claude como plugin de la sesión y `agy` dentro de su plugin. Modos **Automática / Siempre / Nunca** por agente y por etapa del pipeline (manda la etapa). El **probador** dice qué skills recibiría una tarea, y la ejecución muestra cuáles se le ofrecieron, cuáles cargó, cómo y en qué versión.
- **Propuestas de los agentes**: con `propose_skill` (una skill nueva o una versión nueva de una existente). Llegan a la **Inbox** («Skill propuesta») y no se usan hasta que las apruebas, con ediciones y el nivel que elijas. No se puede aprobar sin abrir antes sus scripts. Hay una propuesta por ejecución como máximo (ajustable en Ajustes › Skills).
- **Explorar**: las más usadas de los registros públicos (clasificación abierta de *Best Skills by Linkly AI*, skills.sh y las oficiales de Anthropic; SkillsMP y ClawHub se activan en Ajustes) y búsqueda, también pegando la dirección de un repositorio de GitHub. La ficha enseña el `SKILL.md`, los ficheros, la licencia y el análisis de seguridad de la fuente. Se instala exactamente lo revisado, en el nivel que elijas, y se avisa de las versiones nuevas con sus diferencias.
- **Uso**: qué skills se usan más, con filtros (periodo, agente, equipo, proyecto, pipeline, CLI, cuenta, modelo, nivel, origen, vía y «nunca usadas»), orden por cualquier columna, agrupación, gráficos, las ejecuciones de cada cifra y exportación a CSV.

## Conexiones MCP
Servidores MCP externos (GitHub, bases de datos, navegador…) que los agentes usan en sus ejecuciones, configurados desde la app ([ADR 0025](docs/adr/0025-mcp-connections.md)). Página «Conexiones» (`/conexiones`).
- **Catálogo**: se crean con un formulario, una plantilla (GitHub, Playwright, Postgres, SQLite, Filesystem, Fetch, Context7, Linear, Notion), pegando un bloque JSON `mcpServers` o importando las de tus CLIs (el original no cambia). Se prueban (lista sus herramientas, con errores en palabras), se apagan, se exportan y se borran.
- **Secretos**: van al almacén de credenciales del sistema; en la base de datos solo hay marcadores. La API no los devuelve y se tapan (`•••`) en el terminal, el log y los visores.
- **Herramientas**: se eligen cuáles puede llamar el agente y cuáles no piden permiso en el modo Restringido.
- **OAuth**: «Conectar» abre el navegador; los *tokens* se guardan en el almacén del sistema y se renuevan solos. Si falla, la conexión pide volver a conectar y avisa en la Inbox.
- **Dónde llegan**: general, proyecto o agente (gana el más concreto); un agente o una etapa del pipeline pueden quitar una. La app escribe la configuración solo para esa ejecución (Claude: `mcp.json` de la ejecución; `agy`: el plugin del espacio de trabajo, que se retira al terminar) y no toca la configuración de tus CLIs. Las conexiones SSE no funcionan en `agy` y se omiten con aviso.
- **En la ejecución**: panel «Conexiones MCP» con lo recibido, el estado y las llamadas a herramientas externas.
- **Explorar**: los más usados del registro oficial de MCP y de Smithery, y búsqueda por paquete o repositorio (npm, PyPI, GitHub). La ficha enseña el comando exacto y lo que falta; instalar no ejecuta nada y fija la versión. Las versiones nuevas se avisan, nunca se aplican solas.
- **Límite conocido**: el agente puede leer las variables de entorno de su proceso, y el servidor `stdio` hereda las del CLI.

## Agente Arquitecto
Crea y mejora agentes, equipos y pipelines conversando ([ADR 0026](docs/adr/0026-meta-agents.md)). Pantalla «Crear con el Arquitecto» (Agentes › Arquitecto, Inicio y la paleta): chat a la izquierda y la **ficha en vivo** a la derecha.
- **Un CLI por conversación** (Claude o `agy`, a elegir en Ajustes › Arquitecto): se duerme por inactividad y se retoma con su historial; «Reiniciar» lo deja limpio. Solo usa lo que existe (CLIs, cuentas, modelos, skills, documentos y conexiones) y nunca escribe fuera de su ficha.
- **Nada cambia sin tu aprobación**: un agente nuevo nace como **borrador** (sin tareas hasta aprobarlo, con sus skills propuestas); mejorar un agente activo crea una **propuesta de cambios** que revisas campo a campo (las instrucciones como diff) y aplicas entera o en parte, con conflicto si lo editaste a mano. Lo aplicado queda en el Historial del agente.
- **Campos fijados**: lo que editas a mano en la ficha queda con candado y el Arquitecto no lo toca salvo que lo sueltes.
- **Equipos y pipelines**: la ficha tiene pestañas Equipo · Agentes · Pipeline (con vista previa del grafo); «Aprobar todo» crea los agentes, el equipo y el pipeline de un proyecto en una sola operación. «Mejorar con el Arquitecto» está también en el equipo y en el editor de pipeline.
- **`propose_agent`**: un agente con el permiso «Puede proponer agentes» propone otro (una por ejecución); llega como borrador con su origen y motivo y aviso en la Inbox.
- **Plantillas y compartir**: «Guardar como plantilla», «Exportar» e «Importar» (formato `agentic-os.agent`, sin secretos). Las plantillas del usuario salen en el selector de nuevo agente.
- **Consumo**: cada conversación es una ejecución `architect` que cuenta en el panel de consumo y en el límite diario.

## Apariencia, avatares, Acerca de y registros
Personalización y soporte ([ADR 0027](docs/adr/0027-personalization-support.md)).
- **Temas**: Ajustes › **Apariencia**. Cinco temas incluidos (Oscuro navy, Claro, Alto contraste, Cálido y Grafito) o **Seguir al sistema**. «Personalizar» crea un tema propio que parte de otro y se edita con vista previa en toda la app: colores, estados, terminal (fondo, texto y 16 ANSI), tipografía, escala de texto, densidad y radio, con aviso de contraste (WCAG AA, sin bloquear). Los temas propios se exportan e importan como JSON (`agentic-os.theme`) y se guardan en el backend, no en el navegador.
- **Avatares**: en la pestaña General de la ficha del agente, un búho de la galería (13 ilustraciones propias en SVG), una **foto** (hasta 2048 px por lado, encuadrada en la app) o las iniciales. Solo se guarda el recorte (WebP 256 × 256, sin metadatos); la foto original no sale del navegador. La imagen viaja con la exportación del agente.
- **Acerca de** (`/acerca-de`): versión, autoría, licencia GPLv3 con su texto completo, licencias de terceros, «Informar de un error» (`mailto`) y **«Preparar registros para enviar»**.
- **Registros para soporte**: genera un `.zip` en local con los registros del backend y de la app de escritorio, los errores recientes de la interfaz y un `info.txt` del sistema, sin salidas de ejecuciones ni contenido tuyo. Los secretos se ocultan al escribir cada línea y de nuevo al empaquetar; lo revisas y lo adjuntas tú al correo. No se envía nada solo ni hay telemetría.
- **Regenerar recursos**: `uv run --project backend python scripts/licenses.py` rehace la lista de licencias de terceros (un test falla si se queda atrás de los *lockfiles*) y `uv run --project backend python scripts/owls.py` rehace los SVG de los búhos.

## Dictado por voz
Dictas en lugar de escribir ([ADR 0023](docs/adr/0023-dictation.md)). La transcripción es **local**: Whisper (`whisper.cpp`) corre en tu equipo, el audio no sale de él, nunca se guarda y funciona sin conexión.
- **Dónde**: un micrófono en los campos de texto largos (descripción de la tarea, resumen y motivo de rechazo, instrucciones y descripción del agente, memoria del proyecto, prompt de una ejecución, respuestas y rechazos de la Inbox, propuestas y fichas de conocimiento). La respuesta de la Inbox crece con el texto; `Intro` la envía y `Mayús+Intro` hace un salto de línea.
- **Cómo**: clic en el micrófono para empezar y otro para terminar, o **mantén pulsado `Ctrl+Espacio`** (configurable) con el cursor en el campo, habla y suelta. `Esc` cancela. Se ve el nivel y el tiempo; a los 5 minutos (configurable) se corta y se transcribe lo grabado.
- **El texto** entra donde estaba el cursor al empezar (o sustituye la selección), aunque sigas escribiendo mientras transcribe. Las transcripciones van de una en una.
- **Primera vez**: el micrófono ofrece descargar el motor y el modelo recomendado (`Whisper small`, 190 MB) y empieza a usarlo al terminar. En Ajustes › **Modelos locales** hay también uno rápido (`base`) y uno más preciso pero lento (`large-v3 turbo`).
- **Ajustes › Dictado**: activar, idioma, atajo, micrófono (con prueba de nivel), duración máxima y **vocabulario**. Los nombres de tus agentes, proyectos, equipos y etapas se pasan solos como pista a Whisper para que los acierte.

## API (backend)
| Ruta | Para qué |
|---|---|
| `GET /api/health` | Estado y versión |
| `/api/knowledge/docs`, `POST …/docs/files · url`, `PATCH/DELETE …/docs/{id}`, `POST …/docs/{id}/relocate · reprocess · open · reveal`, `GET …/docs/{id}/markdown · images · original` | Documentos de la biblioteca: añadir por ruta o dirección, editar, mover de nivel, reubicar, reprocesar y verlos |
| `POST /api/knowledge/search · explore`, `GET /api/knowledge/queue · system`, `POST …/queue/pause · resume`, `WS /api/knowledge/events` | Probar la búsqueda y la exploración del grafo, cola, carga del equipo y eventos en vivo |
| `POST /api/knowledge/docs/{id}/accept · reject`, `GET /api/knowledge/docs?review=proposed&origin=agent` | Revisar las propuestas de los agentes |
| `GET /api/knowledge/graph?project_id&agent_id&all` | Grafo de documentos: nodos, vínculos «derivado de» y «relacionado» y temas |
| `/api/skills`, `GET/PATCH/DELETE /api/skills/{id}`, `POST …/{id}/versions · restore/{version}`, `GET …/{id}/versions · diff · files/{path} · export · origin` | Biblioteca de skills, versiones, diferencias y ficheros |
| `POST /api/skills/import · cli-import`, `GET /api/skills/cli-scan` | Importar por ruta y desde los CLIs |
| `GET/PUT /api/agents/{id}/skill-modes · /api/stages/{id}/skill-modes`, `POST /api/skills/try`, `GET /api/runs/{id}/skills` | Modos, probador y skills de una ejecución |
| `GET /api/skills/proposals/pending · {version}`, `POST …/{version}/accept · reject` | Propuestas de los agentes |
| `GET /api/skills/registries · registries/popular · registries/search`, `POST …/registries/preview · install`, `POST /api/skills/updates/check · {id}/update-preview · {id}/update` | Explorador de registros públicos e instalaciones |
| `GET /api/skills/stats · stats/daily · stats/runs · stats.csv`, `GET/PUT /api/settings/skills` | Estadísticas de uso y ajustes de skills |
| `POST /api/dictation/transcribe · warmup`, `GET /api/dictation/status`, `GET/PUT /api/settings/dictation` | Dictado por voz: el cuerpo de `transcribe` es el WAV (16 kHz, mono) y devuelve el texto; estado; ajustes |
| `GET/PUT /api/settings/knowledge`, `/api/local-models`, `GET/PUT /api/settings/local-models · huggingface-token` | Ajustes de la biblioteca, modelos y motores locales y su selección |
| `/api/agents`, `/api/agents/{id}`, `POST /api/agents/{id}/duplicate`, `GET /api/agent-templates` | Agentes y plantillas |
| `/api/projects`, `/api/projects/{id}`, `POST /api/projects/{id}/open` | Proyectos (con el estado git calculado al leerlos) |
| `/api/projects/{id}/memory`, `/api/projects/{id}/memory/{note_id}` | Notas de la memoria del proyecto |
| `GET/PUT/DELETE /api/projects/{id}/pipeline`, `POST …/pipeline/template · validate · decide-preview` | Pipeline del proyecto como grafo (etapas y enlaces; las etapas y enlaces conservan su id), validarlo sin guardar y probar las condiciones de una bifurcación |
| `/api/tasks?project_id&agent_id&status`, `/api/tasks/{id}`, `GET /api/tasks/{id}/events` | Tareas e historial |
| `POST /api/tasks/{id}/enqueue · retry · complete · review · cancel · open-worktree` | Acciones sobre una tarea (en una rama, sobre esa rama) |
| `GET /api/tasks/{id}/decisions`, `POST /api/tasks/{id}/decision · lanes` | Decisiones de rama de una tarea, elegirlas (o cambiar una propuesta) y añadir una rama en curso |
| `GET /api/tasks/{id}/join`, `POST /api/tasks/{id}/join/editor · join/editor/finish · join/agent` | Conflictos al unir las ramas y cómo resolverlos |
| `GET/PUT /api/agents/{id}/queue` | Cola de un agente / reordenarla |
| `GET /api/scheduler`, `POST /api/scheduler/pause · resume` | Estado y pausa global del scheduler |
| `GET /api/inbox?status=`, `GET /api/inbox/summary` | Inbox y contador (con los elementos aún sin notificar) |
| `POST /api/inbox/{id}/answer · approve · reject · review · dismiss · notified · resume` | Acciones de la Inbox (`resume`: tras «Cuota agotada») |
| `GET /api/usage/summary · daily · breakdown · sessions · sessions.csv ?from&to&agent_id&project_id` | Consumo del periodo (días locales; 30 días por defecto) |
| `GET /api/usage/today`, `GET/PUT /api/settings/usage-limits` | Consumo de hoy con el estado de los límites, y límites diarios |
| `GET/PUT /api/settings/notifications` | Ajustes de notificaciones |
| `GET /api/tasks/{id}/tree`, `GET /api/tasks?parent_task_id=` | Árbol de ejecución y subtareas |
| `POST /api/runs/{id}/permission {approve}` | Responder al diálogo de permiso abierto del CLI |
| `GET /api/clis?refresh=true` | CLIs detectados: versión, modelos, sesión iniciada y cuándo se comprobaron |
| `POST /api/runs/{id}/resume` | «Reanudar sesión»: una ejecución nueva que retoma la conversación del CLI |
| `GET /api/settings/data-dir`, `POST /api/settings/data-dir/open · move` | Carpeta de datos: ruta y tamaño, abrirla y moverla (reinicia el backend) |
| `GET /api/maintenance/branches`, `POST /api/maintenance/branches/delete` | Ramas `agentic/T-n` por proyecto y borrarlas (las no fusionadas, con `force`) |
| `GET/PUT /api/settings/maintenance`, `POST /api/maintenance/logs/cleanup` | Retención de los logs de terminal y limpieza inmediata |
| `POST /api/runs`, `GET /api/runs?agent_id&project_id&task_id&active`, `GET /api/runs/{id}` | Ejecuciones: lanzar un agente sobre un proyecto con un prompt, listar y consultar |
| `POST /api/runs/{id}/control` (`take`/`release`), `POST /api/runs/{id}/stop` | Tomar o devolver el control de la terminal; parar (salida ordenada y, si no, forzada) |
| `GET /api/runs/{id}/events` | Eventos de la ejecución (herramientas MCP, hooks y acciones de Agentic OS) |
| `WS /api/runs/{id}/terminal?client_id=` | Terminal en vivo: `snapshot`, `output`, `state`, `event`, `usage`, `exit`; el cliente envía `input` y `resize` |
| `/r/<token>/mcp`, `POST /r/<token>/hook/<evento>` | Para los CLIs de los agentes: servidor MCP `agentic-os` y hooks (token por ejecución) |

Los errores tienen la forma `{"detail": {"code", "message", "field"}}`; la interfaz traduce por `code`.

## Licencia

Made By Café Con Palito with ❤️ — Albano Díez de Paulino.

Copyright (C) 2026 Albano Díez de Paulino

Agentic OS es software libre: puedes redistribuirlo y modificarlo bajo los términos de la **GNU General Public License**, publicada por la Free Software Foundation, en su versión 3 o (a tu elección) cualquier versión posterior. Se distribuye con la esperanza de que sea útil, pero **sin ninguna garantía**, ni siquiera la implícita de comerciabilidad o idoneidad para un fin concreto. El texto completo está en [`LICENSE`](LICENSE).

Errores y sugerencias: [contacto@cafeconpalito.com](mailto:contacto@cafeconpalito.com).
