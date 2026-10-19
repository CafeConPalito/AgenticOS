# Fase 14: Conocimiento · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-18) · en desarrollo (bloques 0 a 6 hechos; sigue el 7)

## Lo que ya se sabe (revisado al escribir el plan)
- **Contexto** (`services/context.py`): `build_instructions` monta las instrucciones por secciones (rol, proyecto, repos, git, memoria, tarea, subagente, reglas). El conocimiento es una sección más, después de la memoria. `get_context` devuelve lo mismo.
- **MCP** (`services/mcp_server.py`): las herramientas llaman a un `AgentBackend` (protocolo) con el `run_id` del token. Añadir `search_knowledge` y `read_knowledge` es añadir dos métodos al protocolo y su implementación en el `RunManager`. `RunManager.add_event(run_id, EventKind.MCP, …)` deja la traza en la ejecución.
- **Acceso a ficheros fuera del workspace**: los dos adaptadores ya pasan `ctx.extra_dirs` como `--add-dir` (Claude Code y agy), y `runrepos.extra_dirs` los rellena con los repos vinculados. Las carpetas de imágenes del conocimiento se añaden igual.
- **Llamada *headless*** (`services/decider.py`, fase 13): `call()` lanza el CLI sin PTY, con el entorno de la cuenta (`accounts.env_for`), un tiempo máximo y el consumo leído de la salida. `record_run` deja una `Run` con `kind` distinto de `agent`, que cuenta en el consumo y el límite diario. Las listas, los diffs y el `RunManager` ya filtran `kind == agent`. El describidor por CLI reutiliza todo esto con un `kind` nuevo.
- **Eventos en vivo**: `/git/events` (`services/gitx/events.py`, `GitEvents`) es un *hub* de colas por suscriptor sobre WebSocket. El de conocimiento sigue el mismo patrón.
- **Ajustes**: los valores sueltos se guardan en `AppState` (clave y valor), con endpoints `/settings/...` por sección (`inbox.py`, `usage.py`, `maintenance.py`).
- **Secretos**: el ADR 0018 dice que **la app no guarda secretos propios**: el token de GitHub y GitLab sale de `git credential fill`. El *token* de Hugging Face, si hace falta, sigue la misma regla.
- **Carpeta de datos** (`services/datadir.py`): `disk_usage` reparte el tamaño entre base de datos, sesiones, logs y otros. Se añaden «conocimiento» y «modelos».
- **Empaquetado** (`scripts/build-backend.ps1`): PyInstaller `--onefile`. Cada dependencia nueva alarga la descompresión al arrancar; hay que medirlo (spike S1) y vigilar el tiempo de `smoke-installed.ps1`.
- **Tauri**: ya están `plugin-dialog` (con `dialog:allow-open`) y `plugin-shell`. El arrastrar y soltar de la ventana de Tauri da rutas reales (`onDragDropEvent`). La CSP no permite marcos ni imágenes del backend: hay que ampliarla para el visor.
- **Frontend**: `react-markdown` con `remark-gfm` ya renderiza Markdown. No hay resaltado de código; las pestañas «Conocimiento» del proyecto y del agente existen como `ComingSoonTab`.

## Bloque 0 · Spikes (antes de programar)
Scripts en `spikes/knowledge/` con un corpus de ejemplo en `spikes/knowledge/corpus/`: PDF con texto y tablas, PDF escaneado, `.docx` con imágenes, `.xlsx` con dos hojas, `.pptx` con imágenes, capturas con texto y una URL. Evidencias en `evidencias/`.

| # | Pregunta | Si falla |
|---|---|---|
| S1 | **MarkItDown**: ¿qué calidad da con el corpus (títulos, tablas, hojas)? ¿Con `keep_data_uris` deja las imágenes de `.docx` y `.pptx` en su sitio como *data URI*? ¿Cuánto crece el ejecutable de PyInstaller con los extras `pdf`, `docx`, `xlsx` y `pptx`, y cuánto tarda más en arrancar? | Plugins propios para los formatos flojos; si el tamaño es excesivo, quitar `pandas` con un plugin de Excel sobre `openpyxl` |
| S2 | **PDF con `pypdfium2`** (Apache 2.0) como plugin de MarkItDown: texto por página con marca de página, detección de páginas escaneadas (sin texto), renderizado de página a imagen para el OCR y extracción de las imágenes incrustadas | `pdfminer` (el de MarkItDown) para el texto y `pypdfium2` solo para renderizar |
| S3 | **OCR**: RapidOCR sobre ONNX Runtime con capturas y escaneos en español: calidad, tiempo por imagen con 4 hilos, tamaño de los modelos y si empaqueta bien | Otro OCR en ONNX; como último recurso, OCR solo en inglés y español con modelos más grandes |
| S4 | ***Embeddings***: `multilingual-e5-small`, **EmbeddingGemma** (la versión más reciente, la 2 si está publicada en ONNX) y `bge-m3`, con `onnxruntime` + `tokenizers`, sin `fastembed`. Con 30 preguntas sobre el corpus (la mitad con otras palabras, la mitad con términos exactos): acierto en el top 5 por separado y en híbrido (RRF), tiempo por 1 000 trozos, memoria, y `int8` frente a `float32`. ¿Se descargan sin cuenta de Hugging Face? | `fastembed`, si simplifica sin pesar mucho más; si un modelo pide cuenta, se ofrece con el *token* (§6) |
| S5 | **SQLite FTS5** en el Python empaquetado: disponible, tokenizador `unicode61 remove_diacritics 2` con búsquedas en español (acentos, plurales simples) | Prefijos (`palabra*`) o un *stemmer* sencillo propio |
| S6 | **`llama.cpp`**: descargar la versión para CPU de Windows desde las *releases* oficiales, comprobar su suma, arrancar `llama-server` con **Qwen 3.5** y **Gemma 4** pequeños con visión (GGUF + `mmproj`), describir 10 imágenes por su API compatible con OpenAI: tiempo por imagen, memoria, calidad en español. ¿Hay GGUF sin cuenta? ¿Avisa el antivirus? | Ofrecer solo el modelo que funcione; si ninguno funciona en CPU en tiempos razonables, la opción local queda marcada como experimental |
| S7 | **Describir con el CLI**: `claude -p` con la herramienta `Read` limitada a la carpeta de la imagen (o la imagen en el prompt) y salida JSON: calidad, tiempo y coste con `haiku`; y lo mismo con `agy -p` | Solo Claude Code; el ajuste no ofrece agy y lo explica |
| S8 | **Recursos y proceso de trabajo**: CPU y memoria con `psutil`; GPU de cualquier fabricante con los contadores PDH `\GPU Engine(*)\Utilization Percentage` por `ctypes`; lanzar el mismo ejecutable de PyInstaller como proceso de trabajo (`--knowledge-worker`) con prioridad `BELOW_NORMAL` y comunicarse por stdin/stdout | GPU «No disponible»; si el subproceso empaquetado da problemas, hilos con prioridad baja dentro del backend |
| S9 | **Tauri**: rutas reales al soltar ficheros (`onDragDropEvent`) y con el selector; PDF del backend en un `iframe` con el visor de WebView2; imágenes del backend; qué cambios de CSP hacen falta | `pdf.js` como visor; imágenes como `blob:` |

## Resultados de los spikes (bloque 0, 2026-10-18)
Scripts en `spikes/knowledge/` y `spikes/scenarios/knowledge_describe.py`; evidencias completas en `evidencias/`.

- **S1 · MarkItDown 0.1.8** ([evidencia](evidencias/s1-markitdown.md)): bien con `.docx`, `.pptx` (imágenes en su sitio como *data URI*), `.xlsx`, texto, código y HTML. **Flojo con PDF** (sin títulos ni páginas y con la tabla desordenada) y **0 caracteres** con imágenes y PDF escaneados. El HTML conserva el menú: para URLs, `trafilatura` 2.3.1 (Apache 2.0) extrae solo el contenido principal (en una página real, 114 000 → 72 000 caracteres). **Peso**: el trabajador completo pesa 160 MB y, **sin `pandas`, sin `pdfminer` y sin los modelos de OCR, 109 MB** (el *sidecar* actual: 30,5 MB). Todo funciona congelado.
- **S2 · PDF** ([evidencia](evidencias/s2-s3-s5-pdf-ocr-fts.md)): `pypdfium2` da el texto por página en orden de lectura (la tabla sale como filas legibles) en 0,04 s, detecta las páginas escaneadas, las renderiza y extrae las imágenes incrustadas.
- **S3 · OCR**: RapidOCR 3.10 con el reconocedor **latino** de PP-OCRv5 lee bien el español (tildes, `ñ`, códigos) a ~1 s por página. Modelos: ~18 MB (detector 9,9 + clasificador 0,6 + reconocedor 7,9). Lo pesado es OpenCV (113 MB sin comprimir).
- **S4 · Embeddings** ([evidencia](evidencias/s4-embeddings.md)): sin cuenta de Hugging Face. `multilingual-e5-small` (118 MB): 1 000 trozos en **52 s**, +0,6 GB de memoria. **EmbeddingGemma 2 (q4)** (174 MB, Apache 2.0) y **bge-m3** (570 MB): unos 400 s, +1,3–1,5 GB. Calidad entre 127 pasajes: bge-m3 0,93 de acierto en el primero y 0,97 en los cinco primeros; Gemma 2 0,87/0,90; e5 0,73/0,87, que con el híbrido sube a 0,80/0,90. **La fusión del plan empeoraba el resultado** (ver abajo).
- **S5 · FTS5**: disponible (SQLite 3.53.1), ignora tildes y encuentra identificadores; sin *stemming*.
- **S6 · `llama.cpp`** ([evidencia](evidencias/s6-llamacpp-vision.md)): release `b11720`, `win-cpu-x64` de **20 MB**, con `sha256` publicado por GitHub; arranca sin avisos de Windows. Por imagen en CPU: **Gemma 4 E2B 7,0 s** (4,1 GB de descarga, 4 GB de memoria), **Qwen3.5-2B 9,2 s** (2,0 GB, 3,1 GB; leyó mal un código), Qwen3.5-4B 18,8 s (3,4 GB, 6 GB). Ninguno pide cuenta.
- **S7 · CLI** ([evidencia](evidencias/s7-cli-describe.md)): `claude -p` (`haiku`, `--tools Read --allowedTools Read`) describe una imagen en **6,5 s por ~0,0009 USD**; `agy -p` en **9,7 s** (~24 800 tokens por llamada). 21/21 palabras clave en los dos y configuración global sin cambios.
- **S8 · Recursos y trabajador** ([evidencia](evidencias/s8-recursos-trabajador.md)): CPU y memoria con `psutil`; **GPU de cualquier fabricante con los contadores PDH** (`GPU Engine`) por `ctypes`, sin permisos especiales; el trabajador arranca con prioridad `BELOW_NORMAL` y queda listo en 0,2 s. Las tuberías hay que forzarlas a UTF-8.
- **S9 · Tauri** ([evidencia](evidencias/s9-tauri.md)): el evento `drop` trae las rutas reales y `dragDropEnabled` es `true` por defecto. El visor de PDF en un `iframe` y la CSP no se pueden comprobar sin una ventana real: quedan para la prueba manual del bloque 8, con `pdf.js` como plan B.

### Cambios al diseño por los spikes
1. **Búsqueda por palabras solo con identificadores** (§4): la fusión con todas las palabras de la pregunta empeoraba el top-1 (bge-m3: de 0,93 a 0,33 en preguntas con otras palabras). Se usa la parte de palabras únicamente con términos tipo identificador (con dígitos, `_`, `/`, `.`, `-`, `+` o en MAYÚSCULAS); si la pregunta no tiene ninguno, solo manda el vector. Sin modelo de *embeddings*, se busca por palabras con todos los términos y sin fusión.
2. **Modelo de *embeddings* por defecto: `multilingual-e5-small`** (§6), por velocidad (8× más rápido) y memoria; EmbeddingGemma 2 (q4) y bge-m3 son las opciones de más calidad.
3. **Conversión** (§3): MarkItDown con conversores registrados en la misma pipeline: PDF (`pypdfium2`), Excel (`openpyxl`, sin `pandas`), imágenes y páginas escaneadas (OCR) y URLs (`trafilatura`, con MarkItDown de respaldo). Sin `pdfminer`.
4. **Modelos de visión** (§6 y §7): Gemma 4 E2B por defecto; Qwen3.5-2B (el más ligero) y Qwen3.5-4B (el más preciso). `llama.cpp` `b11720`, build CPU de 20 MB, con `sha256` fijado.
5. **Trabajador** (§3): protocolo en UTF-8 forzado; descarga el modelo de la memoria tras un rato sin trabajo.
6. **Tamaño del instalador**: el trabajador recortado añade ~100 MB al *sidecar* (~140 MB en total con `trafilatura`). Decisión abierta: instalador con todo o motor de conocimiento descargable (ver «Decisiones»).

## Diseño ([ADR 0021](../../adr/0021-knowledge.md), nuevo)

### 1. Modelo de datos (migración `0016_knowledge`)
- **`KnowledgeDoc`** (`knowledge_docs`):
  - nivel: `scope` (`general` · `project` · `agent`), `project_id` y `agent_id` (uno o ninguno según el nivel, con `CHECK`);
  - `title`, `description`, `mode` (`auto` · `context` · `search` · `off`) y `describe_images` (nulo: lo que digan los ajustes);
  - origen: `source_kind` (`file` · `url` · `image`), `path` o `url`;
  - huella del original al procesarlo: `size`, `mtime` y `sha256`;
  - presencia: `presence` (`ok` · `missing` · `changed`) y `checked_at`;
  - proceso: `status` (`queued` · `converting` · `images` · `describing` · `indexing` · `ready` · `failed`), `progress_done`, `progress_total`, `error_code` y `error_message`;
  - resultado: `markdown` (texto), `md_tokens` (estimado), `embed_model` y `processed_at`.
- **`KnowledgeChunk`** (`knowledge_chunks`): `doc_id`, `ord`, `heading` (ruta de títulos), `location` (p. ej. «p. 12», «Hoja Ventas», «§ Instalación»), `start` y `end` (posición en el Markdown, **sin repetir el texto**), `tokens`, `vector` (BLOB) y `vector_model`.
- **`knowledge_fts`**: tabla virtual FTS5 con el texto de cada trozo (`content=''` sin copia, o externa según S5) y `unicode61 remove_diacritics 2`.
- **`KnowledgeImage`** (`knowledge_images`): `doc_id`, `sha256`, `file` (en la carpeta de datos, para las extraídas; nulo en una imagen suelta), `location`, `width`, `height`, `ocr_text`, `description` y `described_by` (`cli:<modelo>` · `local:<modelo>`).
- `Run.kind` admite `describe` (consumo del describidor por CLI). `RunEvent` no cambia: las búsquedas son eventos `mcp`.
- `downgrade` borra las tablas nuevas.

**Qué se guarda en disco** (`<datos>/knowledge/`):
- `images/<sha256>.<ext>`: solo las imágenes **extraídas** de documentos, una vez por contenido;
- `run-images/<run_id>/`: copias temporales de imágenes sueltas que pide una ejecución (§5), borradas al terminar.

No hay copias de los originales ni ficheros intermedios. El Markdown y el índice viven en SQLite.

### 2. Ficheros por referencia (`services/knowledge/docs.py`)
- **Añadir**: `add_files(scope, paths)` y `add_url(scope, url)` crean el documento en `queued` y lo encolan. Rechazos inmediatos (sin crear el documento): ruta inexistente, carpeta, tamaño por encima del límite. Un formato no admitido sí se crea, como «Fallo · Formato no admitido», para que se vea.
- **Presencia**: `check(doc)` hace `stat` del original (barato). Si no existe → `missing`; si cambian el tamaño o la fecha → se calcula el `sha256` y, si difiere, `changed`. Se llama al listar los documentos de una página y antes de abrir, reprocesar o reubicar. No hay vigilancia del disco.
- **Reubicar**: `relocate(doc, new_path)` calcula el `sha256`. Si coincide, cambia la ruta y conserva el índice; si no, avisa (409 `different_content`) y, con `confirm`, cambia la ruta y reprocesa.
- **Quitar**: borra el documento, sus trozos y su FTS, y las imágenes extraídas que no use otro documento.
- **Mover de nivel**, editar título, descripción, modo y `describe_images`.
- **Abrir el original**:
  - `GET /knowledge/docs/{id}/original` sirve el fichero **solo si es un documento registrado** (nunca rutas arbitrarias), con su tipo, para el visor (PDF, imágenes, texto, código y CSV);
  - `POST …/open` lo abre con la aplicación del sistema (`os.startfile`); en una URL, el navegador;
  - `POST …/reveal` abre el explorador con el fichero seleccionado (`explorer /select,`).
  
  Si el original no está, los tres devuelven 410 `missing` y la UI ofrece reubicar o quitar.

### 3. La pipeline (`services/knowledge/pipeline.py`)
**Una sola pipeline** para cualquier documento, con estos pasos:
1. **Comprobar el origen** (presencia y huella) y, en una URL, descargarla con `httpx` (tiempo máximo, tamaño máximo, solo `http(s)`).
2. **Convertir con MarkItDown** (`convert_local` o `convert_stream`), con `keep_data_uris=True` y estos conversores propios registrados con `register_converter` (misma pipeline, no una aparte):
   - `PdfPagesConverter` (`pypdfium2`, S2): texto por página con una marca `<!-- page: 12 -->`; las páginas sin texto salen como una imagen de la página entera (para el OCR); las imágenes incrustadas salen como *data URI* en su sitio;
   - `XlsxConverter` (`openpyxl`): una tabla por hoja, sin `pandas`;
   - `HtmlMainConverter` (`trafilatura`, con el conversor de MarkItDown de respaldo): solo el contenido principal de las URLs;
   - `ImageConverter`: una imagen suelta es solo su marca (`![…](kimg:…)`), y su texto lo añade el paso 3.
   
   `pdfminer` y `pandas` no se empaquetan (S1).
3. **Imágenes** (paso común, `images.py`): recorre los *data URI* del Markdown y, para cada uno:
   - descarta los pequeños (de menos de 64 px de lado) y los repetidos (`sha256`);
   - guarda el fichero en `images/` y sustituye el *data URI* por `![Figura, p. 12](kimg:<id>)`;
   - le pasa el OCR y escribe el texto debajo como bloque citado (`> Texto de la imagen: …`);
   - si toca describir (§7), añade la descripción marcada como «Descripción generada».
   
   Las páginas escaneadas son una imagen más: su OCR **sustituye** a la marca y queda como texto normal de la página.
4. **Trocear** (`chunking.py`): por títulos de Markdown y, dentro, por párrafos, hasta unos 400 tokens con unos 50 de solapamiento (lo fija S4). Las tablas no se parten por la mitad si caben; si no, se parten repitiendo la fila de cabecera. Cada trozo lleva su `heading` y su `location` (la última marca de página o de hoja). El texto que se codifica empieza por «título del documento › apartado».
5. **Indexar**: inserta en FTS y calcula los vectores por lotes (§4). Si no hay modelo de *embeddings*, el documento queda `ready` solo con FTS.
6. **Listo**: `ready`, la huella del original y `processed_at`. Se emite el evento final.

**Fallos**: cada paso lanza `KnowledgeError(code, mensaje)` con el motivo en español. Códigos: `not_found`, `unsupported`, `encrypted`, `empty` (sin texto ni imágenes), `too_large`, `url_error` (con el estado HTTP), `convert_error`, `ocr_missing` (aviso, no fallo), `embed_error`. Lo imprevisto es `convert_error`, con la traza en el log. El documento queda `failed` con `error_code` y `error_message`, y no entra en el contexto ni en la búsqueda.

**Reprocesar**: vuelve a encolar desde el paso 1 y sustituye el Markdown, los trozos, el FTS y las imágenes solo al terminar bien: si falla, se conserva lo anterior (marcado `failed` con el motivo). Si cambia el modelo de *embeddings*, solo se repite el paso 5 (`reindex`).

**Dónde se ejecuta** (según S8):
- Un **proceso de trabajo** con prioridad baja, el mismo ejecutable con `--knowledge-worker`, hace los pasos de cálculo (convertir, OCR, *embeddings*). Recibe peticiones y devuelve resultados y progreso por stdin/stdout en líneas JSON. Así la API no se ralentiza y el sistema operativo prioriza lo demás.
- En el backend, un hilo `knowledge-queue` reparte trabajos al proceso (de uno en uno por defecto, `knowledge.concurrency`), escribe en la BD y emite los eventos.
- `onnxruntime` usa `knowledge.threads` hilos (por defecto, la mitad de los núcleos).
- **Pausar** deja de repartir trabajos; el que está en curso termina su paso actual y queda en cola. **Reanudar** sigue.
- Al arrancar la app, los documentos que estaban a medias vuelven a la cola.
- En los tests, el trabajo se hace en el mismo proceso (`InlineWorker`).

**Progreso**: `progress_done` y `progress_total` según el paso: páginas al convertir, imágenes con OCR o descripción, trozos al indexar. Se emite como mucho cada 250 ms por documento.

### 4. Búsqueda híbrida (`services/knowledge/search.py`)
- **Visibilidad** (`visible_docs(project_id, agent_ids)`): `general` + `project` del proyecto + `agent` de los agentes dados (el de la ejecución y, en un subagente, también el padre), con `status = ready` y `mode != off`. Una imagen suelta con el original `missing` no es visible.
- **Por palabras, solo con identificadores** (S4): se extraen de la pregunta los términos tipo identificador (con dígitos, `_`, `/`, `.`, `-` o `+`, o en MAYÚSCULAS de más de 2 letras: `ERR_4012`, `/v2/invoices`, `AURORA_PROXY`, `4.18`) y se consultan en FTS5 (escapados, unidos con `OR`, ordenados por `bm25`), top 50. Si no hay ninguno, esta parte no participa. Las palabras vacías nunca cuentan.
- **Por significado**: el vector de la consulta (con el prefijo del modelo) contra la matriz de vectores de los trozos visibles, por producto escalar (están normalizados), top 50. La matriz se carga con NumPy y se guarda en caché por modelo, invalidada cuando cambia algún trozo.
- **Fusión** RRF (`k = 60`, peso 1 para el vector y 2 para las palabras) y top `limit` (por defecto 8, máximo 20). Sin modelo de *embeddings* (o con vectores de otro modelo) no hay fusión: se busca en FTS5 con **todos** los términos sin palabras vacías.
- **Resultado**: documento (id y título), nivel, `location`, el texto del trozo, la puntuación y las imágenes del trozo (`kimg:` → ruta, §5).
- **Codificador** (`embeddings.py`): protocolo `Embedder` (`encode(texts, kind="query" | "passage")`), `OnnxEmbedder` (`onnxruntime` + `tokenizers`, *mean pooling* o el del modelo, normalizado) y `FakeEmbedder` para los tests (vectores por palabras).

### 5. Contexto, MCP e imágenes en las ejecuciones
**Sección «Conocimiento»** (`context.knowledge_section`), después de la memoria del proyecto:
- el **índice** de los documentos visibles: título, nivel, descripción, modo y tamaño en tokens;
- el **texto entero** de los que van al contexto, por este orden: primero los `context` y luego los `auto` con `md_tokens ≤ knowledge.small_doc_tokens` (por defecto 2 000), de menor a mayor, hasta `knowledge.context_budget` (por defecto 8 000). Los que no caben se marcan «solo búsqueda» en el índice. Las marcas `kimg:` se sustituyen por rutas;
- una línea con cómo usar `search_knowledge` y `read_knowledge`, en las reglas de Agentic OS.

Los tokens se estiman como caracteres ÷ 4. La UI de cada nivel avisa cuando el conjunto de documentos que entraría en el contexto pasa del presupuesto.

**MCP** (`mcp_server.py` y `AgentBackend`):
- `search_knowledge(query, limit=8)`: resultados en Markdown, con documento, ubicación y rutas de imágenes;
- `read_knowledge(document, location="")`: `document` es el id o el título; `location`, una página («12» o «p. 12»), una hoja o un apartado. Devuelve ese fragmento del Markdown o, sin `location`, el documento entero en partes de unos 6 000 tokens (`part=2`…);
- las dos dejan un evento `mcp` en la ejecución con la consulta y los documentos devueltos.

**Imágenes**:
- `extra_dirs` de la ejecución gana `<datos>/knowledge/images` (solo imágenes que gestiona la app) y `<datos>/knowledge/run-images/<run_id>` (vacía al arrancar).
- Las **imágenes sueltas** no exponen su carpeta original: cuando una búsqueda, una lectura o el contexto las devuelven, se **copian** a `run-images/<run_id>/` y se da esa ruta. La carpeta se borra al terminar la ejecución (y, al arrancar, las de ejecuciones que ya no existen).

**Plantillas** (`services/templates.py`): Redactor, Comercial y Analista mencionan en sus instrucciones que consulten el conocimiento.

### 6. Modelos y motores locales (`services/localmodels/`)
- **Catálogo** en código (`catalog.py`). Cada entrada tiene `id`, `kind` (`embedding` · `ocr` · `vision` · `engine`), nombre, tamaño, ficheros (URL, `sha256` y tamaño), si pide cuenta y sus datos de uso (dimensiones, prefijos, `mmproj`…). Entradas:
  - *embeddings* (S4): **`multilingual-e5-small`** (por defecto; `Xenova/multilingual-e5-small`, `model_quantized`, 118 MB, 384 dim.), **EmbeddingGemma 2** (`onnx-community/embeddinggemma-2-ONNX`, `model_q4` con su `.onnx_data`, 174 MB, 768 dim.) y **`bge-m3`** (`Xenova/bge-m3`, `model_quantized`, 570 MB, 1024 dim.). Cada entrada lleva sus prefijos de consulta y de documento, el *pooling* y las entradas extra (EmbeddingGemma 2 pide tres vacías);
  - OCR (S3): detector `PP-OCRv6_det_small` (9,9 MB), clasificador de orientación (0,6 MB) y reconocedor `latin_PP-OCRv5_rec_mobile` (7,9 MB), unos 18 MB;
  - visión (S6): **Gemma 4 E2B** (`unsloth/gemma-4-E2B-it-GGUF`, `Q4_K_M` + `mmproj-F16`, 4,1 GB; por defecto), **Qwen3.5-2B** (`unsloth/Qwen3.5-2B-GGUF`, 1,95 GB) y **Qwen3.5-4B** (`unsloth/Qwen3.5-4B-GGUF`, 3,4 GB);
  - motor: `llama.cpp` **`b11720`**, `llama-b11720-bin-win-cpu-x64.zip` (20 MB, `sha256 d59fd840…728de`).
- **Descargas** (`downloads.py`): `httpx` en un hilo, a `<datos>/models/<id>/` o `<datos>/engines/<id>/`, con reanudación (`Range`), progreso por eventos, cancelación y comprobación del `sha256`. Se escribe a un `.part` y se renombra al final. El motor se descomprime tras comprobarlo.
- **Estado**: se deduce del disco (`manifest.json` por modelo, escrito al terminar). La selección vive en `AppState`: `models.embedding`, `models.ocr` y `models.vision`.
- **Cuenta de Hugging Face**: para los modelos que la piden, el *token* sale de `HF_TOKEN`, del fichero de `huggingface_hub` (`~/.cache/huggingface/token`) o de `git credential fill` con `host=huggingface.co`. Si la persona lo pega en Ajustes, se guarda con `git credential approve`, igual que en el ADR 0018: la app no guarda secretos propios.
- **Cambio de modelo de *embeddings***: encola `reindex` de todos los documentos (solo el paso 5) y la búsqueda usa FTS hasta que terminan.
- **Ajustes de dictado** (fase 15): el catálogo admite `kind = "speech"` sin cambios de estructura.

### 7. Describir imágenes (opcional, `services/knowledge/describe.py`)
- **Ajustes**: `knowledge.describe` (desactivado por defecto) y `knowledge.describer` (`cli` con CLI, cuenta y modelo, o `local` con el modelo de visión). Cada documento puede forzarlo con `describe_images`.
- **Protocolo** `Describer.describe(image_path, context) -> Description`, donde `context` es el título y el apartado del documento. El prompt pide una descripción breve, en español y centrada en lo que aporta información (texto, datos, diagramas).
- **`CliDescriber`** (S7): reutiliza `decider.call`. Copia la imagen a una carpeta temporal vacía (el `cwd` de la llamada) y pide leerla con la herramienta de lectura del CLI: `claude -p … --model haiku --output-format json --tools Read --allowedTools Read --strict-mcp-config --no-session-persistence --max-budget-usd 0.10` o `agy -p … --output-format json` (la descripción está en `result.response`). Deja una `Run` `kind=describe`, con `agent_name` «Describir imágenes» (en las pruebas: ~0,0009 USD y 6,5 s por imagen con Claude; ~24 800 tokens y 9,7 s con agy). Antes de llamar, comprueba el límite diario y la cuota (`usage_limits.blocked_all`); si está bloqueado, el paso se salta con aviso y el documento queda `ready` sin descripciones.
- **`LlamaDescriber`**: `services/localmodels/llama.py` arranca `llama-server` (modelo + `mmproj`, `--threads` de los ajustes, puerto libre en `127.0.0.1`) cuando hay imágenes que describir, le habla por `/v1/chat/completions` con la imagen como *data URI*, y lo para tras 60 s sin trabajo y al cerrar la app. Si no arranca, error claro: «No se pudo iniciar llama.cpp: …».
- Cuenta en el progreso como «describiendo imágenes (n de m)».

### 8. Recursos del equipo (`services/system_stats.py`)
- `psutil` (dependencia nueva): CPU total y por proceso (backend, proceso de trabajo y `llama-server`) y memoria.
- GPU con PDH por `ctypes` (S8): suma de `Utilization Percentage` de los motores 3D y Compute del sistema y de los procesos propios. Si falla, `null` («No disponible»).
- Mientras haya trabajos activos, el *hub* emite una muestra por segundo (`{"type": "system", …}`). Sin trabajos, no se mide nada.

### 9. API y eventos
- **Documentos**:
  - `GET /knowledge/docs?scope=&project_id=&agent_id=` (comprueba la presencia);
  - `POST /knowledge/docs/files` (`{scope, project_id?, agent_id?, paths[]}`) y `POST /knowledge/docs/url`;
  - `PATCH /knowledge/docs/{id}` (título, descripción, modo, `describe_images` y nivel) y `DELETE /knowledge/docs/{id}`;
  - `POST …/reprocess`, `POST …/relocate` (`{path, confirm?}`), `GET …/markdown`, `GET …/original`, `POST …/open` y `POST …/reveal`.
- **Búsqueda de prueba**: `POST /knowledge/search` (`{scope, project_id?, agent_id?, query}`): lo mismo que vería una ejecución de ese ámbito (un agente en un proyecto ve los tres niveles).
- **Cola**: `GET /knowledge/queue` (estado, en pausa) y `POST /knowledge/queue/pause` y `…/resume`.
- **Modelos locales**: `GET /local-models` y `POST /local-models/{id}/download`, `…/cancel`, `DELETE /local-models/{id}`; `PUT /settings/local-models` (selección) y `PUT /settings/huggingface-token`.
- **Ajustes de conocimiento**: `GET` y `PUT /settings/knowledge` (presupuesto, umbral de documento pequeño, tamaño máximo, concurrencia, hilos, describir y describidor).
- **WebSocket** `/knowledge/events` (`KnowledgeEvents`, como `GitEvents`): `doc` (estado y progreso), `queue`, `model` (descarga) y `system` (recursos).

### 10. Frontend
- **Componente común** `components/knowledge/KnowledgeLibrary.tsx` con `scope`, usado en:
  - una página nueva **Conocimiento** (`/conocimiento`, entrada en el menú) para el nivel general;
  - la pestaña «Conocimiento» del proyecto y la del agente (sustituyen a `ComingSoonTab`).
- **Biblioteca**:
  - zona para soltar ficheros (`onDragDropEvent` de Tauri; en el navegador de desarrollo, aviso de que hace falta la app), botón «Añadir ficheros» (`plugin-dialog`, multiselección) y campo de URL;
  - lista de documentos con icono por tipo, título, tamaño, modo y estado; **barra de progreso** con el paso y «n de m»; insignias «Fallo» (con el motivo), «No encontrado» y «Ha cambiado»;
  - aviso cuando el contexto se pasa del presupuesto;
  - **monitor de recursos** (`ResourceMonitor.tsx`), visible mientras se procesa: CPU, GPU y memoria, total y de la app, con barras y la cifra; y botones de pausar y reanudar;
  - **«Probar la búsqueda»** (`SearchTester.tsx`).
- **Ficha del documento** (`DocSheet.tsx`, panel lateral):
  - título, descripción, modo, nivel y «Describir imágenes»;
  - botones «Abrir» (visor o aplicación del sistema según el tipo), «Mostrar en la carpeta», **«Ver Markdown»** y **«Reprocesar»**;
  - el motivo del fallo;
  - si falta el original: «El fichero se borró o se movió» con «Indicar la nueva ruta» (selector de Tauri) y «Quitar de la app».
- **Visor** (`DocViewer.tsx`, diálogo grande):
  - PDF en un `iframe` del endpoint `original` (visor de WebView2, según S9);
  - imágenes;
  - Markdown renderizado;
  - texto, código y CSV (como tabla); el código con un resaltado ligero (`highlight.js` con un puñado de lenguajes, unos 30 KB);
  - «Ver Markdown» abre el Markdown convertido (renderizado o en crudo), con las imágenes extraídas.
- **Ajustes**:
  - sección **Modelos locales** (`LocalModelsSection.tsx`): por función, cada modelo con tamaño, estado, progreso, descargar, cancelar, borrar y «Usar este»; los motores; el *token* de Hugging Face;
  - sección **Conocimiento** (`KnowledgeSection.tsx`): presupuesto, umbral, tamaño máximo, concurrencia, hilos y describir imágenes (CLI o local, con los avisos);
  - Ajustes › General muestra «Conocimiento» y «Modelos» en el uso de la carpeta de datos.
- **Ejecución**: los eventos `search_knowledge` y `read_knowledge` se ven en la lista de eventos de la ejecución con la consulta y los documentos.
- **i18n**: claves `knowledge.*`, `localModels.*` y los mensajes de error por código.
- **Tauri**: CSP con `frame-src` e `img-src` para `http://127.0.0.1:*` (según S9).

## Archivos
| Archivo | Cambio |
|---|---|
| `spikes/knowledge/*` | nuevos (bloque 0) |
| `backend/pyproject.toml` | `markitdown[docx,pptx]` (sin los extras `pdf` ni `xlsx`, que arrastran `pdfminer` y `pandas`), `openpyxl`, `pypdfium2`, `trafilatura`, `onnxruntime`, `tokenizers`, `numpy`, `rapidocr` y `psutil` |
| `backend/src/agentic_os/models/knowledge.py` | nuevo: `KnowledgeDoc`, `KnowledgeChunk`, `KnowledgeImage` |
| `backend/src/agentic_os/models/run.py` | `RunKind.DESCRIBE` |
| `backend/src/agentic_os/db/migrations/versions/0016_knowledge.py` | nuevo (tablas, FTS5, `CHECK` de `runs.kind`) |
| `backend/src/agentic_os/services/knowledge/` | nuevo: `docs.py`, `pipeline.py`, `worker.py`, `convert.py` (MarkItDown y plugins), `images.py`, `ocr.py`, `chunking.py`, `embeddings.py`, `search.py`, `describe.py`, `events.py` |
| `backend/src/agentic_os/services/localmodels/` | nuevo: `catalog.py`, `downloads.py`, `llama.py`, `hf_token.py` |
| `backend/src/agentic_os/services/system_stats.py` | nuevo |
| `backend/src/agentic_os/services/context.py`, `services/mcp_server.py`, `services/runs/manager.py`, `services/runrepos.py` | sección de conocimiento, herramientas MCP, `extra_dirs` y copias temporales de imágenes |
| `backend/src/agentic_os/services/templates.py` | instrucciones de Redactor, Comercial y Analista |
| `backend/src/agentic_os/services/datadir.py`, `api/settings.py` | tamaño de conocimiento y modelos |
| `backend/src/agentic_os/api/knowledge.py`, `api/local_models.py`, `schemas/knowledge.py` | nuevos |
| `backend/src/agentic_os/app.py`, `backend/packaging/entry.py` | servicios en el *lifespan*; `--knowledge-worker` |
| `scripts/build-backend.ps1` | datos y módulos ocultos de las librerías nuevas |
| `backend/tests/knowledge/corpus/*` | ficheros de ejemplo pequeños |
| `backend/tests/test_knowledge_*.py`, `test_local_models.py`, `test_migration_0016.py`, `test_e2e_knowledge.py` | nuevos |
| `desktop/src-tauri/tauri.conf.json` | CSP |
| `frontend/package.json` | `highlight.js` (núcleo y lenguajes sueltos) |
| `frontend/src/components/knowledge/*` | nuevos: biblioteca, ficha, visor, monitor, buscador |
| `frontend/src/pages/knowledge/KnowledgePage.tsx`, `routes.tsx`, menú | página general |
| `frontend/src/pages/projects/ProjectDetailPage.tsx`, `pages/agents/AgentEditorPage.tsx` | pestañas reales |
| `frontend/src/pages/settings/LocalModelsSection.tsx`, `KnowledgeSection.tsx`, `SettingsPage.tsx`, `GeneralSection.tsx` | ajustes |
| `frontend/src/api/knowledge.ts`, `api/localModels.ts`, `hooks/useKnowledgeEvents.ts` | tipos, llamadas y WebSocket |
| `frontend/src/i18n/*` | textos |
| `docs/adr/0021-knowledge.md`, `README.md`, `docs/roadmap.md` | nuevo / actualizados |

## Tareas (en orden)
Cada bloque se cierra con sus tests en verde y un commit (o varios) en `phase/14-conocimiento`.

0. [x] **Spikes S1–S9** con sus evidencias; ajustar el plan si algo cambia. (S9, el visor de PDF y la CSP, se completa con la prueba manual del bloque 8.)
1. [x] **Documentos por referencia**:
   - modelo y migración `0016`;
   - añadir, editar, mover, quitar, presencia, reubicar, `original`, `open` y `reveal`;
   - API sin procesado (los documentos se quedan en cola).
2. [x] **Pipeline y conversión**:
   - proceso de trabajo, cola, pausa y recuperación al arrancar;
   - MarkItDown y el plugin de PDF;
   - progreso, fallos con su código, reprocesar;
   - `KnowledgeEvents` y el WebSocket;
   - `system_stats`.
3. [x] **Modelos locales**: catálogo, descargas, selección, *token* de Hugging Face y API.
4. [x] **Imágenes y OCR**: extracción, deduplicación, marcas `kimg:`, OCR de imágenes y de páginas escaneadas.
5. [x] **Índice y búsqueda**: troceado, FTS5, *embeddings*, búsqueda híbrida, `reindex` al cambiar de modelo y búsqueda de prueba.
6. [x] **Contexto y MCP**:
   - sección de conocimiento con el presupuesto;
   - `search_knowledge` y `read_knowledge` con sus eventos;
   - carpetas de imágenes en `extra_dirs` y copias temporales;
   - plantillas.
7. [ ] **Describir imágenes**: `CliDescriber` (y agy según S7), `LlamaDescriber` con la descarga y el ciclo de vida de `llama-server`, ajustes.
8. [ ] **UI de la biblioteca**: página, pestañas, lista con progreso, ficha, visor, «Ver Markdown», monitor de recursos, pausa y «Probar la búsqueda».
9. [ ] **UI de ajustes**: Modelos locales, Conocimiento y uso de la carpeta de datos.
10. [ ] **e2e y cierre**:
    - `test_e2e_knowledge.py` (CA1);
    - instalador en una máquina limpia (CA10);
    - prueba manual con Claude Code y un PDF real (CA1, CA11);
    - prueba manual con `llama.cpp` y con el CLI (CA12);
    - ADR 0021, README;
    - `/code-review`;
    - `validacion.md`.

## Estado del desarrollo (traspaso, 2026-10-19)
**Hecho**: bloques 0 a 6. **Siguiente**: bloque 7 (describir imágenes con IA).

### Bloque 1 · qué hay y qué se decidió al hacerlo
- **Código nuevo** (`backend/src/agentic_os/`): `models/knowledge.py` (`KnowledgeDoc`, `KnowledgeChunk`, `KnowledgeImage` y sus enums), migración `0016_knowledge`, `services/knowledge/{formats,config,docs}.py`, `schemas/knowledge.py` y `api/knowledge.py` (registrado en `api/__init__.py`). Cambios menores: `RunKind.DESCRIBE`, la clave `KNOWLEDGE` de `app_state`, `reveal_in_file_manager` en `services/proc.py`.
- **API ya disponible** (`/api/knowledge/docs`): listar con filtros de nivel (comprueba la presencia de cada original), leer uno, añadir ficheros (`/files`, devuelve un resultado por ruta) y URL (`/url`), editar y mover de nivel (`PATCH`), borrar, `relocate`, `markdown`, `original` (para el visor), `open` y `reveal`. **Aún no hay** `reprocess` ni cola: los documentos se quedan en `queued` (bloque 2).
- **Tests**: `tests/test_migration_0016.py` y `tests/test_knowledge_docs.py` (31 tests). El ayudante `process()` de este último imita lo que hará la pipeline (huella del original y Markdown) para probar presencia, reubicación y borrado.
- **Desviaciones del diseño** (por qué):
  1. **`knowledge_fts` es una tabla FTS5 normal**, no «sin contenido»: columnas `text`, `chunk_id UNINDEXED` y `doc_id UNINDEXED`. Así se puede borrar por documento sin enlazar con un `rowid` que `VACUUM` podría renumerar. El texto de un trozo queda en el índice además de en el Markdown del documento (los trozos solo guardan `start`/`end`). Si el volumen molesta, se revisa.
  2. **La huella se rellena en dos tiempos**: al añadir se guardan `size` y `source_mtime` (provisionales); `sha256` solo lo pone la pipeline al procesar. Antes de procesar un documento **nunca** se marca «Ha cambiado».
  3. **Un formato no admitido** se crea ya como `failed` con `error_code = unsupported`. `empty` (fichero vacío o sin texto) lo decide la pipeline.
  4. **Ajustes**: `services/knowledge/config.py` lee y guarda el JSON `app_state.knowledge` (límite de tamaño 100 MB, presupuesto 8 000 tokens, documento pequeño 2 000, concurrencia, hilos, descripción de imágenes). La API de Ajustes llega en el bloque 9.
  5. `GET …/original` responde con `Content-Disposition: inline; filename=…` y `X-Content-Type-Options: nosniff`; los textos y el código se sirven como `text/plain` (un `.html` se ve como código, nunca se ejecuta).
  6. `runs.kind` es `String(8)` sin `CHECK`: «describe» (8 letras) cabe y **no hizo falta tocar `runs`**. Las listas y los diffs ya filtran por `kind == agent`.

### Bloque 2 · qué hay y qué se decidió al hacerlo
- **Código nuevo** (`backend/src/agentic_os/services/knowledge/`):
  - `convert.py`: MarkItDown con solo los conversores que queremos (Word y PowerPoint de MarkItDown) más los propios, con prioridad -1: `PdfPagesConverter` (`pypdfium2`), `XlsxConverter` (`openpyxl`), `HtmlMainConverter` (`trafilatura`, con el HTML genérico de respaldo), `ImageFileConverter` y `TextConverter` (texto y código; el código va en un bloque con vallas para que un `# comentario` no sea un título).
  - `images.py` (`ImageCollector`, `extract_data_uris`), `errors.py` (`KnowledgeError` con los códigos), `worker.py` (protocolo, `InlineWorker`, `ProcessWorker`, `serve`), `pipeline.py`, `service.py` (la cola), `events.py`.
  - `services/system_stats.py` (CPU, memoria y GPU por PDH) y `packaging/entry.py` (`--knowledge-worker`).
- **API nueva**: `POST …/{id}/reprocess`, `GET /knowledge/queue`, `POST /knowledge/queue/pause|resume`, `GET /knowledge/system`, y el WebSocket `/knowledge/events` (`doc`, `doc_removed`, `queue` y `system`).
- **Ajuste nuevo** `Settings.knowledge_processing`: `subprocess` (por defecto), `inline` u `off` (los tests: nada corre solo y llaman a `service.run_pending()`).
- **Tests** (`backend/tests/`): `test_knowledge_convert.py` (21), `test_knowledge_pipeline.py` (35), `test_system_stats.py` (8) y `test_knowledge_e2e.py`, que también sirve con el binario empaquetado (`AGENTIC_OS_E2E_BINARY`). Corpus pequeño en `tests/fixtures/knowledge/`.
- **Empaquetado**: `scripts/build-backend.ps1` incluye las librerías nuevas. El *sidecar* pasa de 30,5 a **87 MB** (aún sin OCR ni *embeddings*). El e2e con el binario real convierte los 9 formatos con su propio trabajador. **FTS5 existe en el SQLite empaquetado**: la migración `0016` lo usa al arrancar.
- **Desviaciones del diseño** (por qué):
  1. **MarkItDown sin sus conversores genéricos y con una sola pista de formato** (`MarkItDown(enable_builtins=False)` + `_convert(stream_info_guesses=[info])`, método interno: la versión está fijada en `uv.lock`). Con el comportamiento normal, un `.docx` dañado que fuera texto «se convertía» como texto plano, porque MarkItDown reintenta con lo que adivina del contenido (`magika`). Lo cubre `test_a_failure_is_marked_with_its_reason`.
  2. **Codificación del texto**: UTF-8, luego Windows-1252 y solo después el detector; se ignora la pista de `charset` de MarkItDown, que acierta mal en textos cortos en español (leía `ñ` como `ń`). En HTML se usa el decodificador de `trafilatura`, que lee la codificación declarada en la página.
  3. **Se quitó el filtro de imágenes por bytes** (4 KB): descartaba diagramas sencillos de colores planos. Basta el lado mínimo de 64 px (iconos, viñetas y separadores).
  4. **Las imágenes se encuentran y se miden, pero aún no se guardan**: salen del conversor a una carpeta de trabajo y el Markdown lleva `![alt](kimg:N)`; la carpeta se borra al acabar. El documento queda `ready` tras convertir. Hasta el **bloque 4** esas referencias no apuntan a nada.
  5. **El título de un PDF o de un fichero no sustituye al nombre**; solo una URL toma el título de su página (y solo si el usuario no lo cambió). `trafilatura` prefiere el `<h1>` al `<title>`.
  6. **La cola es la base de datos**: reclamar un documento es un `UPDATE … WHERE status = 'queued'` (dos hilos nunca cogen el mismo) y al arrancar lo que estaba a medias vuelve a `queued`. La **pausa vive en memoria** (no sobrevive a un reinicio). La **concurrencia** (`knowledge.concurrency`) se lee al arrancar: cambiarla pide reiniciar.
  7. **El trabajador** sale a los 60 s sin trabajo (libera su memoria), muere si una petición pasa de 20 minutos, y un trabajador que se cae es un `convert_error` («prueba otra vez»), nunca un cuelgue. Los avisos de progreso se escriben como mucho cada 0,25 s por documento.
  8. **`onnxruntime` del backend es la 1.20.1** (la fija `magika`), no la 1.31 de los spikes. Hay que comprobarlo con EmbeddingGemma 2 y bge-m3 en el bloque 5.

### Bloque 3 · qué hay y qué se decidió al hacerlo
- **Código nuevo** (`backend/src/agentic_os/services/localmodels/`):
  - `catalog.py`: las 8 entradas (`e5-small`, `embeddinggemma-2`, `bge-m3`, `ocr-latin`, `gemma4-e2b`, `qwen3.5-2b`, `qwen3.5-4b` y `llama-cpp`), cada fichero con URL, tamaño y `sha256`;
  - `_pins.py`: los datos de Hugging Face, **generados** por `spikes/knowledge/s10_emit_catalog.py` a partir de `s10_catalog_hashes.py` (revisión exacta del repositorio y hash de cada fichero, comprobado contra el de LFS). No se teclea ningún hash a mano;
  - `store.py` (carpeta de cada modelo, `manifest.json`, «está instalado», uso de disco), `downloads.py` (`DownloadManager`), `selection.py` (qué modelo hace cada trabajo) y `hf_token.py`.
- **API nueva** (`api/local_models.py`): `GET /local-models` (todas las entradas con su estado y el disco usado y libre), `POST /local-models/{id}/download|cancel`, `DELETE /local-models/{id}`, `GET|PUT /settings/local-models` (la elección; devuelve `reindex: true` si cambia el modelo de *embeddings*) y `GET|PUT /settings/huggingface-token`. Evento `model` en `/knowledge/events`.
- **Tests**: `test_local_models.py` (26): catálogo fijado, descarga completa, hash incorrecto, reanudación tras cortes y con un servidor que ignora `Range`, cancelar, espejo de respaldo, errores HTTP, falta de espacio, desempaquetado seguro del motor, *token* solo a Hugging Face, elección y API. También se amplió `test_datadir.py`.
- **Comprobado con las fuentes reales** ([evidencia](evidencias/m3-descargas-reales.md)): OCR desde `modelscope.cn` (18,4 MB), `llama.cpp` desde GitHub (19,7 MB, desempaquetado: `llama-server.exe` queda en `engines/llama-cpp/bin/`) y e5-small desde Hugging Face, cancelado al 37 % y reanudado.
- **Desviaciones del diseño** (por qué):
  1. **Descarga de e5-small: 135 MB, no 118**: el modelo (118 MB) más su `tokenizer.json` (17 MB). Con los demás pasa igual (EmbeddingGemma 2: 207 MB, bge-m3: 587 MB).
  2. **Cada fichero se fija a una revisión exacta** (`resolve/<sha de 40 letras>/…`, nunca `main`), y los dos `config.json` que no son LFS se comprobaron contra lo probado en los spikes. Los `config.json` no se descargan porque la app no los usa.
  3. **La reanudación se verifica al final de cada fichero** (un paso extra de lectura para el `sha256`, unos segundos para los más grandes) en lugar de ir calculándolo mientras se descarga, porque así vale también para lo que quedó a medias de otro intento.
  4. **Un fallo se recuerda solo durante la ejecución actual**: tras reiniciar la app, un modelo a medias vuelve a verse como «parcial» (con los bytes que ya tiene) y se reanuda con un clic.
  5. **Las descargas de modelos distintos son independientes y pueden ir a la vez**; no hay límite global. La UI del bloque 9 las pide de una en una.
  6. **El motor `llama.cpp` ocupa 50 MB desempaquetado** (el zip, 20 MB, se borra). Solo hay build para Windows (`platforms=("win32",)`); `GET /local-models` marca `available: false` en otros sistemas.
  7. **`reindex` es informativo hasta el bloque 5**: avisa de que cambia el modelo de *embeddings*; el reindexado real lo hace el índice.
  8. `GET /settings/data-dir` incluye ahora `knowledge_bytes` y `models_bytes` (la UI de Ajustes › General, en el bloque 9).
- **Decisión tomada (2026-10-19): los modelos de OCR van dentro del instalador.** Solo existen en `modelscope.cn` (sin espejo) y el OCR debe funcionar sin configurar nada ni tener internet. Cómo se hizo:
  - `CatalogEntry.bundled` (solo `ocr-latin`). `services/localmodels/stage.py` descarga y verifica sus ficheros, con los mismos hashes fijados, en `backend/build/bundled/models/<id>/` durante `scripts/build-backend.ps1`, y PyInstaller los añade como `bundled_models`. Si la preparación falla, la construcción se detiene.
  - En tiempo de ejecución, `store.bundled_folder` los busca en `sys._MEIPASS/bundled_models` (o en la carpeta de `AGENTIC_OS_BUNDLED_MODELS`, para los tests). Si están completos, el modelo cuenta como instalado y **se lee en el sitio**: nada se copia a la carpeta de datos. En desarrollo no hay paquete y se descarga como los demás.
  - `GET /local-models` marca `bundled: true` (listo, no se puede borrar: `DELETE` da 409 `bundled`). Si el paquete estuviera dañado, vuelve a descargarlo.
  - **Tamaño del *sidecar*: 102,8 MB** (30,5 MB antes de la fase; 87 MB tras el bloque 2). El e2e contra el binario real confirma que `ocr-latin` sale `ready` y `bundled` sin tocar la carpeta de datos.

### Bloque 4 · qué hay y qué se decidió al hacerlo
- **Código nuevo**: `services/knowledge/ocr.py` (RapidOCR dentro del trabajador, con los tres modelos por ruta, hilos limitados y confianza mínima 0,5), la operación `ocr` del trabajador, `images.compose` (pone el texto leído en el Markdown) y el paso de imágenes de `pipeline.py`. Migración `0017` (`notice` e `image_count` en el documento; `ord` y `kind` en la imagen, único por documento). API: `GET /knowledge/docs/{id}/images` y `…/images/{ord}`.
- **Cómo funciona**: tras convertir, el estado pasa a `images` con progreso «imagen n de m»; el trabajador lee cada imagen; en **una sola transacción** se guardan las imágenes que valen la pena (`<datos>/knowledge/images/<sha256>.<ext>`, una vez por contenido, compartidas entre documentos), se escribe el Markdown final y se borran las del intento anterior que ya nadie usa.
- **Reglas** (`compose`): una imagen de un documento conserva `![…](kimg:N)` y lleva debajo su texto como cita (`> Texto de la imagen: …`, solo la primera vez que aparece); **una página escaneada leída se convierte en su texto y no se guarda** (el original ya está por referencia); una página que nadie pudo leer (una foto, un dibujo) se queda como imagen; una referencia a una imagen que no tenemos desaparece; una imagen que añadió el usuario no se copia (`file = None`, se sirve desde el original).
- **Avisos, no fallos** (`doc.notice`): `ocr_missing` (no hay modelo de OCR: las imágenes se guardan sin texto y las páginas escaneadas siguen siendo imágenes) y `ocr_failed` (el OCR falló en todas). El documento queda `ready` y reprocesarlo con el modelo los quita.
- **Tests**: `test_knowledge_images.py` (14, con un OCR falso), `test_knowledge_ocr.py` (5, **OCR real** con los modelos auténticos, que se descargan una vez a la carpeta temporal y se saltan sin red) y `test_migration_0017.py`. El e2e empaquetado comprueba que el binario lee un PDF escaneado, un Word y una captura.
- **Empaquetado**: `build-backend.ps1` incluye `rapidocr` y sus ficheros de configuración (sin sus modelos). El *sidecar* pasa a **149 MB** (102,8 antes): RapidOCR con OpenCV añade ~46 MB. Con la ruta explícita de modelos, RapidOCR no descarga nada.
- **Desviaciones del diseño**: (1) la referencia de imagen es **el número dentro del documento** (`kimg:3`), no un id global; (2) el texto de la imagen se guarda también en `KnowledgeImage.ocr_text`; (3) la descripción con IA (bloque 7) añadirá `description` a esa misma fila.

### Bloque 5 · qué hay y qué se decidió al hacerlo
- **Código nuevo** (`services/knowledge/`): `chunking.py` (troceado), `embeddings.py` (`OnnxEmbedder` en el trabajador, operación `embed`, y el cliente por lotes), `index.py` (guarda trozos, vectores y filas FTS), `search.py` (visibilidad, canal de palabras, canal de significado, fusión, caché de vectores) y, en `service.py`, la búsqueda (`search`, `embed_query`) y el reindexado. `POST /knowledge/search` es la búsqueda de prueba (lo que vería un agente de ese proyecto y ese agente). Dependencias explícitas: `numpy`, `onnxruntime`, `tokenizers`.
- **Pipeline**: entre las imágenes y el resultado, el estado `indexing` (progreso por trozos); el índice se guarda en la **misma transacción** que el Markdown y las imágenes. Sin modelo de *embeddings*, el documento se indexa solo por palabras (`embed_model = ""`); si el modelo falla, queda `ready` con el aviso `embed_failed`.
- **Troceado**: bloques de Markdown (títulos, párrafos, citas, tablas y código; un bloque que cabe no se parte), unos 400 tokens, un título de nivel 1-3 abre trozo cuando el actual ya tiene cuerpo, **solapamiento de unos 50 tokens** (las últimas frases del trozo anterior; si no hay puntos, las últimas palabras), `location` de las marcas de página, diapositiva u hoja («p. 3-4» si abarca dos). Un bloque de más de 520 tokens se parte por frases o líneas y, si no hay, por tamaño.
- **Búsqueda** (cambios respecto a lo planeado, por los spikes y los tests):
  1. el canal de palabras usa **solo identificadores** cuando hay vectores (RRF: vector 1, palabras 2);
  2. **un documento sin vectores del modelo elegido** (se está reindexando, falló el cálculo o no había modelo cuando se procesó) **se busca por palabras con todos los términos significativos**, para que nunca quede invisible;
  3. sin modelo, solo palabras (`mode: "words"`).
- **Reindexado**: `service.reindex()` en un hilo cuando cambia la elección del modelo (`PUT /settings/local-models`), cuando termina de descargarse un modelo de *embeddings* (`DownloadManager.on_ready`) y al arrancar. Los documentos **siguen `ready`** (se buscan por palabras) y el progreso sale como evento `reindex` (`{done, total, model}`) y como `reindexing` en `GET /knowledge/queue`.
- **Consulta**: se vectoriza en un **trabajador aparte** (`ProcessWorker` que aguanta 5 minutos), para no esperar a una indexación larga.
- **Tests**: `test_knowledge_chunking.py` (12), `test_knowledge_search.py` (30, con un modelo falso que entiende sinónimos: indexado, búsqueda por significado y por identificador, visibilidad por niveles, fallos, reindexado y caché) y `test_knowledge_quality.py` con **el modelo real**: 30 preguntas entre 127 pasajes (97 casi idénticos), de extremo a extremo por la pipeline y la API. Resultado medido: acierto en los 5 primeros **0,93** (0,87 en las preguntas con otras palabras), primer puesto **1,00** con identificadores y **0,73** en conjunto (el spike S4 daba 0,90, 0,80, 1,00 y 0,80 con el mismo modelo; aquí hay menos de lo último porque el título entra en el texto que se vectoriza). El e2e hace la misma búsqueda con el trabajador real, también en el binario empaquetado.

### Bloque 6 · qué hay y qué se decidió al hacerlo
- **Código nuevo**: `services/knowledge/context.py` (la sección «Conocimiento», la resolución de imágenes y las carpetas de la ejecución) y `services/knowledge/agent_tools.py` (`search_knowledge` y `read_knowledge`). Cambios: `mcp_server.py` (protocolo y dos herramientas), `RunManager` (`knowledge`, `_instructions`, `search_knowledge`, `read_knowledge`, `extra_dirs` y limpieza al terminar), `context.build_instructions(knowledge=…)`, las reglas de Agentic OS y las plantillas (`_COMMON_RULES`, que usan los cinco agentes de ejemplo).
- **Sección «Conocimiento»**: índice de los documentos visibles (título, identificador corto, nivel, `completo`/`solo búsqueda`, tokens, imágenes y descripción) y el texto de los que van enteros: primero los de modo «siempre» (aunque se pasen del presupuesto), luego los «automático» de hasta `small_doc_tokens` de menor a mayor, mientras quepan en `context_budget`. Los que no caben pasan a «solo búsqueda». Sin documentos, la sección no existe. También se rehace en cada `get_context`.
- **Quién ve qué**: general, proyecto y agente propio; un **subagente** ve además lo del agente padre. Solo documentos `ready` y no apagados.
- **Imágenes**: `![…](kimg:N)` se convierte en la **ruta** del fichero: las extraídas, en `<datos>/knowledge/images/`; la que añadió el usuario se **copia** a `<datos>/knowledge/run-images/<run_id>/` (si el original ya no está, el agente lee «[nombre: no disponible]»). Las dos carpetas se pasan al CLI como `--add-dir` en todas las ejecuciones; la copia se borra al terminar la ejecución y todas al arrancar la app.
- **Herramientas**: `search_knowledge(query, limit)` devuelve los pasajes con su documento, apartado, lugar, identificador corto y rutas de imágenes; `read_knowledge(document, location, part)` lee un documento por **título (o parte del título) o identificador**, y una **página** (`12`, `p. 12`, `1-3`), **diapositiva**, **hoja** o **apartado**; los documentos de más de 6 000 tokens se leen **por partes**. Todo error se contesta **con palabras** (documento ambiguo o inexistente con la lista de los que puede leer, ubicación inexistente con lo que sí hay, nada encontrado, biblioteca vacía) para que el agente se corrija. Cada llamada deja un evento `mcp` con la consulta y los documentos devueltos.
- **Tests**: `test_knowledge_context.py` (14), `test_mcp_knowledge.py` (9, con el cliente MCP oficial contra un backend real) y, en `test_knowledge_e2e.py`, el criterio principal de la fase (**CA1**): una tarea cuya respuesta solo está en un PDF del proyecto; el CLI falso (con un cliente MCP de verdad) ve el documento en su contexto, lo busca y lo lee, y la ejecución registra las dos consultas. El CLI falso gana las directivas `BUSCA:` y `LEE:` y conoce `--add-dir`.
- **Hallazgo**: el CLI falso tomaba la carpeta de `--add-dir` como el *prompt*, lo que rompía los tests de `agy` en cuanto todas las ejecuciones llevaban carpetas adicionales; el CLI real sí sabe que es una opción con valor.

### Bloque 7 · qué hay y qué se decidió al hacerlo
- **Código nuevo**: `services/knowledge/describe.py` (`Describer`, `CliDescriber`, `LlamaDescriber`, parseo de `claude` y `agy`, `resolve_cli`, `default_factory`, `record_run`) y `services/localmodels/llama.py` (`LlamaServer`). Cambios: `config.py` (`describer_cli`, `describer_account`, `describer_model`), `images.compose(descriptions=…)`, `pipeline.py` (paso `describing` y `Outcome`), `service.py` (`describers`, `_llama_for`, `pipeline()`), `app.py` (`cli_overrides`), `GET/PUT /api/settings/knowledge` y `ImageRead.described_by`.
- **Por CLI**: la imagen se copia a una carpeta temporal vacía y el CLI la lee con `Read` (`claude -p … --tools Read --allowedTools Read --strict-mcp-config --no-session-persistence --max-budget-usd 0.10`; `agy -p … --output-format json`). Cada llamada deja una `Run` `kind=describe` con tokens y coste, que cuenta en el consumo por proyecto y cuenta pero no sale en las listas de ejecuciones. Cuenta bloqueada (`usage_limits.blocked`) o CLI sin sesión → aviso `describe_blocked`.
- **Local**: `llama-server` solo escucha en `127.0.0.1`, se arranca con la primera imagen, se reutiliza entre documentos, se para tras 60 s sin trabajo y al cerrar; comprueba memoria libre y que existan motor y modelo (`engine_missing`, `model_missing`, `not_enough_memory`, `start_failed`). Sin motor o modelo de visión descargados → `describe_missing`.
- **Pipeline**: solo describe imágenes que no son páginas escaneadas, y solo si `doc.describe_images` (o el ajuste global si es `null`); progreso «n de m» en estado `describing`; la descripción va bajo la imagen y en `KnowledgeImage.description/described_by`. Si fallan todas: aviso `describe_failed` y el documento queda `ready`. Reprocesar sin la opción quita las descripciones.
- **Tests**: `test_knowledge_describe.py` (28): parseo, argv y carpeta temporal, fallos del CLI, resolución y bloqueo, `Run` contada por proyecto y cuenta, ciclo de vida de `llama-server` con un servidor HTTP falso, integración en la pipeline y ajustes.
- **Hallazgo**: con salida estándar vacía y código de salida distinto de 0, el error útil es el `stderr` del CLI, no «no devolvió JSON».
- **Pendiente de validar con el binario real**: descripción con `claude`/`agy` y con `llama-server` descargado (bloque 10).

### Bloque 8 · qué hay y qué se decidió al hacerlo
- **Código nuevo** (frontend): `api/knowledge.ts` (tipos, hooks de React Query y `applyKnowledgeEvent`), `lib/knowledge-events.ts` (WebSocket `/api/knowledge/events` con reconexión) y `hooks/use-knowledge-events.ts`, `lib/native-files.ts` (diálogo nativo de ficheros y `onDragDropEvent` de Tauri), y `components/knowledge/`: `KnowledgeLibrary` (una biblioteca por nivel), `AddDocuments`, `DocList`, `DocSheet`, `DocViewer`, `ResourceMonitor`, `SearchTester` y `status.ts`. Página `/conocimiento` (`pages/knowledge/KnowledgePage.tsx`), pestañas «Conocimiento» de proyecto y de agente (sustituyen a `ComingSoonTab`), entrada en la paleta y en el breadcrumb, claves `knowledge.*` en `es.json`.
- **Añadir**: arrastrar y soltar (solo escritorio, por *paths*: no se copia nada), diálogo nativo de ficheros, dirección web y, en el navegador (que no da rutas reales), un campo de ruta. Los ficheros rechazados salen en un aviso con la razón traducida por código.
- **Lista**: título, nombre del original, tamaño, tokens, estado, **barra de progreso** `n/m` mientras convierte/lee imágenes/describe/indexa, **razón del fallo**, avisos (`notice`) y las marcas **«No encontrado»** y **«Ha cambiado»**. Sigue a la cola en vivo por WebSocket sin sondeo; tras reconectar se vuelve a leer todo.
- **Ficha del documento** (panel lateral): Abrir, Mostrar en carpeta, **Reprocesar**, Quitar (con confirmación), título y descripción editables, modo de uso por los agentes, «describir imágenes» (ajustes / sí / no), **Reubicar** si falta o cambió (si el contenido es otro, pide confirmar y reenvía con `confirm`), imágenes con su texto leído y su descripción.
- **Visor**: pestañas **Original** (PDF en `<iframe>`, imagen, Markdown/texto/código y CSV como tabla) y **Markdown** (lo que leen los agentes, con las imágenes `kimg:N` servidas por el backend). Sin resaltado de sintaxis: texto monoespaciado (no se añade una librería por esto).
- **Monitor de recursos**: CPU, GPU y memoria del equipo con la parte de la app, y «Pausar/Reanudar» la cola; solo aparece si hay trabajo o está en pausa. La GPU no disponible se dice («no disponible»), no se pinta 0 %.
- **Pestaña del agente**: se pinta **fuera** del `<form>` de edición, porque la biblioteca tiene formularios propios y un `<form>` dentro de otro no es HTML válido.
- **Escritorio**: la CSP gana `frame-src` y `img-src` para `http://127.0.0.1:*` y `http://localhost:*` (visor de PDF e imágenes); el permiso `dialog:allow-open` ya cubre ficheros.
- **Tests**: `components/knowledge/knowledge.test.tsx` (16): lista y estados, vacío, añadir por ruta/URL, eventos en vivo, monitor y pausa, búsqueda, ficha (Markdown con imágenes, PDF, modo, reubicar con confirmación, quitar, fallo), biblioteca de proyecto y de agente, `parseCsv`. `fake-backend` gana `handleKnowledge`. Suite completa del frontend: 382 tests en verde.
- **Pendiente (comprobación manual)**: el `<iframe>` del PDF y la CSP en una ventana real de WebView2 (S9); si no se viera, el plan B es pdf.js.

### Bloque 9 · qué hay y qué se decidió al hacerlo
- **Código nuevo** (frontend): `api/local-models.ts` (catálogo con sondeo cada segundo solo mientras algo se descarga, descargar/cancelar/borrar, selección por función y token de Hugging Face), `pages/settings/LocalModelsSection.tsx` y `pages/settings/KnowledgeSection.tsx`. Cambios: `SettingsPage` (secciones `knowledge` y `models`, entre Git y Limpieza), `GeneralSection` (la carpeta de datos dice cuánto ocupan la biblioteca y los modelos) y `api/settings.ts` (`knowledge_bytes`, `models_bytes`). Claves `settings.knowledge.*`, `localModels.*` y `settings.general.dataDirKnowledge`.
- **Modelos locales**: agrupados por función (significado, OCR, visión, motor) con licencia, tamaño, «Recomendado», «En uso», «Incluido en la app» (no se puede borrar), barra de progreso con bytes, «Reanudar» si quedó a medias, motivo del error traducido por código y espacio libre del disco. «Usar» solo aparece en los ya descargados; al cambiar el modelo de significado avisa de que se reindexa. El evento `model` del WebSocket invalida el catálogo. El campo del **token de Hugging Face** (guardado en las credenciales de git) solo aparece si falta algún modelo que pida cuenta.
- **Conocimiento**: tamaño máximo por fichero, presupuesto de contexto, umbral de documento pequeño, documentos a la vez e hilos (con validación de rango antes de enviar y el error de campo del backend), y la opción **opcional** de describir imágenes con IA: CLI (primer CLI con sesión, `claude` o `agy`, y modelo) o modelo de visión local, con el aviso de que el motor se descarga en «Modelos locales».
- **Tests**: `pages/settings/knowledge-settings.test.tsx` (9): uso de disco, guardar, rango, opciones de describir, lista de modelos, descargar/cancelar/borrar con confirmación, elegir modelo, token solo cuando hace falta. `fake-backend` gana `handleLocalModels`; el test del índice de Ajustes incluye las secciones nuevas. Suite completa del frontend: 391 tests en verde; `npm run build` compila.

### Entorno y trampas
- **Material de los spikes** (ignorado por git, **11 GB**): `spikes/knowledge/models/` (e5-small, EmbeddingGemma 2, bge-m3, Qwen3.5-2B/4B, Gemma 4 E2B y `llama.cpp` b11720), `spikes/knowledge/.venv` y `out/`. Sirve para probar con modelos reales; se puede borrar sin perder nada que no se pueda volver a bajar (`s4_download.py`, `s6_download.py`). Hugging Face además guarda caché en `~/.cache/huggingface`.
- **Suite completa del backend**: tarda más de 10 minutos; lanzarla en segundo plano. Para el conocimiento: `cd backend && uv run pytest tests/test_knowledge_*.py tests/test_migration_0016.py tests/test_system_stats.py`. Con el binario empaquetado: `npm run build:backend` y luego `AGENTIC_OS_E2E_BINARY=<ruta del sidecar> uv run pytest tests/test_knowledge_e2e.py`.
- **Git Bash**: los heredocs largos con comillas fallan sin ejecutar nada; escribir los ficheros con la herramienta de escritura. Los `.py` del repo pueden ser CRLF (un `str.replace` con `\n` no encuentra nada).
- **`husky` + `lint-staged`** formatean y ejecutan `ruff` al commitear y **bloquean** el commit si queda algún aviso (incluida la carpeta `spikes/`; `spikes/pyproject.toml` ya exime a `spikes/knowledge/*.py` de E501 y similares).
- La consola de Windows imprime en cp1252: forzar UTF-8 en los scripts que impriman tildes o `→`.
- **Pendientes que no son de un bloque concreto**: FTS5 dentro del ejecutable empaquetado del backend (comprobar en `npm run test:packaged`); el visor de PDF y la CSP en una ventana real (bloque 8); repetir el test de calidad de búsqueda con documentos reales en la validación.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_knowledge_docs.py`: añadir por ruta y URL, rechazos, mover de nivel, quitar (y sus imágenes), presencia `missing` y `changed`, reubicar con el mismo contenido (conserva el índice) y con otro (409 y `confirm`), `original` solo de documentos registrados, 410 si falta | CA3, CA4 |
| `test_knowledge_convert.py` (corpus): `.md`, código, PDF con texto (marcas de página y tablas), PDF escaneado (OCR), `.docx` y `.pptx` con imágenes en su sitio, `.xlsx` con dos hojas, URL (servidor local), imagen suelta; formato no admitido, PDF cifrado y fichero vacío con su código | CA2, CA9, CA11, CA13 |
| `test_knowledge_pipeline.py`: estados y progreso en orden, eventos, reprocesar conserva lo anterior si falla, pausar y reanudar, recuperación al arrancar, concurrencia 1, `reindex` al cambiar de modelo | CA9, CA14, CA15 |
| `test_knowledge_images.py`: descartar pequeñas y repetidas, `kimg:`, OCR debajo de la imagen, imágenes compartidas al quitar un documento | CA11 |
| `test_knowledge_search.py`: troceado (títulos, tablas, solapamiento, `location`), FTS con acentos, `FakeEmbedder`, RRF, visibilidad por niveles, sin modelo solo FTS, `off` y `failed` invisibles | CA5, CA7, CA8 |
| `test_knowledge_quality.py` (marcado `slow`, con el modelo real descargado): las 30 preguntas del spike S4 con un acierto mínimo en el top 5 | CA7 |
| `test_context.py` (ampliado): índice, documentos enteros dentro del presupuesto y por orden, los que no caben pasan a búsqueda, rutas de imágenes | CA6 |
| `test_mcp_knowledge.py`: `search_knowledge` y `read_knowledge` (por página, por hoja, por partes), eventos de la ejecución, copias temporales de imágenes sueltas y su limpieza, `extra_dirs` | CA1, CA11 |
| `test_local_models.py`: catálogo, descarga con un servidor local (progreso, reanudación, `sha256` incorrecto, cancelar), selección, *token* desde `git credential` (falso) | CA10, CA15 |
| `test_knowledge_describe.py`: `CliDescriber` con un CLI falso (Run `describe`, coste, límite diario bloqueado), `LlamaDescriber` con un servidor falso compatible con OpenAI (arranque, parada por inactividad, error al arrancar), por documento y global | CA12 |
| `test_system_stats.py`: forma de la muestra, GPU `null` si PDH falla, solo con trabajos activos | CA14 |
| `test_migration_0016.py`: tablas, FTS y `runs.kind`; `downgrade` | CA16 |
| `test_e2e_knowledge.py`: PDF grande en el proyecto, procesado con `FakeEmbedder`, tarea con el CLI falso que llama a `search_knowledge` y responde con el dato del PDF; la ejecución registra la llamada | CA1 |
| Frontend: `knowledge-library.test.tsx` (lista, progreso por eventos, fallo con motivo, no encontrado y reubicar, pausar, aviso de presupuesto), `doc-sheet.test.tsx` (abrir según tipo, Ver Markdown, reprocesar), `search-tester.test.tsx`, `resource-monitor.test.tsx` (GPU no disponible), `local-models.test.tsx` (descarga, selección, *token*), `knowledge-settings.test.tsx` | CA2–CA4, CA9, CA14, CA15 |
| Prueba manual: instalador en máquina limpia; PDF real con Claude Code; descripción con `llama.cpp` y con el CLI; monitor de recursos con un PDF grande | CA1, CA10–CA12, CA14 |
| `check` (lint, tipos, tests de backend y de frontend) | CA16 |

## Decisiones (ADR)
- **ADR 0021 · Conocimiento**:
  - ficheros **por referencia** con huella y comprobación de presencia bajo demanda; en la app solo el Markdown, el índice y las imágenes extraídas;
  - **una sola pipeline** con MarkItDown y plugins, y pasos comunes (imágenes, troceado, índice);
  - imágenes incrustadas como *data URI* convertidas en marcas `kimg:` con OCR; describir con IA, opcional;
  - búsqueda **híbrida** (FTS5 + vectores en SQLite con NumPy, RRF) y presupuesto de contexto;
  - procesado en un **proceso de trabajo** con prioridad baja;
  - modelos y motores **descargados aparte**, *token* de Hugging Face sin secretos propios (ADR 0018);
  - imágenes sueltas copiadas temporalmente a la ejecución en lugar de exponer su carpeta.
- **Concreciones de la spec** (para aprobar con el plan):
  - las imágenes sueltas no se dan al agente con su ruta original, sino con una **copia temporal** en la carpeta de la ejecución, para no darle acceso a la carpeta del usuario con `--add-dir`;
  - si el describidor por CLI está bloqueado por el límite diario o la cuota, el documento queda listo sin descripciones, con aviso, en lugar de fallar;
  - reprocesar conserva el resultado anterior si el nuevo intento falla.
- **Concreciones tras el bloque 0** (para aprobar):
  - la parte de palabras de la búsqueda híbrida **solo se activa con términos tipo identificador**; el resto lo resuelve el vector (los spikes muestran que usar todas las palabras empeora el resultado);
  - modelo de *embeddings* por defecto `multilingual-e5-small` y de visión por defecto Gemma 4 E2B, con las demás opciones en Ajustes;
  - **instalador**: el motor de conocimiento (conversión, OCR y *embeddings*) va **dentro del *sidecar*** (~140 MB en total, frente a 30,5 MB hoy), sin descargas obligatorias salvo los modelos. La alternativa, un ejecutable aparte que se descarga bajo demanda, exige alojar y firmar ese artefacto, y se revisará en la fase 20 (instaladores firmados) si el tamaño molesta.
- **Fuera de esta fase**, anotado para el futuro: GPU para ONNX y `llama.cpp`, binarios de `llama.cpp` para macOS y Linux (fase 20), reranking local.
