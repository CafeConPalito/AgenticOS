# Prompt para Claude Design: interfaz de Agentic OS

> Copia todo lo que hay debajo de la línea y pégalo en Claude Design. Cuando tengas el resultado, exporta o guarda en `docs/design/` las pantallas, los tokens y el código o HTML si lo da.

---

Diseña la interfaz de **Agentic OS**, una aplicación de escritorio (Windows, ventana de 1280–1920 px de ancho) para orquestar un equipo de **agentes de IA que trabajan como empleados**. Cada agente es un CLI de IA (Claude Code, Antigravity/Gemini…) que se ejecuta en su propia terminal real. El usuario es un desarrollador o emprendedor técnico que dirige varios proyectos a la vez y quiere ver, controlar e intervenir en lo que hacen sus agentes.

## Estilo
- Herramienta profesional de productividad para desarrolladores, densa en información pero tranquila. Referencias: Linear, Raycast, Vercel dashboard, Warp terminal.
- **Identidad de color: azul navy como color principal y textos en blanco.** El tema principal es oscuro sobre una base navy (fondos, barra lateral y superficies en distintos tonos de navy, p. ej. alrededor de `#0A1A33`–`#13284D`), con texto blanco (`#FFFFFF`) y texto secundario blanco atenuado. El color `--primary` es navy; para los botones primarios y los elementos activos usa una variante navy más luminosa que contraste bien, siempre con texto blanco.
- Modo claro secundario y coherente: fondos claros con el navy como color principal en botones, barra lateral y elementos activos (con texto blanco sobre navy).
- **Tipografía: Ubuntu** (Google Fonts) para toda la UI, y **Ubuntu Mono** para terminales, IDs y logs.
- Colores semánticos de estado que funcionen sobre fondo navy: en cola, ejecutando, esperando humano, en revisión, hecho, fallido, cancelado.
- Cada agente tiene un **avatar o icono y un color propio** para reconocerlo en todas partes (tablero, colas, terminales).
- Implementable con **React + Tailwind + shadcn/ui** (Radix): usa sus patrones de componentes (Sidebar, Card, Table, Tabs, Dialog, Sheet, Command, Badge, Tooltip).
- Todos los textos de la interfaz **en español**.

## Estructura general
- **Barra lateral izquierda** colapsable con el logo "Agentic OS" y estas secciones: Dashboard, Agentes, Proyectos, Tablero, Inbox (con contador de pendientes), Consumo y Ajustes. Abajo, el estado del backend ("Conectado") y el cambio de tema.
- **Cabecera** con breadcrumb, buscador o paleta de comandos (Ctrl+K) y un botón primario contextual (p. ej. "Nueva tarea").
- **Panel de terminal acoplable** abajo o a la derecha (estilo VS Code) con pestañas por ejecución, que se puede abrir desde cualquier pantalla.

## Pantallas a diseñar
1. **Dashboard**
   - Tarjetas de cada agente con su estado (inactivo / trabajando en "Tarea X · Proyecto Y" con tiempo transcurrido / esperando humano), su cola (n tareas) y su concurrencia (1/1).
   - Actividad reciente (timeline de eventos).
   - Aprobaciones pendientes destacadas.
   - Consumo de hoy (tokens y coste).
2. **Agentes (lista + detalle/editor)**
   - Lista: nombre, rol, CLI (Claude Code / Antigravity) con su logo, modelo, estado, tareas en cola, y consumo del mes.
   - Editor en pestañas:
     - **General**: nombre, rol, avatar y color, descripción.
     - **Instrucciones**: editor del system prompt en markdown.
     - **Ejecución**: CLI, modelo, modo de permisos (Autónomo / Restringido / Preguntar), herramientas permitidas, concurrencia máxima, interruptores "Puede lanzar subagentes" y "Puede crear tareas".
     - **Conocimiento**: documentos de este agente.
     - **Skills**.
     - **Historial**: ejecuciones anteriores.
   - Un estado **"Borrador propuesto por el Agente Arquitecto"** con un banner para aprobar o rechazar.
3. **Proyectos (lista + detalle)**
   - Lista: nombre, ruta de la carpeta, git (rama), pipeline asignado, tareas abiertas, último movimiento.
   - Detalle en pestañas: Resumen, Tareas, Pipeline, Memoria del proyecto (notas que escriben los agentes, editables), Conocimiento, Ajustes (modo de workspace: carpeta directa o git worktree por tarea).
   - **Editor visual de pipeline**: etapas en fila (Requisitos → Desarrollo → QA), cada una asignada a un agente; flecha de "rechazo" de QA a Desarrollo; añadir o reordenar etapas.
4. **Tablero (Kanban)**
   - Columnas por estado: Backlog, En cola, En ejecución, Esperando humano, En revisión, Hecho; y otra vista agrupada por etapa del pipeline.
   - Filtro por proyecto (o "Todos los proyectos") y por agente.
   - Tarjeta de tarea: título, proyecto (chip de color), etapa, agente asignado (avatar), prioridad, subtareas (n/m), tiempo y coste acumulados; si se está ejecutando, indicador animado.
   - Vista alternativa **"Colas por agente"**: una fila por agente con su tarea actual y las siguientes en orden, de varios proyectos (con arrastrar para reordenar).
5. **Detalle de tarea / ejecución**: la pantalla más importante.
   - Izquierda: descripción, etapa, historial de transiciones, subtareas, resultado o resumen del agente.
   - Centro: la **terminal en vivo** (xterm, fondo oscuro, monoespaciada), por defecto en "Solo lectura (observando)" y con un botón claro **"Tomar control"**, que cambia el estado visual a "Estás interviniendo" con un borde de color de aviso, y el botón "Devolver al agente".
   - Derecha: **árbol de ejecución** (la ejecución principal y los subagentes anidados, cada uno con estado y duración; al hacer clic se abre su terminal), timeline de eventos MCP ("update_status: implementando el login…") y consumo de la sesión (tokens de entrada, salida y caché, coste, duración, ID de sesión del CLI).
   - Acciones: pausar, cancelar, reintentar, abrir carpeta o worktree.
6. **Inbox**: bandeja de peticiones de los agentes.
   - Tipos: Aprobación (p. ej. "¿Puedo ejecutar `npm install`?"), Pregunta ("¿Usamos Postgres o SQLite?"), Bloqueo y Tarea completada.
   - Cada elemento muestra el agente, el proyecto, el contexto y acciones rápidas (Aprobar / Rechazar / Responder con texto / Abrir terminal).
   - Filtros: pendientes y resueltas.
7. **Consumo**
   - KPIs: tokens, coste y horas de agente del periodo.
   - Gráficas por agente y por proyecto en el tiempo.
   - Tabla de sesiones de CLI (agente, proyecto, tarea, modelo, tokens, coste, duración), ordenable y con selector de periodo.
8. **Conocimiento y Skills** (puede ser un componente reutilizable dentro de Ajustes, Proyecto y Agente)
   - Un selector de nivel: General / Proyecto / Agente.
   - Zona de subida (arrastrar archivos: md, código, PDF, Word, Excel, imágenes; o pegar una URL).
   - Lista de documentos con su estado de indexado.
   - Biblioteca de skills con interruptores de activación, la etiqueta "Autoseleccionada" y el estado "Propuesta por un agente – pendiente de aprobar".
9. **Crear agente con el Arquitecto**: un flujo conversacional (chat a la izquierda y, a la derecha, la ficha del agente que se va rellenando en vivo: rol, prompt, CLI, skills, conocimiento) con un botón "Crear borrador".
10. **Ajustes**: CLIs detectados (ruta, versión, sesión iniciada sí/no, botón "Comprobar"), carpeta de datos, notificaciones, idioma y tema.

## Estados y detalles a incluir
- Estados vacíos con una llamada a la acción ("Aún no tienes agentes – Crea tu primer agente o usa una plantilla: Analista, Desarrollador, QA, Redactor, Comercial").
- Estados de carga (skeletons) y de error (backend desconectado).
- Notificación tipo toast: "QA ha rechazado 'Login con Google' → vuelve a Desarrollo".
- Indicadores en vivo sutiles (punto pulsante) para los agentes que están trabajando.
- Accesibilidad: contraste AA y foco visible.

## Entregables
- Las pantallas anteriores en el tema navy oscuro (y como mínimo Dashboard y Detalle de tarea también en claro).
- Un **mini design system**: paleta con tokens (CSS variables compatibles con shadcn: `--background`, `--foreground`, `--primary`, `--muted`, `--accent`, `--destructive`, `--border`, `--ring` y los tokens de estado), tipografía, radios, espaciado, y los componentes clave (tarjeta de agente, tarjeta de tarea, badge de estado, elemento de inbox, panel de terminal, nodo del árbol de ejecución).
- Si es posible, el código React + Tailwind de los componentes clave.

Usa datos de ejemplo realistas: agentes "Ana · Analista" (Claude Code), "Dev · Desarrollador" (Claude Code), "Quique · QA" (Antigravity), "Rita · Redactora" (Antigravity); proyectos "Tienda online", "App reservas" y "Blog corporativo".
