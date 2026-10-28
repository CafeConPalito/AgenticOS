# Fase 20: Personalización y Acerca de · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-27)

## Lo que ya se sabe (revisado al escribir el plan)
- **Cabecera** (`components/layout/AppHeader.tsx`): logo, botón **Atrás** (`navigate(-1)`, o al nivel padre si es la primera página de la sesión), **miga de pan** generada por los `handle.crumb` de las rutas (`crumbs.tsx`) con cada nivel enlazable, pestañas (`TopNav`) con contadores de `useHome().counts` (`open_tasks`, `active_runs`), paleta, dock, estado del backend y el conmutador claro/oscuro. **Falta**: Adelante, `Alt+←/→`, botones laterales del ratón y el contador de la Inbox (`HomeCounts` no lo tiene).
- **Tema** (`theme/ThemeProvider.tsx`): `'dark' | 'light'` en `localStorage` (`agentic-os.theme`), aplicado con la clase `.dark` sobre `styles/tokens.css`. El terminal usa una constante fija (`XTERM_THEME` en `components/terminal/use-run-terminal.ts`). Hay **63 colores fijos** (hex o `rgb()`) en 19 ficheros de componentes (primitivas, logo, terminal, Inicio, tareas, Arquitecto…), además de los de `tokens.css`. Fuentes incluidas: Ubuntu y Ubuntu Mono (`@fontsource`).
- **Avatar** (`components/agentic/primitives.tsx`): `AgentAvatar({ name, color, size… })` pinta la inicial sobre el color con texto fijo `#0A1A33`. Se usa en **53 sitios**; muchos reciben solo `agent_name`/`agent_color` de otras entidades (ejecuciones, tareas, Inbox), no el agente.
- **Agente** (`models/agent.py`): `color` `String(9)`; sin imagen. Las plantillas del usuario (`AgentTemplateRow`, fase 19) también guardan `color`. Exportación `agentic-os.agent` v1 en `services/agent_io.py`.
- **Ajustes globales**: tabla `app_state` (clave → JSON), con una clave por dominio (`knowledge`, `skills`, `architect`…). La apariencia será una clave más.
- **Registros**: el backend escribe `<datos>/logs/backend.log` (rotativo 5 MB × 4) solo cuando hay `log_file` (la app empaquetada); en desarrollo, a `stderr`. El *shell* de Tauri tiene `open_logs` (abre la carpeta) y **no escribe registro propio**. `services/proc.py` ya tiene `open_in_file_manager` y `reveal_in_file_manager`. Pillow ya es dependencia.
- **Tauri**: plugins `shell`, `dialog` (solo `allow-open` en las *capabilities*), `notification`, `single-instance`. Los enlaces externos de la app usan `<a target="_blank">`.
- **Acerca de**: sección de Ajustes (`AboutSection.tsx`) con versión, carpeta de datos, backend y «Abrir registros». `tauri.conf.json` tiene `publisher: "Agentic OS"` y no declara copyright ni licencia.
- Última migración: `0021_architect`. Último ADR: 0026. zod ya está en el frontend.

## Bloque 0 · Spikes (antes de programar)
Scripts en `spikes/personalization/`; evidencias en `evidencias/`.

| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Búhos**: ¿hay un set libre (CC0, CC-BY o MIT/OFL) con ≥ 12 búhos del mismo estilo y variantes (sombrero, gafas, auriculares, libro…), en SVG o PNG ≥ 256 px, que se vea bien a 16, 24 y 48 px sobre colores claros y oscuros? | Set propio en SVG por capas: búho base (2–3 posturas) + accesorios (sombreros, gafas, auriculares, bufanda, libro, pajarita) combinados en ≥ 12 variantes fijas, con licencia del proyecto (decidido en la spec) |
| S2 | **Inventario de colores fijos**: los 63 colores en componentes y los de `tokens.css`: cuáles pasan a un *token* existente, cuáles necesitan uno nuevo (p. ej. `--avatar-foreground`, `--terminal-*`, `--logo-*`) y cuáles se quedan fijos con motivo (p. ej. colores de datos de terceros) | Si salen más de ~30 *tokens* nuevos, se agrupan y el terminal se deja para el final del bloque 3 |
| S3 | **Navegación e integración en WebView2** (app empaquetada): (a) ¿los botones laterales del ratón (X1/X2) llegan como `mouseup` con `button` 3/4 o el WebView los convierte en atrás/adelante por su cuenta? (b) ¿cómo saber si hay «adelante» con React Router (índice `idx` de `history.state`)? (c) ¿un `mailto:` abierto desde la UI llega al cliente de correo predeterminado (con `target`, con `plugin-shell` `open` o desde el backend con `os.startfile`)? ¿Cuánto cuerpo admite sin cortarse? (d) ¿el diálogo «Guardar como» de `plugin-dialog` funciona con la *capability* `dialog:allow-save`? | (a) sin eventos: solo botones y `Alt+←/→`; (b) pila propia de navegación en un *store*; (c) se abre desde el backend con `os.startfile`; cuerpo corto y el resto en `info.txt` |
| S4 | **Qué hay en los registros reales**: con la app empaquetada, una sesión con Claude y `agy`, una conexión MCP con secreto, OAuth y un error de backend; buscar *tokens* de ejecución (`/r/<token>/`, `/a/<token>/`), cabeceras, claves de API, *tokens* OAuth, correos, rutas con el usuario, nombres de proyectos y textos de tareas | Ajustar la lista de patrones de limpieza; lo que no se pueda limpiar con fiabilidad se deja de registrar (cambio en el código que lo registra) |
| S5 | **Licencias**: listar las dependencias de producción de frontend (`npm`), backend (`uv`, incluidas las que empaqueta PyInstaller) y Tauri (`cargo`), con su licencia; marcar las incompatibles con GPLv3 o sin licencia; elegir cómo generar la lista en el *build* (`license-checker-rseidelsohn`, `pip-licenses`, `cargo-about` o un script propio) | Una dependencia incompatible se sustituye o se pregunta al usuario antes de seguir |
| S6 | **Recorte de fotos**: `react-easy-crop` (MIT) u otro: arrastrar y zoom con ratón y rueda, orientación EXIF, leer el tamaño **antes** de decodificar entera (`createImageBitmap` / cabecera) para rechazar > 2048 px, y codificar el recorte a WebP 256 × 256 con `canvas.toBlob` en WebView2. Peso típico del resultado | PNG en lugar de WebP; si la cabecera no se puede leer sin decodificar, se decodifica y se descarta al instante (sin guardarla en ningún sitio) |

## Resultados de los spikes (bloque 0, 2026-10-27)
Evidencias en [`evidencias/`](evidencias/); scripts en `spikes/personalization/`.

- **S1 · búhos**: ❌ no hay un set libre coherente con variantes (solo iconos sueltos CC0, como el de Emojione, o *packs* de pago o con licencia propia). → **Set propio en SVG por capas** (`spikes/personalization/owls.py`): búho base + 12 variantes (sin nada, chistera, birrete, gafas, gafas de sol, auriculares, pajarita, bufanda, gorro, corona, libro, monóculo, mago). Vista en [`evidencias/owls/preview.png`](evidencias/owls/preview.png): se reconocen desde 24 px; a 16 px solo la silueta, que basta para las listas. Para el set final: accesorios de abajo (pajarita, bufanda, libro) subidos al pecho, sombreros altos más bajos, y borde claro en los accesorios oscuros (birrete, chistera), que se pierden sobre colores oscuros.
- **S2 · colores fijos**: 63 en 19 ficheros, en cuatro grupos:
  - **terminal** (≈30: `XTERM_THEME`, `TerminalDock`, `TerminalPanel`) → *tokens* nuevos `--terminal-muted`, `--terminal-accent`, `--terminal-chip`, `--terminal-dot` y los 16 ANSI `--ansi-*`, más `--terminal-cursor` y `--terminal-selection`;
  - **marca** (`Logo.tsx`) → `--logo-from`, `--logo-to`, `--logo-dot`;
  - **aviso ámbar con texto oscuro** (`AgentCard`, `NeedsYouPanel`, `#F5B547`/`#0A1A33`) → `--status-intervening` (ya existe) y nuevo `--status-intervening-foreground`; el texto de las iniciales del avatar → `--avatar-foreground` (calculado por contraste); `#7F8DAA` de `RequestItem` → `--muted-foreground`;
  - **colores de datos** (paletas de agentes y proyectos en `page.tsx` y `NewProjectDialog`, color por defecto de un agente, serie de `SkillStats`, `USER_COLOR` de la memoria): no son del tema, son colores que elige el usuario o que identifican datos. Se juntan en `theme/palettes.ts` (única excepción del test de colores fijos); `SkillStats` pasa a `--chart-*`.
  - En total, ~11 *tokens* nuevos + 16 ANSI: por debajo del umbral, el terminal entra en el bloque 3.
- **S3 · navegación e integración en WebView2**: ✅ prueba manual del usuario en `tauri dev` (2026-10-27), con una página de prueba temporal (no commiteada):
  1. `Alt+←/→` y los botones laterales del ratón **ya navegan solos** (atajos del navegador de WebView2; el SPA recibe `popstate`).
  2. React Router guarda la posición en `history.state.idx`; «Adelante» se calcula con él.
  3. Un `mailto:` abre el cliente de correo con las tres vías probadas (`<a href>`, `target="_blank"` y `window.open`), con asunto y cuerpo (~1,6 KB, acentos y emoji) correctos.
  4. «Guardar como» funciona con la *capability* `dialog:allow-save`.
- **S4 · registros**: ⚠️ con un backend de prueba que escribe a fichero ([`evidencias/s4-logs.txt`](evidencias/s4-logs.txt)), **el registro de accesos de uvicorn escribe los *tokens* de ejecución (`/r/<token>/…`) y del Arquitecto (`/a/<token>/…`) y la *query* completa** (claves, contraseñas o correos que lleve una URL). Además: los fallos de OAuth registran `repr(error)` (puede llevar URLs), y las rutas de la carpeta de datos incluyen el usuario de Windows. No hay `rich` ni `better_exceptions`, así que las trazas no llevan variables locales.
- **S5 · licencias**: ✅ todo compatible con GPLv3.
  - Frontend: 259 paquetes, MIT/ISC/BSD/Apache-2.0/0BSD.
  - Backend: 110, también MPL-2.0 (`certifi`, `tqdm`), LGPL-3.0 (`pyte`), PSF, `tld` (MPL-1.1 / GPL-2.0 / LGPL-2.1+, se usa como LGPL) y MIT-CMU (Pillow).
  - Tauri: 260 *crates* para Windows, MIT/Apache-2.0/Unicode-3.0/MPL-2.0/Zlib/BSD.
  - La única a anotar es la **Ubuntu Font Licence** (`@fontsource/ubuntu`): las fuentes van como ficheros aparte (agregado), sin problema; se cita en terceros.
  - Generación: **script propio** (`scripts/licenses.py`) con los mismos métodos del spike (árbol de `dependencies` de `node_modules`, `importlib.metadata` del entorno sin el grupo *dev*, `cargo metadata --filter-platform`), sin dependencias nuevas.
- **S6 · recorte**: ✅ en Edge (mismo motor que WebView2; [`evidencias/s6-crop.txt`](evidencias/s6-crop.txt)).
  - El tamaño se lee de la **cabecera** de PNG, JPEG y WebP en < 5 ms, sin decodificar; las de 3000 × 2000 se rechazan antes de abrirlas.
  - Recorte a 256 × 256 en WebP con `canvas.toBlob`: **12–15 KB**.
  - `react-easy-crop` 6.2.4 (MIT, una dependencia) para arrastrar y hacer zoom. `createImageBitmap` aplica la orientación EXIF.

### Cambios al diseño por los spikes
1. **Búhos propios** (§5): `frontend/src/assets/owls/*.svg` generados por un script versionado (`scripts/owls.py`, a partir del de S1) con su licencia del proyecto; `owls.json` sin atribución externa.
2. **Registros sin secretos en origen** (§7): un filtro de `logging` en `logging_setup.py` enmascara, **antes de escribir**, los *tokens* de `/r/<token>/` y `/a/<token>/` y los valores de la *query* de las líneas de `uvicorn.access`, y los fallos de OAuth registran el tipo de error y el *host*, no `repr(error)`. La limpieza del zip (`services/redact.py`) se queda como segunda barrera (registros antiguos, terceros).
3. **Lista de terceros** (§6): script propio, sin `license-checker`, `pip-licenses` ni `cargo-about`.
4. **Atrás/Adelante con teclado y ratón** (§2): la app **no** registra `Alt+←/→` ni los botones X1/X2, porque WebView2 y el navegador ya lo hacen (capturarlos navegaría dos veces). Solo se añade el botón «Adelante» y los atajos aparecen en la ayuda de atajos como informativos.
5. **`mailto`** (§6 y §7): enlace `<a href>` normal, sin `plugin-shell` ni el backend.

### Cambios al diseño durante el desarrollo
6. **Contador de la Inbox** (§2, bloque 2): reutiliza `GET /inbox/summary` (`useInboxSummary`, que ya se consulta cada 3 s para las notificaciones) en lugar de añadir `inbox_pending` a `HomeCounts`; sin cambios en el backend.
7. **«Adelante»** (§2, bloque 2): la pila de navegación se sigue con los eventos de React Router (`PUSH`, `REPLACE`, `POP`) en `use-history-stack.ts`, no con `history.state.idx`, que no existe con el router en memoria de los tests. Tras recargar a mitad del historial, «Adelante» empieza desactivado (los atajos del WebView siguen funcionando).
8. **Menos ruido** (§2, bloque 2; revisado con el usuario sobre capturas el 2026-10-27): en la ficha del agente, «Mejorar con el Arquitecto» pasa al menú «⋯», Resumen pierde «Editar» y las pestañas «Historial» y «Cambios» pasan a «Historial de la ficha» y «Código cambiado»; Ajustes agrupa sus secciones bajo Aplicación, Agentes, Recursos y Mantenimiento; en Inicio, «Nuevo agente», «Crear con el Arquitecto» y «Nuevo equipo» pasan a un único «Nuevo». Descartado: ocultar el selector de idioma, reducir el estado del backend a un punto y más cambios en Inicio. El tema pasa a Apariencia en el bloque 4.
9. **Temas** (§3, bloque 3):
   - Los conjuntos base Claro y Oscuro navy viven en `theme/model.ts` y un test los mantiene iguales a `tokens.css`; los demás temas (incluidos y propios) solo guardan lo que cambian.
   - Los *tokens* compuestos (`--sep`, `--glass`, `--card-grad` con el nuevo `--card-top`, sombras y `--atmos`) se calculan con `color-mix` a partir de los básicos, para que un tema los arrastre.
   - La fuente pasa por `--app-font` (`@theme inline` congelaba el valor); la densidad, por `--spacing` de Tailwind v4; el radio, por `--radius`.
   - La **escala de texto es el zoom del WebView** (`setZoom`, permiso `core:webview:allow-set-webview-zoom`): dos tercios de los tamaños de texto están en píxeles fijos y el `zoom` de CSS rompería los `100vh`. En el navegador de desarrollo no se aplica (usa el zoom del navegador).
   - **Contraste**: 4,5:1 para el texto; 3:1 (criterio WCAG de componentes) solo para las etiquetas de los botones sobre su color de acción, porque el rojo de «destructivo» del Oscuro navy actual da 3,9:1 y no se cambia el diseño existente sin pedirlo. Los cinco temas incluidos pasan.
   - El fondo del terminal es `--terminal` en los dos modos (antes, el de xterm era siempre `#050e1e`): en el tema Claro pasa a `#0a1a33`, el mismo que su panel.
   - Fuentes nuevas: Inter y Atkinson Hyperlegible (OFL-1.1), solo el juego latino.
10. **Apariencia** (§4, bloque 4): en Ajustes, una sección «Apariencia» del grupo Aplicación (tema en pantalla y enlace) sustituye al selector de General; la página es `/ajustes/apariencia` y el editor de cada tema propio, `/ajustes/apariencia/<id>` con su miga de pan (Atrás/Adelante funcionan). Los temas incluidos no se editan ni se exportan: «Personalizar» crea una copia que parte de ellos. Borrar un tema en uso vuelve al Oscuro navy o al Claro, y los temas que partían de él pasan a partir del suyo.
11. **Avatares, backend** (§5, bloque 5): el recorte llega como cuerpo binario de `PUT /agents/{id}/avatar` (PNG, WebP o JPEG; sin `multipart`) y la imagen se sirve en `GET /avatars/<hash>.webp` con caché inmutable. La lista de búhos está en `services/avatars.py` (`OWL_IDS`) y un test la compara con los SVG de `frontend/src/assets/owls/`, generados por `scripts/owls.py` (sin `owls.json` compartido). Las fotos cuentan en el uso de disco dentro de «otros», sin campo propio. `propose_agent` (agentes) no pone imagen; solo el Arquitecto, y solo búhos (`list_owls`).
12. **Avatares, interfaz** (§5, bloque 6): la imagen se elige en la pestaña General de la ficha del agente y se aplica al momento (una foto hay que subirla de todos modos), sin pasar por «Guardar cambios»; el color sí. El diálogo de nuevo agente no la ofrece, igual que hoy no ofrece el color (lo trae la plantilla): se elige después en la ficha. La ficha del Arquitecto muestra el búho que propone, pero no se cambia a mano desde ella. `AgentAvatar` busca la imagen por `agentId` en la lista de agentes cuando solo tiene el nombre y el color; por eso las ramas de una tarea (`LaneRead`) ganan `agent_id`. Vite incrusta los SVG de los búhos como `data:` URL.
13. **Acerca de** (§6, bloque 7): `scripts/licenses.py` es Python puro (recorre `node_modules`, `uv export --no-dev` + `importlib.metadata` y `cargo metadata`) y guarda un *hash* de cada *lockfile*; el test que lo vigila está en el backend (`test_third_party_licenses.py`), que también comprueba que todas las licencias sean compatibles con la GPL. El JSON generado queda fuera de Prettier. El texto completo de `LICENSE` y la lista de terceros se cargan bajo demanda (`import()`), fuera del paquete principal. La versión de la interfaz sale de `frontend/package.json` (`__APP_VERSION__`); la del backend solo se muestra si es distinta. En Ajustes, la sección «Acerca de» queda como resumen con enlace a la página.

## Diseño ([ADR 0027](../../adr/0027-personalization-support.md), nuevo)

### 1. Licencia y autoría
- `LICENSE` en la raíz con el texto de la GPLv3 de la plantilla de GitHub (el de la FSF, sin cambios).
- SPDX `GPL-3.0-or-later` en `package.json` (raíz, `frontend`, `desktop`), `backend/pyproject.toml` y `desktop/src-tauri/Cargo.toml`; `tauri.conf.json` con `copyright: "Copyright (C) 2026 Albano Díez de Paulino"` y `publisher: "Café con Palito"`; el instalador NSIS muestra la licencia (`licenseFile`).
- README: sección «Licencia» y aviso de copyright.
- Logos copiados a `frontend/src/assets/brand/ccp-logo.png` y `ccp-logo-negative.png` (de `D:\DAM\LOGO CCP\logo-simple-rb.png` y `logo-simple-negative-rb.png`), optimizados.

### 2. Navegación
- **Atrás / Adelante**: dos botones juntos a la izquierda de la miga de pan. «Atrás» mantiene la regla actual (al padre si no hay historial). «Adelante» se desactiva cuando no hay nada delante (índice de `history.state` o pila propia, según S3).
- Atajos `Alt+←` / `Alt+→` registrados en `lib/shortcuts.ts` (aparecen en la ayuda de atajos y en la paleta); botones X1/X2 del ratón si S3 lo confirma.
- La miga de pan no cambia de comportamiento; se añaden los *crumbs* de Apariencia y Acerca de.
- **Contador de la Inbox**: `HomeCounts.inbox_pending` (pendientes no resueltos) y un botón de la Inbox con su número junto a la paleta (no es una pestaña nueva: las pestañas siguen como en la fase 09). Se refresca con las mismas invalidaciones que ya usa `useInboxNotifier`.
- **Menos ruido**: al empezar el bloque 2 se hace el inventario con capturas de Inicio, editor de agente y Ajustes y se revisa con el usuario (acciones secundarias a un menú «⋯», agrupación de secciones de Ajustes, espaciado y títulos). Solo se aplica lo que el usuario apruebe en esa revisión.

### 3. Temas
- **Modelo** (`theme/model.ts`, validado con zod en el frontend y con Pydantic en el backend):
  ```
  { format: "agentic-os.theme", version: 1, id, name, base: "light" | "dark",
    colors: { background, foreground, card, primary, primary-action, accent, muted, border,
              sidebar, status-*, graph-*, ... },   // los tokens de tokens.css
    terminal: { background, foreground, cursor, selection, ansi: [16] },
    font: "ubuntu" | "inter" | "atkinson" | "system", scale: 0.875–1.25,
    density: "compact" | "normal" | "comfortable", radius: 0–20 }
  ```
  Solo se guardan los valores que difieren del tema del que parte (`extends`), para que los temas propios sobrevivan a cambios de los incluidos.
- **Temas incluidos** (`theme/builtin/`): Oscuro navy (el actual), Claro (el actual), Alto contraste (oscuro), Cálido (claro, tonos crema/terracota) y Grafito (oscuro neutro). Todos pasan el test de contraste AA.
- **Aplicación**: `ThemeProvider` escribe las variables CSS en `document.documentElement.style` y mantiene la clase `.dark` según `base` (para las variantes `dark:` de Tailwind). Densidad y escala como variables (`--density`, `--font-scale`) que usan los espaciados y el tamaño base. El terminal lee su tema del proveedor y lo cambia en vivo (`terminal.options.theme`).
- **Seguir al sistema**: elige un tema para claro y otro para oscuro (por defecto Claro y Oscuro navy) y escucha `prefers-color-scheme`.
- **Persistencia**: `app_state["appearance"] = { mode: "fixed" | "system", theme, light_theme, dark_theme, custom: [temas] }` con `GET/PUT /settings/appearance`; `localStorage` guarda el tema resuelto y un *script* en `index.html` lo pinta antes de montar React (sin parpadeo). El conmutador de la cabecera alterna entre los temas claro y oscuro elegidos.
- **Colores fijos** (inventario de S2): pasan a *tokens*; un test (`no-hardcoded-colors.test.ts`) busca hex/`rgb()` en `src/` salvo en `theme/builtin/` y una lista de excepciones con motivo.
- **Logo de la marca**: `<BrandLogo>` elige la versión normal o la negativa según `base`.

### 4. Ajustes › Apariencia
- Ruta `/ajustes/apariencia` (con *crumb*), enlazada desde Ajustes › General, que deja de tener el selector de tema.
- Lista de temas (incluidos y propios) con miniatura; aplicar, duplicar, renombrar, borrar (solo propios), exportar (`.json`) e importar (validado; un error dice el campo y el motivo).
- Editor a dos columnas: controles agrupados (Superficies, Texto, Acción y acento, Estados, Barra superior, Terminal, Tipografía y densidad, Esquinas) y **vista previa en vivo** con una muestra de la app (cabecera, tarjeta de agente, tabla, botones, *badges* de estado, diff y terminal). Los cambios se ven en toda la app mientras se edita y «Descartar» vuelve al guardado.
- **Contraste**: `theme/contrast.ts` (luminancia relativa WCAG 2.x) sobre los pares definidos (texto/fondo, texto/tarjeta, texto en primario, texto atenuado, estados sobre tarjeta); aviso junto al control, sin bloquear.

### 5. Avatares de los agentes (migración `0022_agent_avatar`)
- `agents.avatar` y `agent_templates.avatar`: `String(80)`, nulo = iniciales; `owl:<id>` = búho de la galería; `photo:<sha256-12>` = foto.
- **Fotos**: `<datos>/avatars/<sha>.webp`. `PUT /agents/{id}/avatar` (multipart) recibe **solo el recorte**: el backend comprueba con Pillow que es PNG/WebP, cuadrado, ≤ 512 px y ≤ 300 KB, lo reescribe a WebP 256 × 256 sin metadatos y guarda el hash. `DELETE` vuelve a iniciales. `GET /avatars/{sha}.webp` con caché inmutable. La limpieza periódica (`housekeeping`) borra los ficheros que ya no usa ningún agente ni plantilla. La carpeta cuenta en el uso de disco de Ajustes.
- **Nunca la original**: el recorte se hace en el navegador sobre un `ImageBitmap` en memoria; no se sube, no se escribe en disco ni en `localStorage`, y se libera (`close()`) al cerrar el diálogo. La comprobación de 2048 px se hace con las dimensiones antes de mostrarla.
- **Búhos**: `frontend/src/assets/owls/` con `owls.json` (`id`, nombre, etiquetas, autor y licencia). El backend tiene la lista de `id` válidos (fichero compartido `shared/owls.json` leído por los dos) para validar `owl:<id>`.
- **Exportación** `agentic-os.agent` v1: campo opcional `avatar` (`owl:<id>` tal cual; la foto como `data:image/webp;base64,…`). Los ficheros antiguos sin `avatar` siguen siendo válidos.
- **Arquitecto**: `update_sheet` acepta `avatar` solo con `owl:<id>` existente; las instrucciones base mencionan la galería (`list_owls` de solo lectura).
- **Frontend**: `AgentAvatar` gana la prop `avatar` y, si no se pasa, la busca por `agentId` en la lista de agentes en caché (`useAgents`), así los 53 sitios solo añaden `agentId` donde no tienen el agente. El texto de las iniciales usa `--avatar-foreground` elegido por contraste con el color.
- **Selector** (`AvatarPicker`) en el editor del agente, el diálogo de nuevo agente y la ficha del Arquitecto: pestañas Búhos · Foto · Iniciales, y el **color** con paleta sugerida (12 colores que se distinguen en claro y oscuro) + hex, con aviso de bajo contraste con la tarjeta del tema actual.

### 6. Página Acerca de
- Ruta `/acerca-de` (crumb «Acerca de»), entrada en la paleta y enlace desde Ajustes (la sección `AboutSection` desaparece; sus datos pasan aquí).
- Bloques: cabecera (logo de la app, nombre, versión de la UI, del backend y del *sidecar*); **autoría** (`BrandLogo` + «Made By Café Con Palito with ❤️» + «Albano Díez de Paulino»); **licencia** (resumen y texto completo de `LICENSE`, importado con `?raw`, en un panel desplegable); **licencias de terceros** (tabla con buscador desde `third-party-licenses.json`, incluida la atribución de los búhos); **sistema** (carpeta de datos, backend, abrir registros); **ayuda** («Informar de un error» y «Preparar registros para enviar»).
- `lib/bug-report.ts`: construye el `mailto:contacto@cafeconpalito.com?subject=…&body=…` (versión, SO, plantilla) con `encodeURIComponent`, recortado a la longitud que confirme S3.
- `scripts/licenses.py` (y lo que elija S5) genera `frontend/src/generated/third-party-licenses.json`; se ejecuta en el *build* del instalador y un test comprueba que el fichero no está desfasado respecto a los *lockfiles* (hash).

### 7. Registros para enviar
- **Errores del frontend**: `lib/client-log.ts` con un búfer circular (200 entradas) de `window.onerror`, `unhandledrejection`, `console.error/warn` y errores de React Query; envía lotes a `POST /support/client-log` (como mucho 1 cada 5 s y 50 entradas por lote). El backend los registra con el *logger* `frontend` en el mismo `backend.log`.
- **Registro del *shell***: `sidecar.rs` escribe `<datos>/logs/desktop.log` (rotado al arrancar si pasa de 1 MB) con arranque, parada, reinicios y caídas del *sidecar*, y su `stderr` si muere.
- **Backend** (`services/support.py`):
  - `GET /support/logs/preview` → ficheros que entrarían, tamaño de cada uno y total.
  - `POST /support/logs/bundle { dest }` → escribe el `.zip` en `dest` (o en Descargas) y devuelve la ruta.
  - Contenido: `backend.log*` (los últimos 10 MB en total, de más nuevo a más viejo), `desktop.log`, `info.txt` (versión, SO, CLIs y versiones, recuentos). Nada de `runs/`, transcripts, conocimiento ni la base de datos.
  - **Limpieza** (`services/redact.py`), línea a línea antes de escribir en el zip: *tokens* de ejecución (`/r/…`, `/a/…`), cabeceras `Authorization`/`Cookie`, patrones de claves (`sk-…`, `ghp_…`, `xox…`, JWT, `key=`/`token=`/`password=` en URLs y JSON), los **valores actuales** de los secretos del almacén del sistema (fase 18) y de las cuentas, correos y `C:\Users\<nombre>` → `C:\Users\<usuario>`. Cada sustitución deja `«oculto»` y el `info.txt` dice cuántas hubo por tipo.
- **Interfaz**: diálogo «Preparar registros» (lista y tamaño de la *preview*, aviso de qué no se incluye) → «Guardar como» (`plugin-dialog` `save`, con *capability* `dialog:allow-save`; en el navegador de desarrollo, a Descargas) → al terminar: «Mostrar en la carpeta» (`reveal_in_file_manager`) y «Abrir correo» (el `mailto` con el cuerpo indicando que adjunte el `.zip` y su nombre). También desde `OfflineBanner` cuando el backend no responde: ahí, sin backend, el *shell* comprime solo `desktop.log` y `backend.log` aplicando los patrones fijos de limpieza (comando Tauri `bundle_logs`).

## Archivos
| Archivo | Cambio |
|---|---|
| `LICENSE`, `README.md`, `package.json` ×3, `backend/pyproject.toml`, `desktop/src-tauri/Cargo.toml`, `tauri.conf.json` | licencia y autoría |
| `frontend/src/assets/brand/*`, `assets/owls/*`, `shared/owls.json` | nuevos |
| `components/layout/AppHeader.tsx`, `nav.ts`, `crumbs.tsx`, `lib/shortcuts.ts`, `routes.tsx` | Adelante, atajos, Inbox, rutas nuevas |
| `backend/.../schemas/home.py`, `services/home.py` | `inbox_pending` |
| `styles/tokens.css`, `theme/*` (`ThemeProvider`, `model.ts`, `builtin/`, `contrast.ts`, `apply.ts`), `index.html` | motor de temas |
| `pages/settings/AppearancePage.tsx` + `appearance/*` | nuevo |
| `api/settings.py` (+ `schemas`), `models/app_state.py` | `appearance` |
| componentes con colores fijos (19, según S2), `components/terminal/use-run-terminal.ts` | a *tokens* |
| `db/migrations/versions/0022_agent_avatar.py`, `models/agent.py`, `api/agents.py`, `services/avatars.py`, `services/agent_io.py`, `services/housekeeping.py`, `services/datadir.py`, `services/architect/*` | avatares |
| `components/agentic/primitives.tsx`, `components/agentic/AvatarPicker.tsx`, `ColorPicker.tsx`, editor y diálogo de agente, ficha del Arquitecto | avatares en la UI |
| `pages/about/AboutPage.tsx`, `lib/bug-report.ts`, `generated/third-party-licenses.json`, `scripts/licenses.py` | Acerca de |
| `lib/client-log.ts`, `api/support.py`, `services/support.py`, `services/redact.py`, `desktop/src-tauri/src/sidecar.rs`, `lib.rs`, `capabilities/*.json`, `OfflineBanner.tsx` | registros |
| `frontend/src/i18n/es/*.json` | textos nuevos |
| `docs/adr/0027-personalization-support.md`, `README.md` | documentación |

## Tareas (en orden)
Bloques pequeños, cada uno con sus tests y su commit.

0. [x] **Spikes S1–S6** y resultados en este plan; cambios al diseño, si los hay, con el OK del usuario.
1. [x] **Licencia y autoría**: `LICENSE`, manifiestos, `tauri.conf.json`, README, logos. Revisión de licencias de S5 resuelta.
2. [x] **Navegación**: Adelante, `Alt+←/→`, ratón; contador de la Inbox; inventario de ruido con capturas → revisión con el usuario → cambios aprobados.
3. [x] **Motor de temas**: modelo, temas incluidos, aplicación por variables, seguir al sistema, persistencia en `app_state` sin parpadeo, terminal en vivo, colores fijos a *tokens* y test de colores fijos.
4. [x] **Ajustes › Apariencia**: lista, editor con vista previa, contraste, exportar/importar.
5. [x] **Avatares (backend)**: migración, almacenamiento y validación, API, limpieza, uso de disco, exportación/importación, Arquitecto.
6. [x] **Avatares (interfaz)**: búhos, `AvatarPicker` con recorte, color con aviso, `AgentAvatar` en los 53 sitios.
7. [x] **Acerca de**: página, autoría con logo según tema, licencia y terceros, `mailto`, paleta y enlace desde Ajustes.
8. [ ] **Registros**: errores del frontend, `desktop.log`, *bundle* con limpieza, diálogo y Guardar como, abrir correo, ruta sin backend.
9. [ ] **Cierre**: ADR 0027 aceptado, README, e2e con el binario empaquetado, `/code-review`, suites completas y `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `AppHeader.test.tsx`: Adelante activo/inactivo, `Alt+←/→`, contador de la Inbox | CA2 |
| Tests de pantallas revisadas (Inicio, editor, Ajustes) tras el inventario | CA1 |
| `primitives.test.tsx` (`AgentAvatar`: búho, foto, iniciales; búsqueda por `agentId`) y tests de las pantallas que lo usan | CA3 |
| `AvatarPicker.test.tsx`: rechazo > 2048 px y formato; solo se envía el recorte | CA4 |
| `test_avatars.py`: validación del recorte (formato, tamaño, peso), reescritura sin metadatos, borrado de huérfanos, nada en temporales | CA4 |
| `test_agent_io.py`: ida y vuelta con búho y con foto; fichero v1 sin `avatar` | CA5 |
| `ThemeProvider.test.tsx`: cambio en vivo, `system` con `matchMedia`, terminal, caché sin parpadeo | CA6 |
| `appearance.test.tsx` + `test_settings_appearance.py`: crear, editar, exportar, importar, JSON no válido | CA7 |
| `contrast.test.ts`: cálculo WCAG y los cinco temas incluidos en AA | CA8 |
| `no-hardcoded-colors.test.ts` | CA9 |
| `AboutPage.test.tsx`: autoría, logo según tema, licencia completa, terceros | CA10 |
| `bug-report.test.ts`: `href` del `mailto` | CA11 |
| `test_support.py` + `test_redact.py`: contenido del zip, exclusiones, secretos sembrados (incluidos los del almacén) eliminados | CA12 |
| e2e con el binario empaquetado: preparar registros, fichero en la carpeta, `reveal` y `mailto` (prueba manual del cliente de correo) | CA13 |
| Revisión de `LICENSE` y manifiestos (+ test del JSON de terceros al día) | CA14 |
| Suites completas, ruff, ESLint, `tsc` | CA15 |

## Decisiones (ADR)
- **ADR 0027** (nuevo, propuesto): temas como datos (JSON de *tokens* en `app_state`, aplicados como variables CSS, `extends` para los propios); avatares solo como recorte reescrito en el backend, nunca la original; registros para soporte generados en local, limpiados y enviados por el usuario a mano (sin servidor ni telemetría).
- ADR 0013 (navegación) no cambia: las pestañas se quedan como están; Adelante y la Inbox en la cabecera se anotan en él como ampliación.
