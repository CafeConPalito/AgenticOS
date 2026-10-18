# S2 · PDF con `pypdfium2` · S3 · OCR · S5 · FTS5

- **Fecha**: 2026-10-18 · Python 3.12 (uv) en Windows 11 · scripts: `spikes/knowledge/s2_pdf.py`, `s3_ocr.py`, `s5_fts.py`.

## S2 · PDF
`manual.pdf` (5 páginas, texto y una tabla) y `manual_escaneado.pdf` (3 páginas solo imagen), con `pypdfium2` 5.14 (Apache 2.0 / BSD).

- **Texto por página en orden de lectura**: 1 355–1 577 caracteres por página; **la tabla sale como filas legibles** (`Básico 100 1 9 €`), a diferencia de `pdfminer` (el que usa MarkItDown), que la deja desordenada. 5 páginas en **0,04 s**.
- **Páginas escaneadas**: texto de 0 caracteres y 1 objeto imagen → detección fiable (`texto < 20 caracteres y hay imagen`).
- **Renderizado** de una página a imagen (`page.render(scale=1.5).to_pil()` → 893×1263 px) y **extracción de las imágenes incrustadas** (`page.get_objects(filter=[FPDF_PAGEOBJ_IMAGE])` → `get_bitmap().to_pil()`, 1000×338 px) funcionan.
- Sin títulos: `pypdfium2` no distingue encabezados. La pipeline añade solo marcas de página (`<!-- page: N -->`); los títulos se infieren, si acaso, por tamaño de letra en una fase futura (no se necesita para trocear: se trocea por párrafos y página).

**Conclusión**: un conversor propio de PDF (plugin de MarkItDown) con `pypdfium2` para texto y páginas, y el OCR de S3 para páginas sin texto.

## S3 · OCR (RapidOCR 3.10, ONNX, CPU)
Reconocedor **latino** de PP-OCRv5 (`latin_PP-OCRv5_rec_mobile`) + detector `PP-OCRv6_det_small` + clasificador de orientación.

| Entrada | Tiempo | Resultado |
|---|---|---|
| `captura_error.png` (900×~220) | 2,99 s (incluye el arranque) | «Aurora - Nueva factura ERR_4012: el NIF del cliente no es válido Revise el formato e inténtelo de nuevo.» |
| `manual_escaneado.pdf` p. 1 / 2 / 3 (render a escala 2) | 1,11 / 0,96 / 0,90 s | Texto completo y correcto, con tildes, `ñ`, `ERR_5103`, `BIENVENIDA25` y `status.aurora.example` |

- **Modelos**: detector 9,9 MB + clasificador 0,6 MB + reconocedor latino 7,9 MB = **~18 MB**. Por defecto RapidOCR los descarga de `modelscope.cn` en el primer uso → la app los descargará con su propio gestor (URL y `sha256` fijados). El reconocedor por defecto (`PP-OCRv6_rec_small`, 21 MB) no hace falta.
- **Peso de las dependencias**: `opencv-python-headless` ocupa 113 MB en disco (el mayor coste del OCR), `onnxruntime` 43 MB, `rapidocr` 39 MB.

**Conclusión**: el OCR en español es suficiente para capturas y escaneos; se usa **siempre** en imágenes y páginas sin texto. Licencia Apache 2.0 (RapidOCR y modelos PaddleOCR).

## S5 · SQLite FTS5
SQLite 3.53.1 del Python 3.12 de `uv`, con `ENABLE_FTS5`; tokenizador `unicode61 remove_diacritics 2`.

| Consulta | Resultado |
|---|---|
| `cancelacion suscripcion` (sin tildes) y `cancelación suscripción` | Ambas encuentran la sección correcta |
| `factura rectificativa` | La sección «Facturas rectificativas» en primer lugar |
| `ERR_4012`, `puerto 587 STARTTLS` | La sección correcta en primer lugar |
| `impuest*` (prefijo) | Encuentra «Impuestos por país» |

- No hay *stemming*: «factura» no encuentra «facturas» salvo con prefijo. Es aceptable porque la parte de palabras solo se usa con identificadores (ver S4).
- **Pendiente de confirmar** en el ejecutable de PyInstaller del backend: que el SQLite incluido tiene FTS5 (la sonda del apartado S1 lo comprueba).
