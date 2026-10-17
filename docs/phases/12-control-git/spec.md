# Fase 12: Control de git · Spec

- **Estado**: borrador
- **Rama**: `phase/12-control-git`

## Objetivo
Llevar el **git de cada proyecto desde la app**: ver en qué estado está el repositorio, qué ramas hay (las de las tareas con su tarea y su estado), quién hizo cada commit, e **integrar la rama de una tarea aprobada en la base y subirla al remoto** sin abrir otra herramienta. A la vez, que cada proyecto decida **qué pueden hacer los agentes con git** (commitear sí, subir no…) y que esas reglas se cumplan, no solo se pidan. Los agentes siguen commiteando como hasta ahora.

## Punto de partida
- **Detección**: `services/git.py` calcula al vuelo si la carpeta es un repo, la rama actual y si hay cambios (`GitInfo`). El Resumen del proyecto lo muestra; no hay más git en la UI.
- **Worktrees** (ADR 0009): cada tarea trabaja en `<proyecto>.wt\T-142`, rama `agentic/T-142`, creada desde la **rama base** del proyecto. Al terminar o cancelar, lo que quede sin commitear se commitea en la rama, se borra el worktree y **la rama se conserva**. Hoy integrarla es cosa del usuario, fuera de la app.
- **Carpeta directa**: la tarea trabaja en la carpeta del proyecto, en la rama que esté activa.
- **Instrucciones**: el contexto le dice al agente su rama de trabajo, pero no le da ni le quita permisos de git. Lo que el CLI pregunte (p. ej. «Bash: git push») llega como petición de permiso (fase 06).
- **Hooks**: el `hook.cmd` de cada ejecución siempre termina con 0 (solo informa). En agy, un hook que falla **bloquea la herramienta** (spike, fase 01); Claude Code permite denegar desde `PreToolUse`.
- **Fase 11**: instantáneas en `refs/agentic-os/…`, visor de diffs reutilizable y `git.merge_base`. Esas referencias salen en `git log --all` y hay que filtrarlas.

## Alcance
### Dentro

**Pestaña «Git» del proyecto** (nueva, junto a Resumen, Tareas, Pipeline, Memoria y Ajustes)
- **Estado del repo**:
  - rama actual, su remoto (*upstream*) y cuántos commits va por delante y por detrás (*ahead/behind*), con la hora del último fetch;
  - cambios sin commitear de la carpeta del proyecto: ficheros modificados, nuevos y borrados, con su diff en el visor de la fase 11;
  - aviso si hay una ejecución viva en esa carpeta (carpeta directa) o una operación a medias (merge o rebase interrumpido).
- **Ramas**:
  - locales y remotas, con su último commit, ahead/behind frente a su remoto y frente a la rama base;
  - las ramas `agentic/T-n` muestran su tarea (código, título, enlace) y su estado: en curso · en revisión · aprobada · terminada · **integrada** (ya contenida en la base) · cancelada;
  - filtro «Solo ramas de tareas» y «Sin integrar».
- **Historial de commits** de la rama elegida (por defecto la actual):
  - mensaje, autor, fecha, hash corto y ramas o tags que apuntan a él; sin las referencias `refs/agentic-os/`;
  - **quién lo hizo**: un agente (con su nombre, la tarea y la ejecución) o el usuario. Lo que no se pueda atribuir a una ejecución cuenta como del usuario;
  - al hacer clic, el diff del commit en el visor de la fase 11;
  - carga paginada (los repos grandes tienen miles de commits).

**Acciones del usuario**
- **Commit**: elegir ficheros (fichero entero, no por trozos), escribir el mensaje y commitear en la rama actual con la identidad git del usuario.
- **Ramas**: crear una rama (desde la actual o desde otra) y cambiar de rama. Cambiar con cambios sin commitear que choquen se impide con aviso, no se pierden.
- **Integrar la rama de una tarea** en la rama base, desde la pestaña Git y desde el detalle de la tarea («Integrar en `main`», visible cuando la tarea está aprobada o terminada y su rama no está integrada):
  - modo **merge** (por defecto, `--no-ff`, con mensaje que cita la tarea) o **rebase** de la rama de la tarea sobre la base seguido de *fast-forward*; el modo por defecto se elige en los ajustes del proyecto;
  - antes de empezar se comprueba que se puede: la carpeta de la base está limpia y no tiene ejecuciones vivas, y la tarea no tiene worktree activo;
  - si hay **conflictos**, la operación se deshace sola (la carpeta queda como estaba) y se muestra la lista de ficheros en conflicto con dos salidas: **«Pasárselos a un agente»** (crea una tarea de resolución, con el agente elegido, que lleva la base a la rama de la tarea y resuelve los conflictos en ella; cuando termina, se vuelve a integrar) o resolverlos fuera de la app;
  - tras integrar, se ofrece **subir** la base y **borrar la rama** de la tarea; el evento queda en el historial de la tarea.
- **Borrar ramas ya integradas**: una a una o todas las de tareas integradas a la vez, con confirmación. Nunca la rama actual, la base ni una rama con worktree o ejecución viva.
- **Descartar cambios** sin commitear: de un fichero o de todos, con confirmación que dice qué se pierde. Impedido si hay una ejecución viva en esa carpeta.
- **Fetch, pull y push**:
  - con las credenciales git que ya tenga el usuario (Git Credential Manager, SSH); la app no guarda credenciales;
  - pull por *fast-forward*; si no se puede, se avisa y se ofrece merge o rebase;
  - push de la rama actual o de una elegida, creando su remoto si no lo tiene. **Nunca forzado**;
  - errores de red o de autenticación con un mensaje claro, sin bloquear la UI (las operaciones largas muestran progreso y se pueden cancelar).

**Reglas de git para los agentes** (Ajustes del proyecto › Git)
- Cada regla con su valor por defecto:
  - **Commitear** en su rama de trabajo: sí;
  - **Subir** (push) al remoto: no;
  - **Crear ramas** nuevas: no;
  - **Tocar la rama base** (commitear, hacer merge o rebase en ella): no. En worktree se aplica a la base del proyecto; en carpeta directa, a la rama que estuviera activa al empezar la ejecución;
  - **Reescribir historial** (push forzado, `reset --hard`, rebase de commits ya subidos): no, y no se puede activar en esta fase.
- **Cómo se aplican**, en tres capas:
  1. **Instrucciones**: el contexto de cada ejecución dice qué puede y qué no puede hacer con git, y en qué rama trabaja;
  2. **Hooks del CLI**, donde el CLI lo permita: Claude Code deniega desde `PreToolUse` los comandos de git prohibidos; en agy, el hook falla para bloquear la herramienta. El agente recibe un motivo legible («Push desactivado en este proyecto»);
  3. **Hooks de git** de la ejecución (p. ej. `pre-push` y `pre-commit` vía configuración por variables de entorno del proceso del CLI), que paran la operación aunque el agente la lance de una forma que el hook del CLI no reconozca. Deben **encadenar los hooks propios del repo** (husky, pre-commit…) y no afectar al usuario cuando trabaja fuera de la app.
  
  El mecanismo concreto de cada capa se decide en el plan y queda en un ADR.
- Cada bloqueo queda como evento en la ejecución y en la tarea («Push bloqueado por las reglas del proyecto»). No crea una petición: la regla ya está decidida.

**Atribución de los commits**
- Un commit es de un agente si se creó **durante una de sus ejecuciones, en su carpeta de trabajo**. La app lo registra al terminar cada ejecución (con las instantáneas de la fase 11 o marcando los commits de la ejecución, a decidir en el plan) y guarda la relación commit → ejecución.
- Commits anteriores a la fase: los de las ramas `agentic/T-n` se atribuyen a la tarea (sin ejecución concreta); el resto, al usuario.

**Transversal**
- API REST: estado, ramas, historial (paginado), diff de un commit, y las acciones anteriores. Las operaciones de escritura se serializan por repositorio (una a la vez) y responden con errores claros cuando git falla.
- Migración de Alembic: reglas de git y modo de integración por proyecto; relación commit → ejecución.
- Textos en i18n; tests de backend con repos reales (worktree, carpeta directa, remoto local *bare* para fetch/pull/push, conflictos, ramas integradas) y con el CLI falso intentando un push prohibido; tests de frontend.
- ADR de control de git (operaciones de escritura, reglas y su aplicación, atribución).

### Fuera
- **Resolver conflictos dentro de la app** (editor de tres vías): se deshace y se pasa a un agente o se resuelve fuera.
- Stash, cherry-pick, revert, tags, submódulos, LFS, `git init` y clonar desde la app.
- Commit por trozos (*hunks*) o por líneas; enmendar commits; rebase interactivo.
- Push forzado y cualquier reescritura de historial desde la app.
- Pull requests y servicios del remoto (GitHub, GitLab…): se verán con las Conexiones MCP (fase 17) o en una fase futura.
- Grafo visual del historial (solo lista).
- Gestionar credenciales o claves SSH: se usan las del sistema.
- Reglas de git por agente (en esta fase son por proyecto) y reglas personalizadas por comando.
- Integración automática al aprobar una tarea (siempre la pide el usuario).

## Historias de usuario
- Como usuario, quiero integrar en `main` la rama de una tarea aprobada y subirla al remoto desde la app, para cerrar el trabajo de un agente sin abrir otra herramienta.
- Como usuario, quiero ver las ramas de un proyecto con su tarea y su estado, para saber qué está integrado, qué falta y qué puedo borrar.
- Como usuario, quiero ver en el historial qué commits hizo cada agente y cuáles yo, para entender quién cambió qué.
- Como usuario, quiero que, si al integrar hay conflictos, se los pueda pasar a un agente, para no tener que resolverlos yo a mano.
- Como usuario, quiero decidir por proyecto si los agentes pueden subir, crear ramas o tocar la rama base, y que se cumpla aunque el agente lo intente, para que no lleguen al remoto cambios que no he revisado.
- Como usuario, quiero commitear, cambiar de rama, descartar cambios y hacer fetch, pull y push desde la app, para las tareas habituales de git del día a día.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Desde la app se integra en `main` la rama de una tarea aprobada (merge y rebase) y se sube al remoto; la tarea pasa a «integrada» y su rama se puede borrar | Tests con repos reales y remoto *bare* + prueba manual |
| CA2 | Un agente commitea en su rama y la regla «sin push» le impide subirla, en Claude Code (hook del CLI) y por la capa de hooks de git; el bloqueo queda en la ejecución y en la tarea, y el remoto no cambia | Tests con el CLI falso + prueba manual con Claude Code |
| CA3 | Las reglas «no crear ramas» y «no tocar la rama base» bloquean al agente en worktree y en carpeta directa; con la regla «commitear» desactivada, el agente no puede commitear | Tests |
| CA4 | Los hooks propios del repo (p. ej. un `pre-commit` del usuario) siguen ejecutándose en las ejecuciones, y fuera de la app el repo se comporta igual que antes | Tests |
| CA5 | Una integración con conflictos deja la carpeta exactamente como estaba (`git status`, `HEAD` y ficheros), lista los ficheros en conflicto y «Pasárselos a un agente» crea una tarea que trabaja en la rama de la tarea; al terminar, se puede integrar sin conflictos | Tests con el CLI falso |
| CA6 | El estado (rama, ahead/behind, cambios), las ramas con su tarea y estado, y el historial coinciden con `git status`, `git branch -vv` y `git log` (sin `refs/agentic-os/`) | Tests |
| CA7 | El historial distingue los commits de cada agente (con su tarea y ejecución) de los del usuario, también en carpeta directa | Tests |
| CA8 | Commit, crear y cambiar de rama, descartar cambios, borrar ramas, fetch, pull y push funcionan; las acciones peligrosas piden confirmación y se impiden con una ejecución viva en la carpeta o con una operación a medias | Tests de API y de UI |
| CA9 | Los errores de git (sin red, sin credenciales, push rechazado, pull que no es *fast-forward*) se muestran con un mensaje claro y la UI no se bloquea; un proyecto sin git muestra su estado vacío | Tests + prueba manual |
| CA10 | Lint, tests de backend y de frontend en verde; `/code-review` resuelto | CI local |

## Prerrequisitos
- Fase 11 cerrada (`v1.3`).
- git instalado (ya lo exigen los worktrees). Para la prueba manual de push, un remoto real con credenciales configuradas.

## Riesgos y preguntas abiertas
- **Dónde se hace la integración**: git no deja tener la misma rama en dos carpetas. Si la base está activa en la carpeta del proyecto, el merge se hace ahí y exige que esté limpia; si no lo está (el usuario está en otra rama), ¿se integra en un worktree temporal y se actualiza la base sin tocar su carpeta? Propuesta: sí, worktree temporal cuando la base no está activa; carpeta del proyecto cuando lo está.
- **Carpeta directa y la rama del usuario**: el agente trabaja en la rama que el usuario tenga activa. La regla «no tocar la rama base» puede dejar al agente sin poder commitear si el usuario está en `main`. Propuesta: en carpeta directa, la regla se aplica solo si se activa explícitamente, y el ajuste lo explica.
- **Hooks de git por ejecución**: inyectarlos sin tocar la configuración del repo (variables `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n` con `core.hooksPath`) cambia dónde busca git los hooks del repo; hay que encadenar los del usuario (incluidos los de husky, que también usa `core.hooksPath`). Hay que validar en el plan que agy y Claude Code pasan el entorno a los comandos que lanzan.
- **Hooks del CLI que bloquean**: el `hook.cmd` actual siempre sale con 0. Bloquear exige que decida según el comando (el backend responde y el script devuelve el código o el JSON de denegación). Si el backend no responde, ¿se bloquea o se deja pasar? Propuesta: dejar pasar y confiar en la capa de hooks de git.
- **Detectar comandos de git** en un `Bash`/`PowerShell` arbitrario (`git -C x push`, alias, scripts) es imposible de cubrir del todo con el hook del CLI; por eso la capa de hooks de git es la que garantiza el criterio.
- **Atribución**: si el usuario commitea en la carpeta mientras corre una ejecución (carpeta directa), su commit se atribuiría al agente. Se acepta y se documenta, como en la fase 11.
- **Credenciales y prompts interactivos**: un push que pide usuario y contraseña colgaría el proceso. Hay que lanzar git sin terminal (`GIT_TERMINAL_PROMPT=0`) y dejar que Git Credential Manager muestre su propia ventana; medir qué pasa con SSH con frase de paso.
- **Tarea de resolución de conflictos**: ¿qué pipeline usa? Propuesta: una tarea suelta (sin pipeline) asignada al agente elegido, con instrucciones generadas y la rama de la tarea original como rama de trabajo.
