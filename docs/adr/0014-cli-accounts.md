# ADR 0014: Cuentas de CLI, equipos y cuota de la suscripción

- **Estado**: aceptado
- **Fecha**: 2026-10-14
- **Contexto de decisión**: fase 10 ([`spec.md`](../phases/10-equipos-cuentas/spec.md), [`plan.md`](../phases/10-equipos-cuentas/plan.md), evidencias [S1–S3](../phases/10-equipos-cuentas/evidencias/s1-s2-captura.md))

## Contexto
Hasta la v1.1 cada CLI tenía una sola sesión: la del usuario del sistema. Los límites diarios, «Cuota agotada» y el bloqueo del scheduler iban por CLI, y la app no sabía cuánto llevaba gastado el usuario de su suscripción (ventana de 5 h y semanal). El usuario quiere repartir el trabajo entre varias suscripciones y verlas de un vistazo.

## Decisión

### Qué es una cuenta
- Una **cuenta** (`cli_accounts`) es un inicio de sesión de un CLI. Cada CLI instalado tiene una **cuenta del sistema** (`config_dir` nulo): su configuración de siempre. La migración `0008` la crea como predeterminada, mueve a ella los límites diarios y asigna las ejecuciones y avisos existentes, de modo que **actualizar no cambia nada**.
- **Claude Code** admite varias: cada cuenta nueva tiene una carpeta propia (`<datos>/accounts/<id>/`) que se pasa en `CLAUDE_CONFIG_DIR` al lanzar. Es lo que aísla el inicio de sesión sin tocar `~/.claude` (S1). `claude auth status` devuelve email y plan, y sale con **código 1 sin sesión**, así que se lee el JSON y no el código.
- **agy** admite **una sola cuenta**. Guarda el inicio de sesión en el Administrador de credenciales de Windows (`gemini:antigravity`), por usuario del sistema, no en una carpeta. Ninguna de sus variables de entorno (`ANTIGRAVITY_APP_DATA_DIR`, `JETSKI_APP_DATA_DIR`, `AGY_ACCOUNT`) lo cambia, y mover `USERPROFILE` solo recoloca su carpeta `.gemini` además de romper `git`, `ssh` y `npm` para los agentes (S2).
- Un agente apunta a una cuenta de su CLI (`agents.account_id`) o, vacío, a la predeterminada. Una reanudación usa siempre la cuenta de la ejecución original: la conversación vive en su carpeta.

### Iniciar sesión desde la app
El login del CLI es interactivo (abre el navegador y, si no puede, imprime una dirección y pide un código). Corre en un **PTY visible** (`WS /api/accounts/{id}/login/terminal`, el mismo protocolo que el terminal de una ejecución, extraído a `api/terminal.py`). Al terminar el proceso, la app vuelve a preguntar al CLI quién está conectado. Claude: `claude auth login --claudeai [--email]`; agy no tiene comando de login, así que abre su TUI.

### Límites, cuota y sesión por cuenta
- El **límite diario** (fase 07) pasa a `cli_accounts.daily_limit`. «Límite diario alcanzado» y «Cuota agotada» se crean, se resuelven y bloquean **por cuenta**: las demás cuentas del mismo CLI siguen. No hay tope global; «Gasto de hoy» compara el coste con la suma de los límites de las cuentas de Claude.
- **Sesión caída**: `probe` (arranque, «Comprobar», tras el login y antes de lanzar si la última comprobación tiene más de 10 min) fija `session_state`. Con `down` el scheduler no lanza tareas de esa cuenta y aparece un aviso «Sesión cerrada» (`InboxKind.ACCOUNT`) solo si algún agente la usa. No se puede descartar: vuelve a crearse mientras siga cerrada; se resuelve solo al reconectar.
- **Inbox**: `limit`, `quota` y `account` llevan el id de la cuenta en `command`.

### Cuota de la suscripción
La leen **las status lines que ya se ejecutan en cada sesión**, no una consulta aparte:
- **Claude Code**: `rate_limits.five_hour` / `seven_day` (`used_percentage`, `resets_at`). La status line por ejecución existe desde la fase 07; solo se lee un campo más. Solo suscripciones Pro/Max y tras la primera respuesta.
- **agy**: `quota.<bucket>` (`gemini-5h`, `gemini-weekly`, `3p-5h`, `3p-weekly`) con `remaining_fraction`, `reset_time`; más `email` y `plan_tier`.
- Se guarda **solo el último valor** de cada ventana por cuenta (`cli_accounts.quota`, JSON), con cuándo se leyó. Una ventana pasada su `resets_at` **se muestra reiniciada** (0 %) hasta que una sesión vuelva a leerla; el cliente lo comprueba también con su reloj. Los valores coinciden con `/usage` de cada CLI (S1, S2).
- **Los avisos de cuota ≥ 95 % no son una petición de la Inbox**: se derivan en el cliente (`buildCliAlerts`), como los avisos de CLI de la fase 09, y desaparecen solos al reiniciarse la ventana.
- Solo hay dato **mientras hay una sesión viva** de esa cuenta; fuera de eso se muestra el último valor con su antigüedad. No se consulta la cuota sin sesión ni se usan endpoints no documentados.

### agy: la cuota exige tocar un fichero de la persona
agy solo ejecuta una status line declarada en `~/.gemini/antigravity-cli/settings.json`: ni un `settings.json` del workspace ni un campo en el `plugin.json` funcionan (S2). Por eso leer la cuota de agy es una **opción explícita y reversible** («Leer la cuota de Antigravity» en CLIs y cuentas), con estas garantías (S3):
- el script (`agyquota.cmd`) **no hace nada fuera de Agentic OS**: solo publica si la sesión recibió `AGENTIC_OS_STATUS_URL`, que solo ponen las ejecuciones lanzadas por la app;
- no imprime nada y se añade `stack_with_default`, así que la línea de estado normal de agy sigue igual;
- **nunca pisa** una `statusLine` que la persona ya tenga (`status_line_taken`);
- **no edita el fichero con agy abierto** (lo reescribe mientras corre): `agy_running`;
- desactivarlo quita solo esa clave; el resto del fichero queda byte a byte como estaba;
- el nombre cabe en 8.3 (`agyquota.cmd`): la ruta corta con la que agy lo ejecuta acorta también el nombre del fichero y de otro modo no se reconocería como propio.

### Equipos
`teams` (nombre, descripción, posición); `agents.team_id` (un equipo como máximo, `SET NULL` al borrarlo). Solo organizan: Inicio agrupa por equipo, con «Sin equipo» al final, y vuelve a la rejilla única si no hay ninguno.

## Alternativas descartadas
- **Aislar agy cambiando `USERPROFILE`/`HOME`**: conserva el login (credenciales del sistema) pero no lo separa, y rompe las herramientas de los agentes.
- **Inyectar la status line de agy por ejecución** (workspace o plugin): no la lee.
- **Instalar la status line de agy sin preguntar**: modifica una configuración de la persona; se prefirió un interruptor.
- **Consultar la cuota con una sesión mínima o endpoints propios**: gasta cuota para medirla y depende de interfaces no documentadas.
- **Bloquear el scheduler por % de cuota** (p. ej. 90 %): se avisa, no se bloquea, hasta ver lo fiable que es el dato en uso real.
- **Un tope global de gasto**: los límites por cuenta lo cubren.
- **Guardar el histórico de cuota**: solo el último valor; el consumo histórico ya está en las ejecuciones.

## Consecuencias
- Cada ejecución guarda su cuenta (`runs.account_id` + copia del nombre), visible en Ejecuciones, el detalle de tarea y Consumo, que filtra y agrupa por cuenta.
- La confianza en carpetas (`.claude.json`) de cada cuenta con carpeta propia se limpia igual que la del sistema (`TrustCleaner.extra_configs`).
- Las rutas de transcript de Claude se calculan con la carpeta de la cuenta de la ejecución.
- `/ajustes#clis` redirige a `/clis`; «CLIs detectados» deja Ajustes.
- Pendiente de probar a mano con una **segunda cuenta real**: el login completo en una carpeta aislada (CA2, CA3) y el aviso de sesión caída (CA5).
