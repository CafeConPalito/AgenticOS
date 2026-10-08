# Agentic OS · Componentes

Cada componente indica en qué componente de shadcn/ui (Radix) se basa, su anatomía, sus variantes y sus estados. Código de referencia: `code/components/`.
Convenciones comunes a todos los componentes interactivos:

- **Hover**: borde `--ring` (tarjetas) o fondo `--accent` (filas, ghost, ítems).
- **Activo/seleccionado**: fondo `--accent` + borde `--ring`, o fondo `--primary-action` en controles.
- **Foco**: `focus-visible:outline-2 outline-ring outline-offset-2`.
- **Deshabilitado**: `opacity-45`, `pointer-events-none`, `cursor-not-allowed`.

---

## AgentAvatar
**Base:** `Avatar` (+ `Tooltip` con «Nombre · Rol»).
- Cuadrado redondeado con fondo = color del agente, inicial en `#0A1A33` 700 (tamaño de fuente ≈ 44% del lado).
- Tamaños: 16 (pestaña del dock) · 18–20 (tablas, tarjetas de tarea) · 24–26 (listas) · 30–34 (tarjetas) · 48 (cabecera de detalle) · 56 (editor).
- Radio: 4px (16), 5–6px (≤24), 7–9px (26–34), 12–14px (≥48).
- Variante con badge de tipo (Inbox): círculo de 18px `--card` en la esquina inferior derecha con un icono lucide de 13px coloreado según el tipo.
- Variante «sin asignar»: fondo `#8492AE` con «?».

## StatusBadge
**Base:** `Badge variant="outline"`.
- Ver reglas en `design-system.md §7`. Props: `status`, `label?` (override, p. ej. «Esperándote»).
- Tamaños: `md` 22px (cabeceras, tarjetas de agente) · `sm` 20px (tablas) · `xs` 19px / 10.5px (tarjeta de tarea).
- No es interactivo.

## ProjectChip
**Base:** `Badge` (custom).
- Alto 18–22px, radio 5–6px, fondo `color-mix(in oklch, <color> 16%, transparent)`, cuadradito de 6–8px y nombre en `--foreground`.
- Variante «punto»: solo cuadradito + texto `--muted-foreground` (metadatos).

## CliTag
- Cuadrado de 22–34px, fondo `--primary`, borde `--border`, texto blanco en Ubuntu Mono 10–11/700 («CC», «AG»). Variante inline: 10px con borde de 1px y radio de 3px, junto al nombre del CLI. Sustituir por el logo oficial.

---

## AgentCard (Dashboard)
**Base:** `Card` (clicable).
**Anatomía:**
1. Cabecera: AgentAvatar 34 · nombre (500) + «· Rol» (muted) · línea con CliTag inline + nombre del CLI (11.5, `nowrap`) · StatusBadge md (`flex-none`, a la derecha).
2. Bloque de trabajo (`--subtle`, borde, radio 8, padding 9×10): etiqueta («Trabajando en» / «Esperando aprobación en» / «En pausa en», 11px muted) · título de la tarea (500, una línea con elipsis) · chip de proyecto + tiempo transcurrido en mono a la derecha (`mm:ss` / `h:mm:ss`; si espera: «hace mm:ss»).
3. Variante inactiva: caja discontinua (`--input`) de 72px de alto mínimo con «Sin tarea activa» y el botón outline pequeño «Asignar tarea».
4. Pie: «Cola **n tareas**» · «Concurrencia **1/1**» (mono).

**Variantes:** `running` · `waiting` (borde ámbar al 50%) · `paused` · `idle`.
**Estados:** hover → borde `--ring`. Clic → Detalle de la tarea actual (o editor del agente si está inactivo). El tiempo transcurrido avanza cada segundo.
**Layout:** rejilla `repeat(auto-fill, minmax(270px, 1fr))` con gap de 12px (4 columnas desde unos 1180px de contenido; 2×2 por debajo).

## TaskCard (Kanban)
**Base:** `Card` como `button`.
**Anatomía (padding 10×11, radio 9, gap 7):**
1. Fila meta (11px muted): ProjectChip · etapa · ID mono a la derecha («T-142»).
2. Título (13/500, `text-wrap: pretty`, máximo 3 líneas).
3. StatusBadge xs: solo en la vista «Por etapa».
4. Fila inferior: avatar 20 · prioridad (texto 500 coloreado: Urgente `--status-failed`, Alta `--status-waiting`, Media `--status-queued`, Baja `--status-cancelled`) · `ListChecks` + «3/5» (solo si hay subtareas) · tiempo mono · coste mono en `--foreground` (si es > 0).
5. Si está en ejecución: barra shimmer de 2px en el borde superior.

**Estados:** hover → borde `--ring`; foco visible; arrastrando (vista de colas) → `opacity .4`; arrastrable → `cursor: grab` + `GripVertical`.
**Variante «QueueCard»** (Colas por agente): 230px de ancho, posición mono («Ahora», «#1», «#2»…) y estado como texto coloreado. La tarjeta actual lleva un fondo running al 7% y un borde running al 40%.

## InboxItem
**Base:** `Card` + `Button` + `Input` (+ `ToggleGroup` para las opciones de respuesta).
**Anatomía:**
- Cuerpo (padding 14×16): AgentAvatar 34 con badge de tipo · fila meta (tipo coloreado 500 · **agente** · chip de proyecto · enlace a la tarea en `--ring` · tiempo a la derecha) · título 15/500 · comando opcional en bloque de terminal (`--terminal`, mono 13, prefijo `❯` en `#7F8DAA`) · contexto en muted.
- Barra de acciones (`--subtle`, borde superior):
  - **Aprobación**: `Aprobar` (primario, `Check`) · `Rechazar` (outline).
  - **Pregunta**: chips de opción («Postgres», «SQLite») que rellenan el input · Input «Responder con texto…» + `Responder`.
  - **Bloqueo**: Input + `Responder`.
  - **Tarea completada**: `Marcar como revisado`.
  - Siempre a la derecha: `Abrir terminal` (ghost, `SquareTerminal`) → abre el dock en la pestaña del agente.
- Resuelto: no tiene barra; muestra «✓ Aprobado por ti» / «Respondido: «…»» en `--status-done`.

**Estados:** el botón `Responder` no hace nada si el input está vacío. Al resolver: toast + el elemento pasa a «Resueltas».

## TerminalPanel
**Base:** contenedor propio con `xterm.js` (`@xterm/xterm` + `@xterm/addon-fit`). Los botones son `Button` y las píldoras, `Badge`.
**Anatomía:**
1. Cabecera (`--terminal-header`, borde inferior `--terminal-border`, padding 8×10×8×12): tres puntos decorativos de 9px `#1E3A66` · título mono 12.5 (`dev@T-142 · cc-7f3a91`, con elipsis) · píldora de modo · botón a la derecha (los tres con `flex-none` + `nowrap`).
2. Cuerpo: xterm con fondo `--terminal`, Ubuntu Mono 13 / 1.6, padding 12×14, autoscroll si el usuario está a menos de 80px del final.
3. Pie de modo: cursor parpadeante (observando) o barra de input (interviniendo).
4. Debajo del panel (fuera de él): línea mono 11.5 muted con `xterm · 132×38`, `pwsh 7.4`, la ruta del worktree y la rama.

**Variantes:** `observing` · `intervening` (ver `design-system.md §7`) · `readonly-dock` (sin control y con el texto «Solo lectura · abre el detalle para tomar el control»).
**Comportamiento:** «Tomar control» pausa al agente y habilita el stdin; «Devolver al agente» reanuda la ejecución, añade un evento MCP y lanza un toast. Al cambiar de nodo en el árbol de ejecución se sale del modo intervención.

## RunTreeNode
**Base:** `Collapsible` / `role="tree"` (`treeitem`).
- Fila de 34px, radio 7, padding izquierdo `8 + depth*16` px. Los hijos llevan un conector `└` mono muted.
- Punto de estado de 8px (pulsante si está en ejecución) · nombre (raíz en Ubuntu 12.5; subagentes en mono 12.5; elipsis) · duración mono 11.5 muted a la derecha (avanza en vivo).
- **Seleccionado:** fondo `--accent` + borde `--ring`. **Hover:** `--accent`.
- Clic → muestra la terminal de ese nodo en el panel central.

## AppSidebar
**Base:** `Sidebar` de shadcn (`SidebarProvider`, `SidebarHeader`, `SidebarMenu`, `SidebarMenuButton`, `SidebarMenuBadge`, `SidebarFooter`), con `collapsible="icon"`.
- Ancho de 232px expandida y 60px colapsada (transición de width en 180ms). Fondo `--sidebar` y borde derecho `--sidebar-border`.
- Header de 52px: logo (cuadrado de 28px `#2E5BD6`, radio 8, con un cuadrado interior de 10px con borde blanco de 2px y un punto de 5px `#4CC9F0` arriba a la derecha) · «Agentic OS» 15/700 · botón colapsar (`PanelLeftClose`).
- Ítems (34px, radio 7, gap 10): icono 16 + etiqueta. Inactivo: `--sidebar-muted`. Hover y activo: fondo `--sidebar-accent` y texto blanco (el activo además en 500). Badge del Inbox: píldora ámbar con el número de pendientes.
- Orden: Dashboard, Agentes, Proyectos, Tablero, Inbox, Consumo, Ajustes. Las subpantallas activan su sección (el editor de agente activa Agentes, el detalle de tarea activa Tablero…).
- Footer: estado del backend (punto de 8px `--status-done` con «Conectado · v0.8.2» / `--status-failed` con «Desconectado · reintentando…») · botón de tema (`Sun` «Tema claro» / `Moon` «Tema oscuro»).
- Colapsada: solo iconos con `Tooltip` a la derecha; el badge pasa a superponerse sobre el icono.

## AppHeader
**Base:** `Breadcrumb`, `Button`, `CommandDialog` (trigger), `Kbd`.
- 52px de alto, padding 0 18px, borde inferior y fondo `--background`.
- Breadcrumb: los niveles intermedios son botones muted con hover `--accent`; el último va en foreground 500. Ejemplo: «Tablero / App reservas / T-142 · Login con Google».
- Trigger de búsqueda: 300px de ancho, 32px de alto, fondo `--subtle`, `Search`, el texto «Buscar o ejecutar un comando…» y el kbd «Ctrl K» (mono 11).
- Botón «Terminal» (outline, `SquareTerminal`): abre o cierra el dock (Ctrl+`); cuando el dock está abierto lleva fondo `--accent`.
- Botón primario contextual (`Plus` + texto):

| Pantalla | Botón |
|---|---|
| Dashboard, Tablero, Detalle de tarea, Detalle de proyecto | Nueva tarea → Dialog |
| Agentes, Editor de agente | Nuevo agente → Arquitecto |
| Proyectos | Nuevo proyecto → selector de carpeta |
| Consumo | Exportar CSV |
| Inbox, Ajustes, Arquitecto | — |

## TerminalDock
**Base:** `ResizablePanelGroup` (shadcn Resizable) + `Tabs`.
- Abajo: 260px de alto (redimensionable) · A la derecha: 440px de ancho.
- Barra de pestañas de 36px `--terminal-header`: una pestaña por ejecución activa (punto de estado, avatar de 16 y título de la tarea). La pestaña activa tiene fondo `--terminal` y una línea superior de 2px `#4CC9F0`.
- Acciones a la derecha: alternar posición (`PanelRight` / `PanelBottom`) · abrir el detalle (`Maximize2`) · cerrar (`X`).
- Se abre desde cualquier pantalla y desde «Abrir terminal» en el Inbox.

## CommandPalette (Ctrl+K)
**Base:** `CommandDialog`, `CommandInput`, `CommandGroup`, `CommandItem`.
- 600px de ancho, 440px de alto máximo, a un 12vh del borde superior. Fondo `--popover`, radio 12.
- Grupos: «Ir a» (secciones), «Acciones» (Nueva tarea, Crear agente con el Arquitecto, Abrir/cerrar terminal, Cambiar tema), «Tareas» (ID + título; nombre del proyecto a la derecha), «Agentes».
- Navegación con ↑↓, Enter ejecuta y Esc cierra. Sin resultados: «Sin resultados para «…»».

## Dialog «Nueva tarea»
**Base:** `Dialog`. 520px de ancho, padding 18.
- Campos: Título (Input, autofocus, placeholder «p. ej. Añadir filtro por precio») · Proyecto (`ToggleGroup` de chips) · Descripción (Textarea, 3 filas) · nota «Entrará en la primera etapa del pipeline: **Requisitos · Ana · Analista**».
- Acciones: «Cancelar» (outline) · «Crear tarea» (primario). Al crear: la tarea va a Backlog y se lanza un toast.

## Toast
**Base:** `Sonner` (`toast()`), abajo a la derecha (18px de margen).
- 320–440px de ancho, fondo `--popover`, borde, radio 10, sombra de nivel toast, entrada con `toast-in` en 220ms.
- Icono de 16px coloreado según el tipo · título 500 · subtítulo opcional 12px muted · acción opcional (botón outline pequeño). Duración: 5,2s.
- Ejemplos:
  - «QA ha rechazado «Login con Google» → vuelve a Desarrollo» (`Undo2`, failed; sub «Quique · «redirige al panel tras el callback» falla»; acción «Ver tarea»).
  - «Aprobado · Quique continúa» (`Check`, done).
  - «Cola de Dev reordenada» (`ArrowDownUp`, ring).
  - «¿Cancelar la ejecución?» (`CircleAlert`, failed; acción «Confirmar»).

## EmptyState
**Base:** `Card` (discontinua).
- Borde de 1px discontinuo `--input`, radio 12, fondo `--subtle`, padding 40–48 y contenido centrado.
- Icono de 22px en un cuadrado de 44px `--accent` · título 16/500 · descripción muted · acciones.
- Ejemplo de Agentes: «Aún no tienes agentes» / «Crea tu primer agente o usa una plantilla:» · chips de plantilla (Analista, Desarrollador, QA, Redactor, Comercial, cada uno con su punto de color) · primario «Crear mi primer agente» (el Dashboard usa «Crear con el Arquitecto» con `Sparkles`).
- Variantes pequeñas: columna del kanban («Sin tareas», caja discontinua), cola vacía («Cola vacía · Rita está disponible»), Inbox («Bandeja al día»), historial («Este agente todavía no ha ejecutado ninguna tarea.»).

## Skeleton
**Base:** `Skeleton` de shadcn.
- Bloques `--muted` con radio de 4px (líneas) a 9px (avatares) y la animación `skel` (opacidad 1 → .45 → 1, 1.2s).
- Plantillas: tarjeta de agente (avatar de 34 + 2 líneas + bloque de 40px + línea) ×4; fila de tabla (avatar de 32 + 3 barras) ×5. Contenedor con `aria-busy="true"`.
- En el Arquitecto, los campos de la ficha que aún no se han rellenado se muestran como skeleton con un borde discontinuo.

## ErrorBanner (backend desconectado)
**Base:** `Alert variant="destructive"` (estilo propio).
- Franja bajo el header con fondo `color-mix(--status-failed 14%, --background)` y borde inferior failed al 40%.
- Contenido: `WifiOff` · «**Backend desconectado.** No se pueden lanzar ni observar ejecuciones. Los agentes en curso siguen trabajando en sus terminales.» · botón «Reintentar ahora» · `ws://127.0.0.1:4317` en mono muted. Además, el punto del footer de la sidebar se pone en rojo.

## Controles base
- **Segmented control** (`Tabs` / `ToggleGroup`): contenedor `--muted` con borde, padding 3 y radio 8. La opción activa lleva fondo `--card`, foreground y sombra; las inactivas, muted. Alto de 24–28px.
- **Tabs con subrayado** (detalle de agente o proyecto): botones de 38px; el activo en foreground 500 con `inset 0 -2px 0 var(--primary-action)`.
- **Switch:** 36×20, track `--primary-action` (encendido) o `--input` (apagado), thumb blanco de 16px y desplazamiento de 16px en 150ms.
- **Radio cards** (CLI, permisos, workspace): borde de 1.5px, `--primary-action` y fondo primary al 10% cuando están seleccionadas.
- **Chips de toggle** (herramientas): píldora de 30px con «✓» o «+»; activos con borde primary y fondo primary al 18%.
- **Stepper** (concurrencia): `−` · valor mono · `+` dentro de un borde `--input`; rango 1–8.
