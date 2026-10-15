# Fase 11: Revisión de código · Spec

- **Estado**: aprobada (2026-10-15)
- **Rama**: `phase/11-revision-codigo`

## Objetivo
Ver **qué código ha cambiado cada agente** sin salir de la app: los ficheros tocados, cuántas líneas ha añadido y borrado y el diff línea a línea, como `git diff`. El diff se ve por tarea y por ejecución, justo donde se decide (al aprobar o rechazar una revisión y al recibir una entrega) y desde la ficha del agente. Hoy, para revisar el trabajo de un agente hay que abrir la rama `agentic/T-142` en otra herramienta, y en un proyecto de carpeta directa no hay forma de saber qué cambió cada ejecución.

## Punto de partida
- **Proyectos con worktree** (ADR 0009):
  - cada tarea trabaja en `<proyecto>.wt\T-142`, en la rama `agentic/T-142`, creada desde la **rama base**;
  - todas las etapas y reintentos comparten el worktree;
  - al terminar o cancelar, lo que quede sin commitear se commitea en la rama, se borra el worktree y **la rama se conserva** (`task.branch`).
  
  El diff de la tarea se puede sacar siempre de la rama frente a la rama base. Lo que hizo **cada ejecución** no: los agentes commitean cuando quieren y una ejecución puede dejar trabajo sin commitear que recoge la siguiente.
- **Proyectos de carpeta directa**: la tarea trabaja en la carpeta del proyecto, sin rama propia. Puede haber cambios del usuario sin commitear de antes y los agentes pueden commitear en la rama actual. Hoy no se guarda en qué estado estaba la carpeta al empezar.
- **Proyectos sin git**: la app no exige git (fase 02). En ellos no hay diff.
- **Dónde se decide hoy**:
  - la etapa con revisión deja la tarea «En revisión» y crea una petición `review` con «Aprobar» y «Rechazar» (Peticiones, «Te necesitan» de Inicio y detalle de tarea);
  - una tarea terminada crea una petición `delivery` («Marcar como revisado»).
  
  Ninguna enseña los cambios: solo el resumen de `complete_task`.
- La ficha del agente tiene las pestañas Resumen, General, Instrucciones, Ejecución e Historial.

## Alcance
### Dentro

**Captura de los cambios**
- Al **empezar y al terminar cada ejecución** en una carpeta con git (de tarea o manual), el backend toma una **instantánea** del estado de la carpeta:
  - incluye lo commiteado, lo modificado sin commitear y los ficheros nuevos no ignorados;
  - **no toca** el índice, la rama ni los ficheros del usuario ni del agente;
  - se guarda en el repositorio con referencias propias de Agentic OS, para que sobreviva al borrado del worktree y al `git gc`.
  
  El mecanismo concreto (commits sin rama con un índice temporal, nombres de las referencias…) se decide en el plan y queda en un ADR.
- **Diff de una ejecución**: de su instantánea inicial a la final. En una ejecución viva, de la inicial al estado actual.
- **Diff de una tarea**:
  - con worktree: de la rama base (su punto de partida, el *merge-base*) a la última instantánea de la tarea o, si no la hay, a la punta de su rama;
  - con carpeta directa: de la instantánea inicial de su primera ejecución a la última instantánea.
- **Resumen guardado** en cada ejecución al terminar: ficheros cambiados, líneas añadidas y borradas. Sirve para las listas sin recalcular diffs.
- **Limpieza**: las referencias de las instantáneas se borran cuando se purgan los logs de la ejecución (housekeeping de la fase 08) y al borrar el proyecto de la app. Se puede vaciar a mano desde Ajustes › Limpieza.
- **Tareas y ejecuciones anteriores a la fase**: sin instantáneas. Las tareas con worktree muestran el diff de su rama frente a la base; el resto, «No hay datos de cambios para esta ejecución».

**Visor de diffs**
- **Cabecera**: n ficheros · +añadidas · −borradas, y de qué a qué se compara («rama base `main` → `agentic/T-142`», «inicio → fin de la ejecución»).
- **Lista de ficheros**: ruta, estado (añadido · modificado · borrado · renombrado), +/− y una barra proporcional. Al hacer clic se salta al fichero.
- **Diff por fichero**, unificado, como `git diff`:
  - números de línea antigua y nueva;
  - líneas añadidas en verde, borradas en rojo y contexto en gris (tokens del tema, claro y oscuro);
  - bloques (*hunks*) con su cabecera y «Mostrar n líneas más» para ampliar el contexto;
  - cada fichero se puede plegar; los ficheros generados (lockfiles, `dist/`, minificados) aparecen plegados.
- **Casos especiales**: los ficheros binarios se indican sin mostrar el contenido («Binario · 24 KB → 31 KB»). Un fichero enorme o un diff con demasiados ficheros se trunca con aviso y se carga bajo demanda. Los finales de línea CRLF y LF no cuentan como cambio.
- **Estados vacíos**: «Sin cambios», «Este proyecto no usa git» y «No hay datos de cambios para esta ejecución».

**Dónde se ve**
- **Detalle de tarea**: nueva sección «Cambios» con el diff de la tarea y un selector para ver el de cada ejecución («Etapa Dev · intento 2 · hace 1 h»).
- **Revisión** (petición `review` en Peticiones, «Te necesitan» y detalle de tarea): junto a «Aprobar» y «Rechazar», un enlace «Ver cambios · 4 ficheros, +120 −35» que abre el visor de la tarea en un panel, con las mismas acciones al pie. Así se decide sin perder el sitio.
- **Entrega** (petición `delivery`): el mismo enlace junto a «Marcar como revisado».
- **Página de ejecución**: sección «Cambios» con el diff de esa ejecución.
- **Ficha del agente**: nueva pestaña «Cambios»:
  - sus ejecuciones recientes que han cambiado código, con tarea, proyecto, fecha y n ficheros +/−;
  - al hacer clic se abre el diff de esa ejecución;
  - se puede filtrar por proyecto.
- **Ejecuciones**: columna «Cambios» (+/−, 12 px, muted) en la lista.

**Transversal**
- API REST: diff de una tarea y de una ejecución (lista de ficheros con totales y, bajo demanda, el contenido de cada fichero), resumen en `/api/runs` y cambios del agente.
- Migración de Alembic para el resumen de cambios de las ejecuciones.
- Textos en i18n y tests de backend (repos de prueba con worktree, carpeta directa, binarios, renombrados, CRLF) y de frontend.
- ADR de captura de cambios (instantáneas, referencias y limpieza).

### Fuera
- **Comentarios en las líneas** del diff y enviarlos al agente como motivo de rechazo. Se anota para una fase futura.
- **Hacer el merge, el rebase o revertir** desde la app: va en la fase 12 (Control de git).
- **Vista lado a lado** y **resaltado de sintaxis**: solo la vista unificada, con colores de diff.
- **Pasar el diff a los agentes** de las etapas siguientes (p. ej. que QA reciba la lista de ficheros cambiados en su contexto).
- Diff entre dos ejecuciones cualesquiera o entre ramas elegidas a mano.
- **Separar en carpeta directa** los cambios del usuario de los del agente cuando ambos tocan la carpeta a la vez: el diff muestra todo lo que cambió durante la ejecución, y la cabecera lo advierte.
- Cambios fuera de la carpeta de la ejecución (otros repos, ficheros del sistema).

## Historias de usuario
- Como usuario, quiero ver los ficheros que ha cambiado una tarea y su diff antes de aprobar o rechazar la revisión, para decidir con lo que ha hecho el agente y no solo con su resumen.
- Como usuario, quiero ver qué cambió cada ejecución de una tarea (Dev, la vuelta tras el rechazo de QA…), para entender qué arregló cada intento.
- Como usuario, quiero ver en la ficha de un agente el código que ha ido cambiando, para saber cómo trabaja sin abrir las ramas una a una.
- Como usuario de un proyecto de carpeta directa, quiero saber qué tocó el agente en mi carpeta, aunque no haya commiteado nada.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | En un proyecto con worktree, el diff de la tarea coincide con `git diff <merge-base>..agentic/T-n` (ficheros, estados y +/−), también después de borrarse el worktree | Tests con repos de prueba + prueba manual |
| CA2 | El diff de cada ejecución muestra solo lo que cambió en ella, aunque el agente commitee a mitad o deje trabajo sin commitear que continúa la siguiente | Tests con el CLI falso (commits y cambios sin commitear entre ejecuciones) |
| CA3 | En carpeta directa, el diff de la ejecución incluye lo que el agente dejó sin commitear y lo que commiteó, y no incluye los cambios del usuario que ya estaban antes de empezar | Tests |
| CA4 | Tomar las instantáneas no cambia el índice, la rama ni los ficheros de la carpeta (`git status` es el mismo antes y después) y las instantáneas siguen tras un `git gc --prune=now` | Tests |
| CA5 | Al revisar una tarea se ven su lista de ficheros y su diff línea a línea, y se aprueba o rechaza desde el mismo panel | Tests de UI + prueba manual |
| CA6 | La pestaña «Cambios» de la ficha del agente lista sus ejecuciones con cambios y abre el diff de cada una | Tests de UI y de la API |
| CA7 | Los binarios, los renombrados, los ficheros borrados y los diffs grandes se muestran sin bloquear la UI, con su aviso | Tests + prueba manual con un diff de más de 5 000 líneas |
| CA8 | Un proyecto sin git y las ejecuciones anteriores a la fase muestran su estado vacío, sin errores | Tests |
| CA9 | Las referencias de las instantáneas se borran con la purga de logs y al borrar el proyecto | Tests |
| CA10 | Lint, tests de backend y de frontend en verde; `/code-review` resuelto | CI local |

## Prerrequisitos
- Fase 10 cerrada (`v1.2`).
- git instalado (ya lo exigen los worktrees).

## Riesgos y preguntas abiertas
- **Rendimiento de las instantáneas** en repos grandes: tomarlas recorre la carpeta como un `git status` y añade los ficheros nuevos al almacén de git. Hay que medir el coste en un repo grande y con muchos ficheros no ignorados (p. ej. un `node_modules` sin `.gitignore`), y fijar un límite de tamaño por fichero.
- **Referencias en el repositorio del usuario**: las instantáneas son referencias ocultas (no son ramas ni tags y no se suben con un `push` normal), pero ocupan espacio hasta que se limpian. Si se borra el repo o se clona de nuevo, se pierden y se muestra «No hay datos».
- **Ejecuciones interrumpidas** (cierre de la app, caída): no tienen instantánea final. Se propone tomarla al recuperar la ejecución en el arranque. Si ya no se puede, el diff llega hasta el estado actual de la carpeta, y se avisa.
- **Ejecuciones simultáneas en la misma carpeta**: una ejecución manual y una de tarea en la misma carpeta directa verán los cambios de la otra. Se avisa en la cabecera; no se intenta separarlos.
- **Ficheros generados**: la lista de patrones que se pliegan por defecto (lockfiles, `dist/`, `*.min.js`…) ¿es fija o configurable por proyecto? Propuesta: fija en esta fase.
- **¿Hace falta la pestaña «Cambios» en la ficha del agente si ya está en el detalle de tarea?** El roadmap la pide; se mantiene, pero como lista ligera que lleva al diff.
