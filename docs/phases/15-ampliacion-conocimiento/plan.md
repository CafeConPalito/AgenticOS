# Fase 15: Ampliación del conocimiento · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-21) · en desarrollo (bloque 0)

## Lo que ya se sabe (revisado al escribir el plan)
- **Documentos** (`models/knowledge.py`): `KnowledgeDoc` con nivel (`scope`, `project_id`, `agent_id`), origen (`source_kind`: `file` · `image` · `url`), proceso (`status`) y resultado (`markdown`, `md_tokens`, `embed_model`). `KnowledgeChunk` guarda el vector de cada trozo (`vector`, `vector_model`). No hay un vector por documento ni ninguna relación entre documentos. Última migración: `0017_knowledge_images`.
- **Pipeline** (`services/knowledge/pipeline.py`): convertir → imágenes → describir → trocear → indexar. Un documento cuyo contenido ya es Markdown puede empezar en «trocear» sin tocar el resto.
- **Búsqueda** (`search.py`): `visible_docs` (nivel, `ready`, `mode != off`) y fusión RRF; cada resultado lleva `found_by`. La matriz de vectores se cachea por modelo y se invalida con `index.bump_when_committed`.
- **MCP** (`mcp_server.py`): cada herramienta es un método del protocolo `AgentBackend`, implementado en el `RunManager` con el `run_id` del token; `knowledge/agent_tools.py` da el texto de `search_knowledge` y `read_knowledge` y deja el evento `mcp` en la ejecución.
- **Contexto** (`knowledge/context.py`): índice de documentos visibles más los textos que caben en el presupuesto, y una línea de uso en las reglas.
- **Inbox** (`models/inbox.py`, `services/inbox.py`): `InboxKind` cerrado con `CHECK`; añadir una clase es migración + texto + vista. Los elementos guardan copias (agente, proyecto) para seguir siendo legibles.
- **Eventos**: `/api/knowledge/events` ya emite cambios de documentos; el frontend los aplica con `applyKnowledgeEvent`.
- **Frontend**: `@xyflow/react` 12.12 ya está (pipelines); no hay librería de *layout* de fuerzas. `numpy` ya está en el backend; `networkx` no.

## Bloque 0 · Spikes (antes de programar)
Scripts en `spikes/knowledge-graph/`, con el corpus de la fase 14 ampliado con **guías derivadas** escritas a mano (Celery → guía de reintentos, guía de colas) y un segundo tema sin relación. Evidencias en `evidencias/`.

| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Relaciones**: con `multilingual-e5-small`, EmbeddingGemma 2 y bge-m3, ¿qué parecido entre documentos funciona mejor: el **vector medio** de sus trozos o la media de los *k* mejores pares de trozos? ¿Qué **umbral** por modelo deja juntos los del mismo tema y separa los de otro (e5 da cosenos altos para todo)? Tiempo con 300 y 1 000 documentos | Umbral relativo (percentil por documento) en vez de absoluto; vecinos solo por pares de trozos |
| S2 | **Temas**: Louvain propio (≈150 líneas sobre las aristas) frente a `networkx.louvain_communities(seed=0)`: calidad con el corpus, **estabilidad** (mismo corpus → mismos temas, también tras añadir un documento) y peso de `networkx` en el ejecutable. Nombre del tema: título del documento más central + términos de sus títulos y apartados (TF-IDF) | Componentes conexas con un umbral más alto; nombre = título del más central |
| S3 | **Dibujo**: `d3-force` en un **Web Worker** + `@xyflow/react` con 300 nodos y 1 000 aristas: tiempo hasta estabilizar, FPS al hacer zoom y arrastrar, y si `onlyRenderVisibleElements` y ocultar aristas débiles al alejar bastan | `layout` por lotes con posiciones guardadas; como último recurso, dibujo en `<canvas>` (sigma.js) solo para la vista «Todo» |
| S4 | **Propuestas reales**: `claude` y `agy` con el MCP de prueba y un PDF de Celery: ¿llaman a `propose_knowledge` cuando deben y no en cada ejecución? ¿Qué redacción de la herramienta y de la línea del contexto lo consigue? ¿Usan `knowledge_map` y `explore_knowledge` sin que se lo pidan? | Ajustar las descripciones; si proponen de más, bajar el máximo por defecto a 1 |

## Resultados de los spikes (bloque 0, 2026-10-21)
Evidencias en [`evidencias/s1-s3-grafo.md`](evidencias/s1-s3-grafo.md); scripts en `spikes/knowledge-graph/`.

- **S1 · Relaciones**: el **centroide** (vector medio de los trozos) gana en los tres modelos (AUC 0,94–0,97) a los pares de trozos. El coseno crudo no da un umbral común (rangos distintos por modelo), pero **restando el vector medio de la biblioteca** la escala es común: umbral **0,20** → precisión de aristas 0,8–0,9. Con **el vecino más próximo siempre que supere 0,10** los documentos puente (Redis entre Celery y Docker) no quedan sueltos. Todos contra todos con 1 000 centroides: 9 ms.
- **S2 · Temas**: Louvain de `networkx` (semilla 0, grafo ordenado) da temas coherentes (NMI 0,88–0,96) y **estables** (barajar el orden o quitar un documento: NMI 1,0). Nombre = documento más central + 2 palabras TF-IDF. `networkx` pesa 14 MB sin comprimir; si el *sidecar* crece demasiado, Louvain propio.
- **S3 · Dibujo**: `d3-force` con 300 nodos y 1 000 aristas tarda **327 ms** (1 000 y 3 500: 1,3 s), así que va en un Worker. La fluidez de `@xyflow/react` se mide con navegador en el bloque 6 (plan B: `<canvas>`).
- **S4 · Agentes reales**: aplazado al bloque 8 (necesita las herramientas hechas).

### Cambios al diseño por los spikes
1. Relación = **coseno de centroides centrado en la media de la biblioteca**; `graph.threshold` = 0,20, vecino más próximo ≥ 0,10 siempre, máximo 8. Con menos de 8 documentos con vectores se usa el coseno crudo con un umbral por modelo en el catálogo (e5 0,91 · Gemma 0,80 · bge-m3 0,68).
2. El recálculo es **completo en memoria con cada cambio** y se escribe solo la diferencia (no «uno contra todos»).
3. Los temas usan `networkx` (se añade a las dependencias del backend en el bloque 3).
4. *Layout* con `d3-force` en un Web Worker, con posiciones parciales cada 30 iteraciones.

## Diseño ([ADR 0022](../../adr/0022-knowledge-graph.md), nuevo)

### 1. Modelo de datos (migración `0018_knowledge_graph`)
- **`KnowledgeDoc`** gana:
  - `origin` (`user` · `agent`): quién lo aportó. `source_kind` admite `markdown` (el contenido es el Markdown propuesto: no hay original en disco, nunca está `missing`);
  - `review` (`none` · `proposed`): `proposed` es una propuesta pendiente (no es visible para ningún agente: `visible_docs` exige `review = none`); rechazar la borra;
  - `summary` (una línea: la descripción o la primera frase del Markdown), para el grafo y las herramientas;
  - `centroid` (BLOB) y `centroid_model`: vector medio normalizado de sus trozos, calculado al indexar.
- **`KnowledgeProvenance`** (`knowledge_provenance`, 1:1 con un documento del agente): `agent_id`, `agent_name`, `run_id` (`SET NULL`), `task_id` (`SET NULL`), `task_title` (copia), `proposed_at`, `suggested_scope`, `replaces_id` (`SET NULL`, la versión que pretende sustituir), `decided_at`, `edited` (si el usuario cambió el texto al aceptar) y `replace_on_ready` (aceptada con «Reemplazar»: la versión anterior se borra cuando la nueva queda lista).
- **`KnowledgeSource`** (`knowledge_sources`): aristas **«derivado de»**. `doc_id` (el derivado, `CASCADE`), `source_id` (`SET NULL`) y `source_title` (copia). Si se borra el origen, la fila queda con `source_id` nulo: el derivado se ve «origen eliminado» (CA11).
- **`KnowledgeRelated`** (`knowledge_related`): aristas **«relacionado»**, `a_id < b_id` (ambas `CASCADE`), `weight` (coseno) y `model`. Clave primaria `(a_id, b_id)`.
- **`KnowledgeRejection`** (`knowledge_rejections`): lo rechazado sin el texto: `title`, `md_sha256`, `centroid`, `agent_id`, `reason`, `rejected_at`. Sirve para avisar al agente si vuelve a proponer lo mismo.
- `InboxKind.KNOWLEDGE` (`knowledge`) con `knowledge_doc_id` en el elemento (`SET NULL`).
- `downgrade` borra lo nuevo.

### 2. Propuestas (`services/knowledge/proposals.py`)
**`propose_knowledge(title, markdown, description="", based_on=[], level="", replaces="")`** (MCP):
1. Comprobaciones, en este orden, cada una con un motivo en palabras que recibe el agente (CA5):
   - ajuste `knowledge.proposals.enabled` (por defecto, sí);
   - máximo por ejecución `knowledge.proposals.per_run` (3) contando las de este `run_id`;
   - tamaño: título ≤ 200 caracteres, Markdown entre 200 caracteres y `knowledge.proposals.max_tokens` (20 000 tokens);
   - `based_on`: cada entrada es un id o un título **visible** para el agente; los que no existen se rechazan con la lista de los parecidos;
   - `replaces`: solo un documento **aceptado propuesto por el mismo agente**;
   - **duplicados**: mismo `sha256` del Markdown, o centroide con coseno ≥ `knowledge.proposals.duplicate_threshold` (calibrado en S1) contra los documentos visibles, las propuestas pendientes y los rechazos → «Ya existe algo muy parecido: «X» (aceptado/pendiente/rechazado el …)». Sin modelo de significado, solo el `sha256` y el título exacto.
2. Crea el `KnowledgeDoc` (`origin=agent`, `source_kind=markdown`, `review=proposed`, `status=ready`, nivel provisional = el del primer documento de origen, o el sugerido si es más estrecho) con su procedencia y sus orígenes. Trocea y calcula el centroide para el duplicado, **sin** meterlo en FTS ni en la matriz de búsqueda.
3. Crea el elemento de la Inbox («Conocimiento propuesto: título», con el agente y el proyecto) y emite el evento. Devuelve al agente «Propuesta registrada (pendiente de revisión): …». No espera.

**Aceptar** (`POST /api/knowledge/docs/{id}/accept`, cuerpo opcional con `title`, `description`, `markdown`, `scope`, `project_id`, `agent_id` y `replace`):
- aplica las ediciones (`edited = true` si hay alguna) y el nivel elegido;
- pasa `review` a `none` y encola el documento desde **«trocear»** (sin conversión ni imágenes): trozos, FTS, vectores, centroide y relaciones;
- con `replace = true` y `replaces_id`, al terminar bien **borra** la versión anterior y mueve a la nueva sus aristas «derivado de» entrantes (los documentos que derivaban de ella). Sin `replace`, conviven;
- resuelve el elemento de la Inbox (`approved`).

**Rechazar** (`POST …/reject`, `reason` opcional): guarda la `KnowledgeRejection`, borra el documento y resuelve el elemento (`rejected`).

**Borrar un origen**: las filas de `knowledge_sources` quedan con `source_id` nulo. Una propuesta pendiente cuyo origen se borra se mantiene (el usuario decide).

Desde la Inbox y desde la biblioteca se usan los mismos endpoints. Si se resuelve en un sitio, el otro se actualiza por eventos.

### 3. Grafo (`services/knowledge/graph.py`)
- **Centroide**: al indexar, media de los vectores de sus trozos, normalizada (o lo que decida S1). Sin modelo de significado no hay centroide.
- **Relaciones** (S1): matriz de centroides de todos los documentos aceptados del mismo modelo, centrada en su media y normalizada; coseno de todos contra todos con NumPy. Cada documento conserva sus hasta `knowledge.graph.max_neighbors` (8) vecinos más próximos que superen `knowledge.graph.threshold` (0,20) y, además, su vecino más próximo si supera 0,10; la arista existe si cualquiera de los dos la elige. Con menos de 8 documentos con vectores se usa el coseno crudo con el umbral del modelo (catálogo). Las relaciones se calculan entre **todos** los niveles; la visibilidad se aplica al leer.
- **Cuándo se recalcula**: al terminar de indexar un documento, al quitarlo, al cambiar el umbral o los vecinos, y al cambiar de modelo (cuando termina el `reindex`). Siempre **completo en memoria** (9 ms con 1 000 documentos) y se escribe solo la diferencia contra `knowledge_related`. Se hace en el hilo de la cola, después de indexar, y sube `graph_version`.
- **Temas** (`topics.py`): comunidades sobre las aristas «relacionado» (peso = coseno) y «derivado de» (peso 1) con el algoritmo de S2, con orden y semilla fijos. Nombre: título del documento más central más los términos más propios del grupo. Se calcula al leer y se cachea por `graph_version`. Los documentos sin aristas forman el tema «Sueltos».
- **Lectura** (`GET /api/knowledge/graph`): parámetros `project_id`, `agent_id` (el contexto actual: lo visible desde ahí, decisión 4 de la spec) o `all=true` (toda la biblioteca), más `include_proposed` (por defecto, sí en la UI). Devuelve nodos (id, título, `origin`, `source_kind`, nivel, proyecto o agente, `review`, `mode`, `presence`, `md_tokens`, tema), aristas (tipo, origen, destino, peso; «derivado de» con origen eliminado incluida como nodo fantasma) y temas (id, nombre, tamaño). Las propuestas pendientes salen con sus aristas «derivado de», sin «relacionado».
- **Eventos**: `graph_changed` con la versión, para que la vista recargue.

### 4. Búsqueda con el grafo (`search.py`, `graph_search.py`)
**Automático (apartado C)**:
- `search_knowledge` añade a cada resultado una línea «Vecinos: título (derivado de), título (relacionado 0,82)…», como mucho 4, solo visibles.
- **Expansión de un salto**: de los 3 mejores resultados directos, sus vecinos visibles que no estén ya en la lista; de cada uno, su mejor trozo para la consulta (de la puntuación por vector que ya se calculó). Se añaden **después** de los directos, hasta `knowledge.graph.expand` (3), si su puntuación es al menos el 80 % de la del último directo. `found_by = "graph"`.

**A demanda (apartado D)**, en `knowledge/graph_tools.py`, todas con el mismo `visible_docs` (solo aceptados, sin apagados) y con evento `mcp`:
- **`knowledge_map(topic="")`**: los temas visibles, de mayor a menor, con nombre, número de documentos, los 3 principales (título y «Generado por agente») y los temas vecinos; con `topic`, la lista de sus documentos con su resumen. Máx. 2 000 tokens.
- **`related_knowledge(document, kinds="all", origin="all")`**: vecinos directos con el motivo y la fuerza.
- **`explore_knowledge(document="", query="", hops=2, kinds="all", origin="all", level="", max_docs=15)`**: si viene `query`, los puntos de partida son los documentos de los 3 mejores resultados de la búsqueda. Recorrido por mejor camino (fuerza = producto de los pesos, «derivado de» = 1), hasta `hops` (máx. 3) y `max_docs` (máx. 30). Devuelve los documentos por fuerza (título, id, tipo, nivel, «Generado por agente», resumen) y, para cada uno, el camino desde el punto de partida. Recorta a 3 000 tokens.
- **`knowledge_path(source, target, max_hops=4)`**: Dijkstra con coste `-log(peso)`; el camino con el motivo de cada salto, o «No hay camino en n saltos».
- **`search_knowledge(query, limit=8, graph="neighbors")`**: `off` (como la fase 14), `neighbors` (apartado C, por defecto) o `explore` (además, el subgrafo de dos saltos de los mejores resultados, como `explore_knowledge`).

**Contexto**: la sección «Conocimiento» gana, dentro del presupuesto, «Temas: nombre (n), …» (hasta 8, ~150 tokens) y la marca «Generado por agente» en el índice. Las reglas de Agentic OS explican en dos líneas `knowledge_map`, `explore_knowledge` y `propose_knowledge` (cuándo proponer: conocimiento nuevo y verificado, no resúmenes de lo que ya hay).

### 5. Ajustes (`GET/PUT /api/settings/knowledge`)
Nuevos: `proposals.enabled`, `proposals.per_run`, `proposals.max_tokens`, `graph.threshold` (por modelo, con su valor por defecto) y `graph.max_neighbors`. Cambiar los dos últimos recalcula las relaciones.

### 6. Frontend
- **API** (`api/knowledge.ts`): `useAcceptProposal`, `useRejectProposal`, `useKnowledgeGraph`, tipos nuevos (`origin`, `review`, `provenance`, `sources`) y el evento `graph_changed`.
- **Revisión** (`components/knowledge/ProposalReview.tsx`): hoja con el texto en Markdown (vista y edición), título, descripción, nivel (por defecto el propuesto, con el sugerido del agente), los orígenes, la procedencia, el aviso «Reemplaza a …» con la opción «Reemplazar», y **Aceptar** / **Rechazar** (con motivo opcional).
- **Biblioteca**: filtro «Propuestos» con contador, marca «Generado por agente» en la lista y en la ficha, bloque «Procedencia» y «Derivado de» (con «origen eliminado») en la ficha, y pestañas **Lista · Grafo**.
- **Inbox**: la clase `knowledge` con el botón «Revisar», que abre la misma hoja.
- **Grafo** (`components/knowledge/graph/`): `KnowledgeGraph.tsx` con `@xyflow/react`, nodos propios por tipo (fichero, web, imagen, generado por agente, pendiente con borde discontinuo; tamaño por `md_tokens`; color por nivel; atenuado si está apagado o falta el original), aristas propias («derivado de» con flecha y continua; «relacionado» discontinua y con grosor por peso; las débiles se ocultan al alejar). *Layout* `d3-force` en `graph-layout.worker.ts` (S3). Filtros (nivel, tipo, estado, proyecto, tema), alternar «Contexto actual / Todo», búsqueda que resalta (usa `search_knowledge` del probador), clic → ficha, doble clic → vecindario.
- **Probador de búsqueda**: muestra «por el grafo» en los resultados de la expansión, y gana los modos **Explorar** (consulta o documento → subgrafo, resaltado en el grafo) y **Mapa** (los temas).
- **Ajustes** (`KnowledgeSection`): bloque «Propuestas de los agentes» y bloque «Grafo».
- **Registro de la ejecución**: etiquetas para las herramientas nuevas en los eventos `mcp`.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/db/migrations/versions/0018_knowledge_graph.py` | nuevo |
| `backend/src/agentic_os/models/knowledge.py`, `models/inbox.py` | modificado |
| `backend/src/agentic_os/services/knowledge/proposals.py` | nuevo |
| `backend/src/agentic_os/services/knowledge/graph.py`, `topics.py`, `graph_search.py`, `graph_tools.py` | nuevo |
| `backend/src/agentic_os/services/knowledge/pipeline.py`, `search.py`, `docs.py`, `context.py`, `agent_tools.py`, `service.py`, `config.py`, `events.py` | modificado |
| `backend/src/agentic_os/services/mcp_server.py`, `services/runs/*` (backend del MCP), `services/inbox.py` | modificado |
| `backend/src/agentic_os/api/knowledge.py`, `schemas/knowledge.py`, `api/settings*` | modificado |
| `backend/tests/test_knowledge_proposals.py`, `test_knowledge_graph.py`, `test_knowledge_topics.py`, `test_knowledge_graph_tools.py`, `test_knowledge_graph_quality.py`, `test_knowledge_graph_e2e.py` | nuevo |
| `frontend/src/api/knowledge.ts`, `lib/knowledge-events.ts` | modificado |
| `frontend/src/components/knowledge/ProposalReview.tsx`, `graph/KnowledgeGraph.tsx`, `graph/nodes.tsx`, `graph/edges.tsx`, `graph/GraphFilters.tsx`, `graph/graph-layout.worker.ts` | nuevo |
| `frontend/src/components/knowledge/KnowledgeLibrary.tsx`, `DocList.tsx`, `DocSheet.tsx`, `SearchTester.tsx` | modificado |
| `frontend/src/pages/inbox/*`, `pages/settings/KnowledgeSection.tsx`, vista de eventos de la ejecución | modificado |
| `frontend/src/i18n/es.json`, `test/fake-backend.ts` | modificado |
| `frontend/package.json` | `d3-force` (y lo que decida S3) |
| `docs/adr/0022-knowledge-graph.md` | nuevo |
| `spikes/knowledge-graph/` | nuevo |

## Tareas (en orden)
1. [x] **Bloque 0 · Spikes** S1–S3 hechos (S4 pasa al bloque 8); evidencias y cambios al diseño anotados arriba.
2. [x] **Bloque 1 · Datos**: migración `0018`, modelos, `visible_docs` exige `review = none`, `InboxKind.KNOWLEDGE`, esquemas y listados con `origin`/`review`.
3. [x] **Bloque 2 · Propuestas (backend)**: `proposals.py`, `propose_knowledge` en el MCP, controles anti-ruido, Inbox, aceptar (pipeline desde «trocear»), rechazar, reemplazar, borrado de orígenes, ajustes.
4. [x] **Bloque 3 · Grafo (backend)**: centroides, relaciones y su recálculo, temas, `GET /knowledge/graph`, evento `graph_changed`.
5. [x] **Bloque 4 · Búsqueda con el grafo (backend)**: vecinos y expansión en `search_knowledge` (+ parámetro `graph`), `knowledge_map`, `related_knowledge`, `explore_knowledge`, `knowledge_path`, contexto (temas, marca, reglas).
6. [x] **Bloque 5 · Propuestas (frontend)**: API, `ProposalReview`, filtro «Propuestos», marcas y procedencia, Inbox, ajustes.
7. [x] **Bloque 6 · Grafo (frontend)**: vista, nodos y aristas, *layout* en Worker, filtros, «Todo», resaltado, clic y doble clic.
8. [x] **Bloque 7 · Probador y registro (frontend)**: «por el grafo», Explorar, Mapa, etiquetas de las herramientas en el registro.
9. [ ] **Bloque 8 · Calidad y rendimiento**: corpus de prueba con derivados, test de calidad (CA9, CA15), temas (CA13), rendimiento del grafo (CA10), e2e con CLI falso y MCP real (CA1, CA16).
10. [ ] **Bloque 9 · Cierre**: e2e con el binario empaquetado (CA12), `/code-review`, ADR 0022 definitivo, README, validación.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_knowledge_graph_e2e.py`: CLI falso con cliente MCP real propone sobre un PDF del proyecto → documento `proposed` con «derivado de», elemento en la Inbox, aparece en el filtro | CA1 |
| `test_knowledge_proposals.py`: la propuesta no sale en `visible_docs`, contexto, `search_knowledge`, `read_knowledge` ni en las herramientas del grafo | CA2, CA14 |
| ídem: aceptar con título, texto y nivel editados → indexado sin conversión y buscable; rechazar → borrado y `KnowledgeRejection`; Inbox resuelto en los dos casos | CA3 |
| ídem: `sha256` y Markdown del PDF iguales antes y después de proponer, aceptar y rechazar | CA4 |
| ídem: máximo por ejecución, tamaño, duplicado (exacto, parecido, rechazado), propuestas desactivadas, `replaces` ajeno: motivos en palabras | CA5 |
| ídem + `knowledge.test.tsx`: procedencia en la API y en la ficha, «Generado por agente» en el índice del contexto y en los resultados | CA6 |
| `knowledge-graph.test.tsx`: tipos de nodo, dos tipos de arista, filtros, «Todo», resaltado de la búsqueda, clic abre la ficha | CA7 |
| `test_knowledge_graph.py`: aristas solo sobre el umbral y con tope, recálculo al indexar, quitar y cambiar de modelo; sin modelo, solo procedencia | CA8 |
| `test_knowledge_graph_quality.py`: acierto con y sin grafo en el corpus (la guía derivada aparece; los directos no empeoran) | CA9 |
| `knowledge-graph.perf.test.ts` (*layout* con 300 nodos / 1 000 aristas en el Worker, en tiempo máximo) + comprobación manual de fluidez | CA10 |
| `test_knowledge_proposals.py`: borrar el origen deja el derivado con «origen eliminado» y en el grafo | CA11 |
| `test_knowledge_e2e.py` (ampliado, con `AGENTIC_OS_E2E_BINARY`): proponer → Inbox → aceptar → buscar → `knowledge_map` → `explore_knowledge` | CA12 |
| `test_knowledge_topics.py`: temas del corpus (Celery junto y separado del otro tema), nombres, estabilidad entre ejecuciones y tras añadir un documento | CA13 |
| `test_knowledge_graph_tools.py`: saltos, filtros, tope, presupuesto, caminos, visibilidad | CA14 |
| `test_knowledge_graph_quality.py`: pregunta a dos saltos resuelta con `explore_knowledge` y no con la búsqueda sola | CA15 |
| `test_knowledge_graph_e2e.py`: CLI falso usa `knowledge_map` → `explore_knowledge` → `read_knowledge`; eventos en la ejecución; temas y reglas en el contexto | CA16 |

## Decisiones (ADR)
- [ADR 0022](../../adr/0022-knowledge-graph.md): propuestas como documentos con `review`, procedencia y orígenes en tablas propias, relaciones por centroide con umbral y tope, temas por comunidades sin LLM, herramientas del grafo de solo lectura y *layout* en el cliente.
- Pendiente de los spikes: centroide o pares de trozos y umbrales (S1), Louvain propio o `networkx` (S2), `d3-force` en Worker o `<canvas>` (S3).

## Estado al 2026-10-21 (para retomar)
- Bloques 0 a 8 hechos; del bloque 9 están hechos el e2e empaquetado (con el ejecutable anterior a la revisión), la medición del grafo en un navegador real, la prueba con `claude` real y `/code-review high` (10 hallazgos, resueltos en `2619ac8`).
- **Falta**:
  1. Suite completa del backend tras la revisión (`cd backend; uv run pytest tests -q`; unos 35 min; la anterior, antes de la revisión, pasó al 100 %). Los tests afectados por la revisión ya pasan.
  2. Reconstruir el ejecutable (`npm run build:backend`) y repetir `AGENTIC_OS_E2E_BINARY=backend\build\dist\agentic-os-backend.exe uv run pytest tests/test_knowledge_e2e.py` (la migración 0018 cambió).
  3. Frontend completo (`cd frontend; npx vitest run`, `npm run build`).
  4. Rellenar `validacion.md` (tabla de CA con la evidencia, hallazgos de la revisión, retro) y actualizar README/ADR 0022 («Consecuencias»: el ejecutable pesa 162,6 MB, +10,6 MB por `networkx`).
  5. Pendiente manual: `agy` real y el instalador en una máquina limpia.
  6. Cierre: OK del usuario → merge `--no-ff` a `main`, tag `v1.7`, roadmap «cerrada».
- Evidencias ya obtenidas: calidad con e5 real (recall de familia 0,44 → 1,00), 442 tests de frontend, e2e empaquetado 5/5, grafo de 300 nodos y 971 vínculos fluido (≈1 fotograma por paso), `claude` real (haiku, ~0,01 USD) propone con `based_on` correcto y recorre mapa → explorar → leer.
