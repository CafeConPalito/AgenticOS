# Handoff: Agentic OS (aplicación de escritorio)

## Resumen
Agentic OS es una app de escritorio para Windows (ventanas de 1280 a 1920px) desde la que se dirige un equipo de **agentes de IA que trabajan como empleados**. Cada agente es un CLI de IA (Claude Code, Antigravity/Gemini…) que se ejecuta en su propia terminal real. El usuario ve lo que hacen sus agentes, lo controla e interviene: un dashboard, la gestión de agentes y proyectos, pipelines, un tablero kanban con colas por agente, el detalle de ejecución con la terminal en vivo y la opción de «Tomar control», un inbox de aprobaciones, el consumo, el conocimiento/skills y la creación de agentes conversando con el Arquitecto.

Stack objetivo: **React + Tailwind CSS v4 + shadcn/ui (Radix) + lucide-react**. Librerías recomendadas: `@xterm/xterm` + `@xterm/addon-fit` (terminal), `@dnd-kit/core` + `@dnd-kit/sortable` (colas y pipeline), `sonner` (toasts), `recharts` (gráficas), `@tanstack/react-table` (tablas ordenables) y `react-dropzone` (subida). Toda la UI va **en español**.

## Sobre los archivos de diseño
Los archivos de `prototype/` son **referencias de diseño creadas en HTML**: un prototipo navegable que muestra el aspecto y el comportamiento previstos. **No son código de producción para copiar.** La tarea es **recrear estos diseños en el entorno de la app** (React + Tailwind 4 + shadcn) con sus patrones habituales. El código de `code/` es una implementación de referencia de los componentes clave y de 4 pantallas, escrita directamente para ese stack. Úsalo como punto de partida y ajusta las rutas de importación (`@/components/ui/*` = componentes generados por la CLI de shadcn).

Para abrir el prototipo: `prototype/Agentic OS.dc.html` en un navegador (requiere `support.js` en la misma carpeta y conexión para las fuentes y los iconos).

## Fidelidad
**Alta fidelidad (hi-fi).** Colores, tipografía, espaciados, radios, estados e interacciones son finales. Hay que recrear la UI con precisión de píxel usando los tokens de `tokens.css`.

## Contenido del paquete

| Archivo | Contenido |
|---|---|
| `tokens.css` | Variables CSS en formato shadcn (`:root` claro / `.dark` navy) + `@theme inline` de Tailwind 4: todos los tokens base, `--sidebar-*`, `--chart-1..5`, `--status-*`, `--radius`, fuentes y animaciones |
| `design-system.md` | Paleta y su uso, tipografía por nivel, espaciado, radios, sombras, iconografía lucide, colores de agentes y proyectos, y reglas de estados (badge, punto pulsante, «Estás interviniendo») |
| `components.md` | Anatomía, variantes, estados y componente base de shadcn de cada componente clave |
| `screens.md` | Las 10 pantallas (+ elementos globales): layout, componentes, comportamiento y textos |
| `code/` | Implementación de referencia en React + Tailwind 4 + shadcn |
| `screenshots/` | PNG de 1440×900 de cada pantalla en navy, y Dashboard + Detalle de tarea en claro |
| `prototype/` | Prototipo HTML interactivo (incluye `Design System.dc.html`) |

### `code/`
```
code/
  app.tsx                         layout: SidebarProvider + header + contenido + dock + Ctrl+K + Toaster
  lib/types.ts                    tipos del dominio (Agent, Project, Task, InboxRequest, Run…)
  lib/status.ts                   metadatos de estado, prioridad, inbox y colores de terminal; formateadores es-ES
  lib/mock-data.ts                datos de ejemplo del diseño
  components/agentic/primitives.tsx   StatusBadge, AgentAvatar, ProjectChip, CliTag, LiveDot
  components/agentic/cards.tsx        AgentCard, TaskCard, QueueCard (dnd-kit), InboxItem, EmptyState, skeletons
  components/agentic/terminal.tsx     TerminalPanel (xterm.js), useXterm, RunTree, TerminalDock
  components/agentic/shell.tsx        AppSidebar, AppHeader, CommandPalette, OfflineBanner
  screens/dashboard.tsx
  screens/board.tsx               por estado / por etapa / colas por agente con drag & drop
  screens/task-detail.tsx         pantalla principal: terminal + Tomar control + árbol de ejecución
  screens/inbox.tsx
```
Las pantallas Agentes (lista + editor), Arquitecto, Proyectos (lista + detalle + editor de pipeline), Consumo, Conocimiento y Ajustes **no tienen código React**: están especificadas en `screens.md` y en el prototipo, y se construyen con los mismos componentes.

Componentes de shadcn necesarios: `sidebar breadcrumb button badge card command dialog input textarea select checkbox switch tabs toggle-group tooltip skeleton sonner resizable scroll-area table radio-group alert`.

## Pantallas
Detalle completo en `screens.md`. Resumen:
1. **Dashboard**: tarjetas de agente en vivo, aprobaciones pendientes, actividad reciente y consumo de hoy.
2. **Agentes**: lista y editor en pestañas (General, Instrucciones, Ejecución, Conocimiento, Skills, Historial), con el estado «Borrador propuesto por el Agente Arquitecto».
3. **Proyectos**: lista y detalle (Resumen, Tareas, Pipeline con editor visual y flecha de rechazo, Memoria, Conocimiento, Ajustes de workspace).
4. **Tablero**: kanban por estado o por etapa, y la vista «Colas por agente» con drag & drop; filtros por proyecto y por agente.
5. **Detalle de tarea / ejecución** ★: terminal xterm en vivo en solo lectura → «Tomar control» → «Estás interviniendo» → «Devolver al agente»; árbol de subagentes, eventos MCP y consumo de la sesión.
6. **Inbox**: aprobaciones, preguntas, bloqueos y tareas completadas, con acciones rápidas; filtro Pendientes/Resueltas.
7. **Consumo**: KPIs, barras apiladas por agente o por proyecto y tabla de sesiones ordenable con selector de periodo.
8. **Conocimiento y Skills**: componente reutilizable con selector de nivel, subida de archivos, estado de indexado y biblioteca de skills.
9. **Crear agente con el Arquitecto**: chat a la izquierda y ficha que se rellena en vivo a la derecha.
10. **Ajustes**: CLIs detectados, carpeta de datos, notificaciones, idioma y tema.

## Interacciones y comportamiento (clave)
- **Navegación:** la sidebar marca la sección activa también en las subpantallas. El breadcrumb permite volver atrás.
- **Ctrl+K:** paleta de comandos. **Ctrl+`:** abre o cierra el dock de terminal (abajo o a la derecha).
- **Indicadores en vivo:** punto pulsante (1.6s), barra shimmer en las tarjetas en ejecución, cronómetros y coste de sesión que avanzan cada segundo y cursor parpadeante. Todo se desactiva con `prefers-reduced-motion`.
- **Terminal:** autoscroll si el usuario está a menos de 80px del final. En modo observación el stdin está deshabilitado; «Tomar control» pausa al agente y habilita el stdin; «Devolver al agente» reanuda la ejecución y lanza un toast.
- **Inbox:** al aprobar, rechazar o responder, el elemento pasa a Resueltas, se actualiza el contador de la sidebar y se lanza un toast.
- **Drag & drop:** reordenar la cola de un agente (eje horizontal) y las etapas del pipeline (en el prototipo con flechas ← →; se recomienda dnd-kit). La flecha de rechazo se recalcula sola.
- **Toasts** (sonner, abajo a la derecha, 5,2s). Ejemplo al arrancar: «QA ha rechazado «Login con Google» → vuelve a Desarrollo» con la acción «Ver tarea».
- **Estados:** vacío (CTA y plantillas Analista, Desarrollador, QA, Redactor, Comercial), carga (skeletons) y error (banner «Backend desconectado» + punto rojo en la sidebar). En el prototipo se activan con el ajuste `demoState`.
- **Accesibilidad:** contraste AA en ambos temas (el color de identidad nunca se usa como texto), foco visible con un anillo de 2px `--ring`, roles `tree/treeitem`, `switch`, `tablist`, `radiogroup`, `aria-sort` en las tablas, `aria-live` en los toasts y `aria-busy` en los skeletons.

## Gestión de estado (sugerida)
- Servidor (backend local por WebSocket `ws://127.0.0.1:4317`): agentes, proyectos, tareas, colas, ejecuciones (árbol), eventos MCP, peticiones del inbox, sesiones y consumo, documentos y skills. Se recomienda TanStack Query + suscripciones WS para los eventos en vivo.
- PTY por ejecución: un stream por `runId` conectado a xterm; `write` solo si `intervening`.
- Estado de UI: tema (por defecto `dark`, persistido), sidebar colapsada, dock (abierto, posición, pestaña), filtros del tablero (vista, proyecto, agente) y estado de intervención por ejecución.

## Tokens de diseño
Todos en `tokens.css` y documentados en `design-system.md`. Valores principales: fondo navy `#0A1A33`, card `#0F2242`, popover `#13284D`, borde `#1E3A66`, texto `#FFFFFF` / `#A8B6CF`, primario de acción `#2E5BD6` (claro `#1B3F8F`), ring `#7AA2FF`. Estados: running `#4CC9F0`, waiting `#F5B547`, review `#B39CFF`, done `#43D392`, failed `#FF6B6F`, queued `#9DB0D0`, cancelled `#8492AE`. Tipografía Ubuntu / Ubuntu Mono con base de 13px. Radios 6, 8, 12 y 14. Espaciado con base de 4px.

## Assets
- Fuentes: Ubuntu y Ubuntu Mono (Google Fonts).
- Iconos: lucide (en el prototipo vía `lucide-static` desde un CDN; en la app, `lucide-react`). La correspondencia de cada icono está en `design-system.md §6`.
- Logos de CLI: **marcadores de texto** («CC», «AG», «CX»). Sustituir por los logos oficiales respetando las guías de marca de cada proveedor.
- Avatares: iniciales sobre el color del agente; el editor permite subir una imagen.
- No hay más imágenes.

## Archivos del prototipo
- `prototype/Agentic OS.dc.html`: la app completa (todas las pantallas, estados, dock, Ctrl+K, toasts y temas).
- `prototype/Knowledge.dc.html`: el componente Conocimiento y Skills (props `level`, `scopeName`, `section`).
- `prototype/Design System.dc.html`: paleta, tipografía, radios, espaciado y componentes.
