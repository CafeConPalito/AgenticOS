# Agentic OS · Design system

Referencia visual: `screenshots/` y `prototype/Design System.dc.html`. Tokens: `tokens.css`.

> Tema **oscuro navy = principal** (`<html class="dark">`). El tema claro es secundario y usa los mismos nombres de token.

---

## 1. Paleta

### Superficies y texto

| Token | Oscuro | Claro | Uso |
|---|---|---|---|
| `--background` | `#0A1A33` | `#F4F6FA` | Fondo de la ventana y del área de contenido |
| `--card` | `#0F2242` | `#FFFFFF` | Tarjetas, tablas, paneles |
| `--popover` | `#13284D` | `#FFFFFF` | Dialog, Command (Ctrl+K), Toast, Dropdown |
| `--subtle` | `#0C1D38` | `#F8FAFD` | Superficie hundida: inputs, cabeceras de tabla, bloques internos de tarjeta |
| `--muted` | `#122A4E` | `#EEF2F8` | Fondo de segmented control, skeletons, barras de progreso vacías |
| `--accent` | `#1A3562` | `#E3EAF5` | Hover de filas, botones ghost e ítems; ítem seleccionado |
| `--secondary` | `#16305A` | `#E9EEF6` | Botón secundario (shadcn `variant="secondary"`) |
| `--border` | `#1E3A66` | `#D6DEEA` | Bordes de 1px de tarjetas, separadores |
| `--input` | `#24426F` | `#C9D3E3` | Borde de inputs, bordes discontinuos de estados vacíos, track de los Switch apagados |
| `--foreground` | `#FFFFFF` | `#0A1A33` | Texto principal |
| `--muted-foreground` | `#A8B6CF` | `#4B5B78` | Texto secundario, etiquetas, metadatos (AA sobre card y background) |

### Primario (navy)

| Token | Oscuro | Claro | Uso |
|---|---|---|---|
| `--primary` | `#13284D` | `#13284D` | Navy de marca: fondos de badge de CLI («CC», «AG»), elementos de marca |
| `--primary-action` | `#2E5BD6` | `#1B3F8F` | **Botones primarios**, pestaña activa (subrayado), Switch encendido, chat del usuario. Texto siempre `#FFFFFF` |
| `--primary-action-hover` | `#3B69E8` | `#24499F` | Hover del botón primario |
| `--ring` | `#7AA2FF` | `#2E5BD6` | Anillo de foco, borde en hover de tarjetas, filtros activos, enlaces |
| `--destructive` | `#E5484D` | `#C9302C` | Cancelar ejecución, eliminar |

### Sidebar (navy en los dos temas)

| Token | Oscuro | Claro |
|---|---|---|
| `--sidebar` | `#071427` | `#0F2347` |
| `--sidebar-foreground` | `#FFFFFF` | `#FFFFFF` |
| `--sidebar-muted` (ítems inactivos) | `#9AA9C4` | `#AEBCD6` |
| `--sidebar-accent` (ítem activo y hover) | `#16305A` | `#1F3C6E` |
| `--sidebar-border` | `#13284A` | `#1A3360` |

### Terminal (siempre oscura)

`--terminal` `#050E1E` (claro `#0A1A33`) · cabecera `#081429` · borde interno `#16294A` · texto `#D7E1F0`.

Colores de las líneas de terminal (fijos, iguales en los dos temas):

| Tipo de línea | Color | Peso | Prefijo |
|---|---|---|---|
| Comando | `#FFFFFF` | 700 | `▶` |
| Info / lectura | `#8FB4FF` | 400 | `●` / `▸` |
| OK / PASS | `#43D392` | 400 | `✓` / `PASS` |
| Error / FAIL | `#FF6B6F` | 400 | `✗` / `FAIL` / `⚠` |
| Edición de archivo | `#F5B547` | 400 | `✎` |
| Evento MCP | `#B39CFF` | 400 | `● mcp ·` |
| Subagente | `#4CC9F0` | 400 | `↳` |
| Secundario / prompt | `#7F8DAA` | 400 | — |
| Entrada del usuario | `#F5B547` | 700 | `❯` |

### Estados

| Estado | Token | Oscuro | Claro | Etiqueta |
|---|---|---|---|---|
| Backlog | `--status-cancelled` | `#8492AE` | `#647089` | «Backlog» |
| En cola | `--status-queued` | `#9DB0D0` | `#4F6385` | «En cola» |
| Ejecutando | `--status-running` | `#4CC9F0` | `#0A78A3` | «Ejecutando» |
| Esperando humano | `--status-waiting` | `#F5B547` | `#9A6200` | «Esperando humano» / «Esperándote» en tarjetas de agente |
| En revisión | `--status-review` | `#B39CFF` | `#6A4FD1` | «En revisión» |
| Hecho | `--status-done` | `#43D392` | `#12805A` | «Hecho» |
| Fallido | `--status-failed` | `#FF6B6F` | `#C9302C` | «Fallido» |
| Cancelado | `--status-cancelled` | `#8492AE` | `#647089` | «Cancelado» |
| Inactivo (agente) | `--status-cancelled` | — | — | «Inactivo» |
| En pausa | `--status-waiting` | — | — | «En pausa» |
| Borrador (agente) | `--status-review` | — | — | «Borrador» |

El violeta de revisión (`--status-review`) también se usa en todo lo que viene del **Agente Arquitecto** y en lo que proponen los agentes: banner de borrador, skills propuestas e icono sparkles.

### Gráficas
`--chart-1…5`. En Consumo se usa **el color propio de cada agente o proyecto**, no los chart tokens; los chart tokens quedan para gráficas genéricas.

### Colores de identidad

**Agentes** (avatar = cuadrado redondeado con la inicial en `#0A1A33`, peso 700):

| Agente | CLI | Color |
|---|---|---|
| Ana · Analista | Claude Code | `#F27FB2` |
| Dev · Desarrollador | Claude Code | `#4FD1C5` |
| Quique · QA | Antigravity | `#B5E061` |
| Rita · Redactora | Antigravity | `#FFA06B` |
| Carla · Comercial (borrador) | Claude Code | `#8FB4FF` |

Paleta del selector de color del agente: `#F27FB2 #4FD1C5 #B5E061 #FFA06B #8FB4FF #C4A1FF #FF8A8A #F2C94C`.

**Proyectos** (chip = cuadradito de 6–8px + nombre; fondo del chip `color-mix(in oklch, <color> 16%, transparent)`):
Tienda online `#7C9CFF` · App reservas `#E58AF0` · Blog corporativo `#F2C94C`.

> Regla de contraste: el color de identidad **nunca** se usa como color de texto (falla AA en claro). Se usa como fondo de avatar, punto o barra, y el texto va en `--foreground`.

---

## 2. Tipografía

Fuentes: **Ubuntu** (400, 500, 700) para la UI; **Ubuntu Mono** (400, 700) para terminal, IDs, rutas, modelos, tiempos, tokens y cifras de coste. Tamaño base 13px y interlineado base 1.45.

| Nivel | Fuente | Tamaño / peso | Interlineado | Tracking | Uso |
|---|---|---|---|---|---|
| Display | Ubuntu | 30 / 700 | 1.2 | -0.02em | Título del design system |
| H1 de pantalla | Ubuntu | 22 / 500 | 1.3 | -0.01em | «Buenos días, Marta», «Agentes», «Consumo» |
| H1 de detalle | Ubuntu | 20 / 500 | 1.3 | 0 | Nombre de agente o proyecto en el detalle |
| Título de tarea | Ubuntu | 17 / 500 | 1.3 | 0 | Cabecera del Detalle de tarea |
| H2 de sección | Ubuntu | 14–15 / 500 | 1.35 | 0 | «Aprobaciones pendientes», «Editor de pipeline» |
| Título de inbox | Ubuntu | 15 / 500 | 1.35 | 0 | Título de cada petición |
| KPI | Ubuntu Mono | 22–26 / 500 | 1.2 | 0 | Cifras de Consumo y de Proyecto |
| Body | Ubuntu | 13 / 400 | 1.45 | 0 | Texto general, celdas |
| Body fuerte | Ubuntu | 13 / 500 | 1.45 | 0 | Títulos de tarjeta, nombres |
| Caption | Ubuntu | 11.5–12 / 400 | 1.4 | 0 | Metadatos, etiquetas de campo, cabeceras de tabla (500) |
| Micro | Ubuntu | 11 / 500 | 1.3 | 0 | Badges, contadores |
| Mono | Ubuntu Mono | 13 / 400 | 1.6 | 0 | Terminal en el detalle |
| Mono pequeño | Ubuntu Mono | 12–12.5 / 400 | 1.6 | 0 | Dock de terminal, IDs, rutas, modelos |
| Mono tag | Ubuntu Mono | 10 / 700 | 1 | 0 | Tag de CLI «CC», «AG», «CX» |

Usar `text-wrap: pretty` en párrafos y títulos de tarjeta. Cifras alineadas a la derecha en tablas.

---

## 3. Espaciado

Base 4px. Escala: 4 · 6 · 8 · 10 · 12 · 14 · 16 · 20 · 24 · 32.

- Padding de pantalla: `22px 24px 32px` (`pt-[22px] px-6 pb-8`), con `max-width` de 1640px en listas y 1080px en Inbox y Ajustes.
- Gap entre bloques de pantalla: 16–20px. Gap en rejillas de tarjetas: 12px.
- Padding de tarjeta: 14px (tarjeta de agente) / 10×11px (tarjeta de tarea) / 14×16px (secciones).
- Filas de tabla: padding `11px 16px` y cabecera `9px 16px`.
- Alturas de control: botón 32px (compacto 28–30px), input 36px (compacto 30–34px), ítem de sidebar 34px, pestaña 38px, header 52px.
- Objetivo táctil mínimo de 28px (aplicación de escritorio con ratón).

## 4. Radios

| Token | Valor | Uso |
|---|---|---|
| `rounded-sm` | 6px | Avatares de 18–24px, botones pequeños e iconos, chips de proyecto (5px) |
| `rounded-md` | 8px | Botones, inputs, avatares de 30–34px, segmented control |
| `rounded-lg` | 12px | Tarjetas, secciones, columnas del kanban, panel de terminal (11px), dialog |
| `rounded-xl` | 14px | Avatar grande (56px) |
| `rounded-full` | 999px | Badges de estado, chips de filtro, Switch, contadores |

Tarjeta de tarea: 9px. Tarjeta de cola: 9px.

## 5. Sombras y elevación

El sistema es plano: la jerarquía se marca con bordes y cambios de superficie.

| Nivel | Valor | Uso |
|---|---|---|
| 0 | Ninguna (borde de 1px `--border`) | Tarjetas, tablas |
| Segmented activo | `0 1px 2px rgba(0,0,0,.25)` | Opción activa del segmented control |
| Stage del pipeline | `0 2px 8px rgba(0,0,0,.12)` | Tarjetas de etapa sobre el lienzo punteado |
| Toast | `0 12px 32px rgba(0,0,0,.35)` | Toasts |
| Dialog / Command | `0 24px 60px rgba(0,0,0,.45)` + overlay `rgba(3,10,22,.55)` | Modales, paleta Ctrl+K |
| Intervención | `0 0 0 4px color-mix(in oklch, var(--status-intervening) 22%, transparent)` | Panel de terminal en «Estás interviniendo» |

## 6. Iconografía

**lucide-react**, trazo 2 por defecto, `size-4` (16px) en la navegación, 14–15px en botones y 12–13px en metadatos. El color hereda de `currentColor`.

| Lugar | Icono lucide |
|---|---|
| Dashboard | `LayoutDashboard` |
| Agentes | `Bot` |
| Proyectos | `FolderGit2` |
| Tablero | `SquareKanban` |
| Inbox | `Inbox` |
| Consumo | `ChartColumn` |
| Ajustes | `Settings` |
| Colapsar / expandir sidebar | `PanelLeftClose` / `PanelLeftOpen` |
| Tema | `Sun` / `Moon` |
| Buscar | `Search` |
| Terminal | `SquareTerminal` |
| Nueva / añadir | `Plus` |
| Aprobaciones | `Hand` (cabecera), `ShieldCheck` (tipo) |
| Pregunta | `MessageCircleQuestion` |
| Bloqueo | `OctagonAlert` |
| Completada | `CircleCheck` |
| Solo lectura | `Eye` |
| Tomar control | `Hand` |
| Interviniendo | `Keyboard` |
| Devolver | `Undo2` |
| Pausar / reanudar | `Pause` / `Play` |
| Reintentar | `RotateCcw` |
| Worktree / carpeta | `FolderGit2` / `FolderOpen` / `GitBranch` / `GitFork` |
| Cancelar | `Square` |
| Arquitecto / IA | `Sparkles`, `WandSparkles` (autoseleccionada) |
| Subtareas | `ListChecks` |
| Arrastrar | `GripVertical` |
| Backend caído | `WifiOff` |
| Permisos | `Zap` (Autónomo), `Lock` (Restringido), `Hand` (Preguntar) |
| Subida / URL | `Upload`, `Link` |
| Comprobar CLI | `RefreshCw` |
| Expandir dock | `Maximize2`, `PanelBottom`, `PanelRight`, `X` |

Logos de CLI: el prototipo usa marcadores de texto («CC» Claude Code, «AG» Antigravity, «CX» Codex) en un cuadrado `--primary` con Ubuntu Mono 10/700. **Sustituirlos por los logos oficiales** respetando las guías de marca de cada proveedor.

## 7. Reglas de estados

### Badge de estado (`StatusBadge`)
- Píldora de 22px de alto (20px en tablas y 19px en tarjetas de tarea), `rounded-full`, padding horizontal de 8px, texto 11/500.
- Color de texto = `var(--status-x)`, fondo = `color-mix(in oklch, var(--status-x) 14%, transparent)` y borde de 1px = `color-mix(… 36%, transparent)`.
- Punto de 6px `bg-current` a la izquierda del texto.
- Solo el estado **Ejecutando** lleva el punto pulsante.

### Punto pulsante (indicador en vivo)
- Animación `live-pulse` 1.6s ease-out infinita: un `box-shadow` que se expande de 0 a 7px y se desvanece desde `--status-running` al 70%.
- Se aplica a: el punto del badge «Ejecutando», los nodos en ejecución del árbol, las pestañas del dock en ejecución y los documentos que se están indexando.
- Barra *shimmer* de 2px en el borde superior de las tarjetas de tarea en ejecución: `linear-gradient(90deg, transparent, var(--status-running), transparent)`, `background-size: 200% 100%`, animación `live-shimmer` 1.6s lineal.
- Cursor de la terminal: bloque de 8×15px en `#4CC9F0` con `blink` 1s steps(1).
- Con `prefers-reduced-motion` se desactivan todas las animaciones.

### «Esperando humano»
- Tarjeta de agente: el borde pasa a `color-mix(in oklch, var(--status-waiting) 50%, var(--border))` y el badge dice «Esperándote».
- Sección «Aprobaciones pendientes»: borde con el 45% de waiting, cabecera con fondo al 10% de waiting y contador ámbar sólido (texto `#0A1A33`).
- Contador del Inbox en la sidebar: píldora `#F5B547` con texto `#0A1A33` 11/700.

### «Estás interviniendo» (terminal)
| | Observando (por defecto) | Interviniendo |
|---|---|---|
| Borde del panel | 1px `--border` | **2px `--status-intervening` (#F5B547)** + halo de 4px al 22% |
| Píldora | `Eye` «Solo lectura (observando)», fondo `#13284D`, texto `#C9D5EA` | `Keyboard` «Estás interviniendo», fondo `#F5B547`, texto `#0A1A33` 700 |
| Botón | Primario `#2E5BD6`, `Hand`, «Tomar control» | Outline ámbar, `Undo2`, «Devolver al agente» |
| Pie | Cursor parpadeante «Dev está trabajando…» | Barra de input `❯` con el placeholder «Escribe en la terminal y pulsa Enter…» y la nota «Enter para enviar» (borde superior `#3A3320`) |
| Línea en el log | — | `■ Has tomado el control. El agente queda en pausa hasta que se lo devuelvas.` (ámbar, 700) |

Transición: `box-shadow, border-color` en 200ms.

### Foco
Todos los elementos interactivos: `outline: 2px solid var(--ring); outline-offset: 2px` con `:focus-visible`. Las tarjetas clicables son `button` o `tabindex="0"`.
