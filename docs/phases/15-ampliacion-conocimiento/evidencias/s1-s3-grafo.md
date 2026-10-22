# Evidencias S1–S3 · relaciones, temas y dibujo (2026-10-21)

Scripts en `spikes/knowledge-graph/` (`corpus.py`, `s1_relations.py`, `s1b_threshold.py`, `s1c_bridges.py`, `s2_topics.py`, `s3_layout.mjs`). Se ejecutan desde `spikes/knowledge` con `uv run --project . python ../knowledge-graph/<script>`.

**Corpus**: 24 documentos de 10 temas (Celery con dos guías derivadas, Redis, Docker, PostgreSQL, React, Git, autenticación, cocina, viajes y el producto Aurora de la fase 14), 3 trozos cada uno, con la verdad de terreno (tema y «derivado de») en `corpus.py`. Es pequeño a propósito: lo que se mide es el comportamiento relativo; la escala se mide aparte.

## S1 · Cómo medir «relacionado»
Parecido entre documentos, por modelo (AUC = probabilidad de que un par del mismo tema puntúe más que uno de otro tema):

| Modelo | Centroide (AUC) | Media de los 3 mejores pares de trozos | Mejor par de trozos |
|---|---|---|---|
| multilingual-e5-small | **0,943** | 0,918 | 0,889 |
| EmbeddingGemma 2 (q4) | **0,970** | 0,962 | 0,958 |
| bge-m3 | **0,944** | 0,938 | 0,929 |

- **El centroide (vector medio normalizado de los trozos) gana en los tres modelos**, y además es una sola comparación por par. Los pares de trozos no aportan nada y cuestan más.
- **El coseno crudo no sirve para fijar un umbral único**: los rangos dependen del modelo (mismo tema 0,91 / 0,82 / 0,68 frente a otro tema 0,87 / 0,70 / 0,52 en e5 / Gemma / bge-m3), y el de e5 es muy estrecho.
- **Restar el vector medio de la biblioteca antes de comparar** (coseno «centrado») da una escala común: con **0,20–0,30** la precisión de las aristas es de 0,79–0,92 en los tres modelos (recall 0,5–0,75). El *z-score* por fila y el percentil funcionan peor.
- Los documentos puente (Redis, entre Celery y Docker) quedan con parecidos bajos (0,09–0,20). Con solo el umbral 0,20 Redis queda suelto; **conservar siempre el vecino más próximo si supera 0,10** lo une a Celery sin añadir ruido (los documentos sin nada cerca, como el viaje a Lisboa, siguen sueltos).
- **Coste**: todos contra todos con 1 000 centroides, **9 ms** (1 000 × 384); un documento contra todos, 0,7 ms. Con 300, 1,3 ms. Recalcular todo en memoria tras cada cambio es barato; lo caro sería escribirlo, por eso se guarda solo la diferencia.

## S2 · Temas
Grafo = aristas «relacionado» (coseno centrado ≥ 0,20, máximo 8 vecinos, más el vecino más próximo ≥ 0,10) y «derivado de» (peso 1). `networkx.community.louvain_communities(seed=0)` sobre el grafo con los nodos y aristas **ordenados** (el resultado no depende del orden de inserción).

| Modelo | Aristas | Temas | NMI con los temas reales | F1 por pares |
|---|---|---|---|---|
| e5-small | 18 | 8 | 0,920 | 0,783 |
| EmbeddingGemma 2 | 21 | 8 | 0,961 | 0,889 |
| bge-m3 | 19 | 8 | 0,879 | 0,681 |

- Los temas son coherentes: Celery + Redis juntos, Docker aparte, los tres de autenticación juntos, Aurora junta, cocina y viajes en el mismo grupo «no técnico». Con bge-m3 `pg-indices` se pega a Docker (único error grave).
- **Estabilidad**: repetir el cálculo da exactamente lo mismo; barajar el orden de inserción o quitar un documento da NMI = 1,000 contra la base. La resolución (0,6 a 1,2) no cambia nada en este tamaño.
- **Nombre del tema**: título del documento más central (mayor grado ponderado) + 2 palabras distintivas por TF-IDF de los títulos: «Desarrollo con Celery · broker · caché», «Transacciones y aislamiento · alembic · migraciones». Legibles; mejorable con títulos de apartados.
- **Coste**: 0,5–0,9 ms con 24 nodos. `networkx` pesa 14 MB sin comprimir (3,7, Python puro); se excluyen sus tests del ejecutable. Si el *sidecar* crece de más al medirlo, se escribe un Louvain propio (~100 líneas).

## S3 · Dibujo (*layout*)
`d3-force` 3.0 sin interfaz, en Node (el mismo código correrá en un Web Worker), 300 iteraciones (más que las ~300 hasta `alphaMin`):

| Nodos | Aristas | Tiempo |
|---|---|---|
| 50 | 120 | 55 ms |
| **300** | **1 000** | **327 ms** |
| 600 | 2 000 | 713 ms |
| 1 000 | 3 500 | 1 340 ms |

- El cálculo del *layout* cabe de sobra en el presupuesto (CA10), pero 330 ms bloquearían el hilo principal con un solo bloque: **va en un Web Worker** y se devuelven posiciones cada 30 iteraciones para ver cómo se asienta.
- La fluidez del dibujo (`@xyflow/react` con 300 nodos y 1 000 aristas: zoom y arrastre) **no se puede medir sin ventana**: queda para el bloque 6 con el navegador, con `onlyRenderVisibleElements`, aristas débiles ocultas al alejar y, como plan B, un lienzo `<canvas>` para la vista «Todo».

## S4 · Propuestas reales con `claude` y `agy`
**Aplazado al bloque 8**: necesita que existan `propose_knowledge`, `knowledge_map` y `explore_knowledge` para probar si los agentes reales las usan bien. Se mide allí, con las descripciones de las herramientas ya escritas.

## Cambios al diseño
1. **Relación = coseno de centroides centrado en la media de la biblioteca**, umbral **0,20** (ajustable) y **vecino más próximo siempre que supere 0,10**, máximo 8 vecinos. Con menos de 8 documentos con vectores no hay media fiable: se usa el coseno crudo con un umbral por modelo en el catálogo (e5 0,91 · Gemma 0,80 · bge-m3 0,68).
2. **Recalculo completo en memoria** (todos contra todos) con cada cambio y escritura de la diferencia, en lugar de «uno contra todos»: 9 ms con 1 000 documentos y no depende de que la media haya cambiado.
3. **Temas** con `networkx` (Louvain, semilla 0, grafo ordenado), resolución 1,0. Nombre por centralidad + TF-IDF.
4. **Layout** con `d3-force` en un Web Worker, con posiciones parciales cada 30 iteraciones.
5. **S4** pasa al bloque 8.
