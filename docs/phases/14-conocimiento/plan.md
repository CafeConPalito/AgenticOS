# Fase 14: Conocimiento · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-18) · en desarrollo (bloques 0 y 1 hechos; sigue el 2)

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
   - descarta los pequeños (menos de 64×64 px o de 4 KB) y los repetidos (`sha256`);
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
2. [ ] **Pipeline y conversión**:
   - proceso de trabajo, cola, pausa y recuperación al arrancar;
   - MarkItDown y el plugin de PDF;
   - progreso, fallos con su código, reprocesar;
   - `KnowledgeEvents` y el WebSocket;
   - `system_stats`.
3. [ ] **Modelos locales**: catálogo, descargas, selección, *token* de Hugging Face y API.
4. [ ] **Imágenes y OCR**: extracción, deduplicación, marcas `kimg:`, OCR de imágenes y de páginas escaneadas.
5. [ ] **Índice y búsqueda**: troceado, FTS5, *embeddings*, búsqueda híbrida, `reindex` al cambiar de modelo y búsqueda de prueba.
6. [ ] **Contexto y MCP**:
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

## Estado del desarrollo (traspaso, 2026-10-18)
**Hecho**: bloque 0 (commit `40ff7f8`) y bloque 1. **Siguiente**: bloque 2 (pipeline y conversión).

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

### Cómo retomar: bloque 2 (pipeline y conversión)
1. **Dependencias** (`backend/pyproject.toml`): `markitdown[docx,pptx]`, `openpyxl`, `pypdfium2`, `trafilatura`, `numpy`, `onnxruntime`, `tokenizers`, `rapidocr`, `psutil` (lista del plan, sin `pandas` ni `pdfminer`). Empaquetado: las banderas de PyInstaller que funcionaron en S1 están en `spikes/knowledge/s1_build.sh` y la variante recortada es: `--collect-submodules markitdown --collect-data markitdown --collect-all magika --collect-submodules rapidocr` + `config.yaml` y `default_models.yaml` de `rapidocr` como datos, `--collect-data pptx --collect-data docx --collect-all pypdfium2 --collect-all pypdfium2_raw` y `--exclude-module pandas --exclude-module pdfminer`. Las rutas de `--add-data` deben ser **relativas** (Git Bash pasa `/d/…` y PyInstaller no lo entiende).
2. **Esqueleto del trabajador**: `spikes/knowledge/probe_worker.py` (proceso relanzado con `--worker`, líneas JSON, prioridad `BELOW_NORMAL`, **UTF-8 forzado** en `stdin`/`stdout`). En el producto el modo es `--knowledge-worker` en `packaging/entry.py`. En los tests, `InlineWorker` (mismo proceso).
3. **Piezas de los spikes que se llevan al producto**: `s2_pdf.py` (PDF por páginas, detección de escaneadas, render, imágenes incrustadas), `s3_ocr.py` (RapidOCR latino; los modelos se pedirán al gestor de modelos del bloque 3 — hasta entonces, en desarrollo, pueden salir de `spikes/knowledge/.venv/…/rapidocr/models`), `s1_urls.py` (`trafilatura`) y `s5_fts.py`/`s4_embed_eval.py` (FTS5 y *embeddings*, para el bloque 5).
4. **Orden sugerido**: (a) `convert.py` con los conversores registrados en MarkItDown y tests con el corpus (`spikes/knowledge/make_corpus.py` lo genera; copiar versiones pequeñas a `backend/tests/knowledge/corpus/`); (b) `pipeline.py` por pasos con `KnowledgeError(code, mensaje)` y progreso; (c) cola y trabajador, pausa y recuperación al arrancar; (d) `events.py` (patrón de `gitx/events.py`) y `/knowledge/events`; (e) `POST …/reprocess`, `POST /knowledge/queue/pause|resume`; (f) `system_stats.py` (S8: `s8_gpu.py` ya lee la GPU por PDH).
5. **Ganchos existentes**: `app.py` crea los servicios en el `lifespan` (ver `GitEvents`, `DecisionService`); `services/decider.py` es el modelo de «hilo + `Run` de consumo» para el describidor del bloque 7.

### Entorno y trampas
- **Material de los spikes** (ignorado por git, **11 GB**): `spikes/knowledge/models/` (e5-small, EmbeddingGemma 2, bge-m3, Qwen3.5-2B/4B, Gemma 4 E2B y `llama.cpp` b11720), `spikes/knowledge/.venv` y `out/`. Sirve para probar con modelos reales; se puede borrar sin perder nada que no se pueda volver a bajar (`s4_download.py`, `s6_download.py`). Hugging Face además guarda caché en `~/.cache/huggingface`.
- **Suite completa del backend**: tarda más de 10 minutos; lanzarla en segundo plano. Para el bloque: `cd backend && uv run pytest tests/test_knowledge_docs.py tests/test_migration_0016.py`.
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
