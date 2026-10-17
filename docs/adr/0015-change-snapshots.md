# ADR 0015: Instantáneas de cambios

- **Estado**: aceptado
- **Fecha**: 2026-10-15
- **Contexto de decisión**: fase 11 ([`spec.md`](../phases/11-revision-codigo/spec.md), [`plan.md`](../phases/11-revision-codigo/plan.md))

## Contexto
Para revisar el trabajo de un agente hay que ver qué ha cambiado. Con git se puede saber lo que hay en una rama, pero no basta:
- **por ejecución**: los agentes commitean cuando quieren y una ejecución puede dejar trabajo sin commitear que continúa la siguiente (QA tras un rechazo, la vuelta de Dev). El diff de una ejecución no es el de ningún commit ni el de `git status`;
- **en carpeta directa** (ADR 0009) no hay rama de la tarea, y la carpeta puede tener cambios del usuario sin commitear de antes;
- **tras el worktree**: al terminar la tarea se borra la carpeta (ADR 0009) y solo queda la rama; el estado de cada ejecución ya no existe.

Hay que decidir qué se guarda, dónde, cómo se calculan los diffs y cuándo se limpia, sin tocar el índice, la rama ni los ficheros del usuario.

## Decisión

### Qué es una instantánea
Un **commit sin rama** que contiene la carpeta tal como está en ese momento: lo commiteado, lo modificado sin commitear y los ficheros nuevos no ignorados (`services/snapshots.py`).

Se toma con un **índice temporal**, para no tocar el real:
1. se copia el índice de la carpeta a un fichero temporal en `<datos>/tmp/`;
2. con `GIT_INDEX_FILE=<temporal>`: `git add -A` (respeta `.gitignore` y `info/exclude`) y `git write-tree`;
3. `git commit-tree` con el `HEAD` como padre, la identidad `Agentic OS <agentic-os@localhost>` y `commit.gpgsign=false`;
4. se borra el temporal.

El índice real, `HEAD`, las ramas y los ficheros quedan **igual** (lo comprueba un test con `git status` antes y después).

**Copiar el índice y no empezar de uno vacío** conserva la caché de `stat` de git: `git add -A` solo vuelve a leer lo que ha cambiado, como un `git status`. Medido en git 2.55 sobre Windows: 0,27 s frente a 0,80 s en un repositorio de 10 000 ficheros, y 0,41 s frente a 1,31 s en este repositorio.

### Dónde se guardan
En **el repositorio del proyecto**, bajo referencias propias: `refs/agentic-os/runs/<run>/start` y `.../end`.
- No son ramas ni tags: `git branch`, `git tag` y un `git push` normal no las ven.
- Mantienen vivos los commits ante `git gc`, y sobreviven al borrado del worktree de la tarea (los worktrees comparten las referencias del repositorio).
- En la base de datos solo se guardan los sha (`runs.snapshot_start`/`snapshot_end`) y el **resumen** +/− de cada ejecución (`runs.changes_*`), para llenar listas sin recalcular diffs.

**Alternativa descartada: un almacén aparte** en la carpeta de datos. Dependería de objetos del repositorio del usuario que un `git gc` puede borrar si ninguna referencia los mantiene; habría que copiarlos todos, y duplicaría el repositorio.

**Contrapartida aceptada**: las referencias aparecen en `git log --all` y en vistas como `gitk --all`. Se limpian con los logs y desde Ajustes › Limpieza.

### Cuándo se toman
- **Al empezar** una ejecución, justo antes de arrancar el CLI y después de que el adapter escriba lo suyo (el plugin de agy va excluido de git, ADR 0009).
- **Al terminar**, cuando el CLI ya ha cerrado y **antes** de que el scheduler cierre la tarea (que commitea lo suelto y borra el worktree).
- **Al reabrir la app**, para las ejecuciones que quedaron activas (`interrupted`): su diff termina donde está ahora la carpeta y se marca como parcial.

Una instantánea que falla (repositorio roto, 30 s de tiempo máximo) **nunca impide lanzar ni terminar la ejecución**: deja un evento `snapshot_failed` y la ejecución no tiene diff.

Los ficheros **nuevos** de más de 5 MB no entran (se cuentan y la cabecera del diff lo avisa), para que un `node_modules` sin ignorar no llene el repositorio.

### Entre qué extremos se compara
| Diff | Origen | Final |
|---|---|---|
| Ejecución | su instantánea inicial | su instantánea final (viva: la carpeta ahora) |
| Tarea con worktree | el commit de la rama base del que salió (`tasks.base_commit`; en tareas anteriores, el *merge-base*) | la última instantánea final de la tarea o, si ya no existe, la punta de su rama |
| Tarea en carpeta directa | la instantánea inicial de su primera ejecución | la final de la última |

En carpeta directa el diff incluye todo lo que cambió mientras corrían las ejecuciones, también si lo tocó el usuario; la cabecera lo avisa. **No incluye** lo que ya estaba antes de empezar, aunque no estuviera commiteado.

Si la primera ejecución de una tarea en carpeta directa ya no tiene instantáneas (o es anterior a la fase), el diff de la tarea **no se ofrece**: uno que empezara en la siguiente pasaría por completo.

### Cómo se calculan los diffs
Nunca se guardan: los calcula git al pedirlos, con `--ignore-cr-at-eol` (un fichero que solo cambia de CRLF a LF no es un cambio) y `-M` (renombrados).
- La **lista de ficheros** sale de `--numstat` y `--name-status`; el **contenido** de cada fichero se pide al desplegarlo, así que un diff grande no se carga entero.
- Las rutas que llegan de la UI se validan: relativas, sin `..` ni unidad, y se pasan con `GIT_LITERAL_PATHSPECS=1`. Una ruta que **no cambia en el rango** es un 404, así que la API no sirve para leer ficheros cualquiera del repositorio.
- Límites: 500 ficheros en la lista, 20 000 líneas por fichero (más: sin contenido) y los ficheros generados (lockfiles, `dist/`, `build/`, minificados) llegan marcados para mostrarse plegados.
- Las vistas que se consultan a menudo (Peticiones) guardan en memoria el total de cada tarea hasta que cambie la tarea o una de sus ejecuciones.

### Limpieza
- La **purga de logs** (fase 08) borra también las referencias de las ejecuciones que purga y olvida sus sha. El resumen +/− se conserva, pero su diff ya no está.
- **Borrar un proyecto** de la app borra las referencias de su repositorio (la carpeta nunca se toca).
- **Ajustes › Limpieza** lista las ejecuciones con instantáneas por proyecto y permite borrarlas.
- Una ejecución que tuvo diff y ya no lo tiene (resumen guardado o purgada) se muestra como «ya no hay datos»; una anterior a la fase, como «no hay datos».

### Detalles de la implementación que importan
- **Ficheros grandes**: se excluyen del propio `git add` (con una lista de pathspecs `:(exclude,literal)…` por la entrada estándar), así que git ni los lee ni los guarda.
- **Alcance**: la instantánea cubre la carpeta de la ejecución (`git add -A .`); en un proyecto que es una subcarpeta de un repositorio, lo que cambie fuera de ella no aparece.
- **Ejecución en marcha**: cada petición no hace una instantánea nueva; la del «ahora» se reutiliza unos 4 s, de modo que la lista de ficheros, el diff de un fichero y sus líneas de contexto (peticiones distintas) comparan el mismo estado, y el sondeo cada 5 s no recorre la carpeta cada vez.
- **Borrado**: cada proyecto borra solo las referencias de **sus** ejecuciones, aunque otro proyecto use el mismo repositorio.
- **Una tarea cuya última ejecución no dejó instantánea final** (cayó, o falló la instantánea) muestra, en un worktree, la punta de su rama y no el final de una ejecución anterior, que pasaría por el total.
- **Saltos de línea**: el diff se trocea solo por `\n` y cada *hunk* se lee por los contadores de su cabecera, de modo que un formfeed, U+2028 o `diff.suppressBlankEmpty` no desalinean las líneas.

## Consecuencias
- ✅ El diff de cada ejecución es exacto aunque el agente commitee a mitad o deje trabajo sin commitear, y el de una tarea coincide con `git diff <base>..<rama>` también después de borrarse el worktree (verificado e2e con el CLI falso).
- ✅ Sin tocar el índice, la rama ni los ficheros, y sin esperar más que un `git status`.
- ✅ Funciona en carpeta directa, donde no hay rama que comparar.
- ⚠️ Las referencias ocupan espacio en el repositorio del usuario hasta que se limpian, y aparecen en `git log --all`.
- ⚠️ Si se borra el repositorio o se vuelve a clonar, las instantáneas se pierden y el diff muestra «ya no hay datos».
- ⚠️ En carpeta directa no se distingue lo que cambió el agente de lo que cambió el usuario durante la ejecución.
- ⚠️ La instantánea final se toma en el hilo del PTY antes de avisar al scheduler, con un máximo de 30 s: en un repositorio enorme y con la caché fría, la tarea tarda en pasar a la siguiente etapa. Al reabrir la app, las ejecuciones que quedaron activas se cierran una tras otra con el mismo límite.
- ⚠️ El total de una tarea para Peticiones se guarda en memoria con una clave que no incluye la punta de la rama: si alguien commitea a mano en la rama de una tarea ya terminada, el número tarda en reflejarse hasta que cambie la tarea.
- ⚠️ Una ejecución interrumpida (cierre de la app, caída) no tiene instantánea final real: su diff llega hasta el estado de la carpeta al reabrir y se marca como parcial.
