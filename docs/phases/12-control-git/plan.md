# Fase 12: Control de git · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-17) · desarrollo sin empezar

## Lo que ya se sabe (revisado al escribir el plan)
- **git 2.55** en el equipo. Trae dos piezas que simplifican mucho la integración:
  - `git merge-tree --write-tree` hace un merge **sin carpeta de trabajo** y dice si hay conflictos;
  - `git replay` hace un rebase sin carpeta de trabajo (sigue marcado como experimental).
- **git-lfs 3.7** instalado. **`gh` y `glab` no** están instalados.
- **agy 1.3.6** tiene `--add-dir` (repetible). No tiene una lista de comandos permitidos por sesión: en el spike de la fase 01 no se consiguió preaprobar herramientas por ejecución. Solo hay modos generales: `--mode accept-edits|auto|plan` y `--dangerously-skip-permissions`.
- **Claude Code 2.1** tiene `--add-dir`. La herramienta `git` de los agentes (fase 02) ya se traduce a `Bash(git:*)` y `PowerShell(git *)`, pero solo en el modo `restricted`. En `manual` no se aplica ninguna lista.
- **Ciclo de una ejecución** (`RunManager`):
  - instantánea inicial en `_launch`, después de `adapter.prepare`;
  - instantánea final en `_on_end`, a través de `_close_changes`, **antes** de `on_run_ended` (el scheduler mueve la tarea y suelta el worktree);
  - las ejecuciones interrumpidas cierran sus cambios en `recover()`.
  
  Todo con una sola carpeta (`run.cwd`) y un solo repo.
- **Worktrees** (`services/worktrees.py`): uno por tarea y por proyecto. `prepare` devuelve la carpeta y `release` commitea lo suelto y la borra. `Task.worktree_path`, `Task.branch` y `Task.base_commit` son de un solo repo.
- **Las referencias son por repositorio**: `refs/agentic-os/runs/<id>/start` puede existir con el mismo nombre en cada repo de un proyecto. No hace falta renombrarlas para tener varios repos.
- **Un repo anidado sin registrar** dentro de otro: `git add -A` lo añade como *gitlink*, y la instantánea del repo padre lo trataría como un submódulo. Hay que excluir sus rutas.
- **Terminales**: el protocolo `TerminalSession` (`api/terminal.py`) ya lo usan dos sesiones, `RunSession` y `LoginSession`. Una «terminal git» es una tercera sesión con el mismo protocolo.
- **Refresco en la UI**: hoy se hace por sondeo (`refetchInterval`); no hay un canal de eventos global.
- **Credenciales**: Git Credential Manager guarda un token OAuth para `github.com` y `gitlab.com`. `git credential fill` lo devuelve y sirve para su API REST. `httpx` ya es dependencia del backend.

## Resultados de los spikes (bloque 0, 2026-10-17)
Scripts en `spikes/` (`git_probe.py`, `git_perf_probe.py`, `scenarios/git_permissions.py`, `agy_git_hook.py`, `agy_git_hook_pty.py`, `agy_add_dir.py`) y evidencias en `evidencias/`.

**S1 · agy 1.4.0**
- **Sesión interactiva (PTY, modo por defecto)**: `git commit`, `git push` y `git push --force` a un remoto *bare* se ejecutan **sin ningún diálogo**, con y sin hook. También `git -C <otra carpeta> commit`. Con este agy y esta configuración, el modo `manual` no pregunta por git.
- **Modo headless (`-p`)** deniega todo comando, también con reglas en `.agents/settings.json` y con el hook. No es el modo de la app (todo va por PTY), así que no cuenta.
- **Hook `PreToolUse`**: agy documenta la respuesta `{"decision": "allow" | "deny" | "ask" | "force_ask", "reason", "permissionOverrides"}`. El hook recibe `toolCall.name == "run_command"` y `toolCall.args.CommandLine` con la línea completa (`git -C . commit …`, `cd . && git …`). Queda como **plan B** si en otra máquina agy pregunta por git: `hook.cmd` imprimiría la respuesta del backend en vez de descartarla. No se implementa ahora.
- **Reglas de permisos de agy**: `command(<prefijo>)`, p. ej. `command(git commit)`, sin comodines. Viven en `~/.gemini/antigravity-cli/settings.json` (global); no se ha encontrado un fichero de proyecto que se aplique. La app **no toca** la configuración global.
- **`--add-dir <carpeta>`** existe y se usa para los repos vinculados; agy actuó en el repo de fuera con y sin él.

**S2 · Claude Code 2.1.302** (modo `-p`, donde lo no permitido se deniega)
- Sin reglas, `git commit` se deniega. Con `--allowedTools "Bash(git:*)"` se permite, también `git -C . commit` y `cd . && git commit`.
- Hay que pasar **las dos reglas, `Bash(git:*)` y `PowerShell(git *)`**: Claude usa una u otra, y con solo la de Bash `git add -A` quedó bloqueado en una ejecución.
- **`--add-dir` es imprescindible** para que Claude escriba en un repo vinculado fuera de su carpeta (sin él, la herramienta de escritura se rechaza). Con `--add-dir` y las dos reglas, `git -C <otro repo> commit` funciona en `default` y en `acceptEdits`.

**S3 · git 2.55 sin terminal (Windows)**
- `git merge-tree --write-tree <a> <b>`: imprime el árbol resultante (código 0) o, con conflictos, código 1, el árbol y los ficheros (`--name-only`). `commit-tree` + `update-ref <ref> <nuevo> <viejo>` completa el merge sin carpeta de trabajo.
- `git replay --onto <base> <base>..<rama>` **actualiza la rama por defecto** (`--ref-action=update`); con `--ref-action=print` solo imprime `update <ref> <nuevo> <viejo>`. No existe `--update-refs`. Sigue marcado experimental: se comprueba al arrancar y, si falla, se usa el worktree temporal.
- **Rebase interactivo**: `GIT_SEQUENCE_EDITOR` debe ser un **script `sh` con ruta POSIX** (git lo lanza con su propio `sh`); un `.cmd` no funciona. Probados: reordenar, `fixup`, `exec git commit --amend -m …` para `reword` y `edit` (el rebase se para; `reset HEAD^` y `rebase --continue` funcionan).
- **Sin terminal**: con `GIT_TERMINAL_PROMPT=0` un fetch https sin credenciales falla en 0,3 s (`terminal prompts disabled`); `ssh` con `BatchMode=yes` no se queda esperando. `git credential fill` para `github.com` **devuelve un token guardado** (Git Credential Manager) → los pull requests por API son viables.

**S4 · rendimiento** (repos sintéticos)
- `git status --porcelain=v2` de 20 repos de 300 ficheros: 625 ms en serie, **109 ms en 8 hilos**.
- Repo de 50 000 commits: `git log --topo-order -n 200` cuesta ~156 ms **sea cual sea la página** (`--skip` hasta 49 800); `log -S` 375 ms; `blame` 266 ms.
- Consecuencia: el historial se pagina con **`--skip` y `-n 200` sobre el mismo conjunto de referencias**, no con un cursor por sha (un cursor solo ve los ancestros de ese commit y perdería los de otras ramas en el grafo).

### Cambios al diseño por los spikes
- §2 Integración: `git replay` se llama sin `--update-refs`; con `--ref-action=print` primero, para registrar el respaldo antes de mover nada.
- §2 Rebase interactivo: el script del editor es un `.sh` en la carpeta de datos, con ruta POSIX.
- §2 Historial: paginación por `--skip`.
- §6 Autorización: Claude lleva las dos reglas; agy no necesita nada en este equipo (el hook queda como plan B).
- Repos vinculados: `--add-dir` en Claude y en agy.

## Diseño

### 1. Proyectos con varios repos ([ADR 0016](../../adr/0016-multi-repo-projects.md))

**Modelo** (`models/repo.py`, nuevo)
- **`ProjectRepo`**:
  - `project_id`, `path` (absoluta, normalizada) y `path_key`;
  - `rel_path`: relativa a la carpeta del proyecto; nula en un repo vinculado;
  - `name`, `base_branch`, `participates` (bool), `linked` (bool), `position`;
  - `pull_mode` (`ff_only` · `merge` · `rebase`), con `ff_only` por defecto.
  
  Unicidad: `(project_id, path_key)`.
- **`Project`** gana:
  - `integration_mode` (`merge` · `squash` · `rebase`);
  - `on_approve` (`none` · `integrate` · `integrate_push` · `pull_request`);
  - `agents_git_authorized` (bool, por defecto `true`);
  - `repo_scan_depth` (int, por defecto 3).
  
  `base_branch` pasa a cada repo y desaparece del proyecto.

**Detección** (`services/repos.py`, nuevo)
- `scan(project)`:
  - recorre la carpeta hasta `repo_scan_depth`;
  - salta `node_modules`, `.venv`, `venv`, `dist`, `build`, `target`, `.git` y las carpetas ignoradas por el repo que las contiene (`git check-ignore`);
  - un `.git` (carpeta o fichero) marca un repo;
  - los submódulos (`git submodule status` del padre) no se añaden como repos.
- `sync(db, project)`:
  - añade los repos nuevos con su base: su rama actual o, si existe, `main`/`master`;
  - marca `missing` los que ya no existen, sin borrarlos: el usuario los quita a mano;
  - nunca toca los vinculados.
  
  Se llama al crear el proyecto, al pulsar «Volver a buscar» y al cambiar su carpeta.
- `nested_paths(repo)`: los repos de la lista que están dentro de otro. Se excluyen en sus instantáneas con `:(exclude)`.

**Worktrees de tarea** (`services/worktrees.py`, reescrito)
- **`TaskRepo`** (nuevo): `task_id`, `repo_id`, `branch`, `worktree_path`, `base_commit`, `integrated_at` e `integrated_sha`.
- `Task.worktree_path` pasa a ser la **carpeta de trabajo** de la tarea; `Task.branch` se queda como el nombre común (`agentic/T-142`).
- `prepare`:
  - en `<proyecto>.wt\T-142` crea un worktree por cada repo que participa:
    - en su `rel_path` (el repo raíz, en la propia carpeta);
    - los vinculados, en `@<name>`;
    - cada uno con su rama desde **su** base;
  - si el repo tiene `.gitmodules`, después `git submodule update --init --recursive`;
  - si un repo falla, se deshacen los worktrees ya creados y la tarea pasa a `workspace_failed`, como hoy.
- `release`: por cada repo, commit de lo que quede suelto y `worktree remove`. Las ramas **sin commits frente a su base** se borran; el resto se conserva.
- Los ficheros sueltos de la raíz (cuando la raíz no es un repo) no están en la carpeta de la tarea. Las instrucciones dan la ruta del proyecto original para leerlos.

**Ejecuciones con varios repos**
- **`RunRepo`** (nuevo) sustituye a `runs.snapshot_*`. Campos:
  - `run_id`, `repo_id` y `path` (dónde estaba ese repo en esa ejecución);
  - `snapshot_start`, `snapshot_end` y `snapshot_skipped`;
  - `files`, `added` y `deleted`;
  - `refs_start` (JSON) y `activity` (JSON, ver §6).
  
  `runs.changes_*` se queda como la suma de todos los repos.
- **Los repos de una ejecución**:
  - en worktree, los de su `TaskRepo`;
  - en carpeta directa o en una ejecución manual, los repos del proyecto.
- `RunManager` toma la instantánea de cada repo, en paralelo, con un tiempo máximo común de 30 s.
- Los repos vinculados que quedan fuera de `cwd` se pasan a los adapters como `extra_dirs`: Claude Code los recibe con `--add-dir` y agy también con `--add-dir`.

**Diffs (fase 11) por repo**
- `services/changes.py`:
  - `Range` pasa a ser por repo;
  - `summary` devuelve `repos[]`, cada uno con `files[]` y sus totales, más los totales generales;
  - `file_diff` y `file_lines` reciben `repo_id`.
- El visor agrupa los ficheros por repo. Con un solo repo, se ve igual que ahora.

**Contexto del agente** (`services/context.py`)
- Nueva sección «Repositorios», con una línea por repo: nombre, ruta en la carpeta de trabajo, rama de trabajo y base.
- Si `agents_git_authorized`, se añade: «Puedes usar git libremente (commit, ramas, merge, rebase, push…). Commitea en tu rama de trabajo de cada repo».

### 2. Operaciones de git de la app ([ADR 0017](../../adr/0017-git-operations.md))

**Ejecución** (`services/gitx/`, nuevo paquete)
- `runner.py`:
  - todas las llamadas de escritura pasan por un **candado por repo** (por su `git-common-dir`, que comparten los worktrees de un mismo repo);
  - entorno fijo:
    - `GIT_TERMINAL_PROMPT=0`;
    - `GIT_SSH_COMMAND="ssh -o BatchMode=yes"`, para que una clave con frase de paso sin agente falle con un error en vez de esperar;
    - `GCM_INTERACTIVE=auto`, para que Git Credential Manager pueda abrir su ventana;
    - `core.editor=true` y `LC_ALL=C`, para leer la salida en inglés.
- `jobs.py`: las operaciones largas (`clone`, `fetch`, `pull`, `push`, `gc`, `lfs pull` y `submodule update`) son **trabajos**:
  - `Popen` con `--progress`, cuyo stderr se lee línea a línea («Receiving objects: 45% (…)») y se convierte en `{fase, porcentaje}`;
  - «Cancelar» mata el proceso y sus hijos (el Job Object de la fase 03);
  - estados `running` · `succeeded` · `failed` · `cancelled`, con un mensaje de error legible;
  - viven en memoria; los terminados se guardan 10 minutos.
- `errors.py`: traduce los fallos típicos a códigos estables, para la UI y la i18n:
  - `auth_failed`, `network`, `non_fast_forward`, `rejected` (*hook* remoto o rama protegida), `conflicts`;
  - `dirty_worktree`, `operation_in_progress`, `branch_checked_out`, `lfs_missing` y `unknown`, que lleva el último renglón de git.

**Eventos en vivo** (`api/git_events.py`)
- Un WebSocket `/api/git/events` empuja:
  - `job` (progreso y fin de los trabajos);
  - `repo_changed` (`repo_id`), después de cada operación de la app, al terminar una ejecución que tocó ese repo y al cerrar una terminal git.
- La UI invalida las consultas de ese repo. Además, el estado se vuelve a pedir al volver a la pestaña, y cada 15 s mientras está visible: cubre lo que haga un agente con una ejecución en curso.

**Lectura** (`services/gitx/read.py`)
- **Estado**: `git status --porcelain=v2 -z --branch --show-stash`. Da la rama, el *upstream*, ahead/behind, los ficheros (preparados, sin preparar, nuevos y en conflicto) y si hay una operación a medias, que se detecta por `MERGE_HEAD`, `rebase-merge/`, `CHERRY_PICK_HEAD`, `REVERT_HEAD` o `BISECT_LOG`. Último fetch: la fecha de `FETCH_HEAD`.
- **Vista general**: el estado de todos los repos en paralelo (hilos, como mucho 8), con caché de 3 s por repo.
- **Historial**:
  - `git log --topo-order -z --format=…` con `%H %P %an %ae %at %s %D`, paginado por cursor: los 200 siguientes después de un sha;
  - sin `refs/agentic-os/*` (`--exclude=refs/agentic-os/* --branches --tags --remotes` cuando se piden todas las ramas);
  - filtros: `--author`, `--grep`, `-S` y `-- <ruta>`;
  - el grafo (las «vías») se calcula **en el cliente**, de forma incremental según llegan las páginas: solo necesita los padres de cada commit, en orden topológico.
- **Blame**: `git blame --porcelain` → grupos de líneas con su commit, al que se añade la atribución (§6).
- **Ramas**: `git for-each-ref` con `%(refname) %(objectname) %(upstream) %(upstream:track) %(committerdate)`, más ahead/behind frente a la base (`rev-list --left-right --count`). En las `agentic/T-n` se cruza con `TaskRepo` para sacar la tarea y su estado; «integrada» = `merge-base --is-ancestor`.
- **Diff de un commit, entre dos referencias y de los cambios sin commitear**: con las funciones de `changes.py` (`Range` con dos shas cualesquiera, o el índice y la carpeta).

**Escritura** (`services/gitx/write.py`). Cada función es una operación con su respaldo (ver «Respaldos y deshacer»).
- **Preparar y descartar por fichero, bloque y línea**:
  - por fichero: `git add` y `git restore --staged`;
  - por bloque y por línea: la UI manda el fichero, los bloques y las líneas elegidas; el backend construye el parche a partir del diff actual (no del que tenía la UI) y lo aplica con `git apply --cached` (preparar), `git apply --cached -R` (quitar) o `git apply -R` (descartar);
  - si el diff cambió entre medias, `409 stale_diff`.
- **Commit**: mensaje, `--amend`, `--no-verify` (con confirmación) y la firma, que sale de la configuración del repo. Si un *hook* falla, se devuelve su salida.
- **Ramas**: crear, cambiar (`switch`; si hay cambios que chocan → `dirty_worktree`, sin forzar), renombrar, borrar (`-d`; `-D` con confirmación si no está integrada), fijar su remoto y borrar varias.
- **Merge** (`--ff`, `--no-ff`, `--squash`), **cherry-pick**, **revert** y **reset** (`--soft`, `--mixed`, `--hard`).
- **Rebase** normal e **interactivo**:
  - la UI manda la lista final (`pick`, `reword` con su mensaje nuevo, `squash`, `fixup`, `edit`, `drop` y el orden);
  - el backend escribe el fichero *todo* y lanza `git rebase -i` con `GIT_SEQUENCE_EDITOR` apuntando a un script que copia ese fichero (se valida en el spike S3);
  - los `reword` se aplican con `exec git commit --amend -m …` detrás del `pick`, para no necesitar editor;
  - **partir** un commit = `edit`: el rebase se para, la UI hace `reset HEAD^` y el usuario commitea por partes;
  - después, «Continuar».
- **Conflictos**:
  - `merge.conflictStyle=diff3` en las operaciones de la app;
  - por fichero se leen las tres versiones (`:1:`, `:2:` y `:3:`) y el fichero con marcas;
  - guardar escribe el resultado y hace `git add`;
  - `--continue`, `--skip` y `--abort` para merge, rebase, cherry-pick y revert.
- **Stash**: `push` (con `-u` y mensaje), `list`, `show -p`, `apply`, `pop`, `branch` y `drop`.
- **Tags**: crear (ligero y anotado), borrar y `push`/`push --delete`.
- **Remotos**: añadir, cambiar la URL, renombrar y quitar; fetch (`--prune`), pull (según el `pull_mode` del repo o el que se elija) y push (`-u` si no tiene remoto). **Push forzado**: `--force-with-lease=<rama>:<sha que conoce la UI>`, con confirmación que dice qué commits del remoto se pierden (`rev-list <remoto> --not <local>`).
- **Submódulos**: `status`, `init`, `update --init --recursive`, `add`, quitar (`deinit` + `rm`) y cambiar el commit (checkout dentro + `add` en el padre).
- **LFS**: si `git lfs version` responde: `ls-files`, patrones de `.gitattributes` (`track`/`untrack`), `pull` y `status`. Si el repo tiene `filter=lfs` en `.gitattributes` y LFS no está, se avisa.
- **Worktrees**: `worktree list --porcelain` (los de las tareas, marcados), `remove` y `prune`.
- **Mantenimiento**: `clean -n` como vista previa y `clean -f [-d] [-x]` con lo que se va a borrar; `gc` (trabajo largo) y `fsck`.
- **Clonar e inicializar**: `clone` (trabajo, con progreso) en una carpeta nueva, que después da de alta el proyecto o el repo; `init -b <rama>`.
- **Configuración**:
  - leer y escribir `git config --local` y `--global` para identidad, firma (`commit.gpgsign`, `gpg.format`, `user.signingkey`), `init.defaultBranch`, `pull.rebase` y `fetch.prune`;
  - el resto, con un editor de claves (`config --list --show-origin`).

**Respaldos y deshacer**
- **`GitOperation`** (nuevo): `repo_id`, `group_id` (las operaciones en lote y las integraciones de varios repos), `kind`, `label`, `at`, `refs_before` y `refs_after` (las referencias que movió: `{refname: sha}`), `head_before`, `worktree_snapshot` y `undone_at`.
- **Antes** de cada operación que mueve ramas (reset, rebase, merge, cherry-pick, revert, amend, borrar rama, push forzado):
  - se apuntan las referencias afectadas y `HEAD`;
  - los commits se protegen con `refs/agentic-os/backup/<op>/<n>`.
- **Antes** de cada operación que puede perder cambios sin commitear (reset `--hard`, descartar, `clean`, cambiar de rama con `--discard-changes`), se toma una **instantánea** de la carpeta con `snapshots.take` (la de la fase 11) y se guarda en `worktree_snapshot`.
- **«Deshacer»** (la última operación no deshecha de ese repo):
  - vuelve a poner cada referencia como estaba (`update-ref <ref> <antes> <después>`: falla si alguien la ha movido luego) y, si la rama está activa, `reset --keep`;
  - si hay instantánea, recupera los ficheros con `git restore --source=<instantánea> --worktree -- .` y borra los que no estaban.
  
  `clean -x` (ignorados) y lo ya subido no se pueden deshacer, y la confirmación lo dice. Un push forzado no se deshace, pero su respaldo permite volver a subir lo anterior.
- **Limpieza**: las operaciones y sus referencias de respaldo se borran a los 30 días (housekeeping de la fase 08) y con «Borrar respaldos» en Ajustes › Limpieza.

**Terminal git** (`services/gitx/shell.py`)
- `ShellSession` implementa `TerminalSession`:
  - abre Git Bash (el `bash.exe` de Git for Windows, con `--login -i`) o, si no está, PowerShell, en la carpeta del repo;
  - usa el mismo PTY y el mismo Job Object que las ejecuciones; no se guarda log en disco.
- Al terminar, `repo_changed`. Como mucho 4 abiertas; se cierran con la app.

### 3. Tareas e integración (`services/integration.py`)
- **Comprobación previa**, por repo de la tarea con commits frente a su base: `git merge-tree --write-tree <base> <rama>` dice, sin tocar nada, si hay conflictos y en qué ficheros. El botón «Integrar» muestra el resultado: «2 repos · sin conflictos» o «conflictos en backend: 3 ficheros».
- **Integrar sin carpeta de trabajo**, cuando la base no está activa en ninguna:
  - **merge**: el árbol de `merge-tree`, `commit-tree -p <base> -p <rama> -m "Merge T-142: <título>"` y `update-ref refs/heads/<base> <nuevo> <viejo>`;
  - **squash**: igual, con un solo padre;
  - **rebase**: `git replay --onto <base> <base>..<rama>` (actualiza la rama de la tarea) y *fast-forward* de la base.
  
  Si `git replay` no está o falla, se hace en un worktree temporal en `<datos>/tmp/integrate-<id>`.
- **Cuando la base está activa en una carpeta** (la del proyecto o un worktree): la carpeta tiene que estar limpia y la operación se hace allí, con `merge`/`rebase` normales. Si no está limpia, `dirty_worktree` con la lista de ficheros.
- **Varios repos**:
  - un `group_id` común y un `GitOperation` por repo;
  - si uno tiene conflictos, se para ahí y se ofrecen tres salidas:
    1. **resolver en el editor**: se crea un worktree de integración en `<proyecto>.wt\merge-T-142\<repo>`, con la base en un punto sin rama y el merge a medias. El editor de conflictos trabaja allí. Al terminar, se hace *fast-forward* de la base y se quita el worktree;
    2. **pasar a un agente**: ver «Tarea de resolución»;
    3. **deshacer los ya integrados**: «Deshacer» del grupo.
- **Después**:
  - `TaskRepo.integrated_at` y `integrated_sha`;
  - evento de tarea `integrated` (nuevo `TaskEventKind`);
  - se ofrece subir (un trabajo de push por repo), abrir un pull request en vez de integrar en local, o borrar las ramas.
- **Al aprobar** (`Project.on_approve`): cuando la tarea pasa a `done` y su worktree ya se soltó, el scheduler llama a `integration.run(task, mode)` en segundo plano. Un fallo o un conflicto no cambia el estado de la tarea: crea una petición `delivery` con el motivo («No se pudo integrar: conflictos en backend»).
- **Tarea de resolución**:
  - `Task.resolves_task_id` (nuevo, FK): una tarea sin pipeline, con el agente elegido, «Resolver conflictos de T-142»;
  - `Worktrees.prepare` le da worktrees con **las ramas de la tarea original** (`agentic/T-142`, que existen y se reutilizan) y solo de los repos con conflictos;
  - su prompt, generado: lleva la base a la rama (`git merge <base>`), resuelve los conflictos de los ficheros listados, ejecuta las pruebas si las hay y commitea;
  - al terminar, la petición `delivery` lleva «Integrar T-142».

### 4. Pull requests ([ADR 0018](../../adr/0018-forges-and-credentials.md))
- `services/forges/`:
  - `base.py`: interfaz `Forge` con `list`, `get` (estado, checks, revisiones y comentarios), `create`, `merge` (`merge` · `squash` · `rebase`), `close`, `reopen` y `update_branch`;
  - `github.py` (REST v3, también GitHub Enterprise por host) y `gitlab.py` (REST v4, también instancias propias).
- **Detección**: por la URL del remoto (`github.com`, `gitlab.com`). Para otro host, se elige el tipo a mano en los ajustes del repo (se guarda en `ProjectRepo.forge`).
- **Token**:
  - se pide a git, `git credential fill` con `protocol=https host=<host>`: es el que ya tiene guardado Git Credential Manager (OAuth) y vale para la API;
  - si no hay, GCM abre su ventana de inicio de sesión;
  - alternativa: pegar un token personal en Ajustes › Git, que se guarda con `git credential approve` en el mismo almacén. **La app no guarda ningún secreto propio.**
- **Desde una tarea**: título `T-142: <título>` y descripción con el resumen de `complete_task`, los cambios (`ChangesBadge` en texto) y un enlace a la tarea. Con varios repos, un pull request por repo, enlazados entre sí en la descripción.
- `httpx` con 15 s de tiempo máximo; los errores de la API se traducen (`auth_failed`, `not_found`, `rate_limited`, `conflict`).

### 5. Credenciales y claves (`services/gitx/ssh.py`)
- **Claves SSH**:
  - lista de `~/.ssh/*.pub` (tipo, comentario y huella con `ssh-keygen -lf`);
  - «Generar» → `ssh-keygen -t ed25519 -C <email> -f <ruta> -N <frase opcional>`, sin sobrescribir nunca;
  - copiar la parte pública.
- **«Probar conexión»**: `ssh -T -o BatchMode=yes git@<host>` (GitHub y GitLab responden con el usuario aunque salgan con 1). Para HTTPS, `git ls-remote --heads <url>`.
- Se usa el `ssh` de Git for Windows (el mismo que usa git), y si no está, el de Windows.

### 6. Agentes y git (ADR 0019)

**Autorización** (`adapters/base.py`)
- Con `agents_git_authorized`:
  - **Claude Code**: `Bash(git:*)` y `PowerShell(git *)` se añaden a `--allowedTools` **en todos los modos** (en `autonomous` ya está todo permitido). Comprobado en S2: funcionan también con `git -C` y `cd … && git …`, y hacen falta las dos.
  - **agy**: en S1 no preguntó por ningún comando de git en sesión interactiva (incluidos `push` y `push --force`), así que no se añade nada. Plan B, solo si una máquina pregunta: el hook `PreToolUse` del plugin responde `{"decision":"allow"}` a las líneas que empiezan por `git` (contrato documentado por agy).
- Sin `agents_git_authorized`: como hoy.

**Registro de lo que hizo cada ejecución** (`services/gitx/activity.py`)
- **Al empezar**, por repo: `refs_start` = `for-each-ref` de `refs/heads`, `refs/tags` y `refs/remotes`, más `HEAD`.
- **Al terminar**, en `_close_changes`:
  - **commits creados**: el *reflog* de `HEAD` **de la carpeta de la ejecución** (en un worktree, el suyo propio) entre `started_at` y `ended_at`: entradas `commit`, `commit (amend)`, `commit (merge)`, `rebase (pick)`, `cherry-pick` y `merge`. Así no se cuentan los commits de otras tareas en otros worktrees del mismo repo;
  - **ramas y tags** creados, movidos y borrados: diferencia de `refs_start` con el estado final, limitada a los que apuntan a commits de la ejecución o a ramas que estaban activas en su carpeta;
  - **lo que subió**: las `refs/remotes/*` que pasaron a apuntar a un commit de la ejecución o de una de sus ramas (un push actualiza la copia local del remoto), y si fue forzado (el valor anterior ya no es ancestro);
  - se guarda en `RunRepo.activity` y se escribe en `CommitAttribution`.
- **`CommitAttribution`** (nuevo): `repo_id`, `sha`, `run_id`, `task_id`, `agent_id` y `agent_name` (copia). Único por `(repo_id, sha)`.
- **Historial, grafo y blame** lo cruzan para mostrar el agente.
- **Commits anteriores a la fase**: los de `agentic/T-n` que no están en la base se atribuyen a la tarea al leer (sin guardar).
- **Página de ejecución**: sección «Git», con commits, ramas, tags y pushes por repo. **Historial de la tarea**: una línea por ejecución que hizo algo con git.
- **«Deshacer lo que hizo esta ejecución»**:
  - por repo, devuelve las **ramas locales** que movió o creó a su valor de `refs_start` (las creadas se borran) y, si la rama está activa, `reset --keep`;
  - se registra como un `GitOperation`, de modo que también se puede deshacer;
  - lo subido al remoto no se toca, y la confirmación lo dice;
  - si una rama se ha movido después de la ejecución, se avisa y no se toca.

### 7. API (`api/git.py`, `api/repos.py`, `api/forges.py`, nuevos)
- **Repos de un proyecto**: `GET/POST /api/projects/{id}/repos` (añadir uno vinculado), `PATCH/DELETE /api/repos/{repo_id}`, `POST /api/projects/{id}/repos/scan`.
- **Vista general**: `GET /api/projects/{id}/git/overview`; lotes con `POST /api/projects/{id}/git/batch` (`fetch` · `pull` · `push` · `commit` · `switch` · `create_branch`, con la lista de repos).
- **Un repo**: `GET /api/repos/{id}/status`, `.../log`, `.../graph-page`, `.../blame`, `.../file-history`, `.../branches`, `.../tags`, `.../stashes`, `.../remotes`, `.../submodules`, `.../lfs`, `.../worktrees`, `.../reflog`, `.../operations`, `.../config`, `.../conflicts/{path}` y `.../diff` (`?from=&to=` o `?worktree=staged|unstaged`, con `/file` y `/lines` como en la fase 11).
- **Acciones**: `POST /api/repos/{id}/<acción>`, una por operación (`stage`, `unstage`, `discard`, `commit`, `branch`, `switch`, `merge`, `rebase`, `rebase/interactive`, `cherry-pick`, `revert`, `reset`, `stash/*`, `tag/*`, `remote/*`, `fetch`, `pull`, `push`, `submodule/*`, `lfs/*`, `worktree/*`, `clean`, `gc`, `continue`, `skip`, `abort`, `conflicts/{path}/resolve`, `undo`). Las largas devuelven `202 {job_id}`.
- **Trabajos**: `GET /api/git/jobs/{id}`, `DELETE /api/git/jobs/{id}` (cancelar) y `WS /api/git/events`.
- **Terminal**: `POST /api/repos/{id}/shell` → `{shell_id}`, `WS /api/git/shells/{id}/terminal` y `DELETE`.
- **Clonar e inicializar**: `POST /api/git/clone` (`url`, `parent_folder`, `name`, `create_project`) y `POST /api/projects/{id}/repos/init`.
- **Tareas**: `GET /api/tasks/{id}/integration` (comprobación previa), `POST /api/tasks/{id}/integrate` (`mode`, `push`, `delete_branches`), `POST /api/tasks/{id}/resolve-conflicts` (`agent_id`).
- **Ejecuciones**: `GET /api/runs/{id}/git` (registro) y `POST /api/runs/{id}/git/undo`.
- **Pull requests**: `GET/POST /api/repos/{id}/pulls`, `GET /api/repos/{id}/pulls/{n}`, `POST .../merge|close|reopen|update-branch`, y `POST /api/tasks/{id}/pulls`.
- **Credenciales**: `GET /api/git/ssh-keys`, `POST /api/git/ssh-keys`, `POST /api/git/test-connection`, `GET/PUT /api/git/global-config` y `POST /api/git/forge-token` (lo guarda con `git credential approve`).
- **Seguridad**:
  - toda ruta que llega de la UI se valida como relativa al repo (sin `..` ni unidad) y se pasa con `GIT_LITERAL_PATHSPECS=1`;
  - solo se opera en repos dados de alta en un proyecto;
  - las referencias que llegan se validan con `git check-ref-format`;
  - nada se pasa por una shell.
- **Las acciones que pueden perder trabajo** exigen `confirm: true` en el cuerpo; sin él, `428 confirmation_required` con la descripción de lo que se pierde, que la UI enseña en el diálogo.

### 8. Frontend
- **`api/git.ts`, `api/repos.ts` y `api/forges.ts`**: tipos, *hooks* de consulta y mutaciones. `useGitEvents()` abre el WebSocket una vez (en `providers.tsx`) e invalida por `repo_id`; `useJob(id)` sigue un trabajo.
- **Pestaña «Git»** (`pages/projects/tabs/git/`), rutas `/proyectos/:id/git/:repoId?/:section?`:
  - `GitTab`: si hay más de un repo, a la izquierda la **vista general** (`ReposOverview`: filas con rama, ↑↓, cambios y avisos; casillas y barra de lotes); a la derecha, el repo elegido;
  - `RepoView`: cabecera (nombre, rama con selector, ↑↓, fetch/pull/push, terminal, «Deshacer: <última operación>») y navegación de secciones: Cambios · Historial · Ramas · Stash · Tags · Remotos · Pull requests · Submódulos · LFS · Worktrees · Reflog · Mantenimiento · Configuración. Las secciones vacías o no disponibles (LFS sin instalar, submódulos sin `.gitmodules`) se ocultan;
  - **`ChangesSection`**: dos listas (preparados y sin preparar) y el diff del fichero elegido con el `Hunk` de la fase 11, ampliado con casillas por bloque y por línea y los botones «Preparar», «Quitar» y «Descartar». Debajo, el formulario de commit (resumen, cuerpo, «Enmendar», «Sin hooks»);
  - **`HistorySection`**: `CommitGraph` (SVG por fila, vías calculadas en `graph.ts` de forma incremental, colores por vía con tokens del tema), lista virtualizada con carga al hacer scroll, buscador y filtro de ramas; al elegir un commit, panel con su diff y sus acciones (menú contextual: cherry-pick, revert, reset ▸, crear rama, crear tag, comparar);
  - **`BlameView`** e historial de un fichero, desde la lista de cambios y desde el diff;
  - **`BranchesSection`**: tabla con filtros («Solo de tareas», «Sin integrar»), estado de la tarea con `TaskStatusBadge`, acciones por fila y en lote, y «Comparar con…» (`ChangesSheet` entre dos ramas);
  - **`MergeDialog`** y **`RebaseDialog`**; **`InteractiveRebase`**: lista ordenable (`@dnd-kit`, ya instalado) con la acción de cada commit y edición del mensaje en línea;
  - **`ConflictEditor`**: lista de ficheros en conflicto; por fichero, tres columnas (nuestra · resultado · suya) con «Aceptar nuestra / suya / ambas» por bloque, y el resultado editable con **CodeMirror 6** (dependencia nueva: `@codemirror/state`, `@codemirror/view` y `@codemirror/commands`, con el tema de la app); «Marcar resuelto»; barra fija de la operación a medias con «Continuar», «Saltar» y «Abortar»;
  - **`StashSection`**, **`TagsSection`**, **`RemotesSection`** (con «Probar conexión»), **`SubmodulesSection`**, **`LfsSection`**, **`WorktreesSection`**, **`ReflogSection`** (con «Volver aquí» = reset con respaldo), **`MaintenanceSection`** (vista previa de `clean`, `gc` con progreso, `fsck`) y **`RepoConfigSection`**;
  - **`PullsSection`**: lista con estado y checks, detalle (descripción, checks, revisiones y comentarios de solo lectura) y acciones;
  - **`GitTerminal`**: un `TerminalPanel` (fase 03) sobre el WebSocket de la terminal git, en un `Sheet` inferior.
- **Diálogos de confirmación**: `ConfirmDialog` con la descripción del `428`: qué se pierde, si se puede deshacer y, en un push forzado, los commits del remoto que se sobrescriben.
- **Progreso**: los trabajos se ven como un *toast* persistente (`sonner`) con barra y «Cancelar».
- **Proyecto**:
  - el Resumen muestra los repos;
  - en Ajustes › Repositorios: lista, «Volver a buscar», añadir vinculado, nombre, base, «Participa en las tareas», `pull_mode` y tipo de servicio;
  - en Ajustes › Git: modo de integración, «Al aprobar…», «Autorizar git a los agentes» y profundidad de búsqueda.
- **Nuevo proyecto**: tercera opción «Clonar desde URL» (URL, carpeta destino, progreso), y aviso cuando la carpeta elegida no tiene ningún repo, con «Inicializar».
- **Tarea**: en `TaskPage`, bloque «Integración» cuando está aprobada o terminada y tiene ramas sin integrar:
  - ramas por repo, resultado de la comprobación previa y botón «Integrar en las bases» (modo, «y subir», «y borrar ramas»);
  - «Abrir pull request»;
  - con conflictos: «Resolver aquí» (abre el `ConflictEditor` del worktree de integración), «Pasar a un agente» (elegir agente) y «Deshacer lo integrado».
- **Ejecución**: en `RunPage`, sección «Git» con el registro por repo y «Deshacer lo que hizo esta ejecución».
- **Diffs** (fase 11): `ChangesViewer` agrupa por repo, con cabecera por repo (nombre, +/−) cuando hay más de uno.
- **Ajustes**: sección nueva «Git»:
  - configuración global (identidad, firma, rama por defecto);
  - claves SSH (lista, generar, copiar, probar);
  - cuentas de GitHub y GitLab (estado del token, «Iniciar sesión», pegar un token).
  
  En Limpieza, «Respaldos de git».
- **i18n**: claves `git.*`, `repos.*` y `forges.*`, y los códigos de error de §2.

### 9. Migración `0011_git_control`
- **Tablas nuevas**: `project_repos`, `task_repos`, `run_repos`, `commit_attributions` y `git_operations`.
- **Datos existentes**:
  - cada proyecto cuya carpeta es un repo → una fila en `project_repos` (`rel_path=""`, su `base_branch` o la rama actual);
  - las tareas con `branch` → una fila en `task_repos` con su `base_commit` y su `worktree_path`;
  - las ejecuciones con `snapshot_*` → una fila en `run_repos`.
  
  Los proyectos cuya raíz no es un repo se detectan con `repos.sync` en el primer arranque, no en la migración: la migración no recorre el disco.
- **Columnas**:
  - `projects`: + `integration_mode`, `on_approve`, `agents_git_authorized` y `repo_scan_depth`; − `base_branch`;
  - `tasks`: + `resolves_task_id`; − `base_commit` (pasa a `task_repos`);
  - `runs`: − `snapshot_start`, `snapshot_end` y `snapshot_skipped`.
  
  Todo con `batch_alter_table` (SQLite).
- **Copia de seguridad** de la BD antes de migrar: la de la fase 08 ya lo hace.

### 10. CLI falso
Órdenes nuevas para los e2e:
- `GIT: <args>` ejecuta git en la carpeta, para ramas, rebase, push y push forzado;
- `EN: <subcarpeta>` cambia de carpeta para las órdenes siguientes, para trabajar en varios repos;
- `CONFLICTO: ruta`: escribe un cambio que choca con la base.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0011_git_control.py` | nuevo |
| `backend/src/agentic_os/models/repo.py` | nuevo: `ProjectRepo`, `TaskRepo`, `RunRepo`, `CommitAttribution`, `GitOperation` |
| `backend/src/agentic_os/models/project.py`, `models/task.py`, `models/run.py`, `models/__init__.py` | modificado |
| `backend/src/agentic_os/services/repos.py` | nuevo: detección y sincronización |
| `backend/src/agentic_os/services/gitx/{__init__,runner,jobs,errors,read,write,backup,shell,activity,ssh,config}.py` | nuevos |
| `backend/src/agentic_os/services/integration.py` | nuevo |
| `backend/src/agentic_os/services/forges/{__init__,base,github,gitlab,credentials}.py` | nuevos |
| `backend/src/agentic_os/services/git.py` | modificado: `detect` por repo, utilidades compartidas |
| `backend/src/agentic_os/services/worktrees.py` | modificado: varios repos, ramas sin cambios, tarea de resolución |
| `backend/src/agentic_os/services/snapshots.py`, `services/changes.py` | modificado: por repo, exclusión de repos anidados |
| `backend/src/agentic_os/services/runs/manager.py` | modificado: instantáneas y registro git por repo, `extra_dirs` |
| `backend/src/agentic_os/services/adapters/base.py`, `claude.py`, `agy.py` | modificado: `extra_dirs` (`--add-dir`), autorización de git |
| `backend/src/agentic_os/services/context.py` | modificado: sección «Repositorios» |
| `backend/src/agentic_os/services/scheduler.py` | modificado: integración al aprobar, tarea de resolución |
| `backend/src/agentic_os/services/maintenance.py`, `services/housekeeping.py` | modificado: ramas de tareas por repo, respaldos |
| `backend/src/agentic_os/api/git.py`, `api/repos.py`, `api/forges.py`, `api/git_events.py` | nuevos |
| `backend/src/agentic_os/api/projects.py`, `api/tasks.py`, `api/runs.py`, `api/changes.py`, `api/maintenance.py`, `app.py` | modificado |
| `backend/src/agentic_os/schemas/git.py`, `schemas/repo.py`, `schemas/forge.py` | nuevos |
| `backend/src/agentic_os/schemas/project.py`, `schemas/task.py`, `schemas/run.py`, `schemas/changes.py` | modificado |
| `backend/tests/fake_cli.py` | modificado: `GIT`, `EN`, `CONFLICTO` |
| `backend/tests/gitrepos.py` | nuevo: fábrica de repos de prueba (varios repos, remoto *bare*, submódulo, LFS) |
| `backend/tests/test_repos.py`, `test_gitx_read.py`, `test_gitx_write.py`, `test_gitx_backup.py`, `test_gitx_jobs.py`, `test_integration.py`, `test_activity.py`, `test_forges.py`, `test_git_api.py`, `test_multirepo_e2e.py`, `test_git_agents_e2e.py`, `test_migration_0011.py` | nuevos |
| `backend/tests/test_worktrees.py`, `test_snapshots.py`, `test_changes*.py`, `test_adapters.py`, `test_context.py`, `test_maintenance.py` | modificado |
| `frontend/package.json` | modificado: CodeMirror 6 |
| `frontend/src/api/git.ts`, `api/repos.ts`, `api/forges.ts` | nuevos |
| `frontend/src/pages/projects/tabs/git/*` | nuevos (vista general, `RepoView` y secciones) |
| `frontend/src/components/git/*` | nuevos: `CommitGraph`, `graph.ts`, `ConflictEditor`, `InteractiveRebase`, `BranchPicker`, `JobToast`, `GitTerminal`, `DangerConfirm` |
| `frontend/src/components/changes/*` | modificado: agrupación por repo, selección por bloque y por línea |
| `frontend/src/pages/projects/ProjectDetailPage.tsx`, `NewProjectDialog.tsx`, `tabs/SettingsTab.tsx`, `tabs/SummaryTab.tsx` | modificado |
| `frontend/src/pages/tasks/TaskPage.tsx`, `pages/runs/RunPage.tsx` | modificado |
| `frontend/src/pages/settings/GitSection.tsx`, `SettingsPage.tsx`, `CleanupSection.tsx` | nuevo / modificado |
| `frontend/src/providers.tsx` | modificado: `useGitEvents` |
| `frontend/src/styles/tokens.css` | modificado: colores de las vías del grafo y de los conflictos |
| `frontend/src/i18n/es.json` | modificado |
| `docs/adr/0016-multi-repo-projects.md`, `0017-git-operations.md`, `0018-forges-and-credentials.md`, `0019-agents-and-git.md` | nuevos |

## Tareas (en orden)
La fase se desarrolla en **7 bloques**. Cada bloque termina con sus tests en verde y un commit (o varios), y no empieza el siguiente sin cerrar el anterior. Al cerrar cada bloque te aviso con lo que se puede probar.

**Bloque 0: spikes** (resultados en este plan)
1. [x] **S1 · agy**:
   - `--add-dir` con un repo vinculado: ¿lo ve y puede escribir sin preguntar por confianza?
   - formas de preaprobar solo los comandos de git en `manual` y `accept-edits`: un *hook* `PreToolUse` que responde «allow», o un `settings.json` del plugin de workspace;
   - qué pregunta `--mode accept-edits` cuando ejecuta un comando.
2. [x] **S2 · Claude Code**:
   - `--allowedTools "Bash(git:*)"` en `manual` con `git commit`, `git -C x push`, `cd x && git push` y PowerShell;
   - `--add-dir` con confianza de carpeta.
3. [x] **S3 · git sin terminal en Windows**:
   - `GIT_SEQUENCE_EDITOR` con un script para el rebase interactivo;
   - `exec git commit --amend -m` para `reword`;
   - `GIT_TERMINAL_PROMPT=0` con Git Credential Manager (¿abre su ventana?);
   - `BatchMode=yes` con una clave con frase de paso;
   - `git credential fill` de `github.com` → token válido para la API;
   - `git replay` y `merge-tree --write-tree` en git 2.55.
4. [x] **S4 · rendimiento**: estado de 20 repos en paralelo; `git log --topo-order` paginado en un repo de 50 000 commits (p. ej. un clon de git). Primer pintado del grafo.

**Bloque 1: varios repos**

5. [x] Modelos y migración `0011`, con su test sobre una BD de la v1.3.
6. [x] `services/repos.py` (`scan`, `sync`, `nested_paths`) y API de repos; Ajustes › Repositorios y Resumen.
7. [x] Worktrees de varios repos (`prepare`/`release`, vinculados en `@<name>`, submódulos, ramas sin cambios), `extra_dirs` en los adapters y sección «Repositorios» del contexto.
8. [x] Instantáneas, diffs y resúmenes por repo (`RunRepo`, `changes.py`, visor agrupado); mantenimiento y limpieza por repo.
9. [x] e2e de varios repos con el CLI falso (CA1, CA2).

**Notas del bloque 1 (cambios respecto a lo planeado)**
- La migración `0011` solo crea `project_repos`, `task_repos` y `run_repos` (más `projects.repo_scan_depth`). `GitOperation` y `CommitAttribution` tendrán su propia migración en el bloque que las usa.
- `projects.base_branch` **no se elimina**: queda como la base por defecto de los repositorios que no tengan la suya. Sí se eliminan `runs.snapshot_*` y `tasks.base_commit` (pasan a las tablas por repositorio).
- `services/runrepos.py` (nuevo) decide qué repositorios ve una ejecución y dónde están; lo usan las instrucciones, `--add-dir` y las instantáneas.
- `Changes` lleva `repos[]` y los endpoints de fichero y de líneas reciben `repo` (`422 repo_required` si hay varios y falta). `changes.changes(rng)` devuelve ahora un `RepoChanges`; `run_range` y `task_range` quedan como atajo del primer repositorio.
- Con **un** repositorio el worktree es la carpeta de trabajo misma (como antes); con varios, la carpeta reproduce el proyecto. Los ficheros que el agente escribe fuera de cualquier repositorio se conservan y la tarea lo anota.
- El CLI falso gana `EN: <subcarpeta>`. Los submódulos del repositorio de una tarea todavía **no** se inicializan en su worktree: pasa al bloque 4 (submódulos).
- La pestaña de ajustes del proyecto muestra «Repositorios» (volver a buscar, vincular, base, modo de pull, participa, quitar). La vista general de la pestaña Git es del bloque 2.
- ADR 0016 escrito.

**Bloque 2: lo básico de un repo**

10. [x] `gitx/runner`, `errors`, `jobs` y `WS /api/git/events`; `gitx/read` (estado, vista general, ramas, historial paginado, blame, historial de un fichero, diffs entre referencias y sin commitear).
11. [x] Escritura básica: preparar y descartar por fichero, bloque y línea; commit y enmienda; crear, cambiar, renombrar y borrar ramas; fetch, pull y push (sin forzar) como trabajos; lotes de la vista general.
12. [x] Frontend: pestaña Git, vista general, `RepoView`, Cambios (con selección por bloque y por línea), Historial con `CommitGraph`, Ramas, blame y `JobToast`.

**Bloque 3: merge, rebase, conflictos y deshacer**

13. [x] `gitx/backup` (`GitOperation`, referencias de respaldo, instantánea de la carpeta, «Deshacer») y confirmaciones `428`.
14. [x] Merge, rebase, rebase interactivo, cherry-pick, revert y reset; continuar, saltar y abortar; lectura y resolución de conflictos.
15. [x] Frontend: `MergeDialog`, `RebaseDialog`, `InteractiveRebase`, `ConflictEditor` (CodeMirror) y «Deshacer» (CA6, CA7).

**Notas de los bloques 2 y 3 (cambios respecto a lo planeado)**
- Paquete `services/gitx/` (`errors`, `runner`, `read`, `write`, `jobs`, `remote`, `events`, `tasks`, `backup`, `oplog`, `merge`). Todo git de la pestaña corre con `GIT_TERMINAL_PROMPT=0`, `LC_ALL=C` y un candado de escritura por repositorio compartido con sus worktrees.
- `changes.py` gana modos de rango (`worktree` preparado / sin preparar, `commit`, `compare`) y el visor se reutiliza; los ficheros sin seguimiento salen como añadidos (con `git diff --no-index`).
- Preparar y descartar por línea: el parche se construye en bytes a partir del diff **de ahora** (`git diff -U3`), no del que vio la UI; si una línea elegida ya no está, `409 stale_diff` y no se aplica nada. No se admiten líneas sueltas en ficheros nuevos, borrados, renombrados, binarios ni junto a «sin salto de línea final» (se puede elegir el bloque entero).
- La paginación del historial usa `--skip` (spike S4); el grafo se calcula **en el cliente** (`graph.ts`) a partir de los padres, de forma incremental por páginas.
- Jobs de red (`fetch`, `pull`, `push`): progreso leyendo stderr (`\r`), cancelación matando el árbol de procesos, eventos por `WS /api/git/events`. `pull` y los trabajos `exclusive` toman el candado del repo. La pestaña solo escucha el WebSocket mientras está abierta (no hay conexión global).
- `GitOperation` (migración `0012`): ramas antes y después, `HEAD`, y una instantánea del árbol de trabajo si la operación puede perder ficheros (`reset --hard`, descartar). Solo se deshace **la última** operación y solo si ninguna de sus ramas se ha movido desde entonces (`moved_since`). Una operación que se detiene en conflictos queda «abierta» hasta continuar (se cierra) o abortar (se borra).
- **Editor de conflictos con `<textarea>`, no CodeMirror**: bloque a bloque (nuestra / suya / ambas), resultado editable, y botón deshabilitado mientras queden marcas. Evita una dependencia nueva y los problemas de CodeMirror en jsdom; si hiciera falta resaltado de sintaxis se añade después.
- Rebase interactivo con **flechas** subir/bajar (accesibles y comprobables) en lugar de arrastrar con `@dnd-kit`. El script del editor es un `.sh` con ruta POSIX (spike S3); `reword` se hace con `exec git commit --amend -F`.
- Lo de la rama (`merge`, `rebase`) y las acciones sobre un commit (cherry-pick, revert, reset, rama aquí, reescribir desde aquí) están en la pestaña Ramas y en el detalle del commit.

**Bloque 4: el resto de git**

16. [x] Stash, tags, remotos y push forzado, submódulos, LFS, worktrees, reflog, mantenimiento, configuración (repo y global), clonar e inicializar, y terminal git.
17. [x] Frontend: sus secciones, «Clonar desde URL» en Nuevo proyecto y la terminal git (CA4, CA9).

**Notas del bloque 4 (cambios respecto a lo planeado)**
- La pestaña Git gana siete secciones: Stash, Tags, Remotos (con el push forzado), Avanzado (submódulos, LFS y worktrees), Mantenimiento (limpiar, gc, comprobar, tamaño), Ajustes (local y global) y Terminal.
- El push forzado enseña antes los commits del remoto que se perderían (`push/overwrites`) y manda `confirm: true` solo al aceptar; limpiar, descartar un stash, borrar un tag y quitar remotos, submódulos o worktrees también piden confirmación.
- La terminal git reutiliza `TerminalSocket` con la ruta `/api/git/shells/{id}/terminal` (hook `use-git-shell`); se cierra al salir de la sección.
- «Clonar desde URL» es un modo de *Nuevo proyecto*: arranca el trabajo `clone`, lo consulta cada segundo (`GET /api/git/jobs/{id}`, la pestaña Git aún no está abierta y no hay WebSocket) y, al terminar bien, crea el proyecto en la carpeta clonada; si falla, no crea nada y enseña el motivo.
- «Inicializar repositorio» (`POST /projects/{id}/repos/init`) tiene hook (`useInitRepo`), pero su botón queda para los ajustes del proyecto del bloque 5.

**Bloque 5: tareas e integración**

18. [x] `services/integration.py` (comprobación previa, merge, squash y rebase sin carpeta y en carpeta, varios repos con grupo, worktree de integración), «Al aprobar…» en el scheduler y tarea de resolución.
19. [x] Frontend: bloque «Integración» de la tarea y ajustes del proyecto; e2e con remoto *bare* (CA3).

**Notas del bloque 5 (cambios respecto a lo planeado)**
- Migración `0013`: `projects.integration_mode`, `on_approve` y `agents_git_authorized`; `tasks.resolves_task_id`; y el evento de tarea `integrated`.
- `integration.check` usa `merge-tree --write-tree` y distingue cuatro estados por repo: `clean`, `conflicts`, `blocked` (la carpeta donde está la base tiene cambios sin commit, con la lista) y `integrated`/`nothing`. Una rama ya integrada con squash o rebase sigue «por delante» en commits, así que se compara el **árbol** que saldría con el de la base: si es el mismo, no hay nada que integrar (evita integrar dos veces).
- Integrar nunca toca la carpeta del usuario salvo para avanzarla con `merge --ff-only` cuando la base está activa en ella; el merge y el squash salen de `merge-tree` + `commit-tree`, el rebase de `git replay` (en git 2.55 actualiza la rama sin imprimir nada; si falla, worktree temporal).
- Varios repos: un `group_id` y un `GitOperation` por repo; se para en el primero que no se puede integrar y los anteriores quedan hechos. «Deshacer lo integrado» no toca nada si alguna base se ha movido desde entonces.
- **Resolver aquí, distinto a lo planeado**: el plan hablaba de un worktree con la base y el merge a medias. Se hace al revés: un worktree en `<proyecto>.wt\merge-T-n\<repo>` sobre **la rama de la tarea** con la base ya fusionada (con sus conflictos). Al «Marcar resuelto» se hace el commit del merge y se quita la carpeta; después integrar es limpio. Es lo mismo que hace el agente de la tarea de resolución, y los conflictos se resuelven con las herramientas del propio usuario: **el `ConflictEditor` de la app no abre ese worktree** (sus rutas trabajan por `repo_id`, y el worktree no es un repo del proyecto). Queda como mejora para una fase futura.
- Al aprobar (`on_approve`): el scheduler lanza la integración en un hilo cuando la tarea está `done` y su worktree ya se soltó. Un fallo o conflicto crea una petición `delivery` («No se pudo integrar T-n» con el motivo); `pull_request` queda para el bloque 6. Una tarea de resolución, al terminar, deja una petición «Integrar T-n».
- Tarea de resolución: `Worktrees.prepare` le da worktrees sobre la rama original, solo en los repos con conflictos (o, si ya no hay, en los que tienen commits).
- Frontend: `IntegrationBlock` en la tarea terminada (se oculta si no dejó ramas o ya está todo integrado) y «Git» en los ajustes del proyecto (guarda cada cambio al hacerlo).
- Arreglado de paso: la sección Ramas enlazaba a `/tareas/:id`, que no existe; la ruta es `/tablero/tareas/:id`.

**Bloque 6: pull requests y credenciales**

20. [x] `services/forges` (GitHub y GitLab, token por `git credential`), claves SSH y «Probar conexión»; API.
21. [x] Frontend: Pull requests (repo y tarea) y Ajustes › Git; prueba manual con un repo real de GitHub (CA3). **La prueba manual con GitHub real queda pendiente de hacerla el usuario** (no hay forma de probarla aquí sin credenciales): los tests usan un transporte HTTP simulado.

**Notas del bloque 6 (cambios respecto a lo planeado)**
- `httpx` pasa de dependencia de desarrollo a dependencia de la app.
- `services/forges/` (`base`, `github`, `gitlab`, `http`, `remoteurl`): un `Forge` común con `list`, `get`, `create`, `merge`, `describe` (cambiar la descripción, para enlazar entre sí los pull requests de una tarea), `close`, `reopen` y `update_branch`. Errores de la API como códigos estables (`auth_failed`, `rate_limited`, `not_found`, `conflict`, `forge_failed`, `network`, `timeout`).
- El token sale de `git credential fill` y el pegado entra con `git credential approve` (`gitx/credentials.py`); la app no guarda ningún secreto. Los tests usan el *helper* `store` de git sobre un fichero temporal y aíslan la configuración global.
- GitLab: «rebase» al fusionar es primero `PUT …/rebase` y después `merge`; el borrador es el prefijo `Draft: `.
- Un pull request desde una tarea hace *push* de la rama y abre uno por repo; con varios, las descripciones se enlazan. Si falla uno, los demás siguen. `Project.on_approve = pull_request` lo hace al aprobar y deja una petición si algo falla.
- Claves SSH (`gitx/ssh.py`): listar `~/.ssh/*.pub` con su huella, generar ed25519 sin sobrescribir nunca (nombre validado), «Probar conexión» con `BatchMode`. Se usa el `ssh` de Git for Windows.
- Frontend: sección Pull requests del repo (lista, detalle con checks, revisiones y comentarios, fusionar con confirmación, cerrar, reabrir, actualizar rama y crear), «Abrir pull request» en la tarea, «Servicio» por repo en los ajustes del proyecto y la sección Ajustes › Git (configuración global, claves SSH, tokens por host).
- El inicio de sesión OAuth de Git Credential Manager solo se dispara al crear un pull request o desde la tarea (acciones del usuario); las lecturas no abren ventanas.

**Bloque 7: agentes**

22. [ ] Autorización de git en los adapters, registro de cada ejecución (`activity`, `CommitAttribution`), atribución en historial, grafo y blame, y «Deshacer lo que hizo esta ejecución».
23. [ ] Frontend: sección «Git» de la ejecución y agente en el historial; e2e con el CLI falso (commit, rama, rebase, push y push forzado) y prueba manual con Claude Code en modo `manual` (CA5, CA8).

**Cierre**

24. [ ] ADRs 0016 a 0019, prueba manual completa (CA10) y `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_repos.py`: detección en raíz que no es repo con 2 repos dentro, profundidad, carpetas saltadas, submódulos no listados, repos que desaparecen, vinculados que no se tocan | CA1 |
| `test_worktrees.py` (ampliado): una carpeta de tarea con un worktree por repo, cada uno desde su base; vinculados en `@<name>`; submódulos inicializados; fallo en un repo deshace los demás; ramas sin cambios borradas al soltar | CA2 |
| `test_changes.py` (ampliado): diff por repo, igual a `git diff` en cada uno; repos anidados excluidos de la instantánea del padre | CA2 |
| `test_multirepo_e2e.py` (CLI falso con `EN`): tarea de dos etapas que cambia dos repos; diffs de tarea y de ejecución agrupados | CA1, CA2 |
| `test_gitx_read.py`: estado, ahead/behind, operación a medias, ramas con tarea y «integrada», historial paginado sin `refs/agentic-os/`, blame, igual que `git status`, `git branch -vv`, `git log --graph` y `git blame` | CA5 |
| `test_gitx_write.py`: una prueba por operación (preparar y descartar por bloque y línea, `stale_diff`, commit, enmienda, ramas, merge, rebase, rebase interactivo con reordenar, juntar, editar, partir y descartar, cherry-pick, revert, reset, stash, tags, remotos, push forzado con *lease*, submódulos, LFS si está, worktrees, clean, gc, clonar, init) | CA4, CA9 |
| `test_gitx_write.py`: conflictos en merge, rebase y cherry-pick → leer las tres versiones, resolver, continuar y abortar | CA6 |
| `test_gitx_backup.py`: «Deshacer» tras reset `--hard` (con ficheros sin commitear recuperados), rebase, merge y borrado de rama; no deshace si la rama se movió después | CA7 |
| `test_gitx_jobs.py`: progreso de un clone y un fetch reales en local, cancelación, `GIT_TERMINAL_PROMPT=0` (un remoto HTTPS sin credenciales falla con `auth_failed` y no se cuelga) | CA10 |
| `test_integration.py`: comprobación previa; merge, squash y rebase sin carpeta y con la base activa en la carpeta; carpeta sucia → `dirty_worktree`; varios repos con conflicto en uno y «deshacer lo integrado»; worktree de integración; push al remoto *bare*; «Al aprobar…» | CA3 |
| `test_integration.py`: tarea de resolución (CLI falso): trabaja en la rama original, resuelve el conflicto y después la integración no tiene conflictos | CA3 |
| `test_forges.py`: GitHub y GitLab contra un servidor HTTP falso (crear, listar, detalle con checks, merge, cerrar), token por `git credential fill` con un *helper* de prueba, errores traducidos | CA3 |
| `test_adapters.py` (ampliado): `--allowedTools` con git en `manual` y `restricted` según `agents_git_authorized`; `--add-dir` de los vinculados en Claude y agy | CA8 |
| `test_activity.py`: commits, ramas, tags y pushes de una ejecución, sin contar los de otro worktree del mismo repo; atribución; «Deshacer lo que hizo esta ejecución» | CA5, CA8 |
| `test_git_agents_e2e.py` (CLI falso con `GIT`): en modo `manual`, commit, rama, rebase, push y push forzado a un remoto *bare* sin preguntas; registro en la ejecución | CA8 |
| `test_git_api.py`: validación de rutas y referencias, `428 confirmation_required`, repos de otro proyecto → 404, errores traducidos | CA8, CA10 |
| `test_migration_0011.py`: proyectos, tareas y ejecuciones de la v1.3 pasan a `project_repos`, `task_repos` y `run_repos` con sus datos | CA9 |
| Frontend: `graph.test.ts` (vías del grafo con merges y páginas), `git-tab.test.tsx` (vista general, lotes, cambios con selección por línea, historial, ramas), `conflict-editor.test.tsx`, `interactive-rebase.test.tsx`, `integration.test.tsx` (bloque de la tarea), `pulls.test.tsx`, `git-settings.test.tsx` | CA1, CA3–CA7 |
| CI local (lint, formato, tipos, tests) y `/code-review` | CA11 |

## Decisiones (ADR)
- **ADR 0016, Proyectos con varios repositorios**: modelo `ProjectRepo` (detectados y vinculados, base por repo), detección (profundidad, carpetas saltadas, submódulos), carpeta de trabajo de la tarea con un worktree por repo (vinculados en `@<name>`, ficheros sueltos fuera), instantáneas y diffs por repo (sustituye en parte al ADR 0015) y `extra_dirs` para los CLIs.
- **ADR 0017, Operaciones de git de la app**: candado por repo, entorno sin terminal, trabajos con progreso y cancelación, eventos por WebSocket, parches para preparar por bloque y por línea, rebase interactivo con `GIT_SEQUENCE_EDITOR`, conflictos `diff3`, respaldos (`GitOperation`, `refs/agentic-os/backup/`, instantánea de la carpeta) y «Deshacer»; integración con `merge-tree`/`replay` sin carpeta de trabajo y cuándo se usa la carpeta del usuario; CodeMirror 6 para el editor de conflictos.
- **ADR 0018, Pull requests y credenciales**: API REST de GitHub y GitLab con `httpx` en vez de `gh`/`glab` (no están instalados y añadirían una dependencia); token de Git Credential Manager con `git credential fill`; la app no guarda secretos propios; claves SSH con `ssh-keygen` de Git for Windows.
- **ADR 0019, Agentes y git**: sin reglas ni bloqueos; autorización de los comandos de git en cada CLI (y la limitación de agy, según S1); registro de cada ejecución a partir del *reflog* de su carpeta y de las referencias; atribución de commits; «Deshacer lo que hizo esta ejecución» solo en ramas locales.
