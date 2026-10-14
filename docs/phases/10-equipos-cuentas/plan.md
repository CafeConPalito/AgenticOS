# Fase 10: Equipos y cuentas de CLI · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-14) · en desarrollo

## Lo que ya se sabe (revisado al escribir el plan)
- **Claude Code**:
  - La sesión se guarda en `<config>/.credentials.json` y la confianza en carpetas en `.claude.json`. Las dos cosas siguen a `CLAUDE_CONFIG_DIR`, así que **una carpeta por cuenta aísla el login**.
  - `claude auth status` devuelve `email`, `subscriptionType` (`pro`, `max`…) y `loggedIn`.
  - **Ya inyectamos una status line por ejecución** desde la fase 07 (`--settings` del adapter, evento `StatusLine` del script de hooks), así que la cuota es un campo más del mismo payload: `rate_limits`. El fixture de la 2.1.296 no lo trae, por lo que se capturará uno nuevo.
- **agy**:
  - Guarda el login en el **Administrador de credenciales de Windows** con un destino fijo (`gemini:antigravity`), no en `~/.gemini`. **Cambiar `HOME` no lo aísla**, así que salvo que el spike encuentre otra vía, agy tendrá **solo la cuenta del sistema** (rama «no» de CA11).
  - Su status line lleva `quota`, `email` y `plan_tier`, pero se configura en `~/.gemini/antigravity-cli/settings.json`. El spike comprobará si un plugin de workspace puede declararla.

## Diseño

### Modelo de datos (migración `0008_accounts_teams`)
- **`cli_accounts`**:
  - `cli`, `label` y `email`;
  - `plan`, el texto del CLI: `pro`, `max`, `plan_tier`…;
  - `config_dir` (nulo = **cuenta del sistema**, con la configuración del usuario);
  - `is_default`;
  - `session_state`: `ok` · `down` · `unknown`, más `session_checked_at`;
  - `daily_limit` (float, nulo = sin límite; USD en Claude, tokens en agy);
  - `quota`: JSON `{window_id: {label, used_pct, resets_at, read_at}}`, solo el último valor.
- **`teams`**: `name`, `description` y `position`.
- **`agents`**:
  - `team_id` (FK, `SET NULL`);
  - `account_id` (FK, `SET NULL`; nulo = la predeterminada de su CLI).
- **`runs`**: `account_id` y `account_label`, la foto del momento, como `agent_name`.
- **Datos que mueve la migración**:
  - crea una cuenta del sistema por cada CLI soportado y la marca como predeterminada;
  - pasa `claude_usd` y `agy_tokens` de `AppState[usage_limits]` al `daily_limit` de su cuenta;
  - rellena `runs.account_id` con la cuenta del sistema de su CLI;
  - cambia el `command` de los avisos `limit`/`quota` pendientes de CLI a id de cuenta.

### Backend
- **`services/accounts.py`** (nuevo):
  - CRUD de cuentas;
  - `for_agent(db, agent)`: la cuenta del agente o la predeterminada de su CLI;
  - `env_for(account)`: `{CLAUDE_CONFIG_DIR: …}`, o nada para la del sistema;
  - `probe(account)`: `claude auth status` con ese entorno, que rellena email, plan y `session_state`;
  - `record_quota(account, windows)`;
  - `quota_view(account, now)`: marca como reiniciadas las ventanas cuyo `resets_at` ya pasó.
  - Las carpetas viven en `<data_dir>/accounts/<id>/` y se borran al quitar la cuenta. Con la cuenta del sistema no se puede borrar ni cambiar de CLI.
- **Login** (`services/accounts_login.py`):
  - un PTY propio, que no es una `Run`, con `claude auth login` (o `claude` + `/login`, según el spike) y el entorno de la cuenta;
  - se sirve por `WS /ws/accounts/{id}/login` con el mismo protocolo que los terminales;
  - al terminar el proceso se ejecuta `probe`.
  - «Reconectar» hace lo mismo sobre una cuenta existente.
- **Lanzamiento**:
  - `LaunchContext` recibe `account_env` y `account_config_dir`;
  - `ClaudeAdapter` mete el entorno en `LaunchSpec`, y `clean_env()` sigue conservando el `CLAUDE_CONFIG_DIR` del usuario para la cuenta del sistema.
  - Afectados por la carpeta de configuración:
    - `trust.py` escribe en `<config>/.claude.json` de la cuenta;
    - `usage/paths.py` calcula el transcript con la carpeta de la cuenta;
    - `resume.py` reanuda siempre con la cuenta de la ejecución original;
    - `housekeeping`/`maintenance` limpian la confianza de los worktrees en todas las cuentas.
- **Cuota**:
  - `hooks.interpret` lee `rate_limits.five_hour` y `rate_limits.seven_day` (Claude) y `quota` (agy) en `HookEffect.quota`;
  - `manager` llama a `accounts.record_quota` con la cuenta de la ejecución.
  - Los buckets de agy tienen etiquetas legibles por prefijo (`gemini-weekly` → «Gemini · semanal»); uno desconocido muestra su id.
  - El script de status line de Claude sigue sin imprimir nada, para no tocar el pie que lee `screen.py`.
- **Límites por cuenta** (`usage/limits.py`):
  - `used_by_account`, `blocked_all` → `{account_id: "quota" | "limit" | "session" | None}`;
  - los avisos `limit`/`quota` llevan el id de cuenta en `command` y la etiqueta en el título;
  - la detección de «Cuota agotada» por pantalla se asigna a la cuenta de la ejecución.
  - `schemas/usage.UsageLimits` pasa a ser una lista por cuenta, con `PUT /api/settings/limits` adaptado.
  - **Sin tope global**: «Gasto de hoy» de Inicio muestra el coste del día frente a la suma de los límites de las cuentas de Claude.
- **Sesión caída**:
  - `probe` se ejecuta al arrancar, al abrir `/clis` («Comprobar»), tras el login y, antes de lanzar, si el último probe tiene más de 10 min.
  - Con `down`, el scheduler no lanza tareas de esa cuenta.
  - Se crea un aviso nuevo `InboxKind.ACCOUNT` («Sesión cerrada en {email}»), que se resuelve solo cuando `probe` vuelve a `ok`.
  - **El aviso de cuota ≥ 95 % no es un item de la Inbox**: se deriva en `/api/home` a partir de `quota_view`, igual que los avisos de CLI de la fase 09, así que desaparece al reiniciarse la ventana.
- **Scheduler**: comprueba el bloqueo de la cuenta del agente en lugar del de su CLI.
- **Equipos**:
  - `services/teams.py` con CRUD y `PUT /api/teams/{id}/agents`, que fija los miembros y quita a esos agentes de su equipo anterior;
  - al borrar un equipo, sus agentes quedan sin equipo.
- **API**:
  - `GET/POST /api/accounts`, `PATCH/DELETE /api/accounts/{id}`, `POST /api/accounts/{id}/default`, `POST /api/accounts/{id}/probe`, `WS /ws/accounts/{id}/login`;
  - `GET/POST/PATCH/DELETE /api/teams`;
  - `agents` con `team_id` y `account_id`;
  - `runs` con `account_label`;
  - `usage` con el filtro `account_id` y un desglose por cuenta;
  - `/api/home` con `teams`, las cuentas por CLI (uso de hoy, límite y cuota) y `cli_alerts` derivados.
  - `/api/clis` sigue dando la instalación y la versión de cada CLI.

### Frontend
- **`/clis` · `ClisPage`** (nueva, según el prototipo v7):
  - `CliSection` con tag, versión, estado y «Añadir cuenta» (oculto en agy si solo admite la del sistema, con una nota);
  - `AccountCard` con email, plan y sesión, y `QuotaBars` (barra, %, reinicio relativo y «hace 5 min»);
  - el uso de hoy frente al límite;
  - los agentes y sus sesiones vivas;
  - las acciones «Predeterminada», «Reconectar» y «Quitar» (con confirmación).
  - `AccountLoginDialog` reutiliza `TerminalPanel` sobre el WS de login.
- **Ajustes**:
  - sale `CliSection` y `SECTIONS` queda en cinco;
  - `/ajustes#clis` → `navigate('/clis', {replace})`;
  - `LimitsSection` muestra una fila por cuenta.
- **Inicio**:
  - `AgentGrid` agrupa por equipo (`TeamGroup`), con «Sin equipo» al final y la rejilla única si no hay equipos;
  - `TeamDialog` para crear y editar, con nombre, descripción, agentes y borrado;
  - en `SummaryAside`, las CLIs tienen cuentas desplegables, y la barra muestra la cuota más alta o, en su defecto, el límite diario, con un `title` que dice cuál es;
  - `CliAlertItem` va por cuenta (cuota ≥ 95 %, límite, sesión caída) con «Revisar cuentas» / «Reconectar» y «Posponer».
- **Agentes**:
  - `NewAgentDialog` y `AgentEditorPage` con los selectores Equipo y Cuenta (la cuenta filtrada por el CLI elegido);
  - `ConfigDisclosure` muestra Equipo y Cuenta;
  - las migas de la ficha quedan Inicio › Equipo › Agente;
  - `AgentsPage` muestra la columna Equipo y permite filtrar por ella.
- **Ejecuciones y tareas**:
  - `RunsTable` con la columna Cuenta (12 px, muted);
  - `SessionFactsLine` y `RunPage` con la cuenta.
- **Consumo**: el filtro y el desglose por cuenta.
- **Ctrl+K**: «CLIs y cuentas», «Añadir CLI o cuenta» y «Nuevo equipo».
- **`stores/dialogs`**: `openTeam` y `openAccountLogin`.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0008_accounts_teams.py` | nuevo |
| `backend/src/agentic_os/models/account.py`, `models/team.py` | nuevos |
| `backend/src/agentic_os/models/agent.py`, `run.py`, `inbox.py` | modificados (FKs, `account_label`, `InboxKind.ACCOUNT`) |
| `backend/src/agentic_os/services/accounts.py`, `accounts_login.py`, `teams.py` | nuevos |
| `backend/src/agentic_os/services/adapters/base.py`, `claude.py`, `agy.py` | modificados (entorno de la cuenta, status line de agy si procede) |
| `backend/src/agentic_os/services/hooks.py`, `runs/manager.py`, `runs/resume.py`, `runs/launcher.py` | modificados (cuota, cuenta de la ejecución) |
| `backend/src/agentic_os/services/trust.py`, `usage/paths.py`, `usage/limits.py`, `usage/stats.py`, `housekeeping.py`, `maintenance.py`, `scheduler.py`, `home.py` | modificados |
| `backend/src/agentic_os/api/accounts.py`, `api/teams.py` | nuevos |
| `backend/src/agentic_os/api/agents.py`, `runs.py`, `usage.py`, `settings.py`, `home.py` + `schemas/*` | modificados |
| `backend/tests/fake_cli.py` | `rate_limits`/`quota` en la status line, `auth status` y `auth login` simulados |
| `backend/tests/fixtures/transcripts/claude-2.1.299-statusline-rate-limits.json` (+ agy si se captura) | nuevos |
| `frontend/src/pages/clis/*` | nuevos (`ClisPage`, `AccountCard`, `QuotaBars`, `AccountLoginDialog`) |
| `frontend/src/pages/home/AgentGrid.tsx`, `TeamGroup.tsx`, `TeamDialog.tsx`, `SummaryAside.tsx`, `alerts.ts`, `NeedsYouPanel.tsx` | nuevos / modificados |
| `frontend/src/pages/agents/NewAgentDialog.tsx`, `AgentEditorPage.tsx`, `ConfigDisclosure.tsx`, `AgentsPage.tsx` | modificados |
| `frontend/src/pages/settings/SettingsPage.tsx`, `LimitsSection.tsx`, `CliSection.tsx` (se mueve a `clis/`) | modificados |
| `frontend/src/pages/runs/RunsTable.tsx`, `RunPage.tsx`, `tasks/SessionFactsLine.tsx`, `UsagePage.tsx`, `usage/*` | modificados |
| `frontend/src/api/accounts.ts`, `api/teams.ts`, `api/types.ts`, `routes.tsx`, `components/palette/CommandPalette.tsx`, `stores/dialogs.ts`, `i18n/es.json`, `test/fake-backend.ts` | nuevos / modificados |
| `docs/adr/0014-cli-accounts.md` | nuevo |

## Tareas (en orden)
1. [ ] **Preparación**:
   - rama `phase/10-equipos-cuentas`;
   - investigar y arreglar (o documentar) los 2 tests que fallan en `test_usage_stats.py`.
2. [ ] **Spike** (evidencias en `evidencias/`):
   - **S1 Claude**:
     - login en un PTY con `CLAUDE_CONFIG_DIR` (¿`claude auth login`?) sin tocar `~/.claude`;
     - `auth status` de la cuenta nueva;
     - captura de una status line con `rate_limits` (fixture) y comparación con `/usage`.
   - **S2 agy**:
     - ¿se puede declarar `statusLine` en el plugin de workspace?;
     - captura de `quota` y comparación con `/usage`;
     - ¿hay alguna variable o flag que cambie el destino de credenciales?
   - Con el resultado se ajusta este plan (CA11, CA14) antes de seguir.
3. [ ] **Migración** `0008`, modelos y test de migración sobre una BD v1.1 con agentes, ejecuciones, límites y avisos (CA1).
4. [ ] **Cuentas en el backend**: `services/accounts.py`, la API de cuentas, `probe` y el login por WS con el CLI falso.
5. [ ] **Lanzar con la cuenta**:
   - adapter, launcher, trust, rutas de transcript, reanudación y limpieza;
   - `account_id`/`account_label` en las ejecuciones (CA3, CA6).
6. [ ] **Límites, «Cuota agotada», sesión caída y scheduler por cuenta**, más `PUT /api/settings/limits` (CA4, CA5).
7. [ ] **Cuota**:
   - parseo de la status line, `record_quota`, `quota_view` con caducidad;
   - avisos ≥ 95 % derivados en `/api/home` (CA13–CA15).
8. [ ] **Equipos en el backend**: modelo, servicio, API, agentes con `team_id` y `/api/home` con equipos.
9. [ ] **Consumo por cuenta**: filtro y desglose en `usage/stats.py` y en la API.
10. [ ] **Frontend · cuentas**:
    - `/clis`, `AccountCard`, `QuotaBars` y diálogo de login;
    - redirección de `/ajustes#clis` y Límites por cuenta (CA7).
11. [ ] **Frontend · Inicio**: equipos, `TeamDialog`, `SummaryAside` con cuentas y alertas por cuenta (CA8, CA9, CA15).
12. [ ] **Frontend · agentes, ejecuciones y consumo**:
    - equipo y cuenta en los diálogos, la edición, la ficha y la lista;
    - columna Cuenta;
    - consumo por cuenta (CA6, CA10).
13. [ ] **Ctrl+K e i18n**; repasar los textos.
14. [ ] **ADR 0014** (cuentas de CLI).
15. [ ] **Prueba manual** con dos cuentas reales de Claude (y agy según el spike), con capturas para la validación (CA2, CA3, CA5, CA13, CA14).

## Tests previstos
| Test | Cubre |
|---|---|
| `test_migration_0008`: BD v1.1 → cuentas del sistema, límites movidos, ejecuciones y avisos reasignados | CA1 |
| `test_accounts.py`: CRUD, la del sistema no se borra, predeterminada única, `probe` con `auth status` simulado, carpeta creada/borrada | CA2, CA7 |
| `test_accounts_login.py`: WS de login con el CLI falso, `probe` al terminar | CA2 |
| `test_adapters.py`: `CLAUDE_CONFIG_DIR` según la cuenta; la del sistema conserva el del usuario | CA3 |
| `test_trust.py`, `test_usage_paths.py`, `test_resume.py`: carpeta de la cuenta | CA3 |
| `test_usage_limits.py`, `test_scheduler.py`: bloqueo por cuenta; otra cuenta del mismo CLI sigue | CA4 |
| `test_scheduler.py` + `test_inbox.py`: sesión caída → aviso `account`, no lanza; se resuelve al volver | CA5 |
| `test_hooks.py`: `rate_limits` y `quota` del fixture → ventanas; payload sin ellas → nada | CA13, CA14 |
| `test_accounts.py::quota_view`: ventana pasada su reinicio → reiniciada; `/api/home` con aviso ≥ 95 % | CA13, CA15 |
| `test_teams.py`: CRUD, miembros únicos, borrar deja sin equipo | CA9 |
| `test_usage_stats.py`: filtro y desglose por cuenta | CA6 |
| `clis.test.tsx`: cuentas, cuota, añadir/reconectar/predeterminada/quitar, agy de solo sistema, redirección | CA7, CA11, CA13 |
| `home.test.tsx`: equipos, «Sin equipo», sin equipos → rejilla, aside con cuentas, alertas por cuenta | CA8, CA9, CA15 |
| `new-agent.test.tsx`, `agents.test.tsx`, `agent-summary.test.tsx`: equipo y cuenta | CA10 |
| `runs.test.tsx`, `tasks.test.tsx`, `usage.test.tsx`: columna y filtro de cuenta | CA6 |
| `settings.test.tsx`: cinco secciones, límites por cuenta | CA7 |

## Decisiones (ADR)
- **ADR 0014 · Cuentas de CLI**:
  - una cuenta es una carpeta de configuración del CLI (`CLAUDE_CONFIG_DIR`), y la del sistema usa la del usuario;
  - agy solo tiene la cuenta del sistema mientras guarde el login en el almacén de credenciales con un destino fijo;
  - límites, «Cuota agotada», sesión y scheduler van por cuenta;
  - la cuota de la suscripción se lee de la status line de cada ejecución, se guarda solo el último valor y caduca con su reinicio;
  - no se consulta la cuota sin sesión;
  - no hay tope global de gasto.
- Los equipos son solo organizativos (ver spec, «Fuera»): no necesitan ADR.

## Desarrollo: resultado del spike y desviaciones del plan
Resultado del spike ([evidencias](evidencias/s1-s2-captura.md)):
- **S1 Claude**: la cuota llega en `rate_limits` y coincide con `/usage`; `CLAUDE_CONFIG_DIR` aísla el login sin tocar `~/.claude`. El login completo en una carpeta aislada necesita una segunda cuenta real y queda para la prueba manual.
- **S2 agy**: la cuota llega en `quota` y coincide con `/usage`, pero la status line **solo se lee del `settings.json` global**; el login vive en el almacén de credenciales del sistema, así que **agy tiene una sola cuenta** (CA11, rama «no»).
- **S3 agy**: la lectura de su cuota es una opción activable y reversible, comprobada de punta a punta con el agy real.

Desviaciones:
- La **cuota de agy** es un interruptor explícito en «CLIs y cuentas» (el plan dejaba la decisión abierta), con un script que no hace nada fuera de la app. Ver ADR 0014.
- Los **avisos de cuota ≥ 95 %** se derivan en el cliente (como los avisos de CLI de la fase 09), no en `/api/home`: `/api/home` solo añade `team_id` y `account_id` a cada agente. El de **sesión caída** sí es una petición de la Inbox (`account`).
- `services/teams.py` no existe: la lógica de equipos vive en `api/teams.py` (no hay reglas de negocio que compartir).
- El login corre en un PTY propio (`services/accounts_login.py`, `LoginSession`) con el mismo protocolo de WebSocket que el terminal de una ejecución, extraído a `api/terminal.py`.
- El diálogo de login arranca el login al abrirse (`POST /accounts/{id}/login`) y no antes; `?reconectar=<cuenta>` y `?nueva=1` abren los diálogos desde la URL.
- No hizo falta tocar `resume.py`, `maintenance.py` ni `housekeeping.py`: la reanudación elige la cuenta en `RunManager._account_for` y la limpieza de confianza se amplió en `TrustCleaner`.
- Los dos tests que fallaban en `test_usage_stats.py` no eran del código: fijaban `DAY = 2026-10-12` pero los avisos llevan la hora real.
- Dos defectos encontrados por los tests y corregidos: el `PATCH` de un agente validaba equipo/cuenta después de asignarlos (un id erróneo daba un error de clave foránea en vez de 422) y los selectores de equipo y cuenta propagaban el valor vacío que Radix emite al montar.
