# Prompt para Claude Design: revisión de UX/UI (fase 09)

> **Cómo usarlo**
> 1. Abre en Claude Design el proyecto del diseño original de Agentic OS. Si ya no lo tienes, adjunta `docs/design/prototype/Agentic OS.dc.html` (con `support.js`), `docs/design/tokens.css` y las capturas de `docs/design/screenshots/`.
> 2. Adjunta también **capturas de la app real v1.0** (Dashboard, Agentes, un proyecto, Tablero, una tarea, Inbox, Ejecuciones, Consumo y Ajustes): reflejan lo que existe de verdad, que no siempre coincide con el prototipo.
> 3. Copia todo lo que hay debajo de la línea y pégalo.
> 4. Guarda el resultado en `docs/design/` (capturas nuevas en `screenshots/` con el sufijo `-v2`, el prototipo actualizado en `prototype/` y las notas de los cambios). Avísame cuando esté y lo reviso como en `revision.md`.

---

Partimos del diseño de **Agentic OS** que ya hiciste (adjunto): app de escritorio (Windows, 1280–1920 px) para orquestar agentes de IA que trabajan a través de CLIs (Claude Code, Antigravity). La v1.0 ya está construida siguiendo ese diseño. Ahora quiero **una revisión de UX/UI, no un diseño nuevo**.

## Qué se mantiene
- La identidad visual: navy con textos blancos, tema claro secundario, Ubuntu / Ubuntu Mono, los tokens de `tokens.css`, los colores de estado y los de cada agente.
- Los componentes existentes (AgentCard, TaskCard, StatusBadge, InboxItem, TerminalPanel, árbol de ejecución…), salvo los cambios de abajo.
- Stack: React + Tailwind 4 + shadcn/ui + lucide-react. Textos en español.

## Problemas detectados al usarla
1. **Demasiados pasos** en las tareas habituales: crear y encolar una tarea, aprobar una petición, ir a la tarea en la que trabaja un agente, encontrar una tarea por su ID.
2. **Navegación confusa**: ocho entradas sueltas en la barra lateral (Dashboard, Agentes, Proyectos, Ejecuciones, Tablero, Inbox, Consumo, Ajustes), y Ejecuciones, Tablero e Inbox se solapan.

## Cambios que te pido
### 1. Barra lateral agrupada
- Tres grupos con título: **Trabajo** (Inicio, Tablero, Inbox) · **Configuración** (Agentes, Proyectos) · **Sistema** (Ejecuciones, Consumo, Ajustes).
- La Inbox lleva el contador de pendientes, en ámbar si hay aprobaciones.
- Versión expandida y colapsada (solo iconos con tooltip).
- **Ejecuciones** es la lista global de ejecuciones de CLIs (historial con estado, agente, proyecto, tarea, duración y coste; estados: iniciando, en ejecución, interviniendo, terminada, completada, parada, fallida, interrumpida). Pasa a ser un historial secundario: desde una tarea se llega a sus ejecuciones y al revés.

### 2. Cabecera coherente
- Migas de pan + buscador/Ctrl+K + **una sola acción principal por pantalla**, siempre en el mismo sitio.
- Un botón **«Nueva tarea»** accesible desde cualquier pantalla (o la acción principal cuando corresponda).

### 3. Dashboard (pantalla de inicio)
Revísalo para que responda de un vistazo a «qué está pasando» y «qué necesita de mí»:
- Saludo y resumen («2 agentes trabajando · 1 esperándote · 5 peticiones en el Inbox»).
- Tarjetas de agentes en vivo con «Asignar tarea»; clic → su tarea actual.
- **Aprobaciones pendientes** con Aprobar / Rechazar en la propia fila.
- Actividad reciente y consumo de hoy (con el límite diario).
- Un aviso cuando ningún CLI está listo (enlaza a Ajustes > CLIs).
- Estados: vacío (sin agentes, con guía para crear el primero), cargando y desconectado.

### 4. Diálogo «Nueva tarea» en un paso
- Campos: título, descripción (opcional), proyecto, agente o etapa, prioridad.
- Proyecto y agente **rellenados por el contexto** (desde un proyecto, una tarjeta de agente o una columna del Tablero) y recordando la última elección.
- Acción principal **«Crear y encolar»**; secundaria «Guardar en backlog». Tras crear, toast con «Ver tarea».
- Muestra también cómo se ve abierto desde una tarjeta de agente (agente ya elegido).

### 5. Crear agente y crear proyecto con lo mínimo
- **Nuevo agente**: elegir plantilla (Analista, Desarrollador, QA, Redactor, Comercial) o en blanco → nombre y CLI → crear. El resto (instrucciones, modelo, permisos, concurrencia…) se edita después en sus pestañas.
- **Nuevo proyecto**: carpeta (con «Examinar…») y nombre (propuesto a partir de la carpeta) → crear. Pipeline y workspace con valores por defecto.

### 6. Paleta de comandos (Ctrl+K)
- Secciones: **Ir a** (secciones, agentes, proyectos, tareas por nombre o `T-12`) y **Acciones** (nueva tarea, nuevo agente, nuevo proyecto, lanzar ejecución, pausar/reanudar el scheduler, cambiar tema, abrir Ajustes).
- Muestra el atajo de cada acción; estados con resultados, sin resultados y búsqueda de tareas.
- Un diálogo de **ayuda de atajos** (tecla `?`).

### 7. Ajustes con índice lateral
Hoy es una página larga con seis secciones: **CLIs detectados** (ruta, versión, estado de sesión, «Comprobar»), **General** (tema e idioma), **Notificaciones**, **Límites diarios** (por CLI, con avisos de cuota), **Limpieza** (ramas de tareas por proyecto y retención de logs) y **Acerca de** (versión, carpeta de datos con espacio ocupado, «Cambiar…», «Abrir logs»). Ordénala con un índice lateral o pestañas, sin perder funciones.

### 8. Acciones sobre peticiones sin cambiar de pantalla
Aprobar, rechazar y responder deben poder hacerse desde el Dashboard, la Inbox y el detalle de la tarea con el mismo componente. Incluye la acción **«Reanudar sesión»** (para ejecuciones interrumpidas) en la Inbox y en la tarea.

## Fuera de esta revisión
Conocimiento y Skills, el Arquitecto, el rediseño de la terminal o del Tablero (solo sus accesos), móvil y nuevos idiomas.

## Entregables
- Capturas (1440×900, navy) de: barra lateral (expandida y colapsada), Dashboard (normal, vacío y con aviso de CLIs), diálogo Nueva tarea (desde cabecera y desde una tarjeta de agente), Nuevo agente, Nuevo proyecto, paleta Ctrl+K (con resultados y buscando una tarea), ayuda de atajos, Ajustes con índice, y el Dashboard también en claro.
- El prototipo HTML actualizado.
- Una nota de cambios respecto al diseño anterior (qué componentes cambian o son nuevos).
- Si puedes, el código React de referencia de los componentes nuevos o modificados (sidebar agrupada, CommandPalette, NewTaskDialog, Dashboard).

Usa los mismos datos de ejemplo: agentes «Ana · Analista» y «Dev · Desarrollador» (Claude Code), «Quique · QA» y «Rita · Redactora» (Antigravity); proyectos «Tienda online», «App reservas» y «Blog corporativo».
