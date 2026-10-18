# S4 · Modelos de embeddings y búsqueda híbrida

- **Fecha**: 2026-10-18 · **Equipo**: Ryzen 5 5600G (12 hilos), 16 GB, Windows 11 · **Motor**: `onnxruntime` 1.31 en CPU con 6 hilos + `tokenizers` (sin `fastembed` ni PyTorch).
- **Scripts**: `spikes/knowledge/s4_embed_eval.py`, `s4_fusion.py`, `s4_distractors.py`; corpus sintético en `spikes/knowledge/facts.py` (30 secciones de un manual ficticio en español: 15 preguntas con **otras palabras** y 15 con **términos exactos**).

## Modelos y descarga
Ninguno pide cuenta de Hugging Face (`gated=False`).

| Modelo | Repo ONNX | Fichero | Descarga | Dim. | Licencia |
|---|---|---|---|---|---|
| `multilingual-e5-small` | `Xenova/multilingual-e5-small` | `model_quantized.onnx` | 118 MB | 384 | MIT |
| **EmbeddingGemma 2** | `onnx-community/embeddinggemma-2-ONNX` | `model_q4.onnx` + `.onnx_data` | 174 MB (`model_quantized`: 314 MB) | 768 | Apache 2.0 |
| `bge-m3` | `Xenova/bge-m3` | `model_quantized.onnx` | 570 MB | 1024 | MIT |

- **EmbeddingGemma 2 existe** (la 1.ª versión, `embeddinggemma-300m`, también). Es multimodal (texto, imagen y audio); el modelo de texto pide tres entradas extra vacías (`image_features`, `video_features`, `audio_features` de forma `(0, 512)`) y devuelve `sentence_embedding` ya calculado.
- **Prefijos**: e5 → `query: ` / `passage: `; bge-m3 → ninguno (pooling CLS); EmbeddingGemma 2 → `task: search result | query: ` / `title: none | text: ` (de `config_sentence_transformers.json`).

## Velocidad y memoria
Trozos de ~350 tokens, 6 hilos.

| Modelo | 1 000 trozos | Consulta | Memoria máxima (+RSS) |
|---|---|---|---|
| e5-small | **~52 s** | 4 ms | +627 MB |
| EmbeddingGemma 2 (q4) | ~410 s | 31–40 ms | +1 540 MB |
| bge-m3 | ~390 s | 23–25 ms | +1 250 MB |

Un PDF de 200 páginas son unos 600–800 trozos: e5 ≈ 40 s; los otros dos, entre 4 y 5 minutos en segundo plano.

## Calidad (30 preguntas)
**Entre los 30 pasajes** (top-1 / top-5):

| Modelo | Vector solo | Palabras solo | Fusión ingenua (todas las palabras, RRF) |
|---|---|---|---|
| e5-small | 0,73 / 0,97 | 0,53 / 0,60 | 0,60 / 0,93 |
| EmbeddingGemma 2 | 0,90 / 1,00 | 0,53 / 0,60 | 0,57 / 1,00 |
| bge-m3 | 0,97 / 1,00 | 0,53 / 0,60 | 0,67 / 1,00 |

**Hallazgo: la fusión del plan (RRF con todas las palabras de la pregunta) empeora el top-1 en las preguntas con otras palabras** (bge-m3: de 0,93 a 0,33). Las palabras vacías («de», «que», «mi») hacen que la parte de palabras devuelva siempre *algún* ranking y la fusión se lo cree. Quitar palabras vacías y dar más peso al vector no basta.

**Solución probada: usar la parte de palabras solo con términos tipo identificador** (con dígitos, `_`, `/`, `.`, `-`, `+` o en MAYÚSCULAS: códigos, versiones, rutas, variables, nombres de comando). Si la pregunta no tiene ninguno, solo manda el vector.

**Entre 127 pasajes** (97 casi idénticos con otros códigos, rutas y variables), top-1 / top-5:

| Modelo | Vector solo | Híbrido solo-identificadores (RRF, palabras ×2) | Fusión ingenua |
|---|---|---|---|
| e5-small | 0,73 / 0,87 (exactas 0,87) | **0,80 / 0,90** (exactas **1,00**) | 0,57 / 0,80 |
| EmbeddingGemma 2 | 0,87 / 0,90 | 0,87 / 0,90 (exactas 1,00) | 0,63 / 0,80 |
| bge-m3 | 0,93 / 0,97 | 0,93 / 0,97 (exactas 1,00) | 0,70 / 0,90 |

- El híbrido de identificadores **nunca empeora al vector solo** y mejora las preguntas con términos exactos cuando el vector es el más flojo (e5: 0,87 → 1,00).
- `int8` en los vectores no cambia ningún resultado (se pueden guardar en 1 byte por dimensión).

## Conclusiones para el diseño
1. **Cambio respecto a la spec y al plan**: la búsqueda por palabras solo se activa con **términos tipo identificador**; el resto lo resuelve el vector. Con un modelo de embeddings ausente, se busca por palabras con todos los términos (sin fusión).
2. **Modelo por defecto**: `multilingual-e5-small`. Es 7–8 veces más rápido, usa la mitad de memoria y con el híbrido queda en 0,90 de top-5 (el agente recibe 8 trozos). **bge-m3** es el de mayor calidad (0,97) y **EmbeddingGemma 2 (q4)** el intermedio, ambos más lentos; los tres se ofrecen en Ajustes.
3. El trabajador debe **descargar el modelo de la memoria** tras un tiempo sin trabajo (+0,6 a +1,5 GB mientras está cargado).
4. La corpus es pequeño: el test de calidad del plan (`test_knowledge_quality.py`) debe repetirse con documentos reales en la validación.
