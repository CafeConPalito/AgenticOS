# Fase 14: Conocimiento · Validación

## Tests automáticos
```
Backend  (uv run pytest, suite completa)   100 % ejecutada; 2 pruebas fallaron una vez por un empate
                                            de reloj al ordenar por fecha de creación (test_the_three_levels
                                            y test_memory_notes::test_notes_crud, esta última anterior a la
                                            fase); repetidas 3 veces, pasan siempre.
Backend  (test_knowledge_e2e, sidecar real) 4 passed   (AGENTIC_OS_E2E_BINARY = sidecar de 152 MB)
Frontend (vitest run)                       44 files · 391 tests passed
Frontend (npm run build)                    tsc -b + vite build correctos
Lint                                        ruff check / format, eslint y prettier limpios
```
- Tests nuevos de la fase: conversión, imágenes y OCR, troceado, búsqueda y calidad, contexto, MCP, modelos locales (con instalador y descargas falsas), describir imágenes, revisión de código (`test_knowledge_review.py`), migraciones `0016` y `0017`, e2e con el sidecar y 26 de interfaz (biblioteca y ajustes).
- El sidecar con todo el motor de conocimiento pesa **152 MB** (30,5 MB antes de la fase); no engordó con los bloques 7–9.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Un agente usa un PDF del proyecto para responder | ✅ automático · ⏳ manual | `test_knowledge_e2e` (CLI falso con cliente MCP real: ve el índice, llama a `search_knowledge` y `read_knowledge`, y la ejecución registra las dos llamadas), también con el sidecar. Falta la prueba con Claude Code real |
| CA2 | Se convierten `.md`, código, PDF, `.docx`, `.xlsx`, `.pptx`, URL e imagen, con progreso y «Ver Markdown» | ✅ | `test_knowledge_convert`, `test_knowledge_pipeline`, `knowledge.test.tsx` (progreso, ficha y Markdown) |
| CA3 | Sin copias de originales; PDF, imágenes, Markdown, texto, código y CSV en el visor; Word, Excel y PowerPoint con el sistema | ✅ · ⏳ PDF en ventana real | `test_knowledge_docs`, visor en `knowledge.test.tsx`. El `<iframe>` de PDF y la CSP no se pueden comprobar sin WebView2 (plan B: pdf.js) |
| CA4 | Original borrado o movido: aviso, reubicar o quitar; mismo contenido conserva el índice; cambiado se marca | ✅ | `test_knowledge_docs`, `knowledge.test.tsx` (reubicar con confirmación) |
| CA5 | Una ejecución ve general + su proyecto + su agente, nada más | ✅ | `test_knowledge_context`, `test_knowledge_search::test_it_sees_only_what_the_agent_may_see` |
| CA6 | Documentos pequeños y «siempre» entran enteros hasta el presupuesto; el resto, en el índice | ✅ | `test_knowledge_context` |
| CA7 | La búsqueda híbrida acierta con otras palabras y con identificadores | ✅ | `test_knowledge_quality` con el modelo real (acierto 0,93 en los 5 primeros) y `test_knowledge_search` |
| CA8 | Sin modelo de embeddings funciona por palabras y se reindexa al llegar | ✅ | `test_knowledge_search` (reindexado al llegar el modelo y al cambiarlo) |
| CA9 | Fallo con motivo claro, no lo usan los agentes, «Reprocesar» lo recupera | ✅ | `test_knowledge_pipeline`, `test_knowledge_docs`, `knowledge.test.tsx` |
| CA10 | El instalador incluye conversión y OCR con sus modelos, no `llama.cpp` ni los demás | ✅ sidecar · ⏳ instalador | `test_local_models_bundled`, e2e con el sidecar real (OCR sin descargas). Falta instalar en una máquina limpia |
| CA11 | PDF escaneado y capturas se encuentran por OCR; imágenes de `.docx` extraídas y el agente las abre | ✅ automático · ⏳ manual | `test_knowledge_images`, `test_knowledge_ocr`, e2e empaquetado. Falta la prueba con Claude Code real |
| CA12 | Describir imágenes con IA: CLI headless (con aviso y consumo) o `llama.cpp` descargado por la app | ✅ automático · ⏳ manual | `test_knowledge_describe` (28: parseo, `Run` contada, `llama-server` falso, bloqueo, reprocesado). Falta probar con `claude`/`agy` y `llama-server` reales |
| CA13 | Una sola pipeline, sin conversión por tipo fuera de sus conversores | ✅ | Revisión de código + `test_knowledge_convert` |
| CA14 | CPU, GPU (o «No disponible») y memoria en vivo; pausar y reanudar | ✅ | `test_system_stats`, `knowledge.test.tsx` (monitor, medidor y pausa) |
| CA15 | Descargar y elegir los modelos; cambiar el de embeddings reindexa | ✅ automático · ⏳ descargas reales | `test_local_models`, `knowledge-settings.test.tsx`. Las descargas reales de Hugging Face se probaron en los spikes (`m3-descargas-reales`) |
| CA16 | Lint, tests de backend y frontend en verde; ADR; `/code-review` resuelto | ✅ | Ver arriba, [ADR 0021](../../adr/0021-knowledge.md) y la tabla siguiente |

## Code review
`/code-review high` sobre la rama frente a `main`: 10 hallazgos.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Cerrar la app esperaba a la conversión (o a `llama-server`) en curso | Alta | Corregido: se detiene el proceso antes de tomar el candado. Test |
| Un 401/403 en una descarga acababa en «network» o «checksum», sin pedir el token | Alta | Corregido. Test |
| La caché de vectores se invalidaba antes del commit y una búsqueda podía cachear filas viejas | Alta | Corregido: se invalida tras el commit. Test |
| Borrar un proyecto o un agente dejaba palabras en el índice e imágenes en disco | Media | Corregido (`remove_owned`). Tests |
| La búsqueda por palabras limitaba a 200 filas antes de filtrar por visibilidad | Media | Corregido: el filtro va dentro de la consulta. Test |
| Reubicar un documento en proceso lanzaba dos pipelines | Media | Corregido: 409 `processing`. Test |
| `threads = 0` en los embeddings usaba todos los núcleos | Media | Corregido (mitad de los núcleos, como el OCR) |
| Listados y búsquedas cargaban el Markdown completo de cada documento | Baja | Corregido (columna diferida; `has_markdown` por `md_tokens`) |
| Cada evento de progreso refrescaba listas de otros niveles | Baja | Corregido: solo las del nivel del documento |
| `DELETE FROM knowledge_fts WHERE doc_id` recorre toda la tabla | Baja | Justificado: sin un identificador entero estable no se puede borrar por `rowid`; con miles de trozos cuesta milisegundos |

## Retro
- **Cambios respecto a la spec**:
  - Los modelos de OCR (~18 MB) **van en el instalador**, porque solo se publican en `modelscope.cn` (decidido el 2026-10-19).
  - La parte de palabras de la búsqueda **solo usa identificadores**: usar todas las palabras empeoraba el primer resultado en las medidas del spike.
  - El modelo de embeddings por defecto es `multilingual-e5-small` (8× más rápido), con EmbeddingGemma 2 y `bge-m3` como opciones.
  - El visor de código es texto monoespaciado, sin resaltado de sintaxis, para no añadir una librería por esto.
- **Impacto en fases futuras**:
  - La fase 15 (ampliación del conocimiento) reutiliza trozos, vectores, ficha y MCP.
  - La fase 16 (dictado por voz) añade modelos Whisper al catálogo de modelos locales sin cambios de estructura.
  - La fase 23 (instaladores firmados) puede reabrir el tamaño del sidecar (152 MB).
- **Deuda anotada**:
  - La ordenación por `created_at` sin desempate hace flaky algún test en Windows (también en las notas de memoria); conviene añadir un desempate cuando se pase a Postgres (fase 24).
  - GPU para ONNX y `llama.cpp`, `llama.cpp` para macOS y Linux, y reranking local quedan fuera.

## Pendiente de comprobación manual (aceptado por el usuario al cerrar)
- Instalador en una máquina limpia, con OCR sin internet (CA10).
- Claude Code real con un PDF real y con imágenes de un `.docx` (CA1, CA11).
- Descripción de imágenes con `claude`/`agy` y con `llama-server` real (CA12).
- Visor de PDF en la ventana de Tauri y la CSP (S9; plan B: pdf.js).
- Descargas reales desde Ajustes › Modelos locales con el instalador.

## Cierre
- [x] OK del usuario («Ok pasamos a la siguiente fase», 2026-10-20, sabiendo que las comprobaciones manuales quedaban pendientes)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v1.6`
- [x] `docs/roadmap.md` actualizado
