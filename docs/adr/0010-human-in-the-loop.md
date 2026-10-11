# ADR 0010: Human-in-the-loop y subagentes

- **Estado**: borrador (se completa durante la fase 06)
- **Fecha**: 2026-10-11
- **Contexto de decisión**: fase 06 ([`spec.md`](../phases/06-subagentes-hitl/spec.md), [`plan.md`](../phases/06-subagentes-hitl/plan.md))

## Contexto
Los agentes tienen que poder pedir cosas a la persona (aprobaciones, preguntas, bloqueos) sin que esta vigile su terminal, y repartir trabajo en subagentes. Las decisiones dependen de cómo se comportan Claude Code y agy de verdad: la tarea 1 de la fase los capturó con Claude Code 2.1.296 y agy 1.3.3 (pantallas en `backend/tests/fixtures/screens`, cargas de hooks en `backend/tests/fixtures/hooks`).

## Decisión
### Diálogos de permiso de los CLIs
- **Claude Code** («Do you want to proceed?», «Do you want to create nota.txt?»):
  - opciones «1. Yes» (seleccionada), «2. Yes, and…», «3. No»;
  - pie «Esc to cancel · Tab to amend».
- **agy**: «Requesting permission for: <comando> / Run this command? / > 1. Yes, run command … 4. No, cancel / ↑/↓ Navigate · tab Amend · esc to cancel».
- **Teclas**, verificadas con los CLIs reales: **Enter aprueba** (la opción 1 viene seleccionada) y **Esc rechaza**.
  - Claude con Enter: crea el archivo y sigue.
  - agy con Esc: cancela el comando y vuelve a su entrada.
- **La pantalla emulada (pyte) descoloca parte del texto de Claude** (glifos anchos): «Tab to amend» aparece a veces como «Tab t  amend» y se pierden nombres de archivo. Por eso:
  - el diálogo de Claude se detecta por fragmentos cortos y estables al pie (`amend`, «1. Yes», «No»);
  - **el detalle se toma del hook `PermissionRequest` de Claude** (`tool_name` + `tool_input`: «Write: …\nota.txt»), no de la pantalla;
  - en agy, el comando se lee de la pantalla (la línea tras «Requesting permission for:»), que llega entera.
- Un diálogo cuenta cuando está **0,5 s** en pantalla, y se da por respondido cuando falta **1,5 s** (las TUI redibujan).
- **«Tomar control» ya no envía Esc si hay un diálogo de permiso**: Esc lo rechazaría.
- Comandos de solo lectura (`git --version`, `Get-ChildItem | Measure-Object`) no piden permiso en Claude.

### Hooks de los subagentes nativos
- **Claude**:
  - `PreToolUse` y `PostToolUse` con `matcher: "Agent|Task"` traen `tool_name: Agent` y `tool_input` con `description` y `prompt`. `PostToolUse` vuelve enseguida (`async_launched`);
  - `SubagentStart` y `SubagentStop` llevan `agent_id` y `agent_type`;
  - Claude también envía **`SubagentStop` de subagentes internos** (`agent_type` vacío, sin `SubagentStart` previo): solo cuentan los que tuvieron inicio.
- **agy**:
  - los eventos de herramienta en `hooks.json` **necesitan otro formato**: `{"matcher": "invoke_subagent", "hooks": [{"type": "command", …}]}`. Con la forma plana de `PreInvocation`/`Stop`, agy no los envía;
  - `PreToolUse` y `PostToolUse` de `invoke_subagent` traen `Subagents[]` con `Role`, `Prompt`, `TypeName` y un `toolSummary`. `PostToolUse` vuelve enseguida;
  - **el subagente tiene su propia conversación** y dispara `PreInvocation` con su `conversationId` por el mismo plugin, pero **nunca envía su `Stop`**. La conversación principal termina su turno con `fullyIdle: false` mientras el subagente sigue;
  - **corregido**: esos hooks no sustituyen el id de sesión de la ejecución ni marcan sus turnos (antes, el `conversationId` del subagente sobrescribía el de la ejecución).

*(Pendiente de completar durante la fase: `request_human` y `deliver`, la Inbox, las notificaciones y los subagentes de Agentic OS.)*

## Consecuencias
- ✅ Los diálogos de permiso se detectan y se responden sin que la persona tome el control.
- ⚠️ La detección depende de textos de las TUI. Están centralizados en `screen.py` y cubiertos por tests con las pantallas reales.
- ⚠️ El fin de un subagente nativo de agy no se conoce con exactitud: se deduce de su última actividad.
