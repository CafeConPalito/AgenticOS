# Fase 12: Control de git · Spec

- **Estado**: aprobada (2026-10-17)
- **Rama**: `phase/12-control-git`

## Objetivo
**Control total de git desde la app**, sin necesitar otra herramienta: estado, ramas, historial con grafo, commits por líneas, merge y rebase (también interactivo) con resolución de conflictos en la app, stash, tags, cherry-pick, revert, reset, remotos, submódulos, LFS, clonar e inicializar, y pull requests de GitHub y GitLab. Los **agentes pueden usar git sin ninguna restricción**: la app no les pone reglas y no les pregunta permiso por los comandos de git. Y un proyecto deja de tener un único git: **puede tener varios repositorios** (p. ej. `backend/` y `frontend/`, cada uno con el suyo), y todo lo anterior, incluidos los worktrees de las tareas y los diffs de la fase 11, funciona por repositorio.

## Punto de partida
- **Un repo por proyecto**: `services/git.py` mira solo la carpeta del proyecto (`GitInfo`: si es repo, rama, si hay cambios). Si la raíz no es un repo, el proyecto cuenta como «sin git», aunque dentro haya varios.
- **Worktrees** (ADR 0009): cada tarea trabaja en `<proyecto>.wt\T-142`, rama `agentic/T-142` desde la **rama base** del proyecto (una sola). Al terminar, lo que queda sin commitear se commitea, se borra el worktree y la rama se conserva. Integrarla es cosa del usuario, fuera de la app.
- **Carpeta directa**: la tarea trabaja en la carpeta del proyecto, en la rama que esté activa.
- **Permisos de los agentes**: según su modo (`bypassPermissions`, `acceptEdits`, `manual`), el CLI puede preguntar antes de un `git push` o un `git commit`; la pregunta llega como petición de permiso (fase 06) y la tarea espera.
- **Fase 11**: instantáneas en `refs/agentic-os/…` y diffs de tarea y de ejecución, ambos de **un solo repo**. Esas referencias salen en `git log --all` y hay que filtrarlas. El visor de diffs se reutiliza.
- **Terminales** (fase 03): PTY con xterm.js, reutilizable para abrir una terminal en un repo.

## Alcance
### Dentro

#### 1. Proyectos con varios repositorios
- **Repositorios de un proyecto**:
  - se **detectan solos** al crear el proyecto y al pulsar «Volver a buscar»: la raíz, si es repo, y los repos que haya dentro de la carpeta (hasta una profundidad configurable, por defecto 3, sin entrar en `node_modules`, `.venv` ni carpetas ignoradas);
  - se pueden **añadir a mano** repos **fuera de la carpeta del proyecto** («repos vinculados»), y quitar cualquiera de la lista sin tocar el disco;
  - cada repo tiene nombre (por defecto, su ruta relativa), **rama base propia** y si participa en las tareas (por defecto, sí);
  - los **submódulos** se muestran dentro de su repo padre, no como repos sueltos.
- **Proyecto sin ningún repo**: sigue funcionando como hoy. Se ofrece «Inicializar repositorio» o «Clonar aquí».
- **Worktrees con varios repos**: al empezar una tarea en modo worktree se crea una **carpeta de trabajo** `<proyecto>.wt\T-142` que reproduce la estructura del proyecto: cada repo que participa tiene su worktree en su ruta relativa, en su rama `agentic/T-142` creada desde **su** base. Lo que no está en ningún repo (ficheros sueltos de la raíz) se trata según el plan (ver riesgos). Al terminar, cada repo se cierra como hoy y las ramas que no tengan cambios se borran.
- **Repos vinculados en las ejecuciones**: el agente recibe acceso a su carpeta (en Claude Code, `--add-dir`; en agy, según lo que permita) y la tiene en su contexto.
- **Diffs de la fase 11 por repo**: instantáneas, diff de tarea y de ejecución y resúmenes +/− se calculan en cada repo; el visor agrupa los ficheros por repo, con totales por repo y en total.
- **Contexto del agente**: la lista de repos del proyecto, su ruta, su rama de trabajo y su base.

#### 2. Pestaña «Git» del proyecto
- **Vista general** (con varios repos): una fila por repo con rama actual, ahead/behind, cambios sin commitear, operación a medias y último fetch. **Acciones en lote**: fetch, pull y push de todos; commit en varios repos con el mismo mensaje; crear o cambiar a una rama del mismo nombre en todos.
- **Vista de un repo**, con estas secciones:
  - **Cambios**: ficheros modificados, nuevos, borrados y en conflicto, con su diff; **preparar (*stage*) y quitar por fichero, por bloque (*hunk*) y por línea**; descartar por fichero, bloque o línea; `.gitignore` desde la lista («Ignorar este fichero o patrón»).
  - **Commit**: mensaje con vista de resumen y cuerpo, **enmendar** el último commit, firmar (GPG o SSH, si está configurado), saltar los hooks con confirmación.
  - **Historial con grafo**: todas las ramas o las elegidas, con su grafo de ramas y merges; mensaje, autor, fecha, hash, ramas y tags; búsqueda por mensaje, autor, fichero y hash; paginado; sin `refs/agentic-os/`. Al hacer clic, el diff del commit. Desde un commit: **cherry-pick, revert, reset (soft, mixed, hard) a él, crear rama o tag** y comparar con otro commit o rama.
  - **Historial de un fichero y *blame*** (quién cambió cada línea, con su commit y su agente).
  - **Ramas**: locales y remotas, con último commit y ahead/behind frente a su remoto y frente a la base; las `agentic/T-n` con su tarea y su estado (en curso · en revisión · aprobada · terminada · **integrada** · cancelada); crear, cambiar, renombrar, borrar (también varias, y las ya integradas de una vez), fijar su remoto y comparar dos ramas.
  - **Merge y rebase**: de cualquier rama en cualquier otra; merge con o sin *fast-forward* o *squash*; **rebase interactivo** visual (reordenar, juntar, editar mensaje, partir, descartar commits).
  - **Conflictos**: **editor de tres vías en la app** (la nuestra, la suya y el resultado, con «Aceptar nuestra / suya / ambas» por bloque y edición libre), marcar como resuelto, continuar, saltar o abortar el merge, rebase o cherry-pick. Alternativa: **«Pasárselos a un agente»**, que crea una tarea de resolución con el agente elegido.
  - **Stash**: guardar (con o sin ficheros nuevos, con mensaje), lista, ver su diff, aplicar, aplicar y quitar, crear una rama desde él, borrar.
  - **Tags**: ligeros y anotados, lista, borrar, subir y borrar en el remoto.
  - **Remotos**: añadir, editar la URL, renombrar y quitar; fetch (con `--prune`), pull (*fast-forward*, merge o rebase, a elegir y con valor por defecto por repo) y push, incluido **push forzado** (`--force-with-lease`) con confirmación que dice qué se sobrescribe.
  - **Submódulos**: lista con su commit y si va desfasado; inicializar, actualizar, cambiar el commit que apunta, añadir y quitar.
  - **LFS**: si está instalado, ficheros seguidos, patrones (`track`/`untrack`), pull y estado; aviso si el repo usa LFS y no está instalado.
  - **Worktrees**: lista de los worktrees del repo (incluidos los de las tareas), abrir su carpeta, quitar y `prune`.
  - **Reflog y deshacer**: el reflog de `HEAD` y de cada rama, y **«Deshacer»** de la última operación de la app que haya movido una rama (reset, rebase, merge, borrado de rama), volviendo a su estado anterior.
  - **Mantenimiento**: `clean` (con vista previa de lo que se borra), `gc` y verificación del repo.
  - **Terminal git**: abrir una terminal (la de la fase 03) en la carpeta del repo para cualquier cosa que la interfaz no cubra (`bisect`, `filter-repo`, alias propios…). La pestaña se refresca sola al cerrarla.
- **Configuración del repo y global**: identidad (`user.name`, `user.email`), firma de commits, ramas por defecto y opciones comunes de pull, en una pantalla; el resto con el editor de configuración.
- **Clonar e inicializar**: «Nuevo proyecto › Clonar desde URL» crea la carpeta y el proyecto; dentro de un proyecto, «Clonar aquí» o «Inicializar» en una subcarpeta añade el repo a su lista.

#### 3. Tareas y git
- **Integrar la rama de una tarea** desde el detalle de la tarea y desde la pestaña Git («Integrar en las bases»): en cada repo con cambios de la tarea, merge (`--no-ff` con mensaje que cita la tarea), *squash* o rebase y *fast-forward*; modo por defecto en los ajustes del proyecto.
  - Si no se puede integrar en la carpeta del usuario (la base no está activa allí o tiene cambios que chocan), se integra en un worktree temporal sin tocar su carpeta, o se avisa (ver riesgos).
  - **Con varios repos**, cada uno se integra por separado y se ve su resultado. Si uno tiene conflictos, se elige entre resolverlos (editor o agente) o **deshacer los ya integrados** en esa operación (antes de subir nada).
  - Tras integrar: subir las bases, abrir un pull request en su lugar y borrar las ramas de la tarea, a elegir. Todo queda en el historial de la tarea.
- **Al aprobar una tarea** (ajuste del proyecto, desactivado por defecto): integrar sola, integrar y subir, o abrir un pull request.
- **Tarea de resolución de conflictos**: tarea suelta, sin pipeline, con el agente elegido. Trabaja en la rama de la tarea original, lleva a ella la base y resuelve los conflictos. Al terminar se vuelve a ofrecer la integración.

#### 4. Pull requests (GitHub y GitLab)
- Detecta el servicio por la URL del remoto.
- **Crear** un pull request (merge request en GitLab) desde una rama, también desde la tarea: título y descripción a partir de la tarea, su resumen y sus cambios; borrador o no; rama destino.
- **Lista y detalle**: estado, checks de CI, revisiones y comentarios (solo lectura), enlace al navegador.
- **Acciones**: fusionar (merge, squash o rebase), cerrar y reabrir; actualizar la rama con su destino.
- Autenticación con `gh` y `glab` si están instalados y con sesión iniciada, o con un token guardado de forma segura (Credential Manager de Windows). El mecanismo se decide en el plan.

#### 5. Credenciales y claves
- Se usan las credenciales que ya tenga el sistema (Git Credential Manager, agente SSH). Git se lanza sin terminal (`GIT_TERMINAL_PROMPT=0`) para que nunca se quede esperando: si falta una credencial, la UI lo dice y Git Credential Manager muestra su ventana.
- **Claves SSH**: ver las claves de `~/.ssh`, generar una nueva (ed25519), copiar su parte pública y probar la conexión con GitHub, GitLab o un host cualquiera.
- **Prueba de remoto**: «Probar conexión» en cada remoto.

#### 6. Agentes con git sin restricciones
- **Sin reglas ni bloqueos de git**: los agentes pueden commitear, crear y borrar ramas, hacer merge y rebase, reescribir historial, subir (también forzado), crear tags y pull requests, en cualquier rama y en cualquier repo del proyecto.
- **Sin preguntas de permiso por git**: los comandos de git quedan autorizados de antemano en el CLI sea cual sea el modo de permisos del agente (p. ej. `Bash(git:*)` en Claude Code; lo equivalente en agy). Ajuste por proyecto «Autorizar git a los agentes», activado por defecto, para quien prefiera que el CLI pregunte.
- **Instrucciones**: el contexto les dice que pueden usar git libremente, en qué repos y ramas trabajan y que, si commitean, lo hagan en su rama de trabajo de cada repo.
- **Lo que hizo cada ejecución con git** (registro, no control): al terminar cada ejecución se anotan, por repo, sus commits, las ramas y tags creados, movidos o borrados y lo que subió al remoto (comparando las referencias al empezar y al terminar). Se ve en la página de la ejecución y en el historial de la tarea.
- **Atribución de commits**: un commit es de un agente si se creó durante una de sus ejecuciones, en un repo de su carpeta de trabajo. El historial, el grafo y el *blame* lo muestran con el nombre del agente, la tarea y la ejecución; lo demás es del usuario. Los commits anteriores a la fase en ramas `agentic/T-n` se atribuyen a la tarea.
- **Convivencia con la app**: la pestaña Git refleja lo que hagan los agentes (se refresca al terminar cada ejecución y al volver a la pestaña). Las acciones del usuario en un repo con una ejecución viva se permiten con un aviso.

#### 7. Transversal
- **Seguridad de los datos del usuario**: toda operación de la app que pueda perder trabajo (reset `--hard`, descartar, `clean`, borrar rama no integrada, push forzado, abortar) pide confirmación diciendo qué se pierde, y antes de ejecutarse guarda una referencia de respaldo para «Deshacer». La app nunca hace un push forzado por su cuenta.
- **Operaciones**: las de escritura se serializan por repo; las largas (clonar, fetch, push, gc) muestran progreso, se pueden cancelar y no bloquean la UI. Errores de git con un mensaje claro.
- **API REST** para todo lo anterior y **eventos en vivo** (WS) del progreso y de los cambios de estado de los repos.
- **Migración de Alembic**: repos del proyecto (ruta, nombre, base, participa, vinculado), ajustes de git del proyecto, ramas y worktrees de una tarea por repo, instantáneas por repo, registro git de cada ejecución y atribución commit → ejecución. Los proyectos existentes pasan a tener un repo (la raíz) con su base actual.
- Textos en i18n; tests de backend con repos reales (varios repos, repos vinculados, submódulos, LFS si está instalado, remoto *bare* local para fetch/pull/push, conflictos, rebase interactivo, deshacer) y con el CLI falso; tests de frontend.
- **ADRs**: proyectos con varios repos (modelo, detección y worktrees de tarea); operaciones de git de la app (ejecución, serialización, respaldos y deshacer); pull requests y credenciales.

### Fuera
- Otros servicios de pull requests (Bitbucket, Azure DevOps, Gitea): se pueden añadir sobre el mismo diseño en una fase futura.
- Escribir comentarios y aprobar revisiones de pull requests desde la app (se leen, no se escriben).
- Otros sistemas de control de versiones (Mercurial, SVN…).
- Reglas o restricciones de git para los agentes: por decisión del usuario, los agentes tienen acceso completo. Si se quieren más adelante, iría en otra fase.

## Historias de usuario
- Como usuario, quiero hacer desde la app cualquier operación de git (commit por líneas, rebase interactivo, stash, cherry-pick, tags, resolver conflictos…), para no tener que salir a otra herramienta.
- Como usuario de un proyecto con varios repositorios, quiero ver todos sus repos juntos y operar en uno o en todos a la vez, y que las tareas trabajen en todos ellos, para gestionar un proyecto de varios repos como uno solo.
- Como usuario, quiero integrar la rama de una tarea aprobada en las bases de todos sus repos y subirla o abrir un pull request desde la app, para cerrar el trabajo de un agente en un paso.
- Como usuario, quiero que los agentes usen git sin pedirme permiso ni chocar con reglas, para que trabajen sin pararse.
- Como usuario, quiero ver qué commits hizo cada agente y qué hizo cada ejecución con git (ramas, pushes…), para saber quién cambió qué aunque tengan vía libre.
- Como usuario, quiero poder deshacer una operación de git que he hecho desde la app, para no tener miedo a equivocarme.
- Como usuario, quiero resolver los conflictos en la app o pasárselos a un agente.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Un proyecto cuya raíz no es un repo y que contiene dos repos, más un repo vinculado fuera de su carpeta, los detecta o los admite, muestra su vista general y permite fetch, pull, push y commit en lote | Tests con repos reales + prueba manual |
| CA2 | Una tarea en modo worktree de ese proyecto trabaja en una carpeta con un worktree por repo, cada uno en su `agentic/T-n` desde su base; el diff de la tarea y de cada ejecución agrupa los cambios por repo y coincide con `git diff` en cada uno | Tests con el CLI falso |
| CA3 | Desde la app se integra la rama de una tarea aprobada en las bases de sus repos (merge, squash y rebase) y se sube o se abre un pull request; con conflictos en un repo se pueden resolver en el editor, pasar a un agente o deshacer lo ya integrado | Tests con repos reales y remoto *bare* + prueba manual con GitHub |
| CA4 | Funcionan desde la app: stage y descarte por fichero, bloque y línea; commit y enmienda; stash; tags; cherry-pick, revert y reset; crear, renombrar, borrar y comparar ramas; rebase interactivo (reordenar, juntar, editar, partir, descartar); remotos; push forzado con confirmación; submódulos; LFS (si está instalado); worktrees; clean y gc | Tests de API y de UI por operación |
| CA5 | El historial con grafo, el *blame* y la lista de ramas coinciden con `git log --graph`, `git blame` y `git branch -vv` (sin `refs/agentic-os/`), y los commits de cada agente aparecen con su agente, tarea y ejecución | Tests |
| CA6 | El editor de tres vías resuelve los conflictos de un merge, un rebase y un cherry-pick, y se puede continuar o abortar cada uno | Tests de UI + prueba manual |
| CA7 | «Deshacer» devuelve la rama a su estado anterior tras un reset `--hard`, un rebase, un merge y un borrado de rama hechos desde la app | Tests |
| CA8 | Un agente de Claude Code en modo `manual` commitea, crea una rama, hace rebase y push (también forzado) sin que el CLI pregunte ni la app lo impida; la ejecución registra sus commits, ramas y pushes | Tests con el CLI falso + prueba manual con Claude Code |
| CA9 | Clonar desde una URL crea el proyecto; inicializar o clonar dentro de un proyecto añade el repo; los proyectos existentes conservan su repo y su base tras la migración | Tests |
| CA10 | Las operaciones largas muestran progreso, se pueden cancelar y no bloquean la UI; los errores (sin red, sin credenciales, push rechazado) se ven con un mensaje claro y git nunca se queda esperando una contraseña | Tests + prueba manual |
| CA11 | Lint, tests de backend y de frontend en verde; `/code-review` resuelto | CI local |

## Prerrequisitos
- Fase 11 cerrada (`v1.3`).
- git instalado. Para las pruebas manuales: un remoto real en GitHub (y GitLab, si es posible) con credenciales, `gh` instalado y git-lfs instalado.

## Riesgos y preguntas abiertas
- **Tamaño de la fase**: es la más grande hasta ahora (varios repos, toda la superficie de git, editor de conflictos, pull requests). Propuesta: un único spec, pero el plan la divide en **bloques que se cierran por separado dentro de la rama** (1: varios repos y migración; 2: estado, cambios, commit, ramas, historial; 3: merge, rebase, conflictos, deshacer; 4: stash, tags, cherry-pick, remotos, submódulos, LFS, worktrees, mantenimiento; 5: tareas e integración; 6: pull requests y credenciales; 7: agentes). Si al planificar sale demasiado grande, se propondrá partirla en dos fases.
- **Ficheros fuera de los repos en el worktree de una tarea**: si la raíz del proyecto no es un repo, sus ficheros sueltos no tienen worktree. Opciones: no estarán en la carpeta de la tarea; copiarlos; o enlazarlos. Propuesta: no se incluyen y se avisa en la configuración del proyecto; el agente los ve en su contexto como ruta del proyecto original.
- **Repos vinculados y agy**: Claude Code tiene `--add-dir`; hay que comprobar en el plan cómo da acceso agy a una carpeta fuera del workspace. Si no puede, los repos vinculados no estarán disponibles para agentes de agy, y se avisa.
- **Integración en la carpeta del usuario**: git no deja tener la misma rama en dos carpetas. Si la base está activa en la carpeta del proyecto, se integra ahí (si está limpia); si no lo está, en un worktree temporal que actualiza la base sin tocar su carpeta.
- **Agentes sin restricciones**: un agente puede reescribir historial o hacer un push forzado de la base. La app no lo impide (decisión del usuario); lo mitiga el registro de cada ejecución y el reflog. «Deshacer» solo cubre las operaciones hechas desde la app, no las de los agentes; ¿se quiere también un «Deshacer lo que hizo esta ejecución» a partir de las referencias guardadas al empezar? Propuesta: sí, para las ramas locales (lo subido no se puede deshacer desde aquí).
- **Autorizar git en agy**: hay que comprobar en el plan cómo preautorizar comandos concretos en agy (en el spike solo se probaron los modos generales).
- **Editor de tres vías y rebase interactivo**: son las piezas de UI más costosas. El editor se apoya en el visor de la fase 11; puede que haga falta un componente de edición de texto (p. ej. CodeMirror). Se decide en el plan.
- **Pull requests**: `gh`/`glab` reutilizan la sesión del usuario pero añaden una dependencia; un token propio exige guardarlo de forma segura. Se decide en el plan.
- **Rendimiento**: la vista general hace `git status` en cada repo; con muchos repos o repos grandes hay que cachear y refrescar bajo demanda. El grafo del historial necesita paginar sin perder las líneas del grafo.
- **Migración de la fase 11**: las instantáneas y los resúmenes existentes son de un repo; pasan a ser del repo raíz del proyecto.
