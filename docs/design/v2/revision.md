# Revisión del diseño v7 (Claude Design) · 2026-10-13

Paquete en `docs/design/v2/`: Agentic OS v7 (README, screens, components, design-system, tokens, 14 capturas, prototipo y código de referencia). Es la referencia visual de la **fase 09**.

## Valoración
Buena entrega: Inicio responde de verdad a «qué necesita de mí» y «qué hacen mis agentes», los diálogos son cortos, la paleta Ctrl+K está completa y el acabado (vidrio, degradados, fondo atmosférico) da un salto de calidad sin tocar la paleta de marca. Pero se aleja del producto real en varios puntos, decididos con el usuario:

## Decisiones
| Tema | v7 | Decisión |
|---|---|---|
| Navegación | Sin barra lateral; cabecera con Tablero · Ejecuciones · Conocimiento · Ajustes; Inicio como centro | **Se adopta.** Inbox, Consumo, Agentes y Proyectos siguen como rutas, accesibles desde Inicio y Ctrl+K. Conocimiento sale cuando exista |
| Equipos de agentes | Agentes agrupados por equipo, «Nuevo equipo» | **Fase 10** (nueva). En la 09, una sola rejilla |
| Cuentas por CLI | Varias cuentas por CLI con cuota, plan y sesiones | **Fase 10**. En la 09, una fila por CLI con el % del límite diario y la sesión |
| Cuota real de la suscripción | % por cuenta | No se puede: los CLIs no la exponen (fase 07). Se usa el límite diario |
| Acabado visual | Radios, vidrio, degradados, sombras, fondo, animaciones | **Se adopta en toda la app**, con `prefers-reduced-motion` |
| Ajustes | 3 filas, sin índice | **Se mantienen las seis secciones reales** con acabado v7 e índice lateral; se añade «Atajos de una tecla» |
| Nuevo agente | Plantillas + campos; se crea como borrador | Se adopta (el estado borrador ya existe) |
| Nueva tarea | Título, proyecto, agente; «Crear y encolar» | Se adopta; se mantienen descripción (plegada) y «Guardar en backlog» |

## Cómo se usa
| Pieza | Uso |
|---|---|
| `tokens.css` | Sustituye a `frontend/src/styles/tokens.css` (los cambios van marcados con «v7»; ningún color de marca cambia) |
| `screens.md`, `components.md`, `design-system.md` | Especificación de la fase 09; lo no marcado sigue en `../screens.md` y `../components.md` |
| `code/` | Punto de partida, no se copia tal cual: textos a i18n, React Router y TanStack Query, sin datos de ejemplo |
| `prototype/`, `screenshots/` | Referencia visual y criterio de aceptación (CA3, CA10) |

## Huecos
- La v7 cita `../v1.1/code` (`RequestActions`, `kbd`), que no está en el repo: se usa `prototype/RequestActions.dc.html`.
- Sin código React para Nuevo agente, Nuevo proyecto, ficha de agente, detalle de tarea y Ejecuciones: se montan con los componentes base a partir del prototipo.
- `UsageBreakdown.dc.html` (consumo de un agente) sirve de referencia para la ficha de agente.
