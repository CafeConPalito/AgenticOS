# Fase 15: Ampliación del conocimiento · Validación

## Tests automáticos
```
Backend  (uv run pytest, suite completa)    100 % ejecutada; 5 pruebas fallaron una vez por intermitencia,
                                            ninguna de esta fase: 4 por empates de reloj al ordenar por fecha
                                            (test_the_three_levels, test_notes_crud, el índice del contexto
                                            y «más antiguo primero» del pipeline) y test_switching por
                                            temporización de la cuota. Repetidas, pasan (test_notes_crud
                                            falla a veces aun solo; ya constaba en la fase 14).
Backend  (test_knowledge_e2e, sidecar real) 5 passed   (AGENTIC_OS_E2E_BINARY = sidecar de 162,6 MB)
Frontend (vitest run)                       48 files · 444 tests passed
Frontend (npm run build)                    correcto
Lint                                        ruff check / format, eslint y prettier limpios
```
- Tests nuevos: `test_migration_0018`, `test_knowledge_graph_data`, `test_knowledge_proposals` (24), `test_knowledge_topics`, `test_knowledge_graph` (relaciones y grafo), `test_knowledge_graph_tools` (herramientas del grafo y probador), `test_knowledge_graph_quality` (modelo e5 real), `test_knowledge_graph_e2e` (cliente MCP real), `test_knowledge_graph_perf`, el e2e de ejecuciones del CLI falso (también empaquetado) y, en el frontend, `proposals`, `graph-model`, `knowledge-graph` y `search-tester`.
- El sidecar pesa **162,6 MB** (152 MB antes de la fase): +10,6 MB por `networkx`, dentro de lo medido en el spike.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Un agente llama a `propose_knowledge` basándose en un PDF: «Propuesto» vinculado al PDF, en la Inbox y en el filtro «Propuestos» | ✅ automático · ✅ `claude` · ⏳ `agy` | `test_knowledge_graph_e2e` (cliente MCP real) y `test_knowledge_e2e` (CLI falso en una ejecución, también empaquetado). **`claude` real** (haiku, ~0,01 USD): buscó en el manual, propuso con `based_on = manual.pdf` y quedó «Propuesto» (spike S4, 2026-10-21). Falta `agy` real |
| CA2 | Un propuesto no aparece en contexto, `search_knowledge`, `read_knowledge` ni herramientas del grafo hasta aceptarlo | ✅ | `test_knowledge_proposals`, `test_knowledge_graph_tools::test_nothing_hidden_ever_shows_up` |
| CA3 | Aceptar (editando título, texto y nivel) lo procesa sin conversión y lo hace buscable; rechazar lo descarta y queda registrado | ✅ | `test_knowledge_proposals`, `proposals.test.tsx` (revisión, nivel, rechazo con motivo, Inbox) |
| CA4 | El PDF y su Markdown no cambian al proponer, aceptar o rechazar | ✅ | `test_the_original_never_changes`, `test_knowledge_graph_e2e` |
| CA5 | Máximo por ejecución, tamaño, duplicados y ajuste que desactiva, con el motivo en palabras | ✅ | `test_knowledge_proposals` (también el tope tras rechazar y los duplicados por significado con un modelo falso) |
| CA6 | «Generado por agente», procedencia en la ficha, marca en el índice y en los resultados | ✅ | `test_an_accepted_document_says_it_was_generated_by_an_agent`, `proposals.test.tsx` |
| CA7 | El grafo distingue fichero / web / imagen / aceptado / pendiente, con aristas, filtros, búsqueda y clic | ✅ | `knowledge-graph.test.tsx` (11), `graph-model.test.ts` |
| CA8 | Relaciones en local, con umbral y tope, recalculadas al indexar, quitar o cambiar de modelo | ✅ | `test_knowledge_graph` (centroides, umbral, tope, vecino más próximo, recálculo, sin modelo) |
| CA9 | El grafo mejora el acierto sin empeorar los resultados directos | ✅ | `test_knowledge_graph_quality` con e5 real: al encontrar un PDF, recall de «su familia» **0,44 → 1,00**; los resultados directos no cambian |
| CA10 | Fluido con 300 documentos y 1 000 aristas | ✅ | *Layout* en 327 ms (`graph-model.test`, 3 s de margen) y medido en **Chrome real** con 300 nodos y 971 vínculos: 130 pasos de zoom y arrastre ≈ 1 fotograma cada uno (p95 18 ms; 3 tareas largas, antes 25) en el servidor de desarrollo |
| CA11 | Borrar el origen no borra el derivado: «origen eliminado» | ✅ | `test_migration_0018`, `test_knowledge_graph_data`, `test_a_deleted_source_leaves_a_ghost…`, `proposals.test.tsx` |
| CA12 | Con el binario empaquetado, el flujo completo funciona | ✅ | `test_knowledge_e2e::test_an_agent_proposes_knowledge_and_walks_the_graph` con el sidecar real (proponer → aceptar → buscar → mapa → explorar), 5/5 |
| CA13 | `knowledge_map` agrupa en temas coherentes y estables | ✅ | `test_knowledge_topics`, `test_knowledge_graph_quality` (8 temas del corpus de 25 documentos; mismo resultado al recalcular) |
| CA14 | `explore_knowledge` y `knowledge_path` respetan saltos, filtros, topes y visibilidad | ✅ | `test_knowledge_graph_tools` (23) |
| CA15 | Lo que está a dos saltos del mejor resultado se alcanza explorando y no con la búsqueda sola | ✅ | `test_what_lies_two_hops_from_the_best_result_is_reached_by_exploring` (e5 real) |
| CA16 | Un agente usa mapa → explorar → leer; queda en el registro; el contexto incluye los temas | ✅ | `test_knowledge_graph_e2e`, `test_knowledge_e2e` (empaquetado) y `claude` real: mapa → explorar → leer, los cinco eventos en el registro |

## Code review
`/code-review high` sobre la rama frente a `main`: 10 hallazgos, resueltos en `2619ac8`.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| La migración no rellenaba el centroide de los documentos ya indexados: sin vínculos ni temas en una biblioteca existente | Alta | Corregido: la migración lo calcula con los vectores de los trozos. Test |
| El tope de propuestas por ejecución se «devolvía» al rechazar (se borraba la procedencia) | Alta | Corregido: se cuenta en la Inbox. Test |
| Dos recálculos del grafo a la vez podían chocar (clave primaria) | Media | Corregido: candado. Test |
| Cada recálculo emitía evento aunque no cambiara nada | Media | Corregido: solo si cambió un vínculo o se pidió anunciar. Test |
| El control de duplicados cargaba y hasheaba el Markdown de toda la biblioteca | Media | Corregido: solo los documentos del mismo tamaño |
| Una búsqueda leía tres veces los documentos y dos los vínculos; los temas se recalculaban en cada ejecución | Media | Corregido: una lectura y caché de la línea de temas por versión del grafo |
| `limit` se superaba con los vecinos del grafo | Media | Justificado y documentado en la herramienta: `limit` cuenta resultados directos y el grafo añade hasta 3 más (CA9 lo mide así) |
| El filtro «Propuestos» dejaba la lista vacía al decidir la última propuesta | Baja | Corregido. Test |
| La búsqueda del grafo en «Toda la biblioteca» preguntaba con el ámbito del nivel | Baja | Corregido. Test |
| Tres copias del estimador de tokens | Baja | Corregido: un módulo (`tokens.py`) |

Hallazgos propios de los e2e (antes de la revisión): terminar una tarea descartaba **todas** sus peticiones de la Inbox, también las propuestas; ahora las propuestas sobreviven a la tarea y a la ejecución (test).

## Retro
- **Cambios respecto a la spec**:
  - La relación «relacionado» usa el **coseno de centroides centrado en la media de la biblioteca** (umbral 0,20, con el vecino más próximo siempre ≥ 0,10), no un umbral por modelo: da una escala común a los tres modelos (spikes S1–S2).
  - Los vínculos solo existen con un modelo de significado; sin él, solo hay vínculos «derivado de».
  - La Inbox cuenta propuestas por ejecución (no por documento) y las propuestas sobreviven al cierre de la tarea.
  - Los nodos del grafo no se arrastran (solo zoom y desplazamiento) y el doble clic centra el vecindario, por eso no hace zoom.
  - S4 (agentes reales) se movió al final: con `claude` hecho y `agy` pendiente.
  - Se añadió `POST /api/knowledge/explore` para el modo «Explorar» del probador.
- **Impacto en fases futuras**:
  - La fase 16 (dictado) reutiliza el catálogo de modelos (`kind = speech`) sin cambios.
  - Las propuestas aceptadas automáticamente quedan preparadas (`review`, `provenance`) pero fuera de alcance: exigen decidir una política de confianza.
  - Pendiente manual aceptado al cerrar: `agy` real y el instalador en una máquina limpia.
  - Deuda: cuatro pruebas intermitentes por empates de reloj al ordenar por fecha de creación (conviene desempatar siempre por `id` en esas consultas).

## Cierre
- [x] OK del usuario (2026-10-22)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v1.7`
- [x] `docs/roadmap.md` actualizado
