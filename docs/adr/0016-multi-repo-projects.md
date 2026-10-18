# ADR 0016: Proyectos con varios repositorios

- **Estado**: aceptado
- **Fecha**: 2026-10-17
- **Contexto de decisión**: fase 12 ([`spec.md`](../phases/12-control-git/spec.md), [`plan.md`](../phases/12-control-git/plan.md))

## Contexto
Hasta la fase 11 un proyecto era una carpeta y, como mucho, un repositorio: el de esa carpeta. Los worktrees (ADR 0009), las instantáneas y los diffs (ADR 0015) y la limpieza de ramas asumían ese único repositorio. Pero hay proyectos que no tienen un control de versiones único: un `backend/` y un `frontend/` con cada uno el suyo, una carpeta que no es repositorio y contiene varios, o una librería compartida en otra ruta del disco.

## Decisión

### Un proyecto tiene una lista de repositorios
Tabla `project_repos` (`ProjectRepo`): ruta absoluta, ruta relativa a la carpeta del proyecto (`""` es la carpeta misma, nula si el repositorio está fuera), nombre, **rama base propia**, si **participa** en las tareas, si está **vinculado** (fuera de la carpeta), si falta en disco, y su modo de pull.
- `projects.base_branch` se conserva como la base por defecto del repositorio de la raíz y de los que no tengan la suya (`repos.base_of`).
- Unicidad por `(proyecto, ruta normalizada)`.

### Cómo se encuentran (`services/repos.py`)
- **Detección**: se recorre la carpeta hasta `projects.repo_scan_depth` (3 por defecto). Un `.git` (carpeta o fichero) marca un repositorio.
  - Nunca se entra en `node_modules`, `.venv`, `dist`, `build`, `target`… ni en carpetas que el repositorio que las contiene ignora (`git check-ignore`).
  - Los **submódulos** pertenecen a su repositorio padre y no se listan (se leen de `.gitmodules`).
- **Sincronización** (`sync`): añade los nuevos (con su rama actual como base), marca `missing` los que desaparecieron (nunca los borra: los quita el usuario) y solo comprueba los vinculados. Se ejecuta al crear el proyecto, al pulsar «Volver a buscar» y al cambiar su carpeta.
- **Perezosa** (`ensure`): un proyecto sin ninguna fila se detecta al primer uso. Así los proyectos creados antes de la fase, y los de los tests, funcionan sin migrar nada a mano.
- **Un proyecto que es una subcarpeta de un repositorio** (soportado desde la fase 11) usa ese repositorio contenedor, como vinculado.
- **Vincular a mano** (`link`): la raíz de un repositorio fuera de la carpeta, o más profundo de lo que llega el recorrido.

La migración `0011` **no toca el disco**: crea la fila del repositorio raíz solo en los proyectos que ya usaban git (modo worktree, o con tareas y ejecuciones con rama o instantáneas), con su base actual.

### Worktrees de una tarea (`services/worktrees.py`)
La **carpeta de trabajo** sigue siendo `<proyecto>.wt\T-n` (`Task.worktree_path`) y la rama `agentic/T-n` (`Task.branch`) es la misma en todos los repositorios. Lo que cada repositorio tiene vive en `task_repos` (`TaskRepo`): rama, ruta del worktree, `base_commit` y, para la fase de integración, `integrated_*`.
- **Un solo repositorio**: su worktree es la carpeta de trabajo misma (idéntico a antes).
- **Varios**: la carpeta de trabajo **reproduce el proyecto**. El worktree de cada repositorio va en su ruta relativa (`backend/`, `frontend/`), el de la raíz en la carpeta misma, y los vinculados en `@<nombre>/`. Se crean de fuera adentro.
- Si falla uno, se deshacen los ya creados y la tarea pasa a «workspace_failed».
- Al soltar la tarea: cada repositorio commitea lo que queda suelto (sin recoger los worktrees de otros repositorios que hay dentro) y se borra su worktree, de dentro afuera. **En una tarea con varios repositorios, las ramas sin commits se borran** (y su fila); con uno se conservan siempre, como antes.
- **Lo que no está en ningún repositorio** (ficheros sueltos de la raíz cuando esta no es un repositorio) no se copia a la carpeta de trabajo. Si el agente escribe ahí, la carpeta **no se borra** y la tarea deja un evento que lo dice: no se destruyen datos.

### Ejecuciones: instantáneas y diffs por repositorio
`run_repos` (`RunRepo`) sustituye a `runs.snapshot_*`: por cada repositorio de la ejecución guarda la carpeta, los dos sha, los ficheros grandes excluidos, el resumen +/− y, más adelante, el registro de git. `runs.changes_*` es la suma. `tasks.base_commit` pasa a `task_repos`.
- **Qué repositorios ve una ejecución** (`services/runrepos.py`): los de su `TaskRepo` si la tarea tiene worktrees; si no, todos los del proyecto que existan. Los vinculados fuera de la carpeta de la ejecución se pasan al CLI como directorios extra (`--add-dir` en Claude Code y en agy).
- **Repositorios anidados**: la instantánea de un repositorio deja fuera (`:(exclude)`) los repositorios que tiene dentro, o git los tomaría por submódulos.
- Las referencias `refs/agentic-os/runs/<id>/{start,end}` se crean en **cada repositorio** (son espacios de nombres distintos), y se borran por repositorio.
- **API**: `Changes` pasa a llevar `repos[]` (cada uno con su lista de ficheros, sus referencias y sus totales) y los totales sumados. Los endpoints de fichero y de líneas reciben `repo` (el id del repositorio), obligatorio si hay varios (`422 repo_required`). Un fichero que no cambió en ese repositorio es un 404.
- **Diff de tarea**: con worktree, uno por `TaskRepo`; en carpeta directa, por repositorio, desde la instantánea inicial de su primera ejecución. Un repositorio sin cambios no sale en el diff de la tarea.

### Limpieza (fase 8 y 11)
Las ramas `agentic/` se listan y borran por repositorio (`repo_id`; con el mismo nombre en dos repositorios hay que decir cuál). Las instantáneas se purgan por `RunRepo`, en el repositorio donde se tomaron.

## Consecuencias
- Un proyecto con repositorios dentro pero cuya raíz no es un repositorio, que antes era «sin git», ahora admite modo worktree, diffs y limpieza de ramas.
- **Límite**: en modo worktree con varios repositorios, un agente no ve los ficheros de la raíz que no son de ningún repositorio.
- **Coste**: `repos.ensure` recorre la carpeta cada vez que un proyecto sin ningún repositorio lanza una ejecución (hasta profundidad 3, sin entrar en carpetas pesadas). Si resultara caro se guardará cuándo se miró por última vez.
- Las referencias de las instantáneas siguen apareciendo en `git log --all` (ADR 0015); la pestaña Git (bloque 2) las filtra.
