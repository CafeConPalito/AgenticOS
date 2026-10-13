# Fase 09: Mejora de UX/UI · Spec

- **Estado**: borrador
- **Rama**: `phase/09-ux-ui`
- **Diseño de referencia**: `docs/design/v2/` (Agentic OS v7, Claude Design) y su revisión en `docs/design/v2/revision.md`.

## Objetivo
Tras usar la v1.0, lo que más estorba es que **las tareas habituales exigen demasiados pasos** y que **la navegación no deja claro dónde está cada cosa**. Esta fase adopta el diseño v7: **Inicio pasa a ser el centro de la app** («qué necesita de mí» y «qué hacen mis agentes»), la navegación se reduce a una cabecera con cuatro destinos, los flujos principales se acortan, se añade la paleta de comandos (Ctrl+K) y se aplica el nuevo acabado visual a toda la app. No añade funciones de dominio nuevas.

## Alcance
### Dentro
**Esqueleto y navegación** (v7 `screens.md` «Esqueleto» y `AppHeader`):
- Desaparece la barra lateral. Cabecera translúcida de 56 px con: logo, «Volver» (fuera de Inicio), migas, **navegación superior** (Tablero · Ejecuciones · Ajustes, con contadores), buscador que abre Ctrl+K, botón de terminal, estado de conexión y tema.
- **Conocimiento** no aparece en la navegación hasta la fase que lo construya.
- Las páginas que hoy están en el menú y dejan de estarlo **siguen existiendo con su ruta** y se llega a ellas desde Inicio, Ctrl+K y las migas:
  - **Inbox** → «Te necesitan · Ver todas» en Inicio; las peticiones resueltas se consultan desde ahí (enlace «Resueltas»).
  - **Consumo** → desde «Gasto de hoy» en la columna de resumen y desde Ctrl+K.
  - **Agentes** → la rejilla de agentes de Inicio («Nuevo agente», clic → ficha); la lista actual se mantiene como ruta.
  - **Proyectos** → la columna de resumen («Ver todos», «+»).
- Desde una tarea se llega a sus ejecuciones y desde una ejecución a su tarea.

**Inicio** (v7 `screens.md` §1, capturas `03a`–`03d`, `01a`/`01b`):
- **Saludo** con la fecha, las sesiones en vivo y tres chips: trabajando · esperan respuesta · gastado hoy.
- **Te necesitan** (`NeedsYouPanel`): las 3 primeras peticiones con sus acciones (aprobar, rechazar, responder con opciones o texto, reanudar sesión), «Ver todas · n» / «Ver menos» y el estado vacío «Nada pendiente…».
- **Avisos de CLI** (`CliAlertItem`) dentro de «Te necesitan», adaptados a lo que sabemos hoy (ver Riesgos): CLI sin cuota (el aviso `quota` de la fase 07), CLI con la sesión cerrada o no detectado, y límite diario al 95 % o más. Acciones: ir a Ajustes > CLIs y «Posponer».
- **Agentes**: una sola rejilla de `AgentCard` v7 (sin equipos): estado, sesiones vivas con su tarea y tiempo, peticiones pendientes, línea animada si está en ejecución y, al pasar el ratón o con el foco, coste, tokens y «+ Asignar tarea». Clic → ficha del agente.
- **Columna de resumen** (`SummaryAside`, 300 px, fija al hacer scroll): Proyectos (abiertas y quién trabaja), Gasto de hoy (con el límite diario), CLIs (una fila por CLI con el uso de su **límite diario** y la sesión; sin cuentas).
- Estados: normal, vacío (sin peticiones y sin agentes, con guía para crear el primero), cargando y desconectado. Tema claro (`03d`).
- Se actualiza en vivo (el mismo mecanismo que Tablero e Inbox).

**Menos pasos**:
- **Nueva tarea** (`NewTaskDialog` v7): «Qué hay que hacer», proyecto y agente; acción **«Crear y encolar»**. Se abre con `N`, desde Ctrl+K y desde «+» en una tarjeta de agente (agente preseleccionado). Desde un proyecto, rellena el proyecto; recuerda la última elección. Toast «T-n en la cola de <agente>» con enlace a la tarea. Se mantiene la opción de dejarla en el backlog y de añadir descripción (plegada) porque hoy se usan.
- **Nuevo agente** (`05`): plantillas en rejilla, nombre, rol, CLI, modelo, permisos e instrucciones; se crea como **borrador** y se activa desde su ficha («Activar»).
- **Nuevo proyecto** (`06`): nombre, carpeta (con «Examinar…»), pipeline (plantilla o sin pipeline) y color.
- **Peticiones**: el mismo componente de acciones (`RequestActions`) en Inicio, la lista de peticiones y el detalle de la tarea.

**Paleta de comandos y atajos** (`CommandPalette`, `ShortcutsDialog`, capturas `07a`, `07b`, `08`):
- Acciones: nueva tarea (`N`), nuevo agente, nuevo proyecto, abrir terminal, cambiar tema, atajos (`?`). Ir a: Inicio, Proyectos, Tablero, Ejecuciones, Consumo, Peticiones, Ajustes. Agentes, proyectos y tareas (por nombre o `T-n`) al buscar.
- Teclado completo (↑↓, Enter, Esc). Ayuda de atajos con `?`.
- Las teclas de un solo carácter no actúan con el foco en un campo, en la terminal o con un diálogo abierto, y se pueden desactivar en Ajustes («Atajos de una tecla»).

**Otras pantallas** (v7 `screens.md` §5, §6, §8):
- **Ficha de agente**: cabecera con «Asignar tarea», «Activar» (si es borrador) y «Editar»; peticiones y tareas del agente, su consumo, y la configuración plegada al final. La edición sigue en sus pestañas actuales.
- **Detalle de tarea**: los datos de la sesión pasan a una línea bajo la salida en directo.
- **Ejecuciones**: jerarquía de columnas de la v7 (sin columna de cuenta).

**Ajustes**: se mantienen las **seis secciones** (CLIs detectados, General, Notificaciones, Límites diarios, Limpieza, Acerca de) con el acabado v7 y un **índice lateral**. Se añade el interruptor **«Atajos de una tecla»** en General.

**Acabado visual v7 en toda la app** (`v2/design-system.md` y `v2/tokens.css`): radios mayores, separadores suaves, superficies con degradado, sombras en capas, vidrio en cabecera, diálogos, Ctrl+K y toasts, fondo atmosférico y animaciones de entrada. Todo respeta `prefers-reduced-motion` y el contraste AA en los dos temas.

**Revisión con el usuario**: al final se recorren con el usuario los flujos de CA1 y cada pantalla; lo que salga y quepa en el alcance se corrige en la fase; lo demás se anota.

### Fuera
- **Equipos de agentes y varias cuentas por CLI** (cuota, plan y sesiones por cuenta, «Nuevo equipo», «Añadir CLI o cuenta»): **fase 10** (nueva, ver roadmap).
- **Conocimiento y skills** en la navegación y en Inicio: se añaden en su fase.
- Porcentaje de la cuota real de la suscripción (Claude Pro/Max, Google): los CLIs no lo exponen (fase 07).
- Rediseño a fondo de la terminal y del Tablero (solo heredan el acabado y los accesos).
- Móvil, otros idiomas y atajos configurables.
- Políticas de aprobación automática.

## Historias de usuario
- Como usuario, quiero abrir la app y ver de un vistazo qué necesitan de mí y qué hacen mis agentes, y resolver las peticiones ahí mismo.
- Como usuario, quiero crear y encolar una tarea con una tecla o desde la tarjeta de un agente, sin elegir otra vez lo que ya está claro.
- Como usuario, quiero encontrar cualquier agente, proyecto o tarea con Ctrl+K.
- Como usuario, quiero una navegación corta en la que sepa dónde está cada cosa.
- Como usuario, quiero que la app tenga un acabado cuidado y coherente en todas las pantallas.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Menos pasos**, medidos antes y después: (a) crear y encolar una tarea para un agente, (b) aprobar una petición al abrir la app, (c) ir a la tarea en la que trabaja un agente, (d) encontrar una tarea por su `T-n`. Cada flujo baja de pasos y ninguno supera 3 interacciones | Tabla antes/después en `validacion.md` + tests de UI |
| CA2 | Cabecera v7 con la navegación superior y sus contadores en vivo; sin barra lateral; Inbox, Consumo, Agentes y Proyectos siguen accesibles por ruta, Inicio y Ctrl+K | Tests de UI + capturas |
| CA3 | Inicio muestra saludo, «Te necesitan», agentes y la columna de resumen, con los estados normal, vacío, cargando, desconectado y tema claro, fiel a las capturas v7 (salvo equipos y cuentas) | Tests de UI + capturas comparadas con `v2/screenshots` |
| CA4 | Aprobar, rechazar, responder y reanudar desde Inicio funcionan igual que desde la Inbox y desbloquean al agente | Test de UI + e2e del backend con el CLI falso |
| CA5 | Los avisos de CLI aparecen en «Te necesitan» (cuota agotada, sesión cerrada, límite diario ≥ 95 %), cuentan en el contador y «Posponer» los oculta en la sesión | Tests de UI |
| CA6 | Nueva tarea: se abre con `N`, Ctrl+K y «+» de una tarjeta (agente preseleccionado), recuerda la última elección y «Crear y encolar» la encola | Tests de UI |
| CA7 | Nuevo agente se crea como borrador y se activa desde su ficha; Nuevo proyecto pide nombre, carpeta, pipeline y color | Tests de UI + tests de la API si cambia |
| CA8 | Ctrl+K encuentra secciones, agentes, proyectos y tareas y ejecuta las acciones; `?` muestra los atajos; ningún atajo actúa con el foco en la terminal o en un campo; «Atajos de una tecla» los desactiva | Tests de UI + prueba manual con una ejecución en vivo |
| CA9 | Ajustes conserva sus seis secciones con índice lateral y añade «Atajos de una tecla» | Tests de UI existentes en verde + captura |
| CA10 | El acabado v7 se aplica a todas las pantallas en los dos temas, con contraste AA y sin animaciones con `prefers-reduced-motion` | Capturas + revisión con el usuario |
| CA11 | Revisión con el usuario de los flujos de CA1 y de cada pantalla, con su OK; lo pendiente queda anotado | Acta en `validacion.md` |
| CA12 | Lint, typecheck y todos los tests (backend y frontend) en verde | `npm run check` / CI local |

## Prerrequisitos
- Fase 08 cerrada (`v1.0`).
- Diseño v7 en `docs/design/v2/`, revisado en `docs/design/v2/revision.md`.

## Riesgos y preguntas abiertas
- **Datos de Inicio**: las sesiones vivas por agente, la actividad de cada proyecto y los contadores probablemente necesitan endpoints nuevos de solo lectura (o ampliar los actuales). Se concretará en el plan, sin cambiar el modelo de datos salvo lo mínimo (p. ej. guardar el interruptor de atajos).
- **Cuota en la columna de CLIs**: el diseño muestra el % de la cuota de cada cuenta, que los CLIs no exponen. Se sustituye por el % del **límite diario** que fija el usuario (coste en Claude, tokens en agy) y el estado de la sesión.
- **Código de referencia que falta**: la v7 depende de `../v1.1/code` (`RequestActions`, `kbd`), que no está en el repo. Se toma del prototipo (`v2/prototype/RequestActions.dc.html`) y de `v2/components.md`.
- **Atajos y terminal**: xterm.js captura el teclado; Ctrl+K y las teclas de un carácter no deben robar teclas al CLI.
- **Rendimiento del acabado**: el vidrio (`backdrop-filter`) y el fondo atmosférico pueden costar en WebView2 con terminales en vivo; se mide y, si hace falta, se simplifica en las pantallas con terminal.
- **Línea base de CA1**: hay que contar los pasos actuales antes de tocar nada (primer paso del desarrollo).
