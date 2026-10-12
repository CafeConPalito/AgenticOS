# Fase 07: Consumo · Spec

- **Estado**: borrador
- **Rama**: `phase/07-consumo`

## Objetivo
Saber **cuánto gastan tus agentes**: tokens, coste y tiempo de cada sesión de CLI, leídos de los transcripts que escribe el propio CLI (ADR 0005), y agregados por agente, proyecto, tarea y día. Con un **límite diario de coste** que evita que el scheduler siga lanzando trabajo cuando se supera.

## Alcance
### Dentro
**Lectura del consumo** (backend, según ADR 0005):
- **Parsers** por CLI a partir del prototipo `spikes/usage_probe.py`:
  - Claude Code: última fila `cost-state` (`totalCostUSD` y `modelUsage`, con los subagentes nativos incluidos). Si no la hay, suma del `usage` de las filas `assistant`, sin duplicar mensajes; en ese caso el coste queda vacío.
  - agy: suma de los tokens de los pasos de `transcript_full.jsonl`. Sin coste.
  - toleran filas y campos desconocidos; si no encuentran nada, la ejecución queda en «consumo no disponible».
- **Ruta del transcript**: la que llega en los hooks (`transcript_path` en Claude, `transcriptPath` en agy) se guarda en la ejecución. Si no ha llegado ningún hook, se calcula a partir de la carpeta de trabajo y el ID de sesión.
- **Cuándo se lee**: en cada fin de turno (hook `Stop`) para tener el consumo parcial en vivo, y al terminar la ejecución para el consumo final. Una lectura que falla no rompe la ejecución: se registra en el log.
- **Subagentes nativos de agy**: tienen su propia conversación y su propio transcript (fase 06). Su consumo se suma al de la ejecución que los lanzó.
- **Subagentes de Agentic OS** (`spawn_subagent`): son ejecuciones con su propio consumo. En el árbol y en la tarea se ve el total de la tarea, con el desglose por ejecución.
- **Ejecuciones anteriores a esta fase**: al arrancar, se calcula en segundo plano el consumo de las ejecuciones terminadas que aún no lo tienen, si su transcript sigue existiendo.
- Se guarda por ejecución: tokens de entrada, salida, razonamiento, lectura de caché y escritura de caché; coste en USD (o vacío); desglose por modelo; fuente (`cost-state`, filas `assistant` o `transcript_full`); versión del CLI y fecha de la última lectura.
- **Fixtures** de transcripts reales de los dos CLIs (anonimizados) para los tests de los parsers.

**Coste**:
- Claude: **coste equivalente API en USD**, tal como lo calcula el CLI. La UI lo etiqueta como «equivalente API» (con suscripción no es un cargo real).
- agy: solo tokens; el coste se muestra como «—» y no suma en los totales de coste.
- Moneda: **USD** (`$`), sin conversión. El diseño usa «€» como ejemplo.

**Agregados y API**:
- Endpoints de consumo con filtros por periodo, agente y proyecto: KPIs del periodo, serie diaria por agente o por proyecto, reparto del periodo y lista de sesiones.
- Exportación de las sesiones del periodo a **CSV**.
- El consumo de cada ejecución viaja en sus datos (API y WebSocket de la ejecución), para mostrarlo en vivo.
- Los días se cuentan en la **hora local** del equipo.

**Límite diario de coste**:
- En **Ajustes**, un importe en USD (vacío = sin límite). Se guarda en el backend.
- Cuenta el coste de hoy de todas las ejecuciones (solo Claude, que es el único con coste).
- Al **superarlo**:
  - el scheduler **no lanza tareas nuevas** hasta el día siguiente o hasta que subas el límite; las tareas siguen en cola;
  - las ejecuciones en marcha **siguen** (no se cortan a medias);
  - lanzar una ejecución a mano sigue siendo posible, con un aviso;
  - llega un aviso a la **Inbox** y como notificación de Windows (con su interruptor en Ajustes > Notificaciones).
- Al **80 %** del límite, aviso informativo en el Dashboard.

**UI** (según `docs/design/screens.md` y las capturas):
- **Consumo** (`11-consumo`): selector de periodo **7 · 30 · 90 días**; 4 KPIs (Coste con la variación frente al periodo anterior · Tokens con el % servido desde caché · Horas de agente · Sesiones de CLI con el % terminadas sin error); gráfica de barras apiladas del coste diario **por agente / por proyecto** (recharts); reparto del periodo; tabla de **sesiones de CLI** ordenable (Inicio, Agente, Proyecto, Tarea, Modelo, Tokens, Coste y Duración; clic → ejecución). Botón de cabecera «Exportar CSV».
- **Dashboard · Consumo de hoy**: KPIs de tokens (con los de caché) y coste, barras por agente, barra del límite diario y «Ver detalle →».
- **Detalle de tarea / ejecución · Consumo de la sesión**: rejilla 2×3 (entrada, salida, caché lectura, caché escritura, coste y duración) en vivo, y el ID de sesión del CLI.
- **Agentes**: columna «Consumo del mes» en la lista; columnas Tokens y Coste en la pestaña Historial.
- **Proyectos**: KPI «Coste del mes» en Resumen; columna Coste en Tareas.
- **Ejecuciones**: columnas Tokens y Coste en la lista.
- Formato: tokens abreviados en español («1,33 M», «230,3 k»); coste con 2 decimales («2,84 $»); «—» si no hay coste y «Consumo no disponible» si el parser no encontró nada.

### Fuera
- Tabla de precios propia para estimar el coste de agy u otros modelos (queda como mejora futura; ADR 0005).
- Conversión a euros u otras monedas.
- Límites por agente o por proyecto, y límites de tokens.
- Cortar una ejecución en marcha al superar el límite.
- Consumo real de la suscripción (cuotas de Claude Pro/Max o de Google): no lo exponen los CLIs.
- Parsers de otros CLIs (Gemini CLI, OpenCode, Codex): llegarán con sus adapters.
- OpenTelemetry de Claude Code.

## Historias de usuario
- Como usuario, quiero ver cuánto ha consumido cada agente y cada proyecto en un periodo para saber dónde se van los tokens.
- Como usuario, quiero ver el consumo de una sesión mientras el agente trabaja.
- Como usuario, quiero fijar un límite diario de coste para que los agentes no sigan lanzando tareas sin control.
- Como usuario, quiero exportar las sesiones a CSV para analizarlas por mi cuenta.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Claude real**: el coste y los tokens de una ejecución (con un subagente nativo) **coinciden** con lo que reporta el propio CLI (`/cost` o el resultado JSON) | Prueba manual con evidencia |
| CA2 | **agy real**: los tokens de una ejecución (con un subagente nativo) coinciden con los del resultado JSON del CLI; el coste se muestra como «—» | Prueba manual con evidencia |
| CA3 | **Parsers**: los tests con fixtures reales de los dos CLIs pasan, incluidos el respaldo de las filas `assistant`, las filas desconocidas o corruptas y el transcript inexistente («consumo no disponible») | Tests |
| CA4 | **En vivo**: el consumo de la sesión se actualiza al final de cada turno y queda fijo al terminar la ejecución | e2e con el CLI falso + prueba manual |
| CA5 | **Agregados**: KPIs, serie diaria, reparto y sesiones son correctos por periodo, agente y proyecto, con días en hora local; el CSV contiene las sesiones del periodo | Tests de la API |
| CA6 | **Límite diario**: al superarlo, el scheduler deja de lanzar tareas, las ejecuciones en marcha siguen, llega el aviso a la Inbox y la notificación; al subir el límite o al cambiar de día, la cola se reanuda | Tests del scheduler + e2e |
| CA7 | **Ejecuciones anteriores**: tras arrancar, las ejecuciones terminadas con transcript disponible tienen su consumo | Test + revisión |
| CA8 | **UI** fiel a `11-consumo`, al bloque de consumo del Dashboard (`01a`) y al de la sesión en `09a`; columnas de consumo en Agentes, Proyectos, Tareas y Ejecuciones; el límite en Ajustes | Tests de componentes + capturas |
| CA9 | `check` en verde; ADR (si hay decisiones nuevas), README y roadmap actualizados | Salida del `check` + revisión |

## Prerrequisitos
- Fase 06 cerrada (`v0.7`).
- Claude Code y agy instalados y con sesión iniciada.

## Riesgos y preguntas abiertas
- **Formatos internos sin documentar**: pueden cambiar con cada versión del CLI. Los parsers toleran lo desconocido, registran la versión del CLI y hay fixtures por versión.
- **`cost-state` y el momento del `Stop`**: puede que el CLI escriba la fila después de lanzar el hook. Si pasa, se repite la lectura con un pequeño retardo o en el siguiente turno; lo confirmará la primera tarea del plan.
- **Transcripts desaparecidos**: el usuario o el CLI pueden borrarlos. El consumo ya guardado no se pierde; solo se dejan de actualizar.
- **`CLAUDE_CONFIG_DIR`**: si el usuario lo usa, los transcripts de Claude no están en `~/.claude`. Por eso la ruta del hook manda sobre la calculada.
- **Límite solo con coste de Claude**: con agentes de agy el límite no protege nada. Se indica en Ajustes.
- **Moneda**: el diseño muestra «€» pero el CLI da USD. Se propone mostrar USD sin convertir; confirmar.
- **Comportamiento del límite**: se propone frenar solo las tareas nuevas del scheduler (no cortar las ejecuciones en marcha ni bloquear las manuales); confirmar.
