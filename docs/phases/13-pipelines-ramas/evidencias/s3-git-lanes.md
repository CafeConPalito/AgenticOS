# Ramas de las vías en git (S3)

- OK · `agentic/T-1/backend` junto a `agentic/T-1` (se espera que falle) · rc=128 · `fatal: cannot lock ref 'refs/heads/agentic/T-1/backend': 'refs/heads/agentic/T-1' exists; cannot create 'refs/heads/agentic/T-1/backend'`
- OK · worktree de la vía backend con la tarea activa en su carpeta · rc=0 · `Preparing worktree (new branch 'agentic/T-1-backend')`
- OK · worktree de la vía frontend con la tarea activa en su carpeta · rc=0 · `Preparing worktree (new branch 'agentic/T-1-frontend')`
- OK · unión 1: fast-forward de la primera vía en la rama de la tarea · rc=0 · `Updating 6f9ee1d..d97500d
Fast-forward
 api.py | 1 +
 1 file changed, 1 insertion(+)
 create mode 100644 api.py`
- OK · unión 2: merge --no-ff de la segunda vía · rc=0 · `Merge made by the 'ort' strategy.
 ui.tsx | 1 +
 1 file changed, 1 insertion(+)
 create mode 100644 ui.tsx`
- OK · la rama de la tarea contiene el trabajo de las dos vías · ['.git', 'api.py', 'base.txt', 'req.txt', 'ui.tsx']
- OK · conflicto al unir vías que tocan el mismo fichero · rc=1 · `Auto-merging shared.txt
CONFLICT (content): Merge conflict in shared.txt
Automatic merge failed; fix conflicts and then commit the result.`
- OK · `merge --abort` deja el worktree de la tarea limpio · rc=0 · ``
- OK · reabrir una vía sin worktree: `branch -f` al extremo de la tarea · rc=0 · ``
- OK · reabrir una vía con worktree vivo: `merge --ff-only` desde la tarea · rc=0 · `Updating a0356c7..aa06323
Fast-forward
 qa.txt | 1 +
 1 file changed, 1 insertion(+)
 create mode 100644 qa.txt`
- OK · la vía reabierta no tiene commits propios sobre la tarea · adelantada 0

Ramas creadas: `['agentic/T-1', 'agentic/T-1-backend', 'agentic/T-1-frontend', 'agentic/T-2', 'agentic/T-2-a', 'agentic/T-2-b']`

Repo de la prueba: `C:\Users\usuario\AppData\Local\Temp\agentic-lanes-7fxgwiwu` (se puede borrar).
