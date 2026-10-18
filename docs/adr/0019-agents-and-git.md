# ADR 0019: Agentes y git

- **Estado**: aceptado
- **Fecha**: 2026-10-18
- **Contexto de decisión**: fase 12 ([`spec.md`](../phases/12-control-git/spec.md), [`plan.md`](../phases/12-control-git/plan.md))

## Contexto
Los agentes ya commiteaban en la rama de su tarea, pero cada CLI preguntaba por cada comando de git y la app no sabía qué había hecho el agente con el repositorio. La fase pide dos cosas: que los agentes usen git **sin restricciones ni preguntas de permiso**, y que **cada ejecución registre lo que hizo** y se pueda deshacer.

## Decisión

### Autorización (`Project.agents_git_authorized`, por defecto sí)
- **Claude Code**: `Bash(git:*)` y `PowerShell(git *)` se añaden a `--allowedTools` en todos los modos (en `autonomous` ya está todo permitido). Hacen falta **las dos reglas**: Claude usa una u otra, y con solo la de Bash `git add -A` quedó bloqueado en una ejecución (spike S2). Funcionan también con `git -C` y con `cd … && git …`.
- **agy**: en una sesión interactiva no preguntó por ningún comando de git (tampoco `push` ni `push --force`, spike S1), así que no se añade nada y la app **no toca** su configuración global. Plan B, solo si en otra máquina agy preguntara: el hook `PreToolUse` del plugin respondería `{"decision":"allow"}` a las líneas que empiezan por `git` (contrato documentado por agy). No se implementa.
- **Repos vinculados** fuera de la carpeta de la ejecución: `--add-dir` en los dos CLIs. Sin él, Claude no puede escribir allí aunque git esté permitido.
- El contexto del agente lo dice con una sección «Git»: puede usar git libremente, que commitee en su rama de trabajo y que la app registra lo que hace.
- Sin `agents_git_authorized`, todo queda como antes.

### Qué hizo cada ejecución (`services/gitx/activity.py`)
- **Al empezar**, por repo, se guarda en `RunRepo.refs_start`: todas las ramas, tags y ramas remotas con su commit, dónde está `HEAD` y **cuántas entradas tiene el reflog de `HEAD`** de esa carpeta.
- **Al terminar**, en `_close_changes` y con la misma carpeta:
  - **commits**: las entradas nuevas del reflog (`commit`, `commit (amend)`, `commit (merge)`, `rebase`, `cherry-pick`, `merge`). Se **cuentan**, no se miden con el reloj: una ventana de tiempo colaba commits anteriores que cayeran dentro (lo destapó un test). La hora solo sirve de respaldo si el registro no trae el contador. Un worktree tiene su propio reflog de `HEAD`, así que no se cuentan los commits de otras tareas en otras carpetas del mismo repo;
  - **ramas y tags**: la diferencia con `refs_start`. Una rama movida o creada solo cuenta si apunta a un commit de la ejecución, es la rama de su carpeta o nació en su `HEAD`; así no se atribuye lo que otra tarea movió a la vez. Los tags son globales y se cuentan todos;
  - **pushes**: las ramas remotas que pasaron a apuntar a un commit de la ejecución (o a un descendiente de alguno). Un push actualiza la copia local del remoto, así que no hace falta preguntar al servidor. **Forzado** si el valor anterior ya no es ancestro del nuevo.
- Se guarda en `RunRepo.activity`, y cada commit en **`CommitAttribution`** (`repo_id`, `sha`, `run_id`, `task_id`, `agent_id`, copias del nombre del agente y del código de la tarea; único por `(repo_id, sha)`). Una copia, para que el historial siga diciendo quién lo hizo aunque el agente o la tarea se borren.
- El historial, el detalle del commit y el *blame* cruzan esa tabla y muestran el agente. La tarea gana el evento `git` (una línea por ejecución que hizo algo). Si la carpeta ya no existe al terminar, no se registra nada y no falla la ejecución.

### Deshacer lo que hizo la ejecución
- Por repo, devuelve las **ramas locales** que movió a su valor de `refs_start` y borra las que creó. Si la rama está abierta en una carpeta, se hace `reset --keep` allí para que los ficheros la sigan; una rama creada que está abierta en una carpeta se deja.
- **Lo subido al remoto no se toca**, y el diálogo lo dice. Una rama que se haya movido después de la ejecución **no se toca** y se informa (`moved_since`): deshacer nunca pisa trabajo posterior.
- Exige `confirm: true`. Se registra como un `GitOperation` (`undo_run`), de modo que el «Deshacer» de la pestaña Git también puede deshacerlo.

## Consecuencias
- Un agente en modo `manual` puede hacer rebase y push sin que nada lo pare, y su ejecución lo registra: es la prueba de aceptación de la fase.
- El registro depende de las instantáneas: una ejecución cuyo diff no pudo tomarse no registra su actividad de git.
- No se atribuyen los commits anteriores a la fase ni los hechos fuera de una ejecución; el historial los muestra sin agente.
- Es un registro de lo **observable** en el repo, no de la conversación del agente: un `git commit --amend` cuenta como `amend`, no como el commit original deshecho.
