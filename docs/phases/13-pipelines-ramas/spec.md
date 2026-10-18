# Fase 13: Pipelines con ramas · Spec

- **Estado**: aprobada (2026-10-18)
- **Rama**: `phase/13-pipelines-ramas`

## Objetivo
Que un pipeline deje de ser una fila de etapas y pase a ser un **grafo con varias vías**: tras una etapa, el flujo se **bifurca** en ramas (p. ej. Dev backend y Dev frontend) y **un LLM decide, según la tarea, qué rama o ramas toma**, explicando por qué. Las ramas elegidas avanzan **en paralelo** y se **vuelven a unir** antes de seguir (p. ej. en QA). La decisión queda en el historial de la tarea y el usuario puede corregirla.

## Punto de partida
- **Pipeline lineal** (fase 05, ADR 0009): `Stage.position` ordena las etapas; `next_stage` es la siguiente por posición; el rechazo vuelve a una etapa anterior (`reject_to_stage_id`); máximo 12 etapas.
- **Una tarea está en un solo sitio**: `Task.stage_id`, `Task.agent_id` y `Task.status` son únicos. La cola del agente, el tablero, el detalle de la tarea, el contexto (`task_context`) y el MCP lo dan por hecho.
- **Workspace**: en modo worktree, todas las etapas de una tarea comparten su carpeta y su rama `agentic/T-n` en cada repo (fases 05 y 12). En carpeta directa, como máximo una tarea en ejecución por proyecto.
- **Editor de pipeline** (`PipelineTab`): lista vertical con flechas para reordenar y la flecha de rechazo.
- **LLM sin agente**: hoy todo lo que hace un LLM es una ejecución de un agente en PTY. El modo *headless* (`claude -p`, `agy -p`) se probó en el spike (P11) pero no se usa.

## Alcance
### Dentro

#### 1. Pipelines como grafo
- Un pipeline tiene **etapas y conexiones** entre ellas. Una etapa sin conexiones de entrada es el **inicio** (solo una); una sin conexiones de salida es un **final**.
- **Bifurcación**: una etapa con varias conexiones de salida. Cada salida es una **rama** con:
  - un nombre (p. ej. «Backend»);
  - una **condición en lenguaje natural** (p. ej. «La tarea toca la API, la base de datos o el backend»);
  - opcionalmente, **«Siempre»**: la rama se toma sin preguntar al LLM.
- **Unión**: una etapa con varias conexiones de entrada. **Espera a que terminen todas las ramas que se tomaron** en la bifurcación correspondiente (las no tomadas no cuentan) y recibe los resúmenes de todas.
- Las ramas pueden **no unirse**: si cada una acaba en un final, la tarea queda «Hecho» cuando terminan todas las ramas tomadas.
- **Grafo estructurado**: cada bifurcación se cierra en una sola unión (o en finales), las bifurcaciones se pueden anidar y no hay ciclos salvo las flechas de rechazo. Así la unión siempre sabe qué ramas espera.
- **Rechazos**: una etapa puede rechazar hacia una etapa anterior de **su mismo camino** (p. ej. QA, tras la unión, a Dev backend). Solo se repite esa rama; al terminar, vuelve a la unión y la etapa que rechazó se ejecuta de nuevo. Se mantiene el máximo de rechazos por tarea.
- **Pipelines lineales**: siguen funcionando igual; la migración los convierte en una cadena de conexiones sin cambiar su comportamiento.
- Límite de etapas: de 12 a 30.

#### 2. Decisión de rama por un LLM
- Cuando una tarea llega al final de una etapa que bifurca, un **decisor** elige las ramas:
  - recibe la tarea (título y descripción), los resúmenes de las etapas ya hechas y las ramas con sus condiciones;
  - devuelve **una o varias ramas** y **un motivo** por cada rama, tomada o no;
  - las ramas «Siempre» se añaden sin preguntar; si todas lo son, no se llama al LLM.
- **El decisor es una llamada corta al LLM, no una ejecución de agente**: un CLI en modo *headless*, con una cuenta (fase 10) y un modelo que se eligen por pipeline (por defecto, el modelo más barato del primer CLI con sesión). Sin herramientas, sin tocar ficheros y con un límite de coste.
- **Su consumo cuenta** (fase 07): se registra como consumo del proyecto y de la tarea, con su coste equivalente, y respeta el límite diario.
- **Si falla** (sin cuota, error, respuesta inválida o ninguna rama elegida): un reintento y, si vuelve a fallar, la tarea queda «Esperando humano» con el motivo **«Hay que elegir la rama»**, y el usuario la elige.
- **Confirmar la decisión** (opcional por bifurcación, desactivado por defecto): la tarea queda «En revisión» con las ramas propuestas y el motivo; el usuario aprueba o cambia la selección.
- **Corregir a mano**:
  - al crear la tarea, «Elegir las ramas a mano» fija de antemano las de cada bifurcación (el LLM no se llama);
  - con la tarea en curso, se puede **añadir una rama** no tomada (empieza ya y la unión la espera) o **cancelar una rama** en marcha (su ejecución se para y la unión deja de esperarla).
  - Cada corrección queda en el historial con «Tú».
- **Probar las condiciones**: en el editor, «Probar» pasa al decisor un título y una descripción de ejemplo y muestra qué ramas elegiría y por qué, sin crear tarea.

#### 3. Tareas en varias ramas a la vez
- Una tarea puede estar **en varias etapas a la vez**, una por rama activa. Cada rama activa tiene su etapa, su agente, su estado (en cola, en ejecución, esperando humano, en revisión) y sus ejecuciones.
- **Estado de la tarea**: se deriva de sus ramas activas, con esta prioridad: esperando humano › en revisión › en ejecución › en cola. Se ve en el detalle el estado de cada rama.
- **Colas**: cada rama entra en la cola del agente de su etapa, como hoy una tarea. Si dos ramas van al mismo agente, cuenta como dos entradas.
- **Acciones** (reintentar, dar por terminada a mano, revisar, tomar el control): se hacen **por rama**. Cancelar la tarea cancela todas.
- **Workspace en modo worktree**: cada rama paralela trabaja en **su propia carpeta** de la tarea, con su rama de git por repo (p. ej. `agentic/T-142/backend`, creada desde `agentic/T-142`). En la unión, la app **integra las ramas de git de cada vía en `agentic/T-142`** de cada repo, y la etapa de unión trabaja allí. Si hay conflictos, la tarea queda «Esperando humano» con el editor de tres vías o «Pasárselos a un agente» de la fase 12.
- **Workspace en carpeta directa**: las ramas tomadas se ejecutan **una detrás de otra** en la carpeta (sigue la regla de una ejecución por proyecto), en el orden del editor. Se avisa en el editor de que en este modo no hay paralelismo.
- **Contexto del agente** (`task_context` y `get_context`): la rama en la que está, por qué se tomó y qué otras ramas corren a la vez; en la unión, los resúmenes de todas las ramas que se unen.
- **Diffs** (fase 11): el de la tarea muestra todo; el de cada ejecución, lo suyo. En el detalle se puede filtrar por rama.

#### 4. Editor visual del grafo
- Lienzo con las etapas como nodos y las conexiones como flechas: añadir y quitar etapas, unirlas arrastrando, mover nodos, zoom y encuadre; la flecha de rechazo con otro estilo.
- Panel lateral de la etapa (nombre, agente, revisión, rechazo) y de la rama (nombre, condición, «Siempre»), y del pipeline (decisor: CLI, cuenta y modelo; máximo de rechazos).
- **Validación en vivo**: un solo inicio, todas las etapas alcanzables, toda bifurcación cerrada en una unión o en finales, sin ciclos, rechazos solo hacia atrás en su camino, ramas con condición o «Siempre». Los errores se marcan en el nodo y no se puede guardar.
- Guardar no rompe las tareas en curso: no se puede quitar una etapa ni una conexión por la que pasa una rama activa (se dice cuál).
- **Plantilla nueva** «Desarrollo web con backend y frontend»: Requisitos → (Dev backend | Dev frontend) → QA, con QA pudiendo rechazar a cualquiera de los dos.
- Accesible con teclado y con el diseño v7 (tokens y componentes de `docs/design/v2/`).

#### 5. Seguimiento
- **Historial de la tarea**: evento «Decisión de rama» con las ramas tomadas y descartadas, el motivo de cada una, quién decidió (el modelo o «Tú») y su coste; eventos de inicio y fin de cada rama y de la unión (incluida la integración de git).
- **Detalle de la tarea**: el **grafo del pipeline con el camino de la tarea** marcado (etapas hechas, en curso, no tomadas) y el motivo de la decisión al pasar sobre la bifurcación.
- **Tablero**: en «Por etapa», una tarea en dos ramas aparece en las dos columnas, con la rama indicada; en «Por estado», una vez, con su estado derivado. Las colas por agente muestran la rama.
- **Peticiones/Inbox**: «Hay que elegir la rama» y «Confirmar la decisión» llegan como peticiones (fase 06), con notificación.

#### 6. Transversal
- **Migración de Alembic**: conexiones y ramas del pipeline, ramas activas de cada tarea (con su etapa, agente, estado y workspace), decisiones; los pipelines y tareas existentes se convierten sin cambiar su comportamiento.
- API REST del grafo, de la decisión (incluido «Probar») y de las acciones por rama; eventos en vivo por WS.
- Textos en i18n; tests de backend (motor del grafo, decisor con un CLI falso, migración, worktrees por rama e integración en la unión) y de frontend (editor, validación, detalle de la tarea).
- **ADR** del modelo de grafo, las ramas activas de una tarea y el decisor.

### Fuera
- Condiciones escritas como código o expresiones (sobre etiquetas, ficheros tocados…): solo lenguaje natural y «Siempre».
- Bucles que no sean de rechazo (repetir una etapa N veces, iterar sobre una lista).
- Grafos no estructurados (una unión que reúne ramas de bifurcaciones distintas).
- Varios pipelines por proyecto o elegir pipeline por tarea.
- Que el decisor sea un agente con herramientas (que lea el código para decidir); se puede añadir más adelante.
- Unir las ramas sin esperar a todas («la primera que acabe»).

## Historias de usuario
- Como usuario, quiero que una tarea de API vaya sola a Dev backend y una de UI a Dev frontend, para no elegir la rama a mano cada vez.
- Como usuario, quiero que una tarea que toca back y front pase por las dos ramas a la vez y llegue a QA cuando acaben ambas, para que QA lo revise todo junto.
- Como usuario, quiero ver por qué el LLM eligió una rama y poder corregirlo, para fiarme de la decisión.
- Como usuario, quiero dibujar el flujo en un lienzo y que me avise si está mal construido, para no descubrirlo con una tarea a medias.
- Como usuario, quiero probar las condiciones de las ramas con un ejemplo antes de guardar, para ajustarlas sin gastar una tarea.
- Como usuario, quiero que, si QA rechaza lo del backend, solo se repita la rama del backend.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Con la plantilla «Desarrollo web con backend y frontend», una tarea de API va solo a Dev backend, una de UI solo a Dev frontend y una que toca ambas pasa por las dos en paralelo y llega a QA cuando terminan las dos, sin elegir la rama a mano | e2e con el CLI falso y el decisor falso + prueba manual con un decisor real |
| CA2 | La decisión queda en el historial con las ramas tomadas y descartadas, su motivo, el modelo y su coste; el consumo del decisor aparece en el panel de consumo | Tests + prueba manual |
| CA3 | Si el decisor falla o no elige ninguna rama, la tarea queda «Esperando humano» con «Hay que elegir la rama» y la elección del usuario la desbloquea; con «Confirmar la decisión», la tarea espera en revisión y se puede cambiar la selección | Tests |
| CA4 | Las ramas fijadas al crear la tarea, añadir una rama en curso y cancelar una rama en marcha funcionan, y la unión espera exactamente a las ramas tomadas que siguen vivas | Tests |
| CA5 | En modo worktree, cada rama paralela trabaja en su carpeta y su rama de git, y en la unión se integran en `agentic/T-n` de cada repo; con conflictos, la tarea espera y se resuelven con el editor o un agente | Tests con repos reales y el CLI falso |
| CA6 | En carpeta directa, las ramas tomadas se ejecutan una detrás de otra y nunca hay dos ejecuciones del proyecto a la vez | Tests del scheduler |
| CA7 | Un rechazo de QA a Dev backend repite solo esa rama y vuelve a QA; al superar el máximo de rechazos la tarea espera | e2e con el CLI falso |
| CA8 | El editor crea, conecta y valida el grafo (inicio único, bifurcaciones cerradas, sin ciclos, rechazos válidos), impide guardar con errores y no deja quitar una etapa o conexión con ramas activas; «Probar» muestra la decisión sin crear tarea | Tests de componentes y de la API + revisión con el usuario |
| CA9 | Los pipelines y tareas existentes siguen funcionando igual tras la migración | Tests de la migración + e2e de la fase 05 en verde |
| CA10 | El detalle de la tarea muestra el grafo con su camino y el estado de cada rama; el tablero muestra la tarea en cada columna de sus ramas | Tests de componentes + capturas |
| CA11 | Lint, tests de backend y de frontend en verde; ADR escrito; `/code-review` resuelto | CI local |

## Prerrequisitos
- Fase 12 cerrada (`v1.4`).
- Claude Code (y, si es posible, agy) con sesión iniciada, para probar el decisor real.

## Riesgos y preguntas abiertas
- **Quién decide** (decidido, 2026-10-18): una llamada *headless* con un modelo barato, configurable por pipeline. Se descarta que decida el agente de la etapa con `complete_task`.
- **Modo *headless* de agy**: en el spike, `agy -p` devolvió `response` vacío. Hay que comprobar en el plan (spike corto) si sirve como decisor; si no, el decisor solo usa Claude Code y se avisa.
- **Ramas paralelas en modo worktree** (decidido, 2026-10-18): una carpeta y una rama de git por vía, integradas en la unión. Evita que dos agentes pisen la misma carpeta y el mismo índice de git; el coste son las integraciones y sus posibles conflictos, que se resuelven con las herramientas de la fase 12.
- **Carpeta directa** (decidido, 2026-10-18): las ramas tomadas se ejecutan en serie, en el orden del editor, que avisa de que en ese modo no hay paralelismo.
- **Tamaño del cambio en el modelo de tareas**: pasar de «una tarea, una etapa» a «una tarea, varias ramas activas» toca el scheduler, las colas, el tablero, el detalle, el MCP y la Inbox. El plan lo dividirá en bloques: modelo de grafo y migración → motor con ramas paralelas (sin LLM, con «Siempre» y elección manual) → decisor → workspaces por rama → editor visual → seguimiento en la UI.
- **Coste y latencia del decisor**: una llamada por bifurcación y tarea; con un modelo pequeño son segundos y céntimos, pero cuenta para la cuota de la suscripción. «Siempre» y la elección manual la evitan.
- **Componente de grafo**: el editor necesita un lienzo de nodos y aristas (p. ej. React Flow / `@xyflow/react`) o uno propio con SVG. Se decide en el plan.
