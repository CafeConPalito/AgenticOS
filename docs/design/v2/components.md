# Agentic OS v7 · Componentes nuevos y modificados

Marcas: **[NUEVO]** · **[CAMBIA]**. Los componentes que no aparecen aquí siguen como en `../components.md` y `../v1.1/`, con el acabado v7 (ver design-system.md §3).
Convenciones v7:
- **Hover:**
  - filas: fondo `--subtle`;
  - ghost: fondo `--accent`;
  - tarjetas clicables: `translateY(-1px)` + borde `--ring`.
- **Pulsado:** `scale(.97)` en todos los `button`.
- **Foco:** igual que antes. El hover de las tarjetas también se activa con `:focus-within`.

---

## AppHeader [CAMBIA] · `code/components/agentic/app-header.tsx`
- **Contenedor:** 56px, `absolute inset-x-0 top-0 z-20`, `glass` (blur 20 + saturate 180 %), borde inferior `--sep`, padding `0 22px`, gap 12.
- **Marca:**
  - logo de 28px, radio 10, `linear-gradient(145deg,#3B69E8,#1B3F8F)`, sombra `0 6px 18px -6px #2E5BD6` + `inset 0 0 0 1px rgba(255,255,255,.14)`;
  - texto «Agentic OS» 15/700.
- **Separador** de 1px × 22.
- **Volver** (solo fuera de Inicio): botón circular de 28px, fondo `--muted`, `ArrowLeft`.
- **Migas** (`flex:1`).
- **[NUEVO] Navegación superior:**
  - ítems Tablero `11` · Ejecuciones `5` · Conocimiento · Ajustes;
  - píldoras de 30px, 12.5, muted;
  - activo: fondo `--accent`, texto foreground y `aria-current="page"`;
  - contador en mono 11.5, muted.
- **Buscador:** 220px × 32, píldora, fondo `--muted` al 80 %, sin borde, `Search` · «Buscar agentes, tareas o acciones…» · kbd `Ctrl` `K`. Abre Ctrl+K.
- **Terminal:** botón circular de 32px sin borde, `SquareTerminal`; con el dock abierto lleva fondo `--accent`.
- **Conexión:** punto de 7px done + «Conectado» (12, muted). Tooltip: `ws://127.0.0.1:4317`.
- **Tema:** botón circular de 32px, `Sun` / `Moon`.
- **Ya no hay botón primario en la cabecera.** «Nueva tarea» se abre con N, desde Ctrl+K o desde las tarjetas de agente.

## SummaryAside [NUEVO] · `code/components/agentic/summary-aside.tsx`
Columna lateral agrupada de Inicio, sustituta de la «sidebar agrupada». 300px, `sticky top-[84px]`, `border-l border-sep pl-7 pt-5`, gap 30. Sin cajas.
- **AsideSection** (`title`, `meta?`, `link?`, `onAdd?`):
  - cabecera: eyebrow · meta 12 muted (con elipsis) · enlace 12 muted a la derecha · «+» circular de 24px;
  - `margin-bottom` 6.
- **ProjectRow:** rejilla `8px 1fr auto`, padding `6px 8px`, margen `0 -8px`, radio 9, hover `--subtle`.
  - Fila 1: cuadradito · nombre · «n abiertas».
  - Fila 2: actividad (12, muted, elipsis) · mini-avatares de 16px.
- **SpendMeter:** «6,51 € / 25 €» (20/700 mono) · barra de 6px (relleno muted, ámbar desde el 80 %) con la marca del 80 % · «26% del límite diario».
- **CliRow** (`Collapsible`): rejilla `24px 1fr 56px 34px 12px`.
  - Contenido: tag (18px, borde, mono 10/700, muted) · nombre · barra de 4px · % (mono 12; ámbar desde el 80 %) · chevron (gira 180°).
  - Fila 2: «2 cuentas · 3 sesiones».
  - Desplegado: una **AccountRow** por cuenta (sangría 32px): email · barra · % y, debajo, «plan · sesiones».
- **KnowledgeLine:** texto de 12, muted, enlace a `#/conocimiento`.

## NeedsYouPanel [NUEVO] · en `screens/dashboard.tsx`
- **Contenedor:**
  - borde 1px `color-mix(waiting 50%, --sep)`, radio 20;
  - fondo `linear-gradient(180deg, color-mix(waiting 10%, card) 0, card 150px)`;
  - sombra: `0 0 0 4px color-mix(waiting 7%, transparent)`, `0 22px 50px -18px color-mix(waiting 30%, transparent)` y `--shadow-card`.
- **Cabecera** (60px, padding `0 14px 0 18px`):
  - icono `Hand` en un círculo ámbar sólido de 30px (`#F5B547`, texto `#0A1A33`) con halo `0 0 22px` ámbar al 50 %;
  - H2 18/700 «Te necesitan»;
  - contador ámbar sólido de 20px;
  - a la derecha, ghost «Ver todas · 6» / «Ver menos».
- **RequestItem** (`article`): rejilla `30px 1fr`, gap 14, padding `16px 18px`, borde superior `--sep`.
  - Avatar de 30 con brillo (ver design-system §3).
  - Título 14/500 · tiempo (12, muted, a la derecha).
  - Meta de 12 muted: icono del tipo · tipo · agente · tarea · proyecto. **El tipo ya no va coloreado.**
  - Comando opcional (mono 12, `--term-bg`).
  - Contexto (12.5, muted).
  - `RequestActions` (de v1.1).
  - El hover sobre una petición resalta la tarjeta de su agente.
- **CliAlertItem** [NUEVO]: misma anatomía.
  - Icono `Gauge` ámbar sobre `--muted` en lugar del avatar.
  - Título: «Antigravity casi sin cuota · 96 %» o «Claude Code: sesión caída en marta@estudio.es».
  - Meta: «Aviso del sistema · CLIs y cuentas».
  - Contexto: «{email} · {cuota}: {reinicio}. Cambia sus agentes a otra cuenta o espera al reinicio.» o «Los agentes que usan esta cuenta están en pausa hasta que vuelvas a iniciar sesión.»
  - Acciones: primario «Revisar cuentas» / «Reconectar» (→ CLIs y cuentas) · outline «Posponer» (oculta el aviso de esa cuenta en esta sesión y lanza el toast «Aviso pospuesto»).
  - **Regla:** se genera por cada cuenta con la cuota más alta ≥ 95 % o `session === "down"`. Cuenta en el contador de «Te necesitan».

## AgentCard [CAMBIA] · en `screens/dashboard.tsx`
- **Contenedor:** `bg-card-grad`, radio 16, padding `13px 14px 10px`, gap 8, `--shadow-card`. Clic o Enter → ficha.
- **Borde:**
  - `--sep` por defecto;
  - waiting al 55 % si tiene peticiones;
  - waiting sólido + halo de 3px si una petición suya está con hover.
- **Badge** «1 petición» (si tiene alguna): píldora ámbar de 18px en `top:-9px; right:12px`, con `box-shadow: 0 0 0 3px var(--background)`.
- **[NUEVO] Línea de ejecución** (solo `running`): 2px en el borde superior, `left/right:16px`, `linear-gradient(90deg,transparent,var(--status-running),transparent)` con `background-size:50% 100%` y `animate-sweep`.
- **Primario:**
  - avatar de 30 (radio 9) con brillo;
  - nombre 14/500;
  - estado a la derecha: punto de 6px (pulsante si está en ejecución) + etiqueta de 12/500 en el color del estado.
  - Una fila de 24px por sesión viva: punto · código mono 12 muted · tarea (elipsis) · cuadradito del proyecto · tiempo mono 12 muted («13:52», «esperándote», «reanudable», «iniciando»).
  - Sin sesiones: «Disponible · sin tareas en curso» / «Borrador · actívalo desde su ficha» (muted).
- **Secundario** (28px, 12, muted): «Analista · CC · 1 en cola».
- **Al hover o `:focus-within`** el secundario pasa a opacidad 0 y en la misma celda aparece (opacidad 0→1, 150ms) la fila de consumo:
  - píldora `--subtle`: **coste** mono · «1,2 M tok» · barra de 4px (muted) · «1 en cola»;
  - botón circular «+» de 28px: Asignar tarea, que abre NewTaskDialog con el agente.
  - **Ya no muestra el nombre largo del CLI** (solo el tag en el secundario).

## CommandPalette [CAMBIA] · `code/components/agentic/command-palette.tsx`
- **Contenedor:** 600px de ancho, 470px de alto máximo, a un 12vh del borde superior; `glass-pop`, radio 20, `--shadow-pop`, entrada `sheet-in` en .24s. Overlay con blur.
- **Input** de 50px: `Search` · placeholder «Busca agentes, tareas, proyectos o acciones…» (14px) · kbd `Esc`.
- **Grupos sin búsqueda:**
  - **Acciones:** Nueva tarea `N` · Nuevo agente · Nuevo equipo · Nuevo proyecto · Añadir CLI o cuenta · Abrir terminal · Cambiar tema · Atajos de teclado `?`.
  - **Ir a:** Inicio · CLIs y cuentas · Proyectos · Conocimiento y skills · Tablero · Ejecuciones · Ajustes.
  - **Agentes.**
- **Con búsqueda:** filtra todos los grupos e incluye **Proyectos** y **Tareas** (`T-142 · Login con Google`). Máximo 14 resultados.
- **Ítems:** 36px, radio 10; activo con fondo `--accent`. ↑↓ mueven, Enter ejecuta y el hover selecciona.
- **Sin resultados:** «Sin resultados.»

## ShortcutsDialog [CAMBIA] · en `command-palette.tsx`
- Dialog de 520px titulado «Atajos de teclado», con 2 columnas de grupos (etiqueta de 11.5 muted y filas de 28px: acción · kbd).
- **General:** Paleta de comandos `Ctrl K` · Atajos de teclado `?` · Abrir / cerrar la terminal ``Ctrl ` `` · Cerrar diálogo o panel `Esc`.
- **Crear:** Nueva tarea `N`.
- Las teclas de un solo carácter (N, ?) se desactivan si «Atajos de una tecla» está apagado en Ajustes, o con el foco en un input, un diálogo abierto o un modificador pulsado.

## NewTaskDialog [CAMBIA] · `code/components/agentic/new-task-dialog.tsx`
Más corto que en v1.1.
- **Contenedor:** 520px. Cabecera de 56px «Nueva tarea» + cerrar.
- **Campos:**
  - «Qué hay que hacer»: Input de 36px, autofocus, placeholder «p. ej. Añadir filtro por precio en categorías»;
  - rejilla de 2 columnas: **Proyecto** (Select, por defecto el primero) · **Agente** (Select con «Nombre · Rol», sin borradores).
- **Pie:** «Cancelar» (outline) · «Crear y encolar» (primario, píldora).
- **Al crear:** la tarea entra en la cola con el siguiente código (T-161…) y se lanza el toast «T-161 en la cola de Dev».
- **Origen:**
  - N o Ctrl+K: agente por defecto `dev`;
  - tarjeta de agente: ese agente preseleccionado.

## ConfigDisclosure [NUEVO] · ficha de agente
`Collapsible` cerrado por defecto. Ver screens.md §5.

## SessionFactsLine [NUEVO] · detalle de tarea
Línea `flex-wrap` de 12 muted: «Etiqueta `valor mono`». Ver screens.md §6.

## Toast [CAMBIA]
- Centrado abajo (24px de margen), `glass-pop`, radio 14, `--shadow-pop`, icono `CircleCheck` done.
- Duración: 2,6s.
