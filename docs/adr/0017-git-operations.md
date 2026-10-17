# ADR 0017: Operaciones de git de la app

- **Estado**: aceptado
- **Fecha**: 2026-10-17
- **Contexto de decisión**: fase 12 ([`spec.md`](../phases/12-control-git/spec.md), [`plan.md`](../phases/12-control-git/plan.md))

## Contexto
La app pasa de leer git (fases 9–11) a **llevar el repositorio del usuario**: preparar líneas, commitear, integrar ramas, resolver conflictos, subir. Las operaciones corren en un proceso del sistema, pueden tardar, pueden pedir credenciales, pueden dejar un merge a medias y pueden perder trabajo. Hay que decidir cómo se ejecutan, cómo se informa de su progreso, qué se guarda para poder deshacerlas y qué nunca se hace por el usuario.

## Decisión

### Cómo se ejecuta git (`services/gitx/runner.py`)
- **Sin terminal**: `GIT_TERMINAL_PROMPT=0`, `GIT_SSH_COMMAND="ssh -o BatchMode=yes"`, `GIT_EDITOR=true` y `LC_ALL=C`. Un credencial que falta es un error inmediato (`auth_failed`, medido en 0,3 s en el spike S3), no un cuelgue. Cuando la persona pidió la operación (`interactive`), `GCM_INTERACTIVE=auto` deja que el Git Credential Manager abra su ventana.
- **Errores con código estable** (`errors.py`): git se lee en inglés y sus fallos se clasifican (`auth_failed`, `network`, `non_fast_forward`, `conflicts`, `dirty_worktree`, `hook_failed`…). La UI traduce por código; `message` es la última línea de git. Un hook que rechaza un commit no dice que es un hook: se deduce de que existan hooks de commit.
- **Un candado de escritura por repositorio**, compartido por todos sus worktrees (clave: su `git-common-dir`). Las lecturas no lo toman.
- **Parches en bytes** (`run_raw`): el modo texto de `subprocess` traduce `\r\n`, lo que estropearía los parches de ficheros CRLF.
- Rutas de la UI relativas y sin `..`, con `GIT_LITERAL_PATHSPECS=1`; nada pasa por una shell.

### Trabajos de red (`jobs.py`, `events.py`)
`fetch`, `pull` y `push` son **trabajos**: un hilo con `Popen`, el progreso leído de stderr (git termina cada actualización con `\r`), cancelación matando el **árbol** de procesos (`taskkill /T`; git lanza `ssh` y helpers de credenciales) y un máximo de 30 min. Los trabajos que cambian el árbol (`pull`) toman el candado del repo durante toda su vida. Los estados viajan por `WS /api/git/events` junto a `repo_changed`, que la UI usa para volver a leer el repositorio; la pestaña solo escucha mientras está abierta.

### Lectura (`read.py`)
`git status --porcelain=v2 -z`, `for-each-ref` con `%(ahead-behind:<base>)` (una llamada para todas las ramas) y `git log` con separadores ASCII. El historial se pagina con **`--skip`**: cuesta lo mismo en cualquier página (~156 ms con 50 000 commits), y un cursor por sha perdería los commits de otras ramas. Las referencias propias (`refs/agentic-os/`) se excluyen siempre. El grafo se calcula en el cliente a partir de los padres.

### Preparar y descartar por bloque y línea (`write.py`)
El parche se construye en el servidor **a partir del diff de ese momento**; la UI solo dice qué líneas (por su número en el lado que viven). Hacia delante (preparar) una eliminación no elegida pasa a contexto y una adición no elegida se omite; hacia atrás (quitar, descartar) es al revés. Si una línea elegida ya no está, `409 stale_diff` y no se aplica nada. No se admiten líneas sueltas donde el parche se contradiría: ficheros nuevos, borrados, renombrados, binarios o con «sin salto de línea final» (el bloque entero sí).

### Integración y conflictos (`merge.py`)
Un **conflicto es un resultado, no un error**: la operación se detiene, git la recuerda, y se continúa, se salta o se aborta (`proceed`). El editor lee las tres versiones (`:1:`, `:2:`, `:3:`) y el fichero con marcas, y guarda el resultado con `git add`. El rebase interactivo escribe el *todo* y lo entrega con `GIT_SEQUENCE_EDITOR` (un script **`sh` con ruta POSIX**: git lo lanza con su propio `sh`, un `.cmd` no sirve, spike S3); `reword` es `exec git commit --amend -F <fichero>`. Se niega si entre los commits hay merges (los aplanaría) o si la lista ya no coincide con `base..HEAD`.

### Deshacer (`oplog.py`, tabla `git_operations`)
Antes de una operación que mueve ramas o pierde ficheros se anota: las ramas locales y dónde apuntan, `HEAD`, y — si puede perder ficheros (`reset --hard`, descartar) — una **instantánea del árbol de trabajo** fijada en `refs/agentic-os/backup/` (el mecanismo del ADR 0015). Al terminar se anotan las ramas otra vez.
- **Se deshace solo la última operación**, y solo si ninguna de sus ramas se ha movido desde entonces (`moved_since`): deshacer nunca pisa trabajo posterior. Tampoco con una operación a medias.
- Deshacer devuelve cada rama a su sitio (`update-ref` con el valor esperado; si es la rama activa, `reset --keep` para que los ficheros la sigan) y restaura la instantánea sobre el árbol.
- Una operación que se detiene en conflictos queda **abierta** (sin «después»): se cierra al continuar y se borra al abortar. Una operación que no movió nada no deja entrada.
- **Descartes y `reset --hard`** exigen `confirm` en la API (`428 confirmation_required`) además del diálogo de la UI.
- No se puede deshacer lo ya subido al remoto, ni `clean -x`.

### Editor de conflictos
Un **`<textarea>`** para el resultado, con elección por bloque (nuestra, suya, ambas). Se descartó CodeMirror 6 (la propuesta del plan): no aporta nada que el flujo necesite hoy, añade una dependencia grande y se comporta mal en jsdom. Si hace falta resaltado de sintaxis, se añade después sin cambiar la API.

## Consecuencias
- Cada operación de la app que cambia ramas deja una entrada que se puede deshacer, con coste de una llamada a `for-each-ref` antes y después.
- Dos copias del árbol (una por descarte) ocupan espacio hasta que se limpian con los respaldos (bloque posterior).
- La pestaña Git funciona igual con los agentes trabajando: lo que hagan se ve al volver a leer (eventos o sondeo), y las acciones con una ejecución viva en la carpeta se permiten (los agentes tienen vía libre).
