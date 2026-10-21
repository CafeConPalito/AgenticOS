# ADR 0022: Propuestas de los agentes y grafo de conocimiento

- **Estado**: propuesto (se cierra al terminar los spikes)
- **Fecha**: 2026-10-20
- **Contexto de decisión**: fase 15 ([`spec.md`](../phases/15-ampliacion-conocimiento/spec.md), [`plan.md`](../phases/15-ampliacion-conocimiento/plan.md))

## Contexto
La biblioteca de la fase 14 ([ADR 0021](0021-knowledge.md)) solo crece con lo que añade el usuario, y sus documentos no se relacionan entre sí. La fase 15 pide que cualquier agente proponga documentos nuevos sin tocar los existentes y con confirmación del usuario, que toda la biblioteca se vea como un grafo y que los agentes usen ese grafo para buscar, tanto de forma automática como recorriéndolo ellos. Todo en local y sin LLM para construir el grafo.

## Decisión

### Una propuesta es un documento más, en revisión
- Las propuestas son `KnowledgeDoc` con `origin = agent`, `source_kind = markdown` y `review = proposed`. Así reutilizan la ficha, el troceado, los vectores y la búsqueda sin un modelo paralelo. `visible_docs` exige `review = none`: **una propuesta no la ve ningún agente** hasta aceptarla.
- La **procedencia** (agente, ejecución, tarea, fechas, nivel sugerido, versión que sustituye) vive en `knowledge_provenance`, no en el Markdown, que queda limpio.
- Las aristas **«derivado de»** viven en `knowledge_sources` con una copia del título del origen y `SET NULL`: borrar el origen nunca borra el derivado; queda «origen eliminado».
- **Nunca se modifica un documento existente.** Una versión nueva es otra propuesta con `replaces_id`; convive con la anterior hasta que el usuario elija «Reemplazar».
- **Rechazar** borra el documento y guarda solo una huella (`sha256`, centroide, título y motivo) en `knowledge_rejections`, para avisar al agente si lo propone otra vez.
- Aceptar procesa el Markdown desde el paso «trocear» de la pipeline: no hay conversión porque el Markdown es el contenido.
- La propuesta **no bloquea** al agente; la revisión llega por la Inbox (clase `knowledge`) y por la biblioteca, con los mismos endpoints.

### Relaciones por vectores, con umbral y tope
- Cada documento tiene un **centroide** (vector medio normalizado de sus trozos). La arista «relacionado» une dos documentos cuyo coseno supera un umbral **por modelo**, con un máximo de vecinos por documento. Se guarda en `knowledge_related` y se recalcula al indexar, quitar o cambiar de modelo.
- Es lineal por documento (uno contra todos con NumPy) y cuadrática solo al cambiar de modelo, aceptable hasta miles de documentos.
- Las relaciones se calculan en toda la biblioteca y **la visibilidad se aplica al leer**, para que el grafo de cada agente sea un subconjunto del global sin recálculos.

### Temas por comunidades, sin LLM
- Los temas son comunidades (Louvain, determinista) sobre las aristas «relacionado» y «derivado de». Su nombre sale de los documentos más centrales. Se calculan al leer y se cachean por versión del grafo.
- Se descarta GraphRAG (entidades y relaciones con un LLM) por coste, tiempo y dependencia de un modelo; queda para una fase futura si hiciera falta.

### El grafo como herramienta de los agentes, de solo lectura
- Ayuda automática: vecinos en cada resultado de `search_knowledge` y expansión de un salto después de los resultados directos (`found_by = graph`).
- A demanda: `knowledge_map`, `related_knowledge`, `explore_knowledge` (varios saltos, máximo 3) y `knowledge_path`, más el parámetro `graph` de `search_knowledge`. Todas con presupuesto de tokens y las mismas reglas de visibilidad que la búsqueda.
- La única herramienta que escribe es `propose_knowledge`, y lo que escribe nadie lo ve hasta que el usuario lo acepta.

### Dibujo en el cliente
- El backend da nodos, aristas y temas; el *layout* (fuerzas) se calcula en un Web Worker del frontend y se dibuja con `@xyflow/react`, que ya usa la app.

## Consecuencias
- El grafo y los temas se degradan sin modelo de significado: solo hay aristas de procedencia.
- El umbral depende del modelo y hay que calibrarlo; se deja ajustable.
- Nuevas tablas y una clase más de la Inbox; `downgrade` las borra.
- Las decisiones pendientes de los spikes (centroide frente a pares de trozos, Louvain propio o `networkx`, `d3-force` o `<canvas>`) se anotarán aquí al cerrarlos.
