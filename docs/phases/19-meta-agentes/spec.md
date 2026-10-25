# Fase 19: Meta-agentes · Spec

- **Estado**: aprobada (2026-10-25)
- **Rama**: `phase/19-meta-agentes`

## Objetivo
Crear agentes **hablando** en lugar de rellenar un formulario. El **Agente Arquitecto** conversa con el usuario sobre lo que necesita («quiero alguien que me escriba los posts del blog con el tono de la marca»), le pregunta lo que falte y va rellenando en vivo la ficha completa del agente: rol, instrucciones, CLI, cuenta y modelo, permisos, skills, conocimiento y conexiones MCP. El resultado es un **borrador** que el usuario revisa y aprueba antes de que pueda recibir tareas. El Arquitecto también **mejora agentes que ya trabajan**, con una propuesta de cambios que el usuario aplica entera o en parte, y los propios agentes pueden **proponer un agente nuevo** cuando detectan que falta un rol. Y a mayor escala, el Arquitecto **diseña equipos enteros con el pipeline de un proyecto** (o mejora los existentes), en una propuesta que el usuario aprueba de una vez o por partes. Además, las **plantillas** dejan de ser solo las cinco fijas: el usuario guarda sus agentes como plantillas, las reutiliza y las exporta o importa, y el Arquitecto parte de ellas cuando encajan.

## Punto de partida (fases 02, 10, 13, 16, 17 y 18)
- El agente ya tiene el estado **borrador** (`AgentStatus.DRAFT`, fase 02): no recibe tareas, el scheduler y los pipelines lo ignoran y el editor muestra «Activar». Falta el banner del diseño («Borrador propuesto por el Agente Arquitecto» con Rechazar / Aprobar agente).
- Hay **cinco plantillas fijas** en código (`services/templates.py`: Analista, Desarrollador, QA, Redactor, Comercial) que solo rellenan el diálogo de nuevo agente.
- El botón **«Crear con el Arquitecto»** existe en Agentes, deshabilitado («próximamente»). El diseño tiene la pantalla completa (`docs/design/screens.md` §11 y el prototipo v7): chat a la izquierda, ficha en vivo a la derecha con su porcentaje y «Crear borrador».
- Las llamadas *headless* a un CLI ya existen: el decisor de ramas (fase 13, `claude -p` / `agy -p`, modelo barato, registrada como `Run` de tipo `decision` para que cuente en el consumo) y la descripción de imágenes (fase 14).
- Las fases 17 (skills) y 18 (conexiones) dejaron fuera, para esta fase, que el Arquitecto **asigne skills y conexiones** a un agente nuevo.
- El dictado por voz (fase 16) se añade a un campo con una línea; la conversación con el Arquitecto estaba prevista como uno de sus campos.
- Los agentes ya proponen cosas con aprobación en la Inbox (`propose_knowledge`, `propose_skill`).

## Alcance
### Dentro
**A. Conversación con el Arquitecto**
- Pantalla **«Crear con el Arquitecto»** según el diseño: chat a la izquierda, ficha en vivo a la derecha. Se abre desde Agentes, Inicio y la paleta de comandos.
- El Arquitecto **pregunta** lo que necesita saber (qué hará el agente, para qué proyectos, con qué herramientas, qué puede y qué no puede hacer, qué tono…) y **propone** el resto con valores razonables, explicando las decisiones importantes (p. ej. por qué el modo *Restringido* o por qué un modelo barato).
- Las respuestas llegan en **streaming** y cada una puede rellenar o cambiar campos de la ficha, que se marcan un momento al cambiar. Los campos aún vacíos se ven como *skeleton* con borde discontinuo.
- El usuario puede **editar la ficha a mano** en cualquier momento; el Arquitecto ve esos cambios en su siguiente turno y no los pisa salvo que se le pida.
- El composer tiene **dictado por voz** (componente de la fase 16).
- **Conversaciones guardadas**: se pueden cerrar y retomar más tarde, se listan (con su estado: en curso, borrador creado, descartada) y se pueden reiniciar o borrar. El borrador creado enlaza con su conversación y viceversa.
- **«Crear borrador»** se habilita cuando la ficha tiene lo mínimo (nombre, rol, CLI e instrucciones); crea el agente en estado borrador y abre su editor con el banner.

**B. Qué rellena el Arquitecto**
- **Identidad**: nombre, rol, descripción, color y equipo (de los existentes, o «Sin equipo»).
- **Instrucciones**: el *system prompt* completo, con las reglas comunes de Agentic OS y las variables disponibles.
- **Ejecución**: CLI, **cuenta** y modelo de entre los **disponibles en la máquina** (CLIs instalados y cuentas dadas de alta), modo de permisos, herramientas permitidas, concurrencia, si puede lanzar subagentes y crear tareas. CLI secundario opcional.
- **Skills**: elige de la biblioteca las que encajan (con su modo por agente) y puede **proponer skills nuevas** escritas para este agente, que se crean como skills propuestas y se aprueban junto con el agente.
- **Conocimiento**: elige documentos y carpetas existentes de la biblioteca para el nivel del agente. No sube ficheros nuevos; si hace falta uno, lo dice y el usuario lo añade desde la ficha.
- **Conexiones MCP**: elige conexiones existentes del catálogo (y sus herramientas permitidas). Si hace falta una que no existe, la **sugiere** desde el explorador de registros o una plantilla de la fase 18, pero no la instala: el usuario la instala con un clic desde la ficha y mete él los secretos.
- **Plantilla de partida**: si una plantilla (fija o del usuario) encaja, la usa de base y lo dice.
- Para todo esto, el Arquitecto **consulta** el estado real de la app (CLIs, cuentas y modelos, equipos, agentes existentes para no duplicar roles, skills, conocimiento, conexiones, plantillas) con herramientas de **solo lectura**. Nunca cambia nada fuera de la ficha de la conversación.
- La ficha se **valida** con las mismas reglas que el editor de agentes: un modelo que no existe para el CLI, una cuenta de otro CLI o una skill inexistente no llegan al borrador, y el Arquitecto lo corrige.

**C. Borradores y aprobación**
- En el editor, el agente en borrador muestra el **banner violeta** del diseño con «Rechazar» y «Aprobar agente», y un enlace «Ver la conversación».
- **Aprobar** lo activa (y aprueba con él las skills que el Arquitecto propuso para él, si el usuario no las desmarca). **Rechazar** lo archiva o lo borra, a elección del usuario, y deja la conversación como «descartada».
- En la lista de Agentes, el chip discontinuo «Propuesto por el Arquitecto». Los borradores aparecen también en la **Inbox** como petición de aprobación.
- Un borrador se puede editar a mano o **seguir hablando** de él con el Arquitecto antes de aprobarlo.

**F. Mejorar agentes activos con el Arquitecto**
- Botón **«Mejorar con el Arquitecto»** en el editor de un agente activo: abre una conversación sobre ese agente («que el QA sea más estricto con los tests», «añádele la conexión de GitHub»).
- La ficha de la derecha parte de la configuración actual y muestra los **cambios propuestos** campo a campo (antes / después; las instrucciones como diff de texto).
- El resultado es una **propuesta de cambios** pendiente de aprobación, no un cambio directo: aparece en el editor del agente (banner violeta «Cambios propuestos por el Arquitecto» con Revisar / Rechazar / Aplicar) y en la Inbox.
- Mientras tanto el agente **sigue trabajando** con su configuración actual. Aplicar la propuesta afecta a las ejecuciones siguientes, nunca a las que están en marcha.
- Se pueden aplicar **todos los cambios o solo algunos** campos.
- Si el agente se edita a mano después de la propuesta, los campos afectados se marcan como **en conflicto** y no se aplican sin que el usuario elija.
- Cada propuesta aplicada queda en la pestaña **Historial** del agente (quién la propuso, qué cambió y la conversación de origen).

**G. Agentes que proponen agentes (`propose_agent`)**
- Nueva herramienta MCP **`propose_agent`** en `agentic-os`, como `propose_skill`: un agente que detecta durante una tarea que falta un rol («haría falta un traductor para estos textos») propone un agente nuevo con su ficha y el **motivo**.
- Solo la tienen los agentes con el permiso **«Puede proponer agentes»** (nuevo, apagado por defecto y activado en las plantillas que lo necesiten). Como mucho **una propuesta por ejecución**.
- La propuesta se valida igual que la ficha del Arquitecto (solo CLIs, cuentas, skills, conocimiento y conexiones que existen) y crea un **borrador** con su origen (agente, tarea y ejecución) y el motivo, con aviso en la Inbox.
- El usuario lo aprueba o rechaza como cualquier borrador, o lo abre con el Arquitecto para **seguir refinándolo** en una conversación.
- Un agente no puede proponer cambios a otros agentes ni a sí mismo: eso solo lo hace el Arquitecto con el usuario (apartado F).

**H. Diseñar equipos y pipelines completos**
- Desde la misma pantalla, el usuario puede pedir **un equipo entero con su flujo de trabajo** («monta un equipo de contenidos que investigue, escriba y revise los posts del blog de este proyecto»).
- El Arquitecto propone una **propuesta compuesta**:
  - un **equipo** (nuevo o uno existente) con su nombre y descripción;
  - sus **agentes**: nuevos (con la ficha completa del apartado B) o **existentes reutilizados**, para no duplicar roles;
  - el **pipeline** de un proyecto existente: etapas con su agente, revisión humana, a qué etapa vuelve un rechazo, ramas con sus condiciones y uniones (fase 13), decisor de ramas y los ajustes por etapa de skills y conexiones (fases 17 y 18).
- La parte derecha de la pantalla pasa a tener pestañas: **Equipo**, **Agentes** (una ficha por agente) y **Pipeline** (el grafo dibujado con el componente del editor de la fase 13, en solo lectura, con cada etapa enlazada a su agente).
- El pipeline propuesto se valida con las **mismas reglas que el editor** (grafo sin ciclos indebidos, ramas que se unen, cada etapa con agente…); si no es válido, el Arquitecto lo corrige antes de poder crear la propuesta.
- **Aprobación**:
  - «Aprobar todo» crea el equipo, activa los agentes nuevos y aplica el pipeline en una sola operación (si algo falla, no se aplica nada);
  - se puede **desmarcar** un agente nuevo; si una etapa del pipeline lo usa, hay que asignarle otro agente antes de aprobar;
  - rechazar la propuesta descarta el equipo, los agentes nuevos y el pipeline, y deja los agentes existentes como estaban.
- Si el proyecto **ya tiene pipeline**, la propuesta se muestra como **cambios** sobre él (etapas añadidas, quitadas y cambiadas, ramas y condiciones) y se aplica con las mismas reglas que al guardar desde el editor: las tareas en curso no se pierden y una etapa con tareas activas no se puede quitar sin moverlas.
- **Mejorar un equipo o un pipeline existente**: botón «Mejorar con el Arquitecto» en el equipo (Inicio y Agentes) y en el editor de pipeline del proyecto, con el mismo modelo de propuesta de cambios y aprobación que el apartado F, también parcial.
- La propuesta compuesta aparece en la Inbox como una sola petición y en el Historial de cada pieza aplicada.

**D. Plantillas**
- **Biblioteca de plantillas** (pestaña en Agentes o en Ajustes): las cinco fijas, que no se pueden editar ni borrar, y las del usuario.
- **Guardar como plantilla** un agente existente: copia su ficha (identidad, instrucciones, ejecución, skills, conocimiento y conexiones asignados por referencia) sin colas, consumo, historial ni cuenta concreta (la cuenta se elige al crear el agente desde la plantilla).
- Crear un agente desde una plantilla (el diálogo actual de nuevo agente, ampliado con las del usuario) y editar, duplicar y borrar las plantillas del usuario.
- **Exportar e importar** un agente o una plantilla como fichero JSON, sin secretos ni identificadores locales. Al importar, lo que no exista en esta instalación (una skill, una conexión, un documento) se lista y se omite o se sustituye, sin fallar.

**E. Configuración y consumo del Arquitecto**
- **Ajustes › Arquitecto**: CLI, cuenta y modelo que usa (por defecto, el mejor modelo disponible del primer CLI instalado) y sus instrucciones base, editables y restaurables.
- Cada turno del Arquitecto se registra como una ejecución de tipo **`architect`** (como el decisor), así que su consumo aparece en el panel y cuenta para el **límite diario**. Si el límite se ha alcanzado o el CLI no tiene cuenta, la pantalla lo dice con palabras.
- El Arquitecto no aparece como agente en la lista ni recibe tareas.

### Fuera
- Que el Arquitecto **cree proyectos** (carpeta, repositorios): el pipeline se diseña para un proyecto que ya existe.
- Plantillas de pipeline o de equipo creadas por el usuario (siguen las dos plantillas fijas de pipeline de la fase 05).
- Que los agentes propongan **cambios** a agentes existentes (solo proponen agentes nuevos).
- Que el Arquitecto **mejore agentes solo**, sin conversación (p. ej. a partir de los rechazos de QA o del consumo).
- Que el Arquitecto suba documentos de conocimiento o instale conexiones MCP por su cuenta.
- Un mercado o registro público de plantillas de agentes.
- Arquitecto con Codex u OpenCode (llegan en la fase 21).
- Avisos externos de borradores pendientes (fase 20).

## Historias de usuario
- Como usuario, quiero describir con mis palabras el agente que necesito y que el Arquitecto me haga las preguntas justas y me deje la ficha completa, sin tener que saber qué es cada campo.
- Como usuario, quiero ver cómo se rellena la ficha mientras hablo y poder corregir un campo a mano sin que el Arquitecto lo deshaga.
- Como usuario, quiero que el agente propuesto use mis CLIs, cuentas, skills, documentos y conexiones reales, no inventados.
- Como usuario, quiero revisar el borrador y aprobarlo o rechazarlo antes de que reciba ninguna tarea.
- Como usuario, quiero dictar lo que necesito en lugar de escribirlo.
- Como usuario, quiero guardar un agente que me funciona bien como plantilla y crear otros a partir de ella.
- Como usuario, quiero exportar un agente a un fichero y llevármelo a otra instalación.
- Como usuario, quiero saber cuánto me cuesta hablar con el Arquitecto y que respete mi límite diario.
- Como usuario, quiero pedirle al Arquitecto que mejore un agente que ya uso, ver qué cambiaría campo a campo y aplicar solo lo que me convenza, sin parar al agente.
- Como usuario, quiero que un agente me avise de que falta un rol en el equipo y me deje el agente propuesto listo para revisar.
- Como usuario, quiero describir un equipo entero y su forma de trabajar y que el Arquitecto me proponga los agentes, el equipo y el pipeline del proyecto, reutilizando los agentes que ya tengo.
- Como usuario, quiero pedirle al Arquitecto que reorganice el pipeline de un proyecto y ver qué cambia antes de aplicarlo.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Se crea un «Redactor» desde una conversación y ejecuta una tarea**: la conversación produce un borrador, el usuario lo aprueba y el agente completa una tarea de un proyecto (CLI falso en el e2e; `claude` real en la prueba manual) | e2e + manual |
| CA2 | Las respuestas llegan en streaming y rellenan la ficha en vivo; un campo editado a mano no lo cambia el Arquitecto en los turnos siguientes salvo que se le pida | tests + UI |
| CA3 | La ficha propuesta solo usa CLIs, cuentas, modelos, skills, documentos y conexiones que existen; una referencia inventada no llega al borrador | tests |
| CA4 | El Arquitecto no puede cambiar nada fuera de la ficha de su conversación: sus herramientas son de solo lectura más la de editar la ficha | tests |
| CA5 | Un borrador no recibe tareas ni aparece en los pipelines; «Aprobar agente» lo activa junto con sus skills propuestas y «Rechazar» lo archiva o borra; el borrador aparece en la Inbox | tests + UI |
| CA6 | Una conversación se cierra y se retoma con su historial y su ficha; el borrador y la conversación se enlazan | tests + UI |
| CA7 | Cada turno queda como ejecución `architect` con su consumo, que aparece en el panel y cuenta para el límite diario; con el límite alcanzado o sin cuenta, la pantalla lo dice y no llama al CLI | tests |
| CA8 | Un agente se guarda como plantilla, se crea otro desde ella con otra cuenta, y las plantillas fijas no se pueden editar ni borrar | tests + UI |
| CA9 | Un agente exportado se importa en una base de datos limpia; lo que falta (skills, conexiones, documentos) se lista y se omite sin fallar, y el fichero no contiene secretos | tests |
| CA10 | El composer del Arquitecto tiene dictado por voz | UI |
| CA11 | Con el binario empaquetado funciona el flujo: conversación → borrador → aprobación → tarea | e2e empaquetado |
| CA12 | **Mejorar un agente activo**: la conversación produce una propuesta con los cambios campo a campo; el agente sigue recibiendo tareas con su configuración actual; aplicar solo algunos campos cambia esos y no los demás; las ejecuciones en marcha no cambian; un campo editado a mano después queda en conflicto; lo aplicado queda en el Historial | tests + UI |
| CA13 | **`propose_agent`**: un agente con el permiso propone un agente nuevo y se crea un borrador con su origen y motivo y aviso en la Inbox; sin el permiso la herramienta no está; una segunda propuesta en la misma ejecución se rechaza; una ficha con referencias inexistentes se rechaza con el motivo | tests (CLI falso) |
| CA14 | Las skills nuevas que propone el Arquitecto se crean como propuestas, se aprueban al aprobar el agente (salvo las que el usuario desmarque) y se descartan al rechazarlo | tests |
| CA15 | **Equipo completo**: una conversación («equipo de contenidos: investigar, redactar y revisar») produce un equipo, agentes nuevos y existentes y el pipeline de un proyecto; «Aprobar todo» lo aplica en una sola operación y una tarea recorre el pipeline hasta el final (CLI falso en el e2e; agentes reales en la prueba manual) | e2e + manual |
| CA16 | El pipeline propuesto pasa la misma validación que el editor; desmarcar un agente usado por una etapa bloquea la aprobación hasta reasignarla; si la aplicación falla a medias no queda nada aplicado | tests |
| CA17 | **Mejorar un pipeline existente**: la propuesta muestra las etapas y ramas añadidas, quitadas y cambiadas; aplicarla conserva las tareas en curso y no permite quitar una etapa con tareas activas; lo mismo con un equipo existente | tests + UI |

## Prerrequisitos
- **Fase 18 cerrada** (hecho, `v1.10`).
- Lo reutilizado: llamadas *headless* y su registro como ejecución (fases 13 y 14), límites de consumo (fase 07), cuentas (fase 10), skills propuestas y su aprobación (fase 17), catálogo de conexiones y su explorador (fase 18), componente de dictado (fase 16), MCP `agentic-os` con *token* por ejecución (fase 04).

## Riesgos y preguntas abiertas
- **Cómo se mantiene la conversación con el CLI (spike).** Opción recomendada: cada turno es una llamada *headless* que **reanuda la sesión** del CLI (`claude -p --resume <id>` con salida en streaming; en `agy`, lo que permita su `-p`), con un MCP propio del Arquitecto (herramientas de solo lectura más `update_draft`). Hay que comprobar en Windows el streaming, la reanudación y el MCP en modo *headless* en los dos CLIs, y medir la latencia por turno. Alternativa: una sesión interactiva en PTY oculta, más rápida entre turnos pero más frágil.
- **Calidad de la ficha.** Que pregunte lo justo, que no invente y que las instrucciones sean buenas depende del modelo y de las instrucciones base. Mitigación: modelo bueno por defecto, instrucciones base con ejemplos de las plantillas, validación estricta de la ficha y conjunto de conversaciones de prueba en el spike.
- **Coste.** Una conversación son varios turnos con un modelo bueno y un contexto que crece (catálogo de skills y conexiones). Mitigación: el catálogo se consulta con herramientas bajo demanda en lugar de ir entero en el prompt, el consumo se ve en la pantalla y cuenta para el límite diario.
- **Inyección de prompts.** Las descripciones de skills, documentos y conexiones (algunas de terceros) llegan al Arquitecto. Su único efecto posible es la ficha de un borrador, que el usuario revisa antes de aprobar; el Arquitecto no tiene herramientas de escritura fuera de ella.
- **Cambios en agentes activos.** Aplicar cambios a un agente con tareas en cola o en marcha no debe afectar a lo que ya corre: la configuración se lee al lanzar cada ejecución (hoy ya es así) y la propuesta guarda la versión del agente sobre la que se hizo para detectar conflictos.
- **Tamaño de la fase.** Con los apartados F y H la fase es grande. El plan la divide en bloques que se puedan validar por separado: Arquitecto de un agente (A–E), mejora de agentes (F), `propose_agent` (G) y equipos y pipelines (H), en ese orden.
- **Calidad de los pipelines propuestos.** Un pipeline mal diseñado (ramas con condiciones vagas, rechazos que vuelven a la etapa equivocada) es más difícil de revisar que una ficha. Mitigación: la validación del editor, el grafo visible antes de aprobar, el Arquitecto explica cada etapa y rama, y conversaciones de prueba con pipelines en el spike.
- **Propuestas de agentes en exceso.** Un agente con `propose_agent` podría llenar la Inbox de borradores parecidos. Mitigación: permiso apagado por defecto, una propuesta por ejecución y aviso si ya hay un agente o borrador con el mismo rol.

## Decisiones del usuario sobre el borrador (2026-10-25)
1. **Skills nuevas**: el Arquitecto puede proponerlas; se aprueban junto con el agente.
2. **Exportar e importar** agentes y plantillas: dentro.
3. **Mejorar agentes activos** con el Arquitecto: dentro (apartado F), como propuesta de cambios con aprobación.
4. **`propose_agent`**: dentro (apartado G), con permiso por agente y una propuesta por ejecución.
5. **Equipos y pipelines completos**: dentro (apartado H), para proyectos existentes, con propuesta compuesta y aprobación total o parcial; también mejorar equipos y pipelines existentes.
