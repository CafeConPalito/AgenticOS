# agy · hook PreToolUse que aprueba git (fase 12)

```
DENIED  hook-git-commit · rc=0 · out='jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under permissions.all'
         hook saw: ['{"name": "run_command", "line": "git commit --allow-empty -m probe-commit"}']
DENIED  hook-non-git-write · rc=0 · out='jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under permissions.all'
         hook saw: ['{"name": "run_command", "line": "echo hi > not-git.txt"}']
DENIED  hook-git-dash-C · rc=0 · out='jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under permissions.all'
         hook saw: ['{"name": "run_command", "line": "git -C . commit --allow-empty -m probe-commit"}']
DENIED  hook-git-chained · rc=0 · out='jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under permissions.all'
         hook saw: ['{"name": "run_command", "line": "cd . && git commit --allow-empty -m probe-commit"}']
```
