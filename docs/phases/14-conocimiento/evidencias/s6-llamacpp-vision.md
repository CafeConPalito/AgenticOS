# S6 · `llama.cpp` y modelos de visión locales

- **Fecha**: 2026-10-18 · Ryzen 5 5600G (12 hilos), 16 GB, Windows 11, **solo CPU** (`-ngl 0`, 6 hilos, contexto 4 096).
- **Scripts**: `spikes/knowledge/s6_download.py`, `make_images.py`, `s6_vision.py`. Cinco imágenes de prueba (gráfico de barras, diagrama de flujo, tabla, organigrama y captura de error) con las palabras clave que debe mencionar una buena descripción.

## `llama.cpp`
- **Release `b11720`** (2026-10-18): `llama-b11720-bin-win-cpu-x64.zip`, **20 MB** (sin CUDA ni Vulkan; hay `win-vulkan-x64` de 32 MB para el futuro).
- GitHub publica el **`sha256`** de cada fichero en la API de releases (`assets[].digest`); el descargado coincide con él (`d59fd840…728de`). La app puede verificarlo, y además lo fija en su catálogo.
- El zip incluye `llama-server.exe` (+ `llama-server-impl.dll`, `mtmd.dll`, varias `ggml-cpu-*.dll` para elegir según la CPU) y se extrae sin instalador. **Windows no avisó** al descargar ni al arrancar `llama-server` (ni Defender ni SmartScreen).
- Se arranca con `llama-server -m <modelo> --mmproj <proyector> -c 4096 -t 6 --host 127.0.0.1 --port N --no-webui -ngl 0 --jinja`; está listo en 3–30 s (según el tamaño del modelo) y su API `POST /v1/chat/completions` acepta la imagen como `data:image/png;base64,…` (formato OpenAI). Con `chat_template_kwargs: {"enable_thinking": false}` no pierde tiempo razonando.

## Modelos (sin cuenta de Hugging Face, Apache 2.0)

| Modelo (GGUF Q4_K_M + `mmproj` F16) | Descarga | Tiempo por imagen | Memoria del servidor | Palabras clave |
|---|---|---|---|---|
| **Qwen3.5-2B** (`unsloth/Qwen3.5-2B-GGUF`) | 1,28 + 0,67 = **1,95 GB** | 9,2 s | 3,1 GB | 20/21 |
| **Gemma 4 E2B** (`unsloth/gemma-4-E2B-it-GGUF`) | 3,11 + 0,99 = **4,1 GB** | **7,0 s** | 4,0 GB | 20/21 (*) |
| Qwen3.5-4B (`unsloth/Qwen3.5-4B-GGUF`) | 2,74 + 0,67 = 3,4 GB | 18,8 s | 6,0 GB | 21/21 |

(*) El «fallo» de Gemma es de mi comprobador: escribió `ERR\_4012` (con la barra de escape de Markdown), así que en realidad acierta todo.

- **Qwen3.5-2B** leyó `ERR_4022` en vez de `ERR_4012` en la captura. Es el caso para el que está el **OCR**: los códigos y números exactos los da el OCR; el modelo de visión aporta el sentido (qué es un gráfico, un diagrama, una tabla).
- Las descripciones salen en buen español y mencionan títulos, valores y estructura; son más largas de lo necesario con Qwen (3–4 frases), por lo que el prompt pide «máximo 4 frases».
- **EmbeddingGemma 2 y Gemma 4**: existen versiones oficiales de Google en GGUF y ONNX sin cuenta (`google/gemma-4-E4B-it-qat-q4_0-gguf`, 5,2 GB).

## Conclusiones para el diseño
1. **Catálogo de visión**: Gemma 4 E2B (equilibrado, el más rápido) y Qwen3.5-2B (el más ligero de descargar y de memoria) y, opcional, Qwen3.5-4B (más preciso, 2,5× más lento). Por defecto, **Gemma 4 E2B**.
2. 7–19 s por imagen implica que un documento con 30 imágenes tarda 4–10 minutos: la UI lo muestra («describiendo imágenes n de m») y se puede pausar. Es lo que avisa la spec.
3. Se necesitan 3–6 GB libres de memoria mientras el servidor está activo: se comprueba la memoria disponible antes de arrancarlo y se avisa si no hay.
4. `llama-server` se arranca bajo demanda y se para tras 60 s sin trabajo (diseño del plan).
