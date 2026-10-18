# S1 · MarkItDown: calidad, imágenes, URLs y peso en el instalador

- **Fecha**: 2026-10-18 · `markitdown` 0.1.8 (MIT), Python 3.12, Windows 11 · scripts: `spikes/knowledge/make_corpus.py`, `s1_markitdown.py`, `s1_urls.py`, `probe_worker.py`, `s1_build.sh`.
- **Corpus** (`make_corpus.py`): PDF con texto y una tabla, PDF escaneado, `.docx` con tabla e imagen, `.xlsx` con dos hojas, `.pptx` con imagen, captura PNG, `.md`, `.py` y una página HTML con menú.

## Calidad por formato (`convert(..., keep_data_uris=True)`)
| Fichero | Resultado |
|---|---|
| `.docx` | **Bien**: 5 títulos `##`, tabla en Markdown (`\| Mes \| Facturas \|…`) y la imagen **en su sitio** como `![](data:image/png;base64,…)`. 0,24 s |
| `.pptx` | **Bien**: marcas `<!-- Slide number: N -->`, títulos `#`, viñetas y la imagen como *data URI* en la diapositiva. 0,05 s |
| `.xlsx` | **Bien**: una sección `##` por hoja con su tabla. Usa `pandas` (44 MB) para leerlo. Los números salen como `18300` (sin separador) |
| `.md`, `.py`, `.html` | Bien. El HTML conserva el **menú** («Inicio \| Precios \| Contacto») |
| **PDF** (`pdfminer`) | **Flojo**: texto plano sin títulos ni marcas de página y la **tabla desordenada** (las columnas salen separadas: «Plan / Facturas/mes Usuarios / Precio / Básico / 100 / 1…») |
| PNG y PDF escaneado | **0 caracteres** (sin OCR ni LLM, como se esperaba) |

**Conclusión**: MarkItDown sirve como pipeline única para `.docx`, `.pptx`, `.xlsx`, texto, código y HTML y deja las imágenes incrustadas en su sitio. Para **PDF** se usa un conversor propio sobre `pypdfium2` (S2) y para **imágenes y páginas escaneadas**, el OCR (S3), registrados con `register_converter`, es decir, en la misma pipeline.

## URLs (`trafilatura` 2.3.1, Apache 2.0)
| Página | MarkItDown | `trafilatura` |
|---|---|---|
| Local (con `<nav>` y `<footer>`) | 983 caracteres, empieza por «Inicio \| Precios \| Contacto» | 944, empieza en el título |
| `docs.python.org/3/library/sqlite3.html` | 114 358 caracteres, empieza por el menú, el logotipo y «Theme / Auto / Light / Dark» | **72 095**, empieza en «`sqlite3` — DB-API 2.0 interface…» |

**Conclusión**: para URLs, `trafilatura` extrae el contenido principal en Markdown (con tablas); MarkItDown hace de respaldo si falla. Se usa en el mismo paso de conversión (no es una segunda pipeline).

## Peso en PyInstaller (`--onefile`, ejecutable que se relanza como trabajador)
Referencia: el *sidecar* actual del backend pesa **30,5 MB**.

| Variante | Tamaño | Notas |
|---|---|---|
| Esqueleto del trabajador (sin librerías) | 7,7 MB | |
| + MarkItDown (con `pandas`, `pdfminer`), `pypdfium2`, `onnxruntime`, `tokenizers`, `numpy` | 114,5 MB | |
| + OCR (RapidOCR con sus 38 MB de modelos + OpenCV) | 160,5 MB | |
| **Recortada**: sin `pandas`, sin `pdfminer`, sin los modelos de OCR (se descargan) | **109,3 MB** | Todo funciona congelado |

- Lo recortado: Excel con un conversor propio sobre `openpyxl` (en vez de `pandas`), PDF con `pdfium` (en vez de `pdfminer`), modelos de OCR descargados por el gestor de modelos. Queda fuera de este recorte el peso de **OpenCV**, que RapidOCR exige (~113 MB sin comprimir).
- Estimación del instalador: sidecar actual 30,5 MB + ~100 MB de la parte nueva + `trafilatura` (~10 MB) ≈ **140 MB**.
- **Hay que decidir** si todo va en el instalador (simple, sin descargas, cumple el CA10) o si el motor de conocimiento se descarga bajo demanda como `llama.cpp` (instalador ligero, pero hay que alojar y firmar el artefacto). El diseño del trabajador (`--knowledge-worker`) vale para las dos.

## Trabajador empaquetado
- El mismo `.exe` relanzado con `--worker` queda **listo en 0,2 s**: el hijo reutiliza el paquete que el padre ya extrajo.
- Prioridad `BELOW_NORMAL` (16384) comprobada con `psutil`; las operaciones (conversión, PDF, OCR, *embeddings*) funcionan congeladas.
- Hay que forzar UTF-8 en las tuberías (ver S8).
- SQLite FTS5 del Python empaquetado: **pendiente de comprobar** en el ejecutable del backend (en el Python de `uv` está disponible, ver S5).
