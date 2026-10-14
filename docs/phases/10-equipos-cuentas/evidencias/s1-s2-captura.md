# S1 · S2 · Spike de cuentas y cuota

Fecha: 2026-10-14 · Claude Code 2.1.299 · agy 1.3.5 · Windows 11
Herramientas: `spikes/quota_probe.py` (lanza el CLI en un PTY con una status line que vuelca su JSON) y `spikes/dump_stdin.py`.

## S1 · Claude Code

### Cuota (`rate_limits`) ✅
- Una sesión real (suscripción Pro) recibe en la status line `rate_limits.five_hour` y `rate_limits.seven_day`, cada uno con `used_percentage` y `resets_at` (epoch en segundos). El payload completo, anonimizado, está en `backend/tests/fixtures/transcripts/claude-2.1.299-statusline-rate-limits.json`.
- **Coincide con `/usage`** ([pantalla](claude-usage-screen.txt)):

| Ventana | Status line | `/usage` |
|---|---|---|
| Sesión (5 h) | 11 % · `resets_at` = 20:40 Madrid | 11 % · «Resets 8:40pm» |
| Semanal | 75 % · reinicia sáb 17 oct, 17:00 | 76 % · «Resets Oct 17, 5pm» |

  El 1 % de diferencia en la semanal es la petición posterior a la última status line (el payload se captura antes de que `/usage` consulte).
- El payload trae `rate_limits` ya en la primera respuesta de la sesión (hubo 3 payloads en la prueba). Sin suscripción Pro/Max no aparece (documentado).
- Los campos de siempre (`cost.total_cost_usd`, `session_id`, `transcript_path`, `version`) siguen ahí: la cuota va en el mismo payload que ya leemos.

### Aislamiento por carpeta ✅
- `CLAUDE_CONFIG_DIR=<carpeta vacía>` → `claude auth status` devuelve `loggedIn: false`, `configDirectory` y `projectsDirectory` de esa carpeta, y crea ahí `.claude.json`. **No toca `~/.claude`**.
- `claude auth status` sale con **código 1 cuando no hay sesión**: `probe` debe leer el JSON y no fiarse del código de salida.
- Login: `claude auth login [--claudeai | --console] [--email <email>] [--sso]`. Con `--claudeai` y `--email` precargado es el flujo de «Añadir cuenta».
- Pendiente de la prueba manual (CA2): completar un login real en una carpeta aislada, que exige una segunda cuenta.

## S2 · agy

### Cuota (`quota`) ✅
- Con la status line configurada, el payload trae `quota` con **cuatro buckets**: `gemini-5h`, `gemini-weekly`, `3p-5h` y `3p-weekly` («3p» = los modelos de terceros: Claude, GPT-OSS). Cada uno con `remaining_fraction`, `reset_time` (ISO UTC) y `reset_in_seconds`. Fixture en `agy-1.3.5-statusline-quota.json`.
- También trae `email`, `plan_tier` («Google AI Pro»), `version`, `conversation_id`, `transcript_path` y `agent_state`.
- **Coincide con `/usage`** ([pantalla](agy-usage-screen.txt)):

| Bucket | Status line | `/usage` |
|---|---|---|
| Gemini · 5 h | 0,982825 · reinicia 16:46:59Z | 98,28 % restante · «Refreshes in 1h 20m» |
| Gemini · semanal | 0,9756125 · reinicia 16 oct | 97,56 % restante · «Refreshes in 50h 0m» |
| Claude y GPT · 5 h y semanal | 1 | 100 % · «Quota available» |

- **Se actualiza durante la sesión**: 19 payloads en una sesión corta; `gemini-5h` pasó de 0,9831207 a 0,982825. Los `reset_in_seconds` bajan solos. La queja del foro sobre un dato congelado no se reproduce en 1.3.5.
- Hay que tratar `remaining_fraction` como «restante» y mostrar `1 − x` como usado.

### Dónde se configura la status line ⚠️
| Dónde | ¿Funciona? |
|---|---|
| `<proyecto>/.agents/settings.json` | ❌ no se ejecuta |
| `statusLine` en el `plugin.json` del plugin de workspace | ❌ no se ejecuta |
| `~/.gemini/antigravity-cli/settings.json` (global) | ✅ |

→ Con el mecanismo de plugin de la fase 04 **no se puede inyectar por ejecución**. Hay que tocar el `settings.json` global, que ya escribe Agentic OS para la confianza en carpetas (ADR 0004). Se hizo la prueba con copia y restauración byte a byte (hash idéntico).

### Aislar el login ❌
- Variables de entorno encontradas en el binario (`ANTIGRAVITY_APP_DATA_DIR`, `JETSKI_APP_DATA_DIR`, `AGY_ACCOUNT`): ninguna cambia nada; `agy models` sigue con la sesión y no escribe en la carpeta.
- Con `USERPROFILE` y `HOME` apuntando a otra carpeta, agy **sigue con login** y crea ahí su propia carpeta `.gemini`. El login vive en el **Administrador de credenciales de Windows** (`gemini:antigravity`), que es por usuario del sistema, no por carpeta.
- Mover `USERPROFILE` además rompería `git`, `ssh`, `npm` y demás herramientas que usen los agentes.

→ **agy tendrá una sola cuenta, la del sistema** (rama «no» de CA11). Se descarta cambiar `USERPROFILE`.

## Conclusiones para el plan
1. **Claude**: varias cuentas por `CLAUDE_CONFIG_DIR` y cuota por la status line que ya inyectamos. Sin cambios de diseño.
2. **agy**: una cuenta (la del sistema). Su cuota solo llega si hay una status line en el `settings.json` global. Se necesita una decisión: ver la sección siguiente del plan.
3. Los buckets de agy se muestran como «Gemini · 5 h», «Gemini · semanal», «Claude y GPT · 5 h» y «Claude y GPT · semanal», igual que `/usage`.
4. `probe` de Claude lee el JSON de `auth status` aunque el código de salida sea 1.
