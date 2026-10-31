# Fase 22: Temas y apariencia · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-31)

## Lo que ya se sabe (revisado al escribir el plan)
- **Modelo** (`frontend/src/theme/model.ts`):
  - `themeSchema` es `agentic-os.theme` v1 con `extends` obligatorio.
  - `font` es un enum de cuatro fuentes (`ubuntu`, `inter`, `atkinson`, `system`).
  - `Appearance` tiene `mode` (`fixed` | `system`), `theme`, `light_theme`, `dark_theme` y `custom`.
  - `BASE_TOKENS` son los dos juegos base, claro y navy, de 95 *tokens* cada uno.
- **Backend** (`schemas/appearance.py`): el mismo esquema en Pydantic con `extra="forbid"` y la lista `BUILTIN_THEMES` de los cinco ids.
  - `services/appearance.load` devuelve los valores por defecto si lo guardado no valida. Si se quitaran campos sin más, un documento antiguo con `mode` se perdería entero, temas propios incluidos.
- **Temas incluidos** (`theme/builtin.ts`):
  - Hay cinco. Cada uno guarda solo lo que cambia sobre su base, a mano, con 40–60 *tokens* por tema.
  - `contrast.test.ts` comprueba el contraste de cada id de `BUILTIN_IDS`, y `titlebar.test.ts` recorre `BUILTIN_THEMES`.
  - Los nombres salen de i18n (`appearance.builtin.<id>`).
- **Aplicar** (`theme/apply.ts`): `FONT_STACKS[font]` en `--app-font`. `index.html` pinta antes de React con `agentic-os.theme.applied`.
- **Selector claro/oscuro**:
  - `toggleTheme` y `setTheme` de `ThemeProvider` se usan en `AppHeader.tsx:213` y en `CommandPalette.tsx:163`, en la acción `palette.actions.toggleTheme`.
  - `theme` (la base) lo siguen necesitando los avisos (`sonner`) y las variantes `dark:`.
- **Galería y editor** (`pages/settings/appearance/`):
  - `AppearancePage` tiene la sección «Modo», con `Segmented` fijo/sistema y los dos `Select`, y la rejilla de temas.
  - Un tema propio nace solo con «Personalizar/Duplicar» (`duplicate`).
  - `ThemeEditorPage` tiene un `Select` de `extends`, el `Segmented` de base y un `Select` con las cuatro fuentes.
  - `theme-io.parseTheme` exige que `extends` exista.
- **Menú de Ajustes** (`pages/settings/SettingsPage.tsx`):
  - `SECTION_GROUPS` tiene cuatro grupos: app, agentes, recursos y mantenimiento.
  - El título de grupo es un `<p>` de 10,5 px, monoespaciado, en mayúsculas y `text-muted-foreground`, el mismo color que las opciones. Por debajo de `lg` se oculta (`max-lg:hidden`) y las opciones pasan a una fila con `flex-wrap`.
- **Licencias**:
  - `scripts/licenses.py` genera `frontend/src/generated/third-party-licenses.json` desde los ficheros de bloqueo (npm, Python y Rust), y lo muestra `pages/about/AboutPage.tsx`.
  - Las paletas de temas de terceros no son dependencias: no salen de ningún fichero de bloqueo.
- **Rust**: no hay ningún *crate* de fuentes en `Cargo.lock`.
- **Numeración**: el último ADR es el 0027 y la última migración la 0023. Esta fase no toca tablas: la apariencia es un JSON en `app_state`.

## Bloque 0 · Spike (antes de programar)
| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Fuentes del sistema en Windows**. (a) ¿`fontdb` (Rust puro, MIT) lista las fuentes de `C:\Windows\Fonts` y también las instaladas solo para el usuario (`%LOCALAPPDATA%\Microsoft\Windows\Fonts`)? (b) ¿WebView2 pinta con `font-family: "<nombre>"` cada familia que da `fontdb`, incluidas las de varios pesos («Segoe UI», «Cascadia Code»)? (c) ¿Cuánto tarda la primera lista y cuánto añade al binario? (d) ¿WebView2 ofrece `window.queryLocalFonts()`? | (a) Si `fontdb` no ve las fuentes del usuario, se leen las dos claves `…\CurrentVersion\Fonts` del registro (HKLM y HKCU) con `winreg`. (b) Se guarda el nombre tipográfico (`typographic family`) en lugar del de la familia antigua. (d) Si existe y no pide permiso, puede sustituir al comando de Rust; se decide con los datos. |

## Diseño
### 1. Formato del tema: `agentic-os.theme` v2 (ADR 0028)
- La v2 es una **ampliación compatible**: todo fichero v1 es un v2 válido.
  - `version` admite `1 | 2`; se escribe siempre `2`.
  - `extends` pasa a ser **opcional**. Sin él, el tema parte del juego base de su `base`; así se representa un tema creado «desde cero».
  - Campo nuevo **`font_family`**: el nombre de una fuente del sistema, de 1 a 80 caracteres, con letras, cifras, espacios y `.-_'&()+`. Si está, tiene prioridad sobre `font`. El patrón evita inyectar CSS al ponerlo entre comillas en `--app-font`.
- Igual en `themeSchema` (zod) y en `ThemeDefinition` (Pydantic).
- `resolveTheme`:
  - Una cadena sin `extends` empieza en `BASE_TOKENS[base]`.
  - `ResolvedTheme` gana `fontFamily: string | null`.
  - `cssVariables` escribe `"<familia>", system-ui, 'Segoe UI', sans-serif`. Si la fuente falta, el navegador cae solo a la fuente del sistema, que es lo que pide la spec.
- `theme-io.parseTheme` valida `extends` solo si viene.

### 2. Sin selector claro/oscuro ni «Seguir al sistema»
- **Frontend**:
  - `ThemeProvider` pierde `setTheme`, `toggleTheme` y `useSystemDark` para el tema.
  - Se quitan el botón de `AppHeader`, la acción de `CommandPalette` y sus claves de i18n.
  - `activeThemeId` desaparece: siempre se usa `appearance.theme`.
- **Backend**:
  - `Appearance` queda con `theme` y `custom`.
  - Un validador `mode="before"` acepta los documentos antiguos. Si `mode == "system"`, convierte sus dos temas en el campo de solo lectura **`legacy_follow: {light_theme, dark_theme}`**; si no, descarta `mode`, `light_theme` y `dark_theme`. Así ningún documento de la fase 20 deja de validar ni pierde los temas propios.
  - `PUT` no acepta `legacy_follow`.
- **Migración en la interfaz**: si `GET` trae `legacy_follow`, `ThemeProvider` elige el tema según `prefers-color-scheme`, el que se estaba viendo, y guarda `{theme, custom}`. Al guardarlo, `legacy_follow` desaparece del documento.
- **Filtro de la galería**: `Segmented` Todos · Claros · Oscuros.
  - La base de cada tema sale de `resolveTheme(...).base`.
  - El valor inicial depende de `matchMedia('(prefers-color-scheme: dark)')`.
  - La elección se guarda en `localStorage` (`agentic-os.appearance.filter`, con `safe-storage`); es una comodidad de esta pantalla, no un ajuste del backend.
  - Si el tema en uso queda fuera del filtro, se sigue mostrando arriba como «En uso».

### 3. «Nuevo tema» y fuentes del sistema
- **«Nuevo tema»**:
  - Botón junto a «Importar». Abre un diálogo corto con el nombre y la base (Claro u Oscuro).
  - Crea `{version: 2, base, colors: {}}` sin `extends` y abre el editor.
  - En el editor, el `Select` de «Parte de» gana la opción «Ninguno (desde cero)». Cambiar la base de un tema desde cero cambia los colores de partida.
- **Lista de fuentes**:
  - Comando de Tauri **`system_fonts() -> Vec<String>`** (`desktop/src-tauri/src/fonts.rs`, con `fontdb` o lo que diga S1). Devuelve las familias únicas, ordenadas, sin las ocultas (las que empiezan por `@` o `.`). Se cachea en memoria del *shell*.
  - Frontend: `lib/system-fonts.ts`.
    - En Tauri invoca el comando.
    - En el navegador usa `queryLocalFonts` si existe; si no, devuelve `null`.
    - Se cachea con `useQuery`.
- **Editor**:
  - El selector de fuente pasa a un *combobox* con buscador (`Command` de shadcn, el que ya usa la paleta).
  - Tiene dos grupos: «Incluidas» (las cuatro) y «Del sistema». Cada fila se pinta con `font-family` de esa fuente.
  - Sin lista (navegador sin acceso) hay un campo de texto para escribir el nombre.
- **Fuente que falta**:
  - Si hay lista, falta la `font_family` que no está en ella.
  - Sin lista, se mide con un *canvas* el ancho de un texto con la fuente pedida y con la de reserva. Si coinciden con dos reservas distintas, la fuente falta.
  - El editor muestra un aviso ámbar: «Esta fuente no está instalada en este equipo; se usa la del sistema».

### 4. Temas incluidos: de 5 a 27
- **Generador** `theme/derive.ts`:
  - `fromPalette(p)` recibe una paleta corta y devuelve los 95 *tokens*:
    - superficie: fondo, superficie, superficie alta y borde;
    - texto: texto y texto apagado;
    - acento, acento al pasar el ratón y color destructivo;
    - barra lateral;
    - los 16 colores ANSI del terminal.
  - De ahí salen las tarjetas, los *popovers*, los estados, los gráficos, el terminal y el logo, con las mismas reglas que siguen hoy el navy y el claro.
  - `ensureContrast(fg, bg, ratio)` aclara u oscurece el color de primer plano en pasos pequeños hasta llegar a 4,5:1 (texto) o 3:1 (etiqueta de botón), y solo si no llega ya. Es el «se ajusta lo mínimo» de la spec.
  - Los cinco temas actuales **no cambian**: siguen escritos a mano.
- **Temas de VS Code** (16), con los colores publicados por cada proyecto y su licencia a comprobar en el repositorio al implementarlos:

  | Tema | Base | Licencia esperada | Origen |
  |---|---|---|---|
  | Dracula | oscuro | MIT | dracula/visual-studio-code |
  | One Dark | oscuro | MIT | Binaryify/OneDark-Pro (paleta Atom One Dark) |
  | Nord | oscuro | MIT | nordtheme/visual-studio-code |
  | Solarized Dark / Solarized Light | oscuro / claro | MIT | altercation/solarized |
  | Gruvbox Dark / Gruvbox Light | oscuro / claro | MIT | morhetz/gruvbox (jdinhify/vscode-theme-gruvbox) |
  | Tokyo Night / Tokyo Night Day | oscuro / claro | MIT | enkia/tokyo-night-vscode-theme |
  | Catppuccin Mocha / Catppuccin Latte | oscuro / claro | MIT | catppuccin/vscode |
  | GitHub Dark / GitHub Light | oscuro / claro | MIT | primer/github-vscode-theme |
  | Night Owl / Light Owl | oscuro / claro | MIT | sdras/night-owl-vscode-theme |
  | Ayu Dark / Ayu Light | oscuro / claro | MIT | ayu-theme/vscode-ayu |

  Si al comprobarla alguna licencia no es libre, el tema se quita de la lista y lo sustituye una paleta propia.
- **Temas propios nuevos** (6): Bosque y Océano (oscuros, verde y azul petróleo), Vino (oscuro, granate), Arena y Lavanda (claros, beige y violeta) y Menta (claro, verde suave). Con ellos quedan 27 temas: 13 claros y 14 oscuros.
- **Créditos**: `theme/credits.ts` lista cada tema de terceros con su nombre, autor, licencia, URL y la marca «adaptado». `AboutPage` añade la sección «Temas incluidos» encima de las dependencias. Un test comprueba que todo tema incluido que no es propio tiene su crédito.
- **Backend**: `BUILTIN_THEMES` pasa a ser la lista de 27 ids. Un test compara las listas del frontend y del backend leyendo un JSON generado (`frontend/src/generated/builtin-themes.json`, escrito por un test de vitest y vigilado por pytest), igual que ya se hace con las licencias.

### 5. Menú de Ajustes
- **Títulos de grupo**:
  - 12 px, `font-semibold`, `text-foreground`, sin monoespaciado y con el icono del grupo (`lucide`).
  - Entre grupos, un separador `border-t border-sep` con aire arriba.
- **Opciones**: sangradas (`pl-6`), en `text-muted-foreground`. La seleccionada mantiene `bg-accent` y el texto en primer plano.
- **Por debajo de `lg`**: cada grupo es una fila con su título como etiqueta a la izquierda y sus opciones en *chips* con `flex-wrap`. El título ya no se oculta.
- **Accesibilidad**: cada grupo es un `role="group"` con `aria-labelledby` apuntando a su título. Se mantienen `aria-current` y el orden de tabulación.

## Archivos
| Archivo | Cambio |
|---|---|
| `docs/adr/0028-themes-v2.md` | nuevo: formato v2, fuentes del sistema, temas de terceros y su crédito, fin de «Seguir al sistema» |
| `frontend/src/theme/model.ts` | v2: `extends` opcional, `font_family`, `Appearance` sin modo |
| `frontend/src/theme/resolve.ts` | cadena sin `extends`, `fontFamily`; fuera `activeThemeId` |
| `frontend/src/theme/apply.ts` | `--app-font` con la familia del sistema |
| `frontend/src/theme/ThemeProvider.tsx` | sin `toggleTheme`/`setTheme`; migración de `legacy_follow` |
| `frontend/src/theme/derive.ts` | nuevo: `fromPalette`, `ensureContrast` |
| `frontend/src/theme/builtin.ts` | 22 temas nuevos con `fromPalette` |
| `frontend/src/theme/credits.ts` | nuevo: autoría y licencia de los temas de terceros |
| `frontend/src/lib/system-fonts.ts` | nuevo: lista de fuentes y comprobación de fuente que falta |
| `frontend/src/components/layout/AppHeader.tsx`, `components/palette/CommandPalette.tsx` | fuera el cambio claro/oscuro |
| `frontend/src/pages/settings/appearance/AppearancePage.tsx` | filtro, «Nuevo tema», fuera la sección «Modo» |
| `frontend/src/pages/settings/appearance/NewThemeDialog.tsx` | nuevo |
| `frontend/src/pages/settings/appearance/FontPicker.tsx` | nuevo: *combobox* de fuentes con aviso de fuente que falta |
| `frontend/src/pages/settings/appearance/ThemeEditorPage.tsx`, `theme-io.ts` | «desde cero», selector de fuentes, importar v1 y v2 |
| `frontend/src/pages/settings/SettingsPage.tsx` | menú con títulos de grupo |
| `frontend/src/pages/about/AboutPage.tsx` | sección «Temas incluidos» |
| `frontend/src/i18n/es.json` | nombres de los temas nuevos y textos nuevos; fuera las claves del modo y del cambio de tema |
| `frontend/src/generated/builtin-themes.json` | nuevo: ids de los temas incluidos, para el backend |
| `backend/src/agentic_os/schemas/appearance.py` | v2, documentos antiguos, `legacy_follow`, lista de 27 ids |
| `desktop/src-tauri/src/fonts.rs`, `lib.rs`, `Cargo.toml` | nuevo comando `system_fonts` |
| `frontend/src/generated/third-party-licenses.json` | regenerado (*crate* nuevo) |

## Tareas (en orden)
1. [ ] **S1**: spike de fuentes del sistema; resultados en este plan.
2. [ ] ADR 0028.
3. [ ] Formato v2 en frontend y backend, y documentos antiguos con `legacy_follow`. Tests de importar v1 y de la migración del backend.
4. [ ] Fuera el cambio claro/oscuro y «Seguir al sistema»: `ThemeProvider`, cabecera, paleta y sección «Modo»; migración en la interfaz.
5. [ ] Filtro de la galería.
6. [ ] «Nuevo tema» y editor «desde cero».
7. [ ] Comando `system_fonts`, `lib/system-fonts.ts`, `FontPicker` y aviso de fuente que falta.
8. [ ] `derive.ts` con sus tests (contraste, ANSI, estados).
9. [ ] Temas de VS Code: comprobar cada licencia, pasar sus colores a `fromPalette`, créditos y Acerca de.
10. [ ] Temas propios nuevos; ids en el backend y JSON generado.
11. [ ] Menú de Ajustes.
12. [ ] Suites completas (de una en una), lint, `cargo test`, `/code-review`, instalador y prueba del usuario en la app instalada; `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `appearance.test.tsx`: sin sección «Modo»; filtro Claros/Oscuros con temas propios; valor inicial según `matchMedia`; se recuerda | CA2, CA3 |
| `ThemeProvider.test.tsx`: `legacy_follow` elige el tema según el sistema y lo guarda; sin `toggleTheme` | CA3 |
| `AppHeader`/`CommandPalette` (tests existentes): sin botón ni acción de cambio de tema | CA1 |
| `test_settings_appearance.py`: documento de la fase 20 con `mode: system` → `legacy_follow` y temas propios intactos; `mode: fixed` → sin campos antiguos; `PUT` con `legacy_follow` rechazado; tema sin `extends` y con `font_family`; `font_family` con caracteres no permitidos rechazada | CA3, CA4 |
| `appearance.test.tsx` / `theme-editor.test.tsx`: «Nuevo tema» claro y oscuro → editor → guardar → exportar → importar | CA4 |
| `theme-io.test.ts`: importar un fichero v1 real de la fase 20 (copiado en `fixtures/`) | CA7 |
| `FontPicker.test.tsx`: busca entre las del sistema, campo de texto sin lista, aviso de fuente que falta | CA6 |
| `system-fonts.test.ts`: Tauri, `queryLocalFonts` y nada; medición con *canvas* simulada | CA6 |
| `fonts.rs` (`cargo test`): lista sin duplicados ni ocultas, ordenada | CA5 |
| `derive.test.ts`: `fromPalette` da los 95 *tokens*; `ensureContrast` solo cambia lo que no llega | CA8 |
| `contrast.test.ts` (ya recorre `BUILTIN_IDS`), `titlebar.test.ts`, y uno nuevo: ≥ 25 temas, de las dos bases, con crédito los de terceros | CA8 |
| `test_builtin_themes.py`: la lista del backend coincide con `builtin-themes.json` | CA8 |
| `settings.test.tsx`: grupos con `role="group"` y su título visible también en ancho estrecho; navegación y `aria-current` | CA9 |
| Prueba en la app instalada: tema desde cero con una fuente del sistema (p. ej. «Cascadia Code») en toda la app | CA5 |

## Decisiones (ADR)
- **ADR 0028 · Temas v2**:
  - el formato v2, compatible con la v1;
  - `font_family` con su patrón seguro;
  - la lista de fuentes desde el *shell*;
  - `legacy_follow` para retirar «Seguir al sistema» sin perder datos;
  - los temas de terceros generados desde su paleta, con contraste ajustado y crédito en Acerca de.
