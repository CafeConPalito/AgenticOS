# Fase 10: Equipos y cuentas de CLI · Spec

- **Estado**: aprobada (2026-10-14)
- **Rama**: `phase/10-equipos-cuentas`

## Objetivo
Poder usar **varias cuentas del mismo CLI** y asignar a cada agente la suya. Además, ver por cuenta cuánto se lleva gastado de las ventanas de la suscripción (5 h y semanal) y cuándo se reinician. Así, dos agentes de Claude Code consumen suscripciones distintas, y si una se agota la otra sigue trabajando. Además, los agentes se pueden **agrupar en equipos** para que Inicio se lea por áreas de trabajo y no como una rejilla plana. Es lo que la fase 09 dejó fuera del diseño v7 (`docs/design/v2/`, revisión en `revision.md`).

## Punto de partida
- Hoy cada CLI usa una sola sesión: la del usuario del sistema (`~/.claude` para Claude Code, `~/.gemini/antigravity-cli` para agy).
- Los límites diarios (fase 07, ADR 0011), los avisos «Cuota agotada» y «Límite diario alcanzado» y el bloqueo del scheduler van **por CLI**.
- Inicio muestra una rejilla única de agentes y, en la columna de resumen, una fila por CLI, sin cuentas.
- Claude Code permite aislar una cuenta con `CLAUDE_CONFIG_DIR`. `claude auth status` devuelve `loggedIn`, `email`, `subscriptionType` (plan) y `configDirectory`.
- agy no tiene opción de carpeta de configuración ni comando de estado. Habrá que verificar si se puede aislar (ver Riesgos).
- **La cuota de la suscripción sí es legible** (la fase 07 no la encontró), a través del JSON que ambos CLIs pasan al script de la **status line**:
  - **Claude Code** ([docs](https://code.claude.com/docs/en/statusline)):
    - `rate_limits.five_hour` y `rate_limits.seven_day`, cada uno con `used_percentage` (0–100) y `resets_at` (epoch);
    - solo con suscripción Pro o Max y a partir de la primera respuesta de la sesión.
  - **agy** ([docs](https://www.antigravity.google/docs/cli/statusline)):
    - `quota`, un mapa por modelo o bucket (p. ej. `gemini-weekly`) con `remaining_fraction`, `reset_time` y `reset_in_seconds`;
    - además trae `email` y `plan_tier`, que sirven para identificar la cuenta.
  - El script se ejecuta cuando cambia el estado de la sesión, así que solo hay datos mientras hay una sesión viva de esa cuenta.

## Alcance
### Dentro

**Cuentas de CLI**
- Nuevo modelo **Cuenta**:
  - CLI y nombre visible (por defecto, el email);
  - email, plan y estado de la sesión (iniciada · caída · desconocida), leídos del CLI;
  - carpeta de configuración propia, bajo la carpeta de datos de la app;
  - marca de **predeterminada** de su CLI.
- **Cuenta del sistema**: al migrar, cada CLI instalado recibe una cuenta que apunta a la configuración actual del usuario, sin carpeta propia. Es la predeterminada, de modo que todo sigue funcionando igual sin hacer nada.
- **Añadir cuenta**: crea la carpeta aislada y abre un terminal de la app con el inicio de sesión del CLI. El usuario completa el login en el navegador y la app lee después email y plan. Se puede reintentar («Reconectar») si la sesión se cae.
- **Quitar cuenta**:
  - con confirmación, si no tiene agentes asignados ni ejecuciones vivas;
  - borra su carpeta aislada;
  - la cuenta del sistema no se puede quitar.
- **Marcar como predeterminada**: la usan los agentes que no eligen cuenta y los que se crean nuevos.

**Agentes y ejecuciones**
- Cada agente tiene una **cuenta** de su CLI (opcional; vacía = la predeterminada). Se elige en «Nuevo agente», en la edición del agente y aparece en «Configuración» de la ficha (Equipo · CLI · Cuenta · Modelo · Permisos). Los modelos ofrecidos dependen de la cuenta.
- Las ejecuciones se lanzan con la configuración de su cuenta:
  - variables de entorno o carpeta;
  - ruta del transcript para el consumo;
  - confianza en carpetas;
  - reanudación de sesiones (siempre con la misma cuenta).
- La ejecución guarda la cuenta usada (id y nombre visible).
- La cuenta usada se ve:
  - en Ejecuciones, en la columna «Cuenta» (12 px, muted);
  - en el detalle de tarea, en la línea de sesión bajo la salida en directo;
  - en la página de ejecución.

**Cuota de la suscripción por cuenta**
- **Captura**:
  - cada ejecución se lanza con una status line propia de Agentic OS (inyectada como los hooks: `--settings` en Claude y el plugin de workspace en agy, si lo admite);
  - el script envía al backend la cuota, con el token de la ejecución, y muestra en el terminal una línea útil (modelo y cuota);
  - el backend guarda por cuenta el **último valor** de cada ventana: % usado, cuándo se reinicia y cuándo se leyó.
- **Ventanas**:
  - Claude: «Ventana de 5 h» y «Semanal»;
  - agy: un bucket por grupo de modelos, con su nombre legible.
  - Una ventana que ha pasado su hora de reinicio se muestra como reiniciada (0 %, «sin datos desde el reinicio»), no con el valor viejo.
- **Dónde se ve**:
  - en «CLIs y cuentas», cada cuenta con sus ventanas (barra, %, «Se reinicia en 1 h 52 min» o «el lunes») y la antigüedad del dato («hace 5 min»);
  - en la columna de resumen de Inicio, el % más alto por CLI y por cuenta, como en el diseño v7;
  - en la ficha del agente, la cuota de su cuenta.
  - Sin dato de cuota (cuenta sin sesiones todavía, o plan sin `rate_limits`), se usa el % del límite diario, como en la fase 09, indicando cuál es.
- **Avisos**:
  - una cuenta con una ventana ≥ 95 % genera un aviso en «Te necesitan»: «{email} · Ventana de 5 h: 96 %, se reinicia en 1 h 10 min. Cambia sus agentes a otra cuenta o espera al reinicio», con «Revisar cuentas» y «Posponer»;
  - se resuelve solo al reiniciarse la ventana.

**Límites, cuotas y avisos por cuenta**
- El **límite diario** pasa de ser por CLI a ser **por cuenta**:
  - la unidad no cambia: coste en Claude y tokens en agy;
  - Ajustes › Límites muestra una fila por cuenta;
  - al migrar, el límite actual de cada CLI pasa a su cuenta del sistema.
- **«Cuota agotada»** y **«Límite diario alcanzado»** se crean, se resuelven y bloquean el scheduler **por cuenta**: si una cuenta se agota, los agentes de las demás siguen recibiendo tareas.
- **Sesión caída**: si la cuenta de un agente no tiene la sesión iniciada al ir a lanzar, la tarea no se lanza. Aparece un aviso en «Te necesitan» con la acción «Reconectar».
- Los avisos de CLI de Inicio (`CliAlertItem`) pasan a ser por cuenta, con email y acciones «Revisar cuentas» / «Reconectar» y «Posponer», según `components.md`.
- **Consumo**: el panel de consumo permite ver y filtrar por cuenta, además de por agente, proyecto y CLI.

**Pantalla «CLIs y cuentas»**
- Nueva ruta `/clis`, según el prototipo v7 (`#/clis`).
- Una sección por CLI con tag, versión, estado de instalación y «Añadir cuenta».
- Por cada cuenta:
  - email, plan y estado de la sesión;
  - uso de hoy frente a su límite diario;
  - los agentes que la usan y sus sesiones vivas;
  - las acciones «Predeterminada», «Reconectar» y «Quitar».
- Un CLI no instalado muestra cómo instalarlo, como hoy.
- Con esta pantalla, la sección «CLIs detectados» sale de Ajustes y `/ajustes#clis` redirige a `/clis`.
- Se llega a ella:
  - desde «Gestionar» en la columna de resumen;
  - desde Ctrl+K («CLIs y cuentas», «Añadir CLI o cuenta»);
  - desde los avisos de CLI.
- **Columna de resumen de Inicio**:
  - una fila por CLI con el % más alto entre sus cuentas (gris; ámbar desde el 80 %) y «n cuentas · n sesiones»;
  - al hacer clic se despliegan sus cuentas, cada una con email, barra, % y «plan · sesiones» (capturas `01a` y `01b`);
  - el % es el de la ventana de cuota más alta de la cuenta y, sin dato de cuota, el de su límite diario.

**Equipos**
- Nuevo modelo **Equipo**: nombre, descripción opcional y orden. Un agente pertenece a **un equipo como máximo**.
- **Crear, editar y borrar equipos**:
  - «Nuevo equipo» en Inicio y en Ctrl+K;
  - el lápiz en la fila del equipo abre la edición: nombre, descripción y agentes que lo forman;
  - al borrar un equipo, sus agentes pasan a «Sin equipo».
- **Inicio agrupa los agentes por equipo**:
  - cabecera «Agentes» con «n equipos · n agentes» y «Nuevo equipo»;
  - por equipo, su fila (nombre, «n agentes · n activos», línea que se desvanece, «+ Agente» y lápiz) y debajo su rejilla de `AgentCard`;
  - los agentes sin equipo van al final, en «Sin equipo»;
  - si no hay ningún equipo, se ve la rejilla única de hoy.
- «+ Agente» en un equipo abre «Nuevo agente» con ese equipo preseleccionado.
- El equipo se elige en «Nuevo agente» y en la edición del agente.
- El equipo aparece en «Configuración» de la ficha y en las migas de la ficha de agente (Inicio › Equipo › Agente).
- En la lista de Agentes, el equipo se puede ver y filtrar.

**Transversal**
- Migraciones de Alembic sin pérdida de datos.
- API REST de cuentas y equipos y cambios en `/api/home`, `/api/agents` y `/api/runs`.
- Textos en i18n y tests de backend y frontend.
- ADR de cuentas de CLI (aislamiento, migración, límites por cuenta).

### Fuera
- **Consultar la cuota sin sesión viva**, por ejemplo lanzando una sesión mínima o llamando a endpoints no documentados con el token del usuario. Solo se muestra lo que llega de las sesiones, con su antigüedad.
- **Que el scheduler pause por % de cuota** (p. ej. «no lanzar por encima del 90 %»). El bloqueo sigue siendo «Cuota agotada» y el límite diario. Se anota para más adelante, cuando se vea lo fiable que es el dato.
- Histórico de la cuota: se guarda solo el último valor por ventana.
- **Cambio automático de cuenta** cuando una se agota (failover): el aviso lo propone y el cambio lo hace el usuario.
- **Comportamiento por equipo**: instrucciones, presupuestos, permisos o colas compartidas. En esta fase el equipo solo organiza.
- **CLIs nuevos** (Codex, Gemini CLI, OpenCode) e instalarlos desde la app: el catálogo «Añadir CLI» solo ofrece los CLIs soportados.
- **Cuentas por API key o proveedores** (Bedrock, Vertex): solo cuentas de suscripción con login.
- Equipos anidados y un agente en varios equipos.

## Historias de usuario
- Como usuario con dos suscripciones de Claude, quiero añadir la segunda cuenta desde la app y asignarla a algunos agentes, para repartir el consumo entre ambas.
- Como usuario, quiero que, si una cuenta agota su cuota, los agentes de las otras cuentas sigan trabajando y que se me avise de cuál se ha agotado.
- Como usuario, quiero ver en un sitio qué cuentas tengo por CLI, su plan, su uso de hoy y qué agentes las usan.
- Como usuario, quiero ver cuánto llevo gastado de la ventana de 5 h y de la semanal de cada suscripción, y cuándo se reinician, para decidir a qué cuenta mando el trabajo sin abrir cada CLI.
- Como usuario, quiero saber qué cuenta usó cada ejecución, para entender el consumo.
- Como usuario, quiero reconectar una cuenta cuya sesión se ha caído sin salir de la app.
- Como usuario con muchos agentes, quiero agruparlos en equipos («Producto», «Contenidos»…), para que Inicio se entienda de un vistazo.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Tras actualizar, cada CLI instalado tiene su «cuenta del sistema» predeterminada; los agentes, ejecuciones, límites y avisos existentes siguen funcionando sin intervención | Test de migración sobre una BD de la v1.1 + prueba manual con la BD real |
| CA2 | Se añade una segunda cuenta de Claude Code desde «CLIs y cuentas»: el login se hace en el terminal de la app y la cuenta aparece con su email y plan | Prueba manual con dos cuentas reales + tests de la API con CLI simulado |
| CA3 | Dos agentes de Claude Code con cuentas distintas ejecutan tareas a la vez y cada ejecución usa su cuenta (carpeta de config, transcript y consumo correctos) | Prueba manual + tests del launcher y del lector de consumo |
| CA4 | Con una cuenta bloqueada (límite diario o «Cuota agotada»), el scheduler no lanza tareas de sus agentes y sí de los de otra cuenta del mismo CLI; el aviso nombra la cuenta | Tests del scheduler y de límites |
| CA5 | Una cuenta con la sesión caída genera un aviso «Reconectar» en «Te necesitan»; al reconectar desaparece y sus tareas vuelven a lanzarse | Tests + prueba manual cerrando la sesión |
| CA6 | La cuenta usada se ve en Ejecuciones, en el detalle de tarea y en la ejecución; el consumo se puede filtrar por cuenta | Tests de UI y de la API |
| CA7 | «CLIs y cuentas» (`/clis`) muestra CLIs, cuentas, plan, uso, agentes y sesiones, y permite añadir, reconectar, marcar como predeterminada y quitar cuentas; `/ajustes#clis` redirige allí | Tests de UI + capturas comparadas con el prototipo v7 |
| CA8 | La columna de resumen de Inicio muestra por CLI el % más alto de sus cuentas y despliega las cuentas | Tests de UI + capturas `01a`/`01b` |
| CA13 | Tras una ejecución de Claude Code con suscripción Pro/Max, la cuenta muestra «Ventana de 5 h» y «Semanal» con el mismo % y reinicio que `/usage` del CLI, y la antigüedad del dato; una ventana pasada su reinicio se ve reiniciada | Prueba manual comparando con `/usage` + tests del receptor y de la caducidad |
| CA14 | Igual para agy con sus buckets de `quota`, comparando con su `/usage` (si su status line se puede inyectar por ejecución; si no, CA11 decide) | Prueba manual + tests |
| CA15 | Una ventana ≥ 95 % genera el aviso de cuota en «Te necesitan» con email, ventana y reinicio, y se resuelve sola al reiniciarse | Tests |
| CA9 | Se crean, editan y borran equipos; Inicio agrupa los agentes por equipo con «Sin equipo» al final y vuelve a la rejilla única si no hay equipos | Tests de UI y de la API |
| CA10 | El equipo y la cuenta se eligen en «Nuevo agente» y en la edición, y aparecen en «Configuración» y en las migas de la ficha | Tests de UI |
| CA11 | agy: si el spike confirma el aislamiento, admite varias cuentas como Claude; si no, tiene solo la cuenta del sistema y la UI lo explica en lugar de ofrecer «Añadir cuenta» | Resultado del spike en el plan + test de UI |
| CA12 | Lint, tipos y tests de backend y frontend en verde; `/code-review` resuelto | `scripts` de CI local |

## Prerrequisitos
- Fase 09 cerrada (`v1.1`). ✅
- Investigar al empezar los 2 tests que fallan en `backend/tests/test_usage_stats.py`, porque esta fase toca los límites.
- Una segunda cuenta de Claude Code (y, si es posible, de agy) para las pruebas manuales.

## Riesgos y preguntas abiertas
- **Aislar agy**: no tiene carpeta de configuración ni comando de estado. Al empezar el plan se hará un spike corto para ver si basta con cambiar `HOME`/`USERPROFILE` o si guarda las credenciales fuera, por ejemplo en el Administrador de credenciales de Windows. El resultado decide CA11.
- **Login dentro de la app**: Claude Code inicia sesión con OAuth en el navegador. Falta comprobar que funciona desde el PTY de la app con `CLAUDE_CONFIG_DIR` y que no pisa la cuenta del sistema.
- **Efectos de `CLAUDE_CONFIG_DIR`**: la confianza en carpetas (`.claude.json`), los transcripts y los ajustes del usuario pasan a la carpeta de cada cuenta. Hay que revisar trust, el lector de consumo, la reanudación y la limpieza.
- **Status line por ejecución**:
  - Falta comprobar que Claude acepta `statusLine` en `--settings` junto a `--setting-sources`, y que agy lo admite desde el plugin de workspace. Si agy solo lo lee de `~/.gemini/antigravity-cli/settings.json`, habría que tocar la configuración global del usuario, que la fase 04 evitó; se decidiría en el plan.
  - Al tener status line propia, el CLI cambia el pie del terminal. Hay que revisar que el lector de pantalla (`screen.py`) no dependa de él.
- **Fiabilidad de la cuota**: hay quejas de usuarios de que el `/usage` de agy no se actualiza durante la sesión. La app mostrará la antigüedad del dato y no lo usará para bloquear.
- **Ejecuciones antiguas**: las ejecuciones antiguas no tenían cuenta y se asignan a la cuenta del sistema de su CLI.
- **Límites por cuenta frente a «Gasto de hoy»**: la cifra global de Inicio sigue siendo la suma del día. Hay que decidir en el plan si se mantiene un tope global además de los límites por cuenta.
