# Fase 15: Ampliación del conocimiento · Spec

- **Estado**: borrador
- **Rama**: `phase/15-ampliacion-conocimiento`

## Objetivo
Que la biblioteca de conocimiento **crezca con el trabajo de los agentes** y que se pueda **ver y recorrer como un grafo**. Hoy solo el usuario añade documentos. Esta fase permite que cualquier agente, de cualquier CLI, **proponga documentos Markdown nuevos** a partir de lo que ha aprendido (sin tocar nunca los originales), que el usuario los acepte o los rechace, y que todo el conocimiento —ficheros subidos y documentos propuestos— se vea en un **grafo visual** donde se distingue quién aportó qué y qué está relacionado con qué. El grafo, además de verse, **mejora la búsqueda**.

## Punto de partida (fase 14)
- La biblioteca tiene tres niveles (general, proyecto, agente), documentos por referencia, Markdown, trozos con vectores y búsqueda híbrida (`search_knowledge`, `read_knowledge`).
- Los agentes **leen** conocimiento; no pueden **escribir** en él. Sí pueden escribir notas en la memoria del proyecto (`write_project_memory`), que es otra cosa: texto corto sin conversión ni búsqueda.
- La Inbox ya canaliza lo que necesita a la persona (aprobaciones, preguntas, revisiones).
- La pantalla de pipelines usa `@xyflow/react`, así que ya hay una base para dibujar grafos.

## Alcance
### Dentro
**A. Propuestas de los agentes**
- Herramienta MCP **`propose_knowledge`** para todos los agentes: título, Markdown, descripción corta y los **documentos en los que se basa** (por título o identificador). Funciona igual con Claude Code y Antigravity (como el resto de herramientas del MCP `agentic-os`).
- La propuesta **no bloquea** al agente: la deja registrada y sigue. Queda en estado **«Propuesto»**: no se indexa para el resto de agentes ni entra en ningún contexto hasta que el usuario la acepta.
- **Nunca se modifica un documento existente.** Ampliar un PDF significa crear un documento nuevo **vinculado** al original («derivado de»). El PDF y su Markdown se quedan exactamente como estaban.
- **Confirmación del usuario** en la **Inbox** (nueva clase de petición «Conocimiento propuesto») y en la biblioteca (filtro «Propuestos»): ver el texto completo, **editarlo**, elegir el **nivel** (por defecto, el del documento de origen; el agente solo sugiere) y **Aceptar** o **Rechazar**. Al aceptar pasa por la misma pipeline de la fase 14 (troceado, vectores, índice) pero **sin conversión**: el Markdown es el contenido.
- **Procedencia visible**: qué agente, en qué ejecución y tarea, cuándo y con qué documentos de origen. Los documentos aceptados llevan la marca **«Generado por agente»** en la biblioteca, en el índice de conocimiento que reciben los agentes y en los resultados de búsqueda, para que un agente sepa qué es fuente original y qué es una síntesis.
- **Controles anti-ruido**: máximo de propuestas por ejecución (3 por defecto, configurable), tamaño máximo, aviso al agente si **ya existe** algo muy parecido (no se crea duplicado), y el rechazo queda registrado para no volver a proponer lo mismo. Ajuste global para **desactivar** las propuestas.
- Un agente puede proponer **una nueva versión de lo que él mismo propuso** (el documento aceptado sigue intacto; la versión nueva es otra propuesta «reemplaza a…» que el usuario decide).

**B. Grafo de conocimiento**
- Vista **«Grafo»** en la biblioteca (general, proyecto y agente) y una vista global en `/conocimiento`.
- **Nodos**: un nodo por documento, con aspecto distinto según su origen —**fichero** (PDF, Word…), **web**, **imagen**, **propuesto por un agente (aceptado)** y **propuesto, pendiente**—, tamaño según su peso y color según el nivel. Los documentos apagados o con el original perdido se ven atenuados o marcados.
- **Aristas**: (1) **derivado de** (procedencia, dirigida, la fija el agente al proponer) y (2) **relacionado** (parecido de contenido, no dirigida, calculada en local con los vectores que ya existen; solo las más fuertes, con un umbral y un máximo de vecinos por nodo). El grosor indica la fuerza. Se distinguen visualmente.
- Interacción: zoom y arrastre, **filtros** (nivel, tipo de origen, estado, proyecto), **búsqueda** que resalta los nodos que responden a una consulta, clic para abrir la ficha del documento (la de la fase 14) y doble clic para centrar en su vecindario.
- El grafo **se mantiene solo**: las relaciones se recalculan al indexar o quitar un documento y al cambiar el modelo de significado.

**C. El grafo ayuda a buscar**
- `search_knowledge` añade a cada resultado los **documentos vecinos** (derivados, de los que deriva y los más relacionados), en una línea, para que el agente sepa que hay más material cerca y pueda leerlo con `read_knowledge`.
- Los vecinos de un resultado fuerte **suben o completan** la lista cuando encajan con la consulta (expansión de un salto, con un límite), sin desplazar los resultados directos.
- Nueva herramienta MCP **`related_knowledge`** (documento → vecinos con el motivo del vínculo), solo lectura.
- El **probador de búsqueda** de la fase 14 muestra qué resultados vienen de la expansión por el grafo.

### Fuera
- Que un agente **edite o borre** documentos existentes (ni los del usuario ni los suyos ya aceptados).
- **Aceptar automáticamente** las propuestas (se deja el diseño preparado, pero esta fase exige confirmación siempre).
- Extraer entidades y relaciones con un LLM (GraphRAG completo); el grafo se basa en procedencia y vectores.
- Colaboración entre usuarios, comentarios o historial de versiones de los documentos del usuario.
- Grafos de otras cosas (código, git, tareas).
- Dictado por voz (fase 16).

## Historias de usuario
- Como usuario, quiero que un agente que ha trabajado con mi PDF de Celery pueda **proponer una guía nueva** con lo que aprendió, **vinculada al PDF**, para que ese conocimiento no se pierda, sin que el PDF cambie.
- Como usuario, quiero **revisar, editar y aceptar o rechazar** cada propuesta antes de que nadie la use, para que la biblioteca no se llene de errores de un agente.
- Como usuario, quiero **ver toda mi biblioteca como un grafo** y distinguir lo que subí yo de lo que propusieron los agentes, para entender qué sabe el equipo y de dónde viene.
- Como agente, quiero saber que un resultado es **generado por otro agente** y qué documentos son **vecinos**, para fiarme más de las fuentes originales y encontrar material relacionado.
- Como usuario, quiero poder **apagar las propuestas** o limitar cuántas hace cada ejecución, para tener el control del ruido.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Un agente (CLI falso con cliente MCP real, y `claude` y `agy` en la prueba manual) llama a `propose_knowledge` basándose en un PDF del proyecto: se crea un documento **«Propuesto»** vinculado al PDF y aparece en la Inbox y en el filtro «Propuestos» | test e2e + manual |
| CA2 | Un documento propuesto **no aparece** en el contexto, en `search_knowledge` ni en `read_knowledge` de ningún agente hasta aceptarlo | test |
| CA3 | **Aceptar** (con edición del título, del texto y del nivel) lo procesa sin conversión, lo indexa y lo hace buscable; **Rechazar** lo descarta y queda registrado | test + UI |
| CA4 | El PDF original y su Markdown **no cambian** (mismo hash, mismo texto) tras proponer, aceptar o rechazar | test |
| CA5 | Se respetan el máximo de propuestas por ejecución, el tamaño máximo, la detección de duplicados («ya existe…») y el ajuste que desactiva las propuestas, y el agente recibe el motivo con palabras | tests |
| CA6 | Los documentos aceptados llevan «Generado por agente», su procedencia (agente, ejecución, tarea, fecha, orígenes) en la ficha y la marca en el índice y en los resultados de búsqueda | test + UI |
| CA7 | El grafo muestra con aspecto distinto fichero / web / imagen / propuesto aceptado / pendiente, aristas «derivado de» y «relacionado», y los filtros y la búsqueda con resaltado funcionan; un clic abre la ficha | tests de UI |
| CA8 | Las relaciones «relacionado» se calculan en local, solo por encima del umbral y con tope de vecinos, y se recalculan al indexar, quitar un documento o cambiar de modelo | tests |
| CA9 | Con un corpus de prueba, una consulta que acierta el PDF devuelve también, como vecino o por expansión, la guía derivada, y esto **mejora** el acierto frente a la búsqueda sin grafo sin empeorar los resultados directos | test de calidad (como el de la fase 14) |
| CA10 | El grafo es fluido con 300 documentos y 1 000 aristas (sin bloquear la interfaz) | test de rendimiento |
| CA11 | Borrar el documento de origen no borra el derivado: queda marcado «origen eliminado» y sigue en el grafo | test |
| CA12 | Con el binario empaquetado el flujo completo (proponer → Inbox → aceptar → buscar) funciona | e2e empaquetado |

## Prerrequisitos
- **Fase 14 cerrada** (biblioteca, pipeline, vectores, MCP, ficha del documento y gestión de modelos).
- La Inbox (fase 06) para la nueva clase de petición.

## Riesgos y preguntas abiertas
- **Calidad y alucinaciones**: un agente puede proponer algo falso o redundante. Mitigación: confirmación obligatoria, procedencia siempre visible, marca «Generado por agente» también de cara a los demás agentes, límites y detección de duplicados.
- **Bucles de ruido**: agentes que leen propuestas y proponen más sobre ellas. Solo se leen las **aceptadas**, con el límite por ejecución y el rechazo registrado el riesgo es bajo, pero se mide en la validación.
- **Coste del cálculo de relaciones**: comparar todos con todos es cuadrático. Se usan **vectores medios por documento** y vecinos más próximos con tope; hay que medir con 300–1 000 documentos y con el cambio de modelo (recalcular todo).
- **Calidad del parecido**: un umbral mal puesto llena el grafo de aristas inútiles o lo deja vacío. Se calibra con el corpus de prueba y se deja ajustable; los documentos sin vectores (sin modelo de significado) solo tienen aristas de procedencia.
- **Rendimiento del dibujo**: `@xyflow/react` con cientos de nodos y un *layout* de fuerzas necesita cuidado (cálculo fuera del hilo principal o por lotes, agrupación por nivel, ocultar aristas débiles al alejar). Posible spike al inicio.
- **Preguntas para decidir en el plan** (con la recomendación entre paréntesis):
  1. ¿El agente puede **sugerir el nivel** o lo decide siempre el usuario? (sugiere, decide el usuario).
  2. ¿La propuesta es una **petición de la Inbox** (como una aprobación) o solo una lista en la biblioteca con un aviso? (ambas: aviso en la Inbox y revisión en la biblioteca, sin bloquear la tarea).
  3. ¿Una **versión nueva** de lo propuesto reemplaza o convive con la anterior? (convive hasta que el usuario elija «Reemplazar»).
  4. ¿El grafo global mezcla **todos los proyectos** o se filtra por proyecto por defecto? (por defecto lo visible desde el contexto actual; opción «todo»).
  5. ¿Se guarda en el Markdown propuesto el **bloque de procedencia** (para que sobreviva si se exporta) o solo en la base de datos? (solo en la base de datos y en la ficha; el Markdown queda limpio).
