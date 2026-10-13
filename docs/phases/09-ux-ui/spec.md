# Fase 09: Mejora de UX/UI · Spec

- **Estado**: borrador
- **Rama**: `phase/09-ux-ui`

## Objetivo
Tras usar la v1.0, lo que más estorba es que **las tareas habituales exigen demasiados pasos** y que **la navegación no deja claro dónde está cada cosa** (ocho entradas sueltas en el menú; Ejecuciones, Tablero e Inbox se solapan). Esta fase reordena la navegación, convierte el Dashboard en el punto de partida real («qué está pasando y qué necesita de mí»), acorta los flujos principales y añade la paleta de comandos (Ctrl+K) del diseño. No añade funciones de dominio nuevas.

## Alcance
### Dentro
**Navegación** (menú lateral agrupado):
- Tres grupos con su título:
  - **Trabajo**: Inicio (Dashboard), Tablero, Inbox.
  - **Configuración**: Agentes, Proyectos.
  - **Sistema**: Ejecuciones, Consumo, Ajustes.
- La Inbox muestra en el menú el **contador** de peticiones pendientes (y en ámbar si hay aprobaciones).
- Las migas de pan y la acción principal de la cabecera se revisan en todas las pantallas para que sean coherentes (una sola acción principal por pantalla, siempre en el mismo sitio).
- Desde una tarea se llega a sus ejecuciones y desde una ejecución a su tarea, sin pasar por la lista de Ejecuciones (que queda como historial global).

**Dashboard** (según `docs/design/screens.md` §1 y las capturas `01a`/`01b`):
- **Saludo y resumen**: «N agentes trabajando · N esperándote · N peticiones en el Inbox» y la fecha.
- **Tarjetas de agentes** en vivo: estado (trabajando, esperando, inactivo), tarea y proyecto actuales, cronómetro y acción «Asignar tarea». Clic en la tarjeta → su tarea actual (o el agente si está inactivo).
- **Aprobaciones pendientes** (hasta 3, con «Ver Inbox →»): **Aprobar / Rechazar** directamente desde el Dashboard; «Responder» en las preguntas abre la petición en la Inbox.
- **Actividad reciente**: línea de tiempo de los últimos eventos (tareas creadas, terminadas, rechazadas en QA, peticiones de aprobación, ejecuciones interrumpidas…) con enlace a la tarea.
- **Consumo de hoy**: la tarjeta actual, con barras por agente y el límite diario.
- Se mantiene el aviso de CLIs no listos.
- Estados: vacío (sin agentes: guía para crear el primero), cargando (skeletons) y desconectado.
- Se actualiza en vivo (el mismo mecanismo que ya usan Tablero e Inbox).

**Menos pasos en los flujos principales**:
- **Nueva tarea desde cualquier pantalla**: botón en la cabecera, Ctrl+K y atajo de teclado. El diálogo **rellena solo** el proyecto y el agente según el contexto (desde un proyecto, una tarjeta de agente, una columna del Tablero) y recuerda la última elección.
- **Crear y encolar** es la acción por defecto; dejarla en el backlog es la opción secundaria. Tras crearla, un toast con «Ver tarea».
- **Aprobar, rechazar y responder** sin salir de donde se está: Dashboard, Inbox, detalle de la tarea y la notificación nativa (que ya lleva a la petición).
- Revisar los diálogos de **Nuevo agente** y **Nuevo proyecto** para pedir solo lo imprescindible al crear (el resto, con valores por defecto, se edita después).
- Se mide el número de pasos de cada flujo antes y después (ver CA1).

**Paleta de comandos (Ctrl+K)** (según la captura `13b`):
- **Ir a**: secciones, agentes, proyectos y tareas (búsqueda por nombre o `T-n`).
- **Acciones**: nueva tarea, nuevo agente, nuevo proyecto, lanzar ejecución, pausar/reanudar el scheduler, cambiar el tema, abrir Ajustes.
- Navegable solo con el teclado; muestra los atajos.
- Una **ayuda de atajos** (tecla `?`) con todos los atajos de la app.

**Ajustes**: las seis secciones se ordenan con un **índice lateral** (o pestañas) para no tener que desplazarse por una única página larga. Sin cambios de funcionalidad.

**Revisión con el usuario**: al final del desarrollo se recorren con el usuario los flujos de CA1 y cada pantalla; lo que salga y quepa en el alcance se corrige en la fase; lo demás se anota para fases futuras.

### Fuera
- Funciones nuevas de dominio (Conocimiento, Skills, Arquitecto: fases 10–12).
- Cambiar el sistema visual (tokens, tipografía, colores) más allá de lo necesario para la jerarquía de las pantallas tocadas.
- Rediseñar a fondo el detalle de la tarea, la terminal o el Tablero (solo se ajustan sus accesos y acciones).
- Diseño para móvil o pantallas estrechas (la app es de escritorio; se mantiene el mínimo actual).
- Idiomas además del español.
- Atajos configurables por el usuario.
- Políticas de aprobación automática (siguen anotadas para una fase futura).

## Historias de usuario
- Como usuario, quiero abrir la app y ver de un vistazo qué hacen mis agentes y qué necesitan de mí.
- Como usuario, quiero aprobar o rechazar una petición desde el Dashboard sin tener que ir a la Inbox.
- Como usuario, quiero crear y encolar una tarea desde cualquier pantalla en pocos pasos, sin elegir otra vez lo que ya está claro por el contexto.
- Como usuario, quiero encontrar cualquier agente, proyecto o tarea con Ctrl+K y lanzar las acciones habituales desde el teclado.
- Como usuario, quiero un menú agrupado en el que sepa dónde está cada cosa.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Menos pasos** en los flujos principales, medidos antes y después: (a) crear y encolar una tarea desde un proyecto, (b) aprobar una petición pendiente al abrir la app, (c) ir a la tarea en la que trabaja un agente, (d) encontrar una tarea por su `T-n`. Cada flujo baja de pasos y ninguno supera 3 interacciones tras el cambio | Tabla antes/después en `validacion.md` + tests de UI de cada flujo |
| CA2 | El menú lateral muestra los tres grupos con sus secciones y el contador de la Inbox, que se actualiza en vivo | Test de UI + captura |
| CA3 | El Dashboard muestra resumen, tarjetas de agentes en vivo, aprobaciones pendientes, actividad reciente y consumo de hoy, con sus estados vacío, cargando y desconectado | Tests de UI + capturas (oscuro y claro) |
| CA4 | Aprobar y rechazar desde el Dashboard resuelve la petición (igual que desde la Inbox) y desbloquea al agente | Test de UI + e2e del backend con el CLI falso |
| CA5 | El diálogo de nueva tarea rellena proyecto y agente según el contexto y recuerda la última elección; «Crear y encolar» encola la tarea | Tests de UI |
| CA6 | Ctrl+K abre la paleta desde cualquier pantalla; encuentra secciones, agentes, proyectos y tareas, y ejecuta las acciones listadas; todo con el teclado | Tests de UI |
| CA7 | `?` muestra la ayuda de atajos; ningún atajo interfiere con la terminal cuando tiene el foco | Test de UI + prueba manual con una ejecución en vivo |
| CA8 | Ajustes tiene un índice lateral (o pestañas) y sus funciones siguen igual | Tests de UI existentes en verde + captura |
| CA9 | Las migas de pan y la acción principal son coherentes en todas las pantallas | Revisión con el usuario (checklist por pantalla) |
| CA10 | Revisión con el usuario: recorre los flujos de CA1 y cada pantalla y da su OK; lo pendiente queda anotado | Acta en `validacion.md` |
| CA11 | Lint, typecheck y todos los tests (backend y frontend) en verde | `npm run check` / CI local |

## Prerrequisitos
- Fase 08 cerrada (`v1.0`).
- Diseño de referencia en `docs/design/` (pantallas 1, 13b y elementos globales).

## Riesgos y preguntas abiertas
- **Datos del Dashboard**: la actividad reciente y el estado en vivo de cada agente probablemente necesitan endpoints nuevos de solo lectura (p. ej. `GET /activity` y el estado por agente). Se concretará en el plan; no cambian el modelo de datos salvo que el plan lo justifique.
- **Atajos y terminal**: xterm.js captura el teclado; los atajos globales (incluido Ctrl+K) no deben robar teclas al CLI cuando la terminal tiene el foco. Se decidirá en el plan qué atajos se respetan dentro de la terminal.
- **Línea base de CA1**: hay que contar los pasos actuales antes de tocar nada (primer paso del desarrollo).
- **Lista de Ejecuciones**: queda como historial en «Sistema». Si en la revisión resulta que no se usa, se puede proponer quitarla del menú en una fase futura.
