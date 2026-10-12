# Fase 08: Empaquetado v1.0 (MVP) · Spec

- **Estado**: aprobada
- **Rama**: `phase/08-empaquetado`

## Objetivo
Convertir Agentic OS en una **aplicación que se instala y se usa a diario**: un instalador de Windows que funciona en una máquina limpia, una pantalla de **Ajustes** completa y una app **robusta ante reinicios y caídas**, sin procesos huérfanos y con la opción de retomar las sesiones de los CLIs que se cortaron. Cierra el MVP con la versión `1.0.0`.

## Alcance
### Dentro
**Instalador** (NSIS, el que ya genera `npm run build:desktop`):
- Versión **`1.0.0`** en todos los paquetes (backend, frontend, desktop, Tauri) y visible en la app (Ajustes > Acerca de).
- **Iconos definitivos** a partir del logo del diseño (`docs/design/`).
- Instalación **por usuario**, sin pedir permisos de administrador. Si falta **WebView2**, el instalador lo descarga e instala.
- **Actualizar encima**: instalar una versión nueva sobre la anterior conserva la base de datos, los logs y los ajustes; las migraciones se aplican solas al arrancar.
- **Desinstalar**: quita la app y pregunta si se borran también los datos (por defecto, se conservan).
- **Sin firma de código**: el README explica el aviso de SmartScreen y qué hacer si el antivirus bloquea el sidecar. El script de build deja preparado el paso de firma (vacío) por si más adelante hay certificado.
- **Arranque del sidecar**: se mide con la app instalada. Si supera los 5 s, se pasa de PyInstaller `--onefile` a `--onedir` (decisión anotada en la fase 00).
- Sin ventana de consola del sidecar ni de los CLIs.
- **Primer arranque** en una máquina sin CLIs: la app abre igualmente y guía al usuario (Ajustes > CLIs detectados, con el comando de instalación y de inicio de sesión de cada CLI).

**Robustez**:
- **Una sola instancia**: abrir la app por segunda vez trae al frente la ventana que ya está abierta (dos backends sobre la misma base de datos la corromperían).
- **Reinicio automático del sidecar** si se cae: Tauri lo vuelve a lanzar (hasta 3 veces seguidas, con espera creciente). Mientras tanto, la UI muestra «Reconectando…»; si no lo consigue, un error con «Reintentar» y «Abrir logs».
- **Sin procesos huérfanos**: al cerrar la app (normal o a la fuerza) o al caerse el sidecar, no queda vivo ningún CLI ni proceso del backend. Se verifica con la app instalada.
- **Ejecuciones interrumpidas** (cierre, caída o reinicio del equipo): siguen quedando «Interrumpidas» y su tarea en «Esperando humano», pero ahora con la acción **«Reanudar sesión»** en el detalle de la ejecución, en la tarea y en la Inbox («Atención»):
  - relanza el CLI en la misma carpeta retomando su conversación (`claude --resume <id>`; en agy, la opción equivalente que confirme el plan), con un contexto y un token de MCP nuevos;
  - es una ejecución nueva enlazada a la interrumpida (se ve en el historial de la tarea), y la tarea vuelve a «En ejecución»;
  - si el CLI no puede retomar la sesión (transcript borrado, ID desconocido), la ejecución termina con un error claro y la tarea vuelve a «Esperando humano» con «Reintentar».
  - «Reintentar» (desde cero) sigue disponible.
- **Copia de la base de datos** antes de aplicar migraciones nuevas (al actualizar). Se guardan las 3 últimas en la carpeta de datos.
- **Restos de ejecuciones anteriores**: al arrancar se limpian los plugins de agy, los worktrees huérfanos y la confianza pendiente que dejó una caída (ampliando la recuperación que ya existe).

**Ajustes** (según `12-ajustes` del diseño; se mantienen Notificaciones y Límites diarios):
- **CLIs detectados**: logo, nombre, ruta, versión, estado («Sesión iniciada» · «Sin sesión» · «No detectado»), «Comprobado hace…» y botón «Comprobar» (con spinner y toast). Si un CLI no está, el comando para instalarlo.
- **Carpeta de datos**: ruta, espacio ocupado (base de datos, logs de sesión y worktrees), «Abrir carpeta» y **«Cambiar…»**: elige una carpeta nueva con el diálogo nativo, mueve los datos con el backend parado y reinicia el sidecar. Solo se permite sin ejecuciones activas.
- **Tema**: Oscuro / Claro (el mismo que el botón actual), guardado entre sesiones.
- **Idioma**: selector con «Español»; queda preparado para añadir idiomas (solo existe `es`).
- **Limpieza**:
  - **Ramas de tareas** (`agentic/T-n`): lista por proyecto de las ramas de tareas terminadas o canceladas, indicando si ya están fusionadas en la rama base; borrar una, o todas las fusionadas. Nunca se borra una rama con trabajo sin fusionar sin confirmación explícita.
  - **Logs de sesión**: retención configurable (por defecto, 90 días; «Nunca borrar» posible). Al arrancar se borran los logs de ejecuciones más antiguas; la ejecución y su consumo se conservan, solo se pierde la reproducción de la terminal. Botón «Limpiar ahora» con el espacio que se libera.
- **Acerca de**: versión, carpeta de datos, «Abrir logs» y enlace a la licencia.

**Comprobaciones pendientes de fases anteriores**, ahora con la app instalada:
- F5 en una subruta (p. ej. `/agentes`) no da 404.
- «Examinar…» abre el diálogo nativo.
- La notificación nativa de Windows llega y su clic lleva a la Inbox.
- «Exportar CSV» descarga el archivo en WebView2.
- Cerrar la app con una ejecución activa: no quedan procesos de `claude` ni `agy`, y al reabrir aparece «Interrumpida» con «Reanudar sesión».

**e2e de la app empaquetada**:
- Las suites e2e del backend (scheduler, HITL, consumo) se pueden ejecutar también **contra el sidecar empaquetado** (el `.exe` de PyInstaller con el CLI falso), para detectar módulos o datos que falten en el empaquetado.
- Un **guion de humo** (`scripts/smoke-installed.ps1`) comprueba la app instalada: arranca, el sidecar responde, la base de datos está en su sitio y al cerrar no quedan procesos.

### Fuera
- **Actualizaciones automáticas** (plugin updater de Tauri): requiere publicar las versiones en un sitio remoto. Fase futura.
- **Firma de código** con certificado.
- Instalador para macOS o Linux, y MSI.
- Políticas de aprobación automática de permisos (anotadas en la fase 06): fase futura.
- Traducciones a otros idiomas (solo se prepara el selector).
- Rediseño de la navegación y del Dashboard completo: fase 09 (UX/UI).
- Instalar los CLIs desde la app: solo se indica cómo hacerlo.
- Reanudar automáticamente las sesiones al arrancar (siempre lo decide el usuario).
- Rutas de datos en red o sincronizadas (OneDrive): no se prueban.

## Historias de usuario
- Como usuario, quiero instalar Agentic OS con un instalador normal y empezar a usarlo sin herramientas de desarrollo.
- Como usuario, quiero actualizar a una versión nueva sin perder mis agentes, proyectos ni historial.
- Como usuario, quiero que, si la app o el equipo se cierran de golpe, pueda retomar la conversación del agente donde se quedó.
- Como usuario, quiero que la app se recupere sola si el backend se cae, sin dejar procesos colgados.
- Como usuario, quiero ver en Ajustes qué CLIs tengo y si tienen sesión iniciada, y dónde se guardan mis datos y cuánto ocupan.
- Como usuario, quiero limpiar las ramas de tareas y los logs antiguos para que no se acumulen.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Máquina limpia**: el instalador `1.0.0` se instala sin permisos de administrador en un Windows sin herramientas de desarrollo (Windows Sandbox o VM), la app arranca, crea su carpeta de datos y muestra los CLIs como «No detectado» con la guía para instalarlos | Prueba manual con evidencias |
| CA2 | **Actualizar encima**: instalar `1.0.0` sobre una build anterior con datos conserva agentes, proyectos, tareas y consumo; se aplica la migración y queda la copia de la base de datos | Prueba manual + test de la copia antes de migrar |
| CA3 | **Desinstalar**: quita la app; los datos se conservan salvo que se marque borrarlos | Prueba manual |
| CA4 | **Una sola instancia**: abrir la app dos veces deja un único backend y trae al frente la ventana existente | Prueba manual + log |
| CA5 | **Sidecar caído**: al matar el proceso del backend, la app muestra «Reconectando…» y vuelve a «Conectado» sola; tras 3 fallos seguidos, muestra el error con «Reintentar» | `cargo test` + prueba manual |
| CA6 | **Sin huérfanos**: cerrar la app (normal y a la fuerza) con ejecuciones activas de Claude y agy no deja procesos del backend ni de los CLIs; al reabrir, las ejecuciones están «Interrumpidas» | Guion de humo + prueba manual con `Get-Process` |
| CA7 | **Reanudar sesión**: con Claude Code real y con agy real, una ejecución interrumpida se reanuda y el agente recuerda la conversación anterior; la tarea vuelve a «En ejecución» y la ejecución nueva queda enlazada. Si la sesión no se puede retomar, error claro y «Reintentar» | Tests con el CLI falso + prueba real con evidencia |
| CA8 | **Ajustes**: CLIs detectados con «Comprobar», carpeta de datos (tamaño, abrir, cambiar moviendo los datos), tema, idioma, limpieza de ramas y de logs, Acerca de; fieles a `12-ajustes` | Tests de componentes y de la API + capturas |
| CA9 | **Limpieza**: las ramas fusionadas se borran; las no fusionadas piden confirmación; los logs más antiguos que la retención se borran al arrancar y la ejecución sigue apareciendo con su consumo | Tests |
| CA10 | **Pendientes de fases anteriores** con la app instalada: F5 en subruta, «Examinar…», notificación nativa con clic a la Inbox, «Exportar CSV» y sin ventanas de consola | Prueba manual con evidencias |
| CA11 | **e2e empaquetados**: las suites e2e del backend pasan contra el sidecar de PyInstaller; el guion de humo pasa con la app instalada; arranque del sidecar medido (< 5 s) | Salida de los tests y del guion |
| CA12 | `check` en verde; ADR (empaquetado y reanudación), README (instalar, actualizar, desinstalar, SmartScreen) y roadmap actualizados | Salida del `check` + revisión |

## Prerrequisitos
- Fase 07 cerrada (`v0.8`).
- Windows Sandbox (Windows 11 Pro) o una VM para la prueba en máquina limpia.
- Claude Code y agy instalados y con sesión iniciada en el equipo de desarrollo.

## Riesgos y preguntas abiertas
- **Reanudar en agy**: hay que confirmar cómo retoma agy una conversación concreta (no solo la última de la carpeta: `-c` podría elegir otra si hubo varias). Es la primera tarea del plan; si no hay forma fiable, en agy «Reanudar sesión» se limita a la última conversación de esa carpeta y se avisa al usuario.
- **Reanudar con el contexto nuevo**: la sesión retomada tiene el token de MCP antiguo en su historial; hay que comprobar que el CLI usa la configuración nueva (MCP y hooks) y no la guardada.
- **Antivirus y SmartScreen**: un sidecar sin firmar de PyInstaller puede dar falsos positivos. Se documenta; `--onedir` suele reducirlos.
- **Mover la carpeta de datos**: con el backend parado, pero los worktrees y la confianza de los CLIs guardan rutas absolutas. El plan decidirá si se mueven también los worktrees o si «Cambiar…» exige no tener tareas con worktree abierto.
- **Una sola instancia y el modo dev**: el bloqueo no debe impedir tener a la vez la build de desarrollo y la instalada; se usará un identificador distinto o el bloqueo solo en release.
- **Windows Sandbox**: puede no estar activado; si no está disponible, se usa una VM o un usuario nuevo de Windows sin herramientas instaladas.
- **Reinicio del sidecar con ejecuciones activas**: al caerse el backend, sus CLIs mueren con él (Job Object); tras el reinicio aparecen como «Interrumpidas», igual que tras cerrar la app.
