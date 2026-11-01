# Fase 24: Proyectos, pipelines y Arquitecto · Spec

- **Estado**: aprobada (2026-11-01)
- **Rama**: `phase/24-proyectos-pipelines-arquitecto`

## Objetivo
Que un proyecto nuevo pueda arrancar a trabajar en el momento de crearlo:
- con su propia foto;
- con un pipeline de desarrollo completo de una sola plantilla, «Desarrollo», que cubre de los requisitos al despliegue, pasando por la arquitectura, y que usa SDD solo cuando el trabajo lo merece;
- con agentes de plantilla para cada uno de esos roles, que se crean solos si faltan;
- o con el pipeline en blanco o copiado de otro proyecto.

Que una tarea **termine donde acaba su trabajo**: un pipeline puede tener varios finales, y una tarea que solo pide definir requisitos termina tras validarlos, sin pasar por los programadores.

Y que el Arquitecto se pueda usar desde donde hace falta: para crear un equipo de agentes y para diseñar el pipeline de un proyecto que todavía no lo tiene.

## Punto de partida
- **Proyectos** (`models/project.py`): un proyecto tiene nombre, color, descripción y carpeta, pero **ninguna imagen**. Se identifica por su color.
  - Los agentes sí tienen avatar desde la fase 20: un búho de la galería o una foto propia (como mucho 2048 px; solo se guarda el recorte en WebP de 256 px, sin metadatos).
- **Forma del pipeline** (fase 13, ADR 0020, `services/pipeline_graph.py`):
  - Las ramas de una bifurcación se vuelven a juntar en una misma etapa, o terminan todas.
  - **Una tarea solo termina en una etapa sin salida.** No puede acabar antes aunque su trabajo ya esté hecho: una tarea que solo pide los requisitos pasa igualmente por desarrollo y QA.
  - El decisor de ramas (una llamada barata a un CLI) elige, en cada bifurcación, las ramas que tocan a la tarea según sus condiciones.
- **Nuevo proyecto** (`NewProjectDialog.tsx`) ofrece dos opciones de pipeline: «Desarrollo web» o ninguno.
- **La pestaña Pipeline de un proyecto sin pipeline** (`PipelineTab.tsx`) ofrece dos plantillas («Desarrollo web» y «Desarrollo web con backend y frontend») o empezar en blanco. No se puede copiar el pipeline de otro proyecto ni llamar al Arquitecto.
- **Plantillas de pipeline** (`services/pipelines.py`): las dos fijas de la fase 05 (ampliada en la 13).
  - Cada etapa de plantilla apunta a una plantilla de agente y recibe el primer agente activo creado desde ella.
  - Si no hay ninguno, la etapa se queda **sin agente** y el usuario tiene que crear y asignar los agentes a mano.
- **Plantillas de agentes** (`services/templates.py`): cinco fijas (Analista, Desarrollador, QA, Redactor, Comercial), más las que guarde el usuario (fase 19).
- **El Arquitecto** (fase 19) ya sabe diseñar un equipo con sus agentes y el pipeline de un proyecto (modo `team`), y mejorar equipos y pipelines. Pero:
  - Solo se llega a ese modo desde su propia pantalla. No hay acceso desde el proyecto, su pestaña Pipeline vacía o la lista de equipos.
  - Sus instrucciones parten de que hay un proyecto existente. No conoce las plantillas nuevas de esta fase.

## Alcance
### Dentro
**A. Foto del proyecto**
1. Un proyecto puede tener una **foto propia**, que se elige al crearlo o desde su ficha. Se encuadra y se recorta con el mismo componente que el avatar de un agente:
   - imagen de 2048 px como mucho;
   - solo se guarda el recorte comprimido, sin metadatos.
2. Para los proyectos **no hay galería de búhos**. Sin foto, el proyecto se ve como ahora: su color y sus iniciales.
3. La foto se puede cambiar o quitar. Sale en todos los sitios donde aparece el proyecto: lista de proyectos, su página, el Tablero, Inicio, las tareas y el selector de proyecto.
4. El color del proyecto se queda: se sigue usando en los chips y en los filtros.

**B. Varios finales en un pipeline**
5. Cualquier etapa puede tener una **salida «Terminar aquí»** con una condición en lenguaje natural, por ejemplo «La tarea solo pide definir los requisitos». En el editor, la salida se dibuja como un nodo **Fin** unido a la etapa. Un pipeline puede tener tantos nodos Fin como haga falta.
6. Cuando una etapa con salida termina su trabajo (y su revisión humana, si la tiene), el **decisor de ramas** decide si la tarea acaba ahí o sigue:
   - Si se cumple la condición de la salida, la tarea **termina**: pasa a hecha, con la integración de ramas que tenga configurada el proyecto (fase 12), igual que en un final normal.
   - Si no, sigue por el resto del pipeline como hasta ahora.
   - En una etapa que además bifurca, terminar es **excluyente**: si el decisor elige la salida, no se toma ninguna rama.
7. La tarea guarda **dónde terminó y por qué**: la etapa, la condición y la explicación del decisor. Se ve en su historial y en el Tablero.
8. El usuario puede **forzar a mano** que una tarea siga o termine, igual que ya puede cambiar las ramas que eligió el decisor.
9. El editor y el Arquitecto validan las salidas con las mismas reglas que el resto del grafo:
   - una salida necesita condición;
   - una etapa tiene como mucho una salida;
   - la última etapa no la necesita, porque ya es un final.

   Una salida dentro de una rama abierta termina toda la tarea, no solo esa rama. Por eso **solo se permiten salidas fuera de las bifurcaciones abiertas**: antes de que la tarea se divida o después de que las ramas se junten.
10. Los pipelines que ya existen no cambian: sin salidas, se comportan exactamente igual que ahora.

**C. Plantilla de pipeline «Desarrollo»**
11. Hay **una sola plantilla de pipeline fija**, «Desarrollo». Sustituye a las dos anteriores en Nuevo proyecto y en la pestaña Pipeline. Los pipelines ya creados con ellas no cambian.
12. Etapas de «Desarrollo»:
   1. **Toma de requisitos**: convierte la petición en requisitos y criterios de aceptación. Antes, **decide si la tarea se hace con SDD** (desarrollo guiado por especificaciones):
      - **Con SDD**, si el proyecto **ya lo usa** o si el trabajo es **grande**: muchas piezas, varias ramas o decisiones que hay que dejar escritas.
        - «Ya lo usa» quiere decir que tiene especificaciones en el repositorio, por ejemplo `.specify/`, `.kiro/specs/`, `openspec/`, `specs/` o documentos de spec por fase.
        - Si el proyecto ya tiene su propio formato, se sigue ese, con sus carpetas y convenciones.
        - Si no lo tiene, se usa uno sencillo de la app: `specs/NNN-nombre/` con `spec.md`, `plan.md` y `tasks.md`.
        - La toma de requisitos escribe la spec en el repositorio.
      - **Sin SDD**, si el cambio es **pequeño** (un arreglo, un ajuste, una tarea de una sola pieza): requisitos breves en la propia tarea, sin documentos.
      - La decisión y su motivo **quedan en la tarea**: se ven en su detalle y en el Tablero, y las etapas siguientes la reciben en su contexto.
        - Con SDD, la validación revisa la spec.
        - La arquitectura escribe el plan.
        - Los programadores trabajan a partir de `tasks.md` y lo van marcando.
        - QA comprueba los criterios de aceptación de la spec.
      - El usuario puede **cambiar la decisión** en la revisión humana de la validación de requisitos, o a mano en la tarea. La tarea vuelve entonces a la toma de requisitos para rehacerlos con el modo nuevo.
   2. **Validación de requisitos**: comprueba que estén completos, que no se contradigan y que se puedan probar, y que la decisión sobre SDD encaje con el tamaño del trabajo. Si no, devuelve la tarea a la toma de requisitos.
      - Salida: *«La tarea solo pide definir o revisar requisitos»*.
   3. **Arquitectura**: decide cómo se construye y lo deja escrito en el proyecto como documento de decisiones. Cubre:
      - el stack tecnológico (lenguajes, frameworks, base de datos…);
      - los servicios en la nube que hagan falta (Azure, AWS o Google Cloud) o el despliegue local;
      - la estructura de componentes y las integraciones.

      Si el proyecto ya tiene arquitectura, la respeta y solo la amplía para lo que pide la tarea. Si la arquitectura no se puede definir con los requisitos que hay, devuelve la tarea a la toma de requisitos.
      - Salida: *«La tarea solo pide definir o revisar la arquitectura»*.
   4. **En paralelo**: **Frontend**, **Backend** y **Datos** (data analyst/scientist). Cada rama tiene su condición, y el decisor elige las que tocan a cada tarea. Por ejemplo, un cambio solo de interfaz pasa solo por Frontend.
   5. **QA**: espera a las ramas por las que ha pasado la tarea. Si algo falla, la devuelve a la rama correspondiente.
      - Salida: *«La tarea no necesita despliegue»* (por ejemplo, un análisis de datos o un cambio interno).
   6. **IT / despliegue**: hace el despliegue según la arquitectura definida, o deja lo necesario para hacerlo (scripts, configuración, notas de la versión).
13. Revisión humana en tres sitios: la validación de requisitos, la arquitectura y el final (después de IT / despliegue). Las demás etapas pasan sin revisión. El usuario la cambia después en el editor como en cualquier pipeline.

**D. Plantillas de agentes para esos roles**
14. **Plantillas fijas nuevas**, una por rol de «Desarrollo», cada una con sus instrucciones, permisos y modelo por defecto:
   - Analista de requisitos: es la «Analista» actual, ajustada a criterios de aceptación y a la decisión sobre SDD;
   - Validador de requisitos;
   - **Arquitecto de software**: stack, servicios en la nube y decisiones de diseño. No es el Arquitecto que diseña agentes, y en la interfaz se distinguen por el nombre;
   - Desarrollador frontend;
   - Desarrollador backend;
   - Data analyst / data scientist;
   - QA: es la actual, ajustada a las ramas;
   - IT / DevOps (despliegue).

   Se quedan también «Desarrollador», «Redactor» y «Comercial».
15. Al aplicar «Desarrollo» (al crear el proyecto o desde su pestaña Pipeline):
   - Cada etapa recibe el agente activo creado desde su plantilla, si existe.
   - Si falta alguno, la app lista los que faltan y **los crea desde sus plantillas**, con el CLI, la cuenta y el modelo que elija el usuario, en un único paso.
   - El usuario puede desmarcar alguno y elegir en su lugar un agente que ya tenga.
   - Los agentes creados quedan activos, en un equipo «Desarrollo» (nuevo, o uno existente que elija el usuario).
16. Las plantillas nuevas salen también en el diálogo de nuevo agente y en la biblioteca de plantillas de la fase 19.

**E. Pipeline en blanco o copiado de otro proyecto**
17. Al crear un proyecto, y en la pestaña Pipeline de un proyecto sin pipeline, se elige entre:
    - la plantilla «Desarrollo»;
    - **copiar el pipeline de otro proyecto**;
    - **en blanco**: abre el editor vacío, como ahora;
    - **diseñarlo con el Arquitecto** (apartado F);
    - ninguno, solo al crear el proyecto.
18. Copiar un pipeline copia sus etapas, ramas y condiciones, uniones, salidas, revisiones humanas, `reject_to`, ajustes del decisor y los ajustes de skills y conexiones de cada etapa, **con los mismos agentes**. Las tareas, el historial y el consumo del proyecto de origen no se copian.
19. Si en el proyecto de origen algún agente está archivado o en borrador, la etapa se copia sin agente y se avisa, igual que al guardar desde el editor.

**F. El Arquitecto donde hace falta**
20. **«Diseñar con el Arquitecto»** en la pestaña Pipeline de un proyecto sin pipeline y en Nuevo proyecto (cuando ya se ha creado):
    - abre una conversación en modo equipo con ese proyecto ya elegido;
    - el Arquitecto propone el pipeline y los agentes que falten, reutilizando los que ya existen;
    - se aprueba como cualquier propuesta compuesta de la fase 19, en una sola operación o por partes.
21. **«Nuevo equipo con el Arquitecto»** en la lista de equipos (Agentes e Inicio): el Arquitecto crea un **equipo con sus agentes sin pipeline**. El pipeline pasa a ser opcional en la propuesta de equipo; si el usuario lo pide, se puede añadir el de un proyecto.
22. El Arquitecto **conoce lo nuevo de esta fase**:
    - puede partir de «Desarrollo» para el pipeline y de las plantillas nuevas para los agentes, y lo dice cuando lo hace;
    - propone salidas «Terminar aquí» donde hay tareas que acaban antes.

### Fuera
- Galería de búhos u otras imágenes predefinidas para los proyectos.
- Salidas que terminan solo una rama dentro de una bifurcación abierta (apartado B, punto 9).
- Que una tarea **empiece** en una etapa intermedia (por ejemplo, directamente en Arquitectura): sigue entrando por la primera etapa y, si no hay nada que hacer, esa etapa la pasa.
- Plantillas de pipeline o de equipo guardadas por el usuario (solo se copia el pipeline de otro proyecto).
- Otras plantillas fijas de pipeline además de «Desarrollo» (contenidos, comercial…).
- Que el Arquitecto **cree el proyecto** (carpeta, repositorios): sigue diseñando para un proyecto que ya existe.
- Copiar un pipeline entre instalaciones (exportar e importar pipelines).
- Que la app cree o contrate recursos en la nube por su cuenta. El Arquitecto de software los elige y el agente de IT / despliegue usa lo que haya en el proyecto y en sus conexiones MCP.
- Cambiar los pipelines existentes creados con las plantillas antiguas.

## Historias de usuario
- Como usuario, quiero poner una foto a cada proyecto para reconocerlo de un vistazo.
- Como usuario, quiero que una tarea que solo pide definir requisitos termine al validarlos, sin pasar por los programadores ni gastar en ellos.
- Como usuario, quiero que las tareas grandes, o las de un proyecto que ya usa SDD, se hagan con spec, plan y tareas, y que las pequeñas no carguen con ese proceso.
- Como usuario, quiero que antes de programar un agente decida y deje escrita la arquitectura del proyecto (stack, servicios en la nube), y revisarla yo.
- Como usuario, quiero crear un proyecto y que quede listo para desarrollar, con su pipeline completo y los agentes que hacen falta, sin crearlos uno a uno.
- Como usuario, quiero reutilizar el pipeline que ya me funciona en otro proyecto.
- Como usuario, quiero que el Arquitecto me diseñe el pipeline de un proyecto que todavía no lo tiene, desde el propio proyecto.
- Como usuario, quiero pedirle al Arquitecto un equipo de agentes aunque todavía no tenga un proyecto para él.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Un proyecto acepta una foto propia encuadrada, guardada solo como recorte comprimido y sin metadatos, que sale en la lista, su página, el Tablero, Inicio, las tareas y el selector; se puede cambiar y quitar. No hay galería de búhos para proyectos | Tests del backend y de la interfaz |
| CA2 | **Varios finales**: una etapa con salida termina la tarea cuando el decisor ve cumplida su condición, y si no, la deja seguir; la tarea guarda dónde y por qué terminó y el usuario puede forzar que siga o termine; el editor rechaza una salida sin condición o dentro de una bifurcación abierta; los pipelines sin salidas funcionan igual que antes | Tests del grafo, del motor y de la interfaz |
| CA3 | Nuevo proyecto y la pestaña Pipeline vacía ofrecen «Desarrollo», copiar de otro proyecto, en blanco y el Arquitecto (y «ninguno» al crear); las plantillas antiguas ya no salen y sus pipelines existentes no cambian | Test de la interfaz + test del backend |
| CA4 | «Desarrollo» crea las etapas, ramas y salidas del apartado C y pasa la validación del editor; el decisor elige entre Frontend, Backend y Datos y QA devuelve la tarea a la rama que falló | Tests del backend |
| CA5 | **Decisión sobre SDD**: la toma de requisitos elige SDD en un proyecto que ya lo usa (sigue su formato) o en un trabajo grande (formato de la app), y lo descarta en un cambio pequeño; la decisión y su motivo quedan en la tarea, las etapas siguientes la reciben y el usuario puede cambiarla, con lo que la tarea vuelve a la toma de requisitos | Tests del backend (contexto de cada etapa y cambio de modo) + e2e con el CLI falso + prueba manual con `claude` real en un proyecto con SDD y otro sin él |
| CA6 | Las ocho plantillas de agentes de «Desarrollo» existen; al aplicar la plantilla se crean en un paso los agentes que faltan, con el CLI, la cuenta y el modelo elegidos, en el equipo elegido, y se asignan a sus etapas | Tests del backend y de la interfaz |
| CA7 | **Un proyecto nuevo con «Desarrollo» completa dos tareas con sus agentes de plantilla**: una de desarrollo, de la toma de requisitos al despliegue y pasando por la arquitectura, y otra que solo pide requisitos, que termina tras su validación | e2e con el CLI falso + prueba manual con `claude` real en la app instalada |
| CA8 | Copiar el pipeline de otro proyecto copia etapas, ramas, salidas, revisiones, `reject_to` y ajustes por etapa con los mismos agentes, sin tareas ni historial; los agentes archivados o en borrador quedan sin asignar con aviso | Tests del backend |
| CA9 | **«Diseñar con el Arquitecto» crea el pipeline de un proyecto vacío** desde su pestaña Pipeline, y **«Nuevo equipo con el Arquitecto» crea un equipo con sus agentes sin pipeline**; los dos se aprueban como propuesta compuesta | Tests del backend + e2e con el CLI falso |
| CA10 | Suites completas, lint y `/code-review` en verde | Comandos de `package.json` |

## Prerrequisitos
- Fase 23 cerrada (`v0.9.3`).
- La app instalada con `claude` y una cuenta, para la prueba manual de CA7.

## Riesgos y preguntas abiertas
- **Varios finales cambian la forma del pipeline** (ADR 0020). Afecta al grafo, que está en el backend y repetido en el frontend (`validate.ts`), al motor, al decisor, al editor y a la validación del Arquitecto. El plan lo recoge en una ampliación del ADR 0020.
- **Cuándo se decide la salida**: decidido con el usuario (2026-11-01), la decide el decisor de ramas después de la etapa, y solo en las etapas con salida. Las demás no pagan esa llamada. Se descartó que lo decidiera el agente de la etapa, porque juzgaría su propio trabajo.
- **Salidas de «Desarrollo»**: decididas con el usuario (2026-11-01), las tres del apartado C: tras la validación de requisitos, tras la arquitectura y tras QA.
- **Salidas dentro de una rama**: se dejan fuera, porque terminar en una rama abierta obligaría a parar o descartar las ramas hermanas. Si hace falta, irá en una fase futura.
- **Revisión humana en «Desarrollo»**: decidido con el usuario (2026-11-01), en la validación de requisitos, en la arquitectura y al final.
- **Ramas en paralelo**: decidido con el usuario (2026-11-01), el decisor elige las ramas que tocan a cada tarea, en vez de pasar siempre por Frontend, Backend y Datos.
- **Agentes creados al aplicar la plantilla**: decidido con el usuario (2026-11-01), se crean activos, sin pasar por borrador.
- **Ocho agentes y su gasto**: una tarea completa pasa por seis o más agentes, más el decisor en las bifurcaciones y en las salidas. El plan fija modelos por defecto baratos donde se pueda (validación de requisitos, IT) y lo deja a la vista al elegir el CLI y el modelo.
- **Dos «Arquitectos»**: el agente de plantilla «Arquitecto de software» y el Arquitecto que diseña agentes (fase 19) pueden confundirse. El plan revisa los textos de la interfaz para que siempre se distingan.
- **Criterio para usar SDD**: «grande» lo juzga el agente con las pautas de su plantilla (número de piezas, ramas implicadas, decisiones que hay que dejar escritas). Puede equivocarse en los casos frontera, y por eso la decisión se revisa en la validación de requisitos y el usuario la puede cambiar. El plan fija las pautas y las prueba con peticiones de ejemplo de los dos tipos.
- **Formatos de SDD que se reconocen**: el plan confirma cuáles se detectan (spec-kit, Kiro, OpenSpec, `specs/`, specs por fase como las de este repositorio) y cómo se sigue cada uno. El formato propio de la app es el de reserva para proyectos que no tienen ninguno.
- **Dónde se guarda la decisión**: el plan decide si es un campo nuevo de la tarea o una nota estructurada de su historial, cómo la marca el agente (propuesta: una herramienta del MCP `agentic-os`) y cómo llega al contexto de cada etapa.
- **Documento de arquitectura**: el plan fija dónde lo deja el Arquitecto de software en el proyecto (propuesta: `docs/arquitectura.md` más ADRs), cómo lo leen las etapas siguientes y cómo se actualiza en tareas posteriores sin rehacerlo.
- **IT / despliegue sin destino**: muchos proyectos no tienen dónde desplegar. Las instrucciones de la plantilla dicen qué hacer entonces: dejar el paquete o los pasos y no inventar destinos. El plan lo concreta.
- **Foto del proyecto**: se reutiliza el almacenamiento de avatares de la fase 20 (migración nueva para el proyecto). El plan confirma que la limpieza de imágenes que no se usan también tiene en cuenta los proyectos.
