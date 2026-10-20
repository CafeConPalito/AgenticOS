# ADR 0021: Biblioteca de conocimiento

- **Estado**: aceptado
- **Fecha**: 2026-10-20
- **Contexto de decisión**: fase 14 ([`spec.md`](../phases/14-conocimiento/spec.md), [`plan.md`](../phases/14-conocimiento/plan.md))

## Contexto
Los agentes solo conocían el código del proyecto y la memoria (notas cortas). La fase pide que el usuario aporte documentos de cualquier tipo en tres niveles (general, proyecto, agente), que se conviertan a Markdown, que los agentes los usen **sin que la app guarde copias de los originales** y que lo hagan con búsqueda por significado, sin servicios externos. Es además el primer modelo local de la app: hay que poder descargar, elegir y borrar modelos, y no inflar el instalador.

## Decisión

### Documentos por referencia (`services/knowledge/docs.py`)
- Un documento guarda la **ruta** (o la URL), el `sha256`, el tamaño y la fecha del original, y su **Markdown**. **No se copia el fichero.** `presence` (`ok`, `missing`, `changed`) se comprueba al listar y al abrir; «Reubicar» conserva el índice si el contenido es el mismo y pide confirmar si es otro.
- Solo se conserva lo imprescindible para la IA: el Markdown, los trozos con sus vectores y las **imágenes extraídas** de los documentos (los agentes no pueden sacarlas del original). Las imágenes sueltas se leen del original, por su ruta.
- Niveles `general`, `project` y `agent`; modos `auto`, `context`, `search` y `off`. Un subagente ve además lo de su agente padre.

### Una sola pipeline, en un proceso aparte (`pipeline.py`, `worker.py`)
- Estados `queued → converting → images → describing → indexing → ready | failed`. La cola vive en la base de datos (reclamo con compare-and-set), se recupera al arrancar y se puede pausar.
- El trabajo pesado va en un **subproceso** (`--knowledge-worker`, JSON por líneas en UTF-8, prioridad `BELOW_NORMAL`, descarga el modelo tras 60 s sin trabajo) para no bloquear la API ni compartir memoria con ella.
- **MarkItDown** con los conversores propios registrados a prioridad −1 y los incorporados desactivados (una sola adivinanza de formato): PDF con `pypdfium2`, Excel con `openpyxl` (sin `pandas`), URLs con `trafilatura`, imágenes y páginas escaneadas con **RapidOCR** (ONNX, rutas de modelo explícitas, sin descargas). No hay código de conversión por tipo fuera de estos conversores.
- Un fallo deja el documento en `failed` con un **código** (la interfaz traduce) y el detalle técnico aparte; avisos que no impiden usarlo van en `notice` (`ocr_missing`, `ocr_failed`, `embed_failed`, `describe_*`).

### Imágenes
- Las marcas `![…](kimg:N)` del Markdown se resuelven al servir (visor) y al construir el contexto (ruta del fichero). Las repetidas se guardan una sola vez (por `sha256`); se descartan las de menos de 64 px de lado. El texto del OCR va debajo de la imagen; en las páginas escaneadas sustituye a la imagen.
- **Describir con IA es opcional y está apagado por defecto** (ajuste global y por documento): con un **CLI en modo headless** (`claude -p` con solo `Read`, o `agy -p`, en una carpeta temporal con la imagen; registra un `Run` `kind=describe` que cuenta en el consumo y respeta el límite diario) o con un **modelo de visión local** servido por `llama-server`.

### Búsqueda híbrida (`chunking.py`, `index.py`, `search.py`)
- Trozos de ~400 tokens con solapamiento de ~50, respetando títulos y párrafos, con ubicación (página, diapositiva, hoja, apartado). Vectores en SQLite como `float32` y similitud del coseno con NumPy; las palabras, en una tabla FTS5.
- **Fusión RRF**: el vector pesa 1 y las palabras 2, y las palabras **solo con términos tipo identificador** (el spike mostró que usar todas las palabras empeoraba el primer resultado). Los documentos sin vectores del modelo elegido caen a búsqueda por palabras completa.
- Cada vector recuerda su modelo; al **cambiar de modelo** (o al terminar su descarga) se reindexa en segundo plano y entretanto se busca por palabras. La consulta se codifica en un trabajador aparte para no esperar a la cola.

### Modelos y motores locales (`services/localmodels/`)
- **Catálogo fijado** en código (revisión, tamaño y `sha256` de cada fichero, generado por un script a partir de los spikes): `multilingual-e5-small` (por defecto), EmbeddingGemma 2, `bge-m3`, OCR latino, Gemma 4 E2B (por defecto), Qwen3.5-2B y 4B, y `llama.cpp` b11720 (CPU).
- Descargas **reanudables** (`.part` + `Range`), verificadas con `sha256`, con manifiesto y progreso por WebSocket; el token de Hugging Face se guarda en el gestor de credenciales de git, nunca en la base de datos y solo se envía a `huggingface.co`.
- **En el instalador** van las librerías de conversión, OCR y ONNX y los **modelos de OCR (~18 MB)** (solo se publican en `modelscope.cn`; se empaquetan con `stage.py`). **No** van `llama.cpp` ni el resto de modelos: se descargan desde Ajustes. El *sidecar* pasa de 30,5 MB a unos 150 MB.
- `LlamaServer` escucha solo en `127.0.0.1`, comprueba la memoria libre antes de arrancar, se reutiliza entre documentos y se para tras 60 s sin trabajo y al cerrar la app.

### Contexto y MCP (`context.py`, `agent_tools.py`)
- Sección «Conocimiento» en el contexto de cada ejecución: **índice** de los documentos visibles y texto entero de los de modo `context` y de los `auto` pequeños, dentro de un **presupuesto** de tokens (8 000 por defecto; los que no caben pasan a «solo búsqueda»).
- Herramientas MCP **`search_knowledge`** y **`read_knowledge`** (por título o identificador, y por página, diapositiva, hoja o apartado; los documentos largos por partes). Los errores se contestan con palabras para que el agente se corrija. Cada llamada deja un evento `mcp` con la consulta y los documentos devueltos.
- Las carpetas de imágenes se pasan al CLI con `--add-dir`; las copias de imágenes del usuario viven solo durante la ejecución.

### Recursos, API e interfaz
- `system_stats` mide CPU, memoria y GPU (contadores PDH por `ctypes`, de cualquier fabricante; `null` si no se pueden leer) y los publica como eventos mientras haya trabajo.
- API REST de documentos, búsqueda de prueba, cola, modelos locales y ajustes; un WebSocket `/api/knowledge/events` (documentos, cola, sistema, descargas).
- Frontend: página `/conocimiento` y pestañas de proyecto y agente con la misma biblioteca, ficha con visor, monitor de recursos y Ajustes › Conocimiento y › Modelos locales.

## Consecuencias
- **Instalador más grande** (~120 MB más) a cambio de que convertir y hacer OCR funcione sin conexión y sin configurar nada. La alternativa (un motor de conocimiento descargable) exige alojar y firmar ese artefacto; se revisará en la fase 21 (instaladores firmados) si el tamaño molesta.
- **Los originales no se copian**: si el usuario los mueve o los edita, la biblioteca lo detecta pero no puede recuperarlos; el Markdown ya procesado sigue siendo utilizable.
- **CPU primero**: ONNX y `llama.cpp` van en CPU. La GPU para ambos, `llama.cpp` para macOS y Linux y el *reranking* local quedan fuera de esta fase.
- La gestión de modelos admite nuevos tipos sin cambios de estructura (la fase 16 añadirá los de Whisper).
- La fase 15 amplía la biblioteca con propuestas de los agentes y un grafo; reutiliza los trozos, los vectores y la ficha de esta fase.

## Alternativas descartadas
- **Copiar los ficheros a la carpeta de datos**: duplica disco y se desincroniza; el usuario pidió explícitamente referencias.
- **Base de datos vectorial aparte** (Chroma, LanceDB…): para miles de trozos NumPy sobre SQLite tarda milisegundos y evita otra dependencia en el *sidecar*.
- **PyTorch / `sentence-transformers`** para los vectores: cientos de MB más; ONNX Runtime ya hace falta para el OCR.
- **Todas las palabras de la consulta en la parte léxica**: empeoraba el primer resultado en las medidas del spike.
- **`llama.cpp` en el instalador**: pesa y solo lo usa quien activa la descripción local.
- **Describir las imágenes siempre con IA**: gasta cuota, saca imágenes de la máquina y es lento; queda como opción.
