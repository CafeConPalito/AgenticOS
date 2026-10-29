# Fase 21: Correcciones de la prueba · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-29)

## Diseño
La causa de cada fallo está localizada en el código (2026-10-29). Un bloque por apartado de la spec, cada uno con su test que reproduce el fallo antes de corregirlo.

### A. Instalador (CA1, CA2)
- **Icono**: `bundle.windows.nsis` no define `installerIcon`, así que la plantilla de Tauri deja `INSTALLERICON` vacío y NSIS usa su icono genérico (`target/release/nsis/x64/installer.nsi`, líneas 43 y 127). Se añade `"installerIcon": "icons/icon.ico"`. El desinstalador ya usa el icono de la app.
- **Textos negros de la última pantalla**: los dos *checkbox* de la página final («Ejecutar Agentic OS» y «Crear acceso directo», `MUI_FINISHPAGE_RUN` y `MUI_FINISHPAGE_SHOWREADME`) son controles con estilo visual de Windows, que ignoran el color de texto que pone MUI2 con `SetCtlColors`. La solución conocida es quitarles el tema con `UxTheme::SetWindowTheme` y volver a pintarlos en blanco sobre navy. Eso necesita una función `SHOW` justo antes de `MUI_PAGE_FINISH`, y los *hooks* de Tauri (`hooks.nsh`) se incluyen antes de todas las páginas, así que no pueden ponerla.
  - Por eso se usa una **plantilla NSIS propia** (`bundle.windows.nsis.template`): la de nuestra versión de `tauri-bundler`, copiada sin cambios salvo la función `SHOW` de la página final, marcada con un comentario.
  - Un test comprueba que la plantilla sigue siendo la de la versión de `tauri-bundler` del `Cargo.lock`, para acordarse de revisarla al actualizar Tauri.
  - Si `SetWindowTheme` no basta en Windows 11, la alternativa es pintar la página final en claro. Se prueba en el bloque 0.

### B. Ejecuciones del Arquitecto (CA3)
- `GET /api/runs` filtra `Run.kind == AGENT` (`api/runs.py:114`), pero el contador de Ejecuciones (`services/home.py:202`) cuenta todas las ejecuciones activas, también las del Arquitecto y las llamadas internas (decisor de ramas, descripción de imágenes).
- **Listado**: incluye `AGENT` y `ARCHITECT`. Si se filtra por agente o proyecto, las del Arquitecto quedan fuera, porque no tienen ninguno de los dos.
- **Contador**: cuenta solo esos dos tipos, como el listado.
- **`RunRead`**: suma `kind` y `conversation_id`. En una ejecución del Arquitecto, `agent_name` es «Arquitecto».
- **`RunsTable`**: muestra una etiqueta «Arquitecto» y enlaza a su conversación (`/agentes/arquitecto?conversacion=…`) en vez de a la página de la ejecución.

### C. Exportar (CA4)
- **Causa**: `downloadAgent` (`api/agents.ts:148`) y la exportación de temas (`pages/settings/appearance/theme-io.ts:123`) descargan con `<a download>` y un `blob:`. En el WebView2 de Tauri esa descarga se ignora sin error. Al revisarlo apareció el mismo fallo en **Consumo › Exportar CSV** (`api/usage.ts:163`), que se corrige igual porque comparte la causa.
- **Ayudante común**: `lib/save-file.ts` con `saveFile({ name, data, filters })`.
  - **App de escritorio**: abre «Guardar como» (`plugin-dialog`, ya permitido) y escribe el fichero con un comando Rust nuevo, `save_file(path, contents)`. El comando solo acepta la ruta que acaba de devolver el diálogo: Rust guarda en memoria la última ruta elegida y rechaza cualquier otra.
  - **Navegador**: la descarga de siempre.
  - **Aviso**: «Guardado en …» con un botón para abrir la carpeta.

### D. Ajustes
- **Limpieza (CA5)**: el contenedor raíz de la app (`AppShell.tsx:58`) tiene `overflow-hidden`, que se puede desplazar desde código aunque no tenga barra. `scrollIntoView` de la última sección (Limpieza), sin contenido debajo para llegar arriba, desplaza también ese contenedor. La cabecera sale de la vista y no hay forma de volver.
  - Se pasa a `overflow-clip`, que no es un contenedor desplazable.
  - Se añade un espacio al final de Ajustes para que la última sección pueda subir hasta arriba.
- **Modelos «En uso» (CA6)**: `selected` (`api/local_models.py:50`) es el modelo elegido en la configuración, que por defecto es el aconsejado, esté descargado o no. La fila (`LocalModelsSection.tsx:72`) cambia así:
  - «En uso» solo si `selected` y `state === 'ready'`;
  - «Aconsejado» si es el elegido o el de por defecto y no está descargado, con el botón «Descargar» a la vista;
  - la etiqueta «Recomendado» pasa a llamarse «Aconsejado».
- **Micrófonos (CA7)**: `enumerateDevices()` no da el id ni el nombre de los dispositivos hasta que la página tiene permiso del micrófono. El selector (`DictationSection.tsx:406`) descarta los que no tienen id, así que no queda ninguno.
  - Si los dispositivos llegan sin nombre, se muestra «Permitir el micrófono para verlos». Ese botón pide `getUserMedia({ audio: true })`, suelta la pista y vuelve a listar.
  - También se vuelve a listar tras una prueba que funcione.
  - En la app instalada se comprueba (bloque 0) que WebView2 pide o concede el permiso. Si lo deniega sin preguntar, el *shell* de Rust atiende `PermissionRequested` de WebView2 y permite **solo** el micrófono para el origen de la app.
  - Si Windows lo tiene bloqueado, el error dice dónde activarlo (Configuración › Privacidad › Micrófono).

### E. Agentes y equipos
- **Huecos (CA8)**: el `<form>` del editor (`AgentEditorPage.tsx:173`) lleva `min-h-full` y ocupa toda la altura. Conocimiento, Skills y Conexiones se pintan fuera del formulario, debajo de él. `min-h-full` se queda solo en las pestañas del formulario.
- **Foto en verde (CA9)**: la CSP de la app de escritorio (`tauri.conf.json`) tiene `img-src 'self' data: http://127.0.0.1:*…`, sin `blob:`. El recortador no puede pintar la URL `blob:` de la foto: se ve solo el fondo con el color del agente, y «Usar» no se activa nunca porque el recorte no llega a calcularse. En el navegador de desarrollo no hay CSP, por eso pasó desapercibido.
  - Se añade `blob:` a `img-src`.
  - Un test de Rust lee la CSP y comprueba que lo permite.
- **Equipo sin agentes (CA10)**: el backend ya acepta un equipo vacío y el diálogo también. Lo que falla es Inicio sin agentes ni equipos: muestra un estado vacío sin «Nuevo equipo» (`AgentGrid.tsx:100`), porque el menú «Nuevo» solo aparece cuando ya hay algo. Se añade «Nuevo equipo» al estado vacío. Se revisa también el estado vacío de la página Agentes.

### F. Ramas sin condición (CA11)
- **Regla nueva**: una rama sin condición se hace siempre.
- **Backend**:
  - `lanes.open_links` (`services/lanes.py:230`) manda al decisor solo las ramas con condición, y el resto se toma sin preguntar. Si ninguna tiene condición, no se llama al modelo: ya existe el caso `DecisionBy.ALWAYS`.
  - `pipelines.py:120` y `pipeline_graph.py` dejan de producir `branch_without_condition`.
- **Frontend**: el validador (`validate.ts:96`) deja de producir ese problema. En el panel de la rama, el interruptor «Siempre se toma» desaparece y su lugar lo ocupa una ayuda: «Sin condición, esta rama se hace siempre, a la vez que las demás».
- **Datos**: la columna `stage_links.always` se queda. Una migración vacía `condition` donde `always` es verdadero, para que la regla nueva dé lo mismo que antes. Ese texto ya se ignoraba, porque esas ramas no pasaban por el decisor.
- **Arquitecto**: su ficha y su *prompt* (`services/architect/sheet.py:817`) proponen ramas sin condición en vez de `always`.

## Archivos
| Archivo | Cambio |
|---|---|
| `desktop/src-tauri/tauri.conf.json` | `installerIcon`, `template`, `blob:` en `img-src` |
| `desktop/src-tauri/windows/installer.nsi` | nuevo: plantilla de Tauri + función `SHOW` de la página final |
| `desktop/src-tauri/src/` (`save_file`, permisos de WebView2 si hacen falta) | nuevo / modificado |
| `backend/src/agentic_os/api/runs.py`, `schemas/run.py`, `services/home.py` | ejecuciones del Arquitecto |
| `backend/src/agentic_os/services/lanes.py`, `pipelines.py`, `pipeline_graph.py`, `architect/sheet.py` | ramas sin condición |
| `backend/src/agentic_os/db/migrations/versions/0023_*.py` | nuevo: `condition` vacía donde `always` |
| `frontend/src/lib/save-file.ts` | nuevo |
| `frontend/src/api/agents.ts`, `api/usage.ts`, `pages/settings/appearance/theme-io.ts` | usan `saveFile` |
| `frontend/src/components/layout/AppShell.tsx`, `pages/settings/SettingsPage.tsx` | Limpieza |
| `frontend/src/pages/settings/LocalModelsSection.tsx`, `DictationSection.tsx` | modelos y micrófonos |
| `frontend/src/pages/agents/AgentEditorPage.tsx`, `pages/home/AgentGrid.tsx`, `pages/agents/AgentsPage.tsx` | huecos y equipo |
| `frontend/src/pages/runs/RunsTable.tsx` | etiqueta y enlace del Arquitecto |
| `frontend/src/pages/projects/tabs/pipeline/validate.ts`, `Panels.tsx` | ramas sin condición |
| `frontend/src/i18n/es.json`, `en.json` | textos nuevos |

## Tareas (en orden)
0. [ ] **Comprobaciones previas** (con el instalador compilado):
   - `SetWindowTheme` en los *checkbox* de la página final en Windows 11;
   - el permiso del micrófono en WebView2 con la app instalada;
   - reproducir CA4, CA5 y CA9.
1. [ ] **A. Instalador**: icono y plantilla con la página final legible, con el test de la versión de la plantilla.
2. [ ] **B. Arquitecto en Ejecuciones**: API, contador, `RunRead` y tabla.
3. [ ] **C. Exportar**: `save_file` en Rust, `saveFile` en el frontend y sus tres usos.
4. [ ] **D. Ajustes**: contenedor raíz y espacio final, etiquetas de modelos, permiso y lista de micrófonos.
5. [ ] **E. Agentes y equipos**: altura del formulario, CSP con `blob:`, «Nuevo equipo» en los estados vacíos.
6. [ ] **F. Ramas sin condición**: backend, migración, validadores, panel y Arquitecto.
7. [ ] **Cierre**:
   - suites completas (backend a `.test-progress.log`), lint y `/code-review`;
   - instalador compilado;
   - comprobaciones en la app instalada (CA1, CA2, CA4, CA7, CA9);
   - `validacion.md`;
   - versión `0.9.1` en los manifiestos, merge y etiqueta `v0.9.1`.

## Tests previstos
| Test | Cubre |
|---|---|
| Rust: la plantilla NSIS corresponde a la versión de `tauri-bundler` del `Cargo.lock` y define el icono | CA1, CA2 |
| Capturas del instalador compilado (icono y página final) | CA1, CA2 |
| pytest: `GET /api/runs` incluye la ejecución del Arquitecto con `kind` y `conversation_id`; el filtro por agente la excluye; el contador coincide con el listado | CA3 |
| vitest: `RunsTable` marca y enlaza la del Arquitecto | CA3 |
| vitest: `saveFile` usa el diálogo y el comando en Tauri y la descarga en el navegador; exportar agente, tema y CSV lo llaman | CA4 |
| Rust: `save_file` rechaza una ruta que no viene del diálogo | CA4 |
| vitest: ir a Limpieza no desplaza el contenedor raíz (`scrollTop` 0) | CA5 |
| vitest: modelo elegido sin descargar → «Aconsejado» y «Descargar»; descargado y elegido → «En uso» | CA6 |
| vitest: dispositivos sin nombre → botón de permiso; tras el permiso, se listan | CA7 |
| Prueba manual en la app instalada: lista de micrófonos y prueba con el elegido | CA7 |
| vitest: la pestaña Conocimiento del agente no lleva `min-h-full` en el formulario | CA8 |
| Rust: la CSP de `tauri.conf.json` permite `blob:` en `img-src` | CA9 |
| vitest: Inicio y Agentes vacíos muestran «Nuevo equipo»; se crea el equipo | CA10 |
| pytest: equipo sin agentes y después con uno | CA10 |
| pytest: bifurcación sin condiciones → todas las ramas sin llamar al decisor; con una condicionada → solo esa va al decisor; la migración vacía `condition` donde `always` | CA11 |
| vitest: el validador acepta ramas sin condición; el panel muestra la ayuda | CA11 |
| Suites completas, lint y `/code-review` | CA12 |

## Decisiones (ADR)
- Sin ADR nuevo: son correcciones. Se anotan aquí dos cambios de criterio:
  - **Plantilla NSIS propia**: amplía lo decidido en la fase 20, enmienda 1. Al actualizar Tauri hay que revisarla, y un test lo recuerda.
  - **Rama sin condición = siempre**: cambia la regla de la fase 13. Se añade una nota al ADR 0020.

## Estado (2026-10-29, fin de la sesión)
Bloques 1–6 hechos y commiteados, cada uno con sus tests (enfocados en verde). Instalador compilado y probado por el usuario en la app instalada.

**Comprobado por el usuario en la app instalada**: textos de la última pantalla del instalador en blanco (CA2), exportar agente, tema y CSV (CA4), Ajustes › Limpieza (CA5), lista de micrófonos tras el permiso (CA7, la parte de la lista), foto del agente (CA9), Conocimiento/Skills/Conexiones sin hueco (CA8), «Nuevo equipo» sin agentes (CA10), ejecuciones del Arquitecto en el listado (CA3).

**Pendiente**:
1. **CA1, el instalador sigue con el icono de NSIS** según el usuario, aunque el script generado ya define `INSTALLERICON` y `UNINSTALLERICON` con `icons/icon.ico`. Comprobar primero si es la caché de iconos de Windows (el `.exe` del escritorio se sobrescribió con el mismo nombre): mirar el icono del `.exe` recién generado en `target/release/bundle/nsis/`, con otro nombre o tras limpiar la caché. Si de verdad no lo lleva, revisar `icons/icon.ico` (tamaños dentro del `.ico`) y el `!define MUI_ICON` del script.
2. **Fallo nuevo: el motor de voz no se instala** (Ajustes › Dictado / Modelos locales). La descarga real del motor quedó pendiente como prueba manual en la fase 16. Reproducir en la app instalada, leer el registro del backend y decidir con el usuario si entra en esta fase (la spec dice que los fallos nuevos se anotan y se decide con él).
3. **Fallo nuevo: el diálogo de editar equipo tiene scroll horizontal** (`pages/home/TeamDialog.tsx`). Pequeño; proponer incluirlo.
4. **CA11 por confirmar**: el usuario anotó «guardar pipeline sin condición» sin decir si funciona. Preguntarle; en los tests de backend y frontend se guarda y la tarea pasa por todas las ramas.
5. **Suite completa del backend sin pasar**: se paró al 4 % (sin fallos hasta ahí) porque el sistema se quedó sin memoria con la compilación a la vez. Lanzarla sola cuando el usuario lo pida; falta también la suite del frontend, lint, `/code-review` y `validacion.md`.
