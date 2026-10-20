"""Knowledge library (phase 14, block 2): converting documents to Markdown."""

import os
import shutil
import sys
import time
from pathlib import Path

import pytest
from openpyxl import Workbook
from PIL import Image

from agentic_os.services.knowledge import convert as convert_module
from agentic_os.services.knowledge.convert import convert_file
from agentic_os.services.knowledge.errors import KnowledgeError
from agentic_os.services.knowledge.images import ImageCollector, extract_data_uris
from agentic_os.services.knowledge.worker import InlineWorker, ProcessWorker

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"


def convert(name: str, tmp_path: Path, **options):
    path = FIXTURES / name if (FIXTURES / name).exists() else tmp_path / name
    return convert_file(path, ext=path.suffix, workdir=tmp_path / "work", **options)


def png(path: Path, size=(200, 120), color="white") -> bytes:
    Image.new("RGB", size, color).save(path, "PNG")
    return path.read_bytes()


# ------------------------------------------------------------------------- the formats
def test_word_keeps_headings_tables_and_the_picture_in_place(tmp_path: Path):
    result = convert("informe.docx", tmp_path)
    assert "## Cancelación de la suscripción" in result.markdown
    assert "| Mes | Facturas | Importe |" in result.markdown
    assert "base64" not in result.markdown
    assert "![](kimg:0)" in result.markdown
    assert [(i.kind, i.width, i.height) for i in result.images] == [("embedded", 900, 126)]
    assert (tmp_path / "work" / "images" / result.images[0].file).is_file()


def test_powerpoint_marks_slides_and_places_the_picture(tmp_path: Path):
    result = convert("presentacion.pptx", tmp_path)
    assert "<!-- Slide number: 1 -->" in result.markdown
    assert "Facturae 3.2.2" in result.markdown
    assert [i.location for i in result.images] == ["diapositiva 2"]
    assert "kimg:0" in result.markdown


def test_excel_gives_one_table_per_visible_sheet(tmp_path: Path):
    result = convert("ventas.xlsx", tmp_path)
    assert "<!-- sheet: Ventas -->\n## Ventas" in result.markdown
    assert "| Enero | 412 | 18300 |" in result.markdown
    assert "## Clientes" in result.markdown
    assert "| Talleres Norte SL | B12345678 | España |" in result.markdown


def test_excel_skips_hidden_sheets_and_formats_values(tmp_path: Path):
    book = Workbook()
    sheet = book.active
    sheet.title = "Datos"
    sheet.append(["a|b", "precio", "ok"])
    sheet.append(["línea\ndos", 2.50, True])
    sheet.append(["x", 3.0, None])
    hidden = book.create_sheet("Oculta")
    hidden.append(["secreto"])
    hidden.sheet_state = "hidden"
    book.create_sheet("Vacía")
    book.save(tmp_path / "libro.xlsx")
    markdown = convert("libro.xlsx", tmp_path).markdown
    assert "a\\|b" in markdown  # a pipe in a cell does not break the table
    assert "| línea dos | 2.5 | sí |" in markdown
    assert "| x | 3 |  |" in markdown
    assert "secreto" not in markdown
    assert "Vacía" not in markdown


def test_pdf_has_page_markers_and_readable_tables(tmp_path: Path):
    seen = []
    result = convert(
        "manual.pdf", tmp_path, progress=lambda done, total: seen.append((done, total))
    )
    assert result.markdown.count("<!-- page: ") == 5
    assert "Básico 100 1 9 €" in result.markdown
    assert result.title == "Manual de Aurora"
    assert seen == [(n, 5) for n in range(1, 6)]
    assert result.images == []


def test_a_scanned_pdf_hands_its_pages_to_the_ocr(tmp_path: Path):
    result = convert("manual_escaneado.pdf", tmp_path)
    assert [(i.kind, i.location) for i in result.images] == [
        ("page", "p. 1"),
        ("page", "p. 2"),
        ("page", "p. 3"),
    ]
    assert "![Página 2](kimg:1)" in result.markdown
    assert all(i.width > 1000 for i in result.images)


def test_a_picture_file_is_its_own_document(tmp_path: Path):
    result = convert("captura_error.png", tmp_path)
    assert result.markdown == "![captura_error.png](kimg:0)"
    assert result.images[0].kind == "file"
    tiny = tmp_path / "icono.png"
    png(tiny, (16, 16))
    assert convert("icono.png", tmp_path).images[0].width == 16  # the user chose it: kept


def test_markdown_stays_and_code_goes_in_a_fence(tmp_path: Path):
    assert convert("notas.md", tmp_path).markdown.startswith("# Notas de la reunión")
    code = convert("ejemplo.py", tmp_path).markdown
    assert code.startswith("```python\n")
    assert code.rstrip().endswith("```")
    # A comment is never a heading: the whole file is inside the fence.
    (tmp_path / "script.py").write_text("# comentario\nprint('```')\n", encoding="utf-8")
    fenced = convert("script.py", tmp_path).markdown
    assert fenced.startswith("````python\n") and fenced.rstrip().endswith("````")


def test_html_keeps_the_article_and_drops_the_menu(tmp_path: Path):
    result = convert("pagina.html", tmp_path)
    assert result.markdown.startswith("# Centro de ayuda")
    assert "Inicio | Precios" not in result.markdown
    assert result.title == "Centro de ayuda"  # the page's h1 wins over its <title>


def test_html_without_an_article_falls_back_to_the_generic_converter(tmp_path: Path):
    (tmp_path / "corta.html").write_text("<html><body><p>Hola</p></body></html>", encoding="utf-8")
    assert "Hola" in convert("corta.html", tmp_path).markdown


def test_text_is_decoded_whatever_its_encoding(tmp_path: Path):
    (tmp_path / "latin.txt").write_bytes("Cancelación y señal".encode("latin-1"))
    assert convert("latin.txt", tmp_path).markdown == "Cancelación y señal"


# --------------------------------------------------------------------------- the errors
def error_of(name: str, tmp_path: Path) -> KnowledgeError:
    with pytest.raises(KnowledgeError) as caught:
        convert(name, tmp_path)
    return caught.value


def test_unsupported_empty_and_damaged_files(tmp_path: Path):
    (tmp_path / "programa.exe").write_bytes(b"MZ")
    assert error_of("programa.exe", tmp_path).code == "unsupported"
    (tmp_path / "vacio.md").write_text("  \n", encoding="utf-8")
    assert error_of("vacio.md", tmp_path).code == "empty"
    (tmp_path / "roto.docx").write_bytes(os.urandom(2000))
    assert error_of("roto.docx", tmp_path).code == "convert_error"
    assert error_of("no-existe.md", tmp_path).code == "not_found"


def test_a_password_protected_office_file_is_recognised(tmp_path: Path):
    # Word, Excel and PowerPoint lock a file by wrapping it in an old-style OLE container.
    (tmp_path / "secreto.xlsx").write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 600)
    assert error_of("secreto.xlsx", tmp_path).code == "encrypted"


def test_a_password_protected_pdf_is_recognised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def locked(_data):
        raise convert_module.pdfium.PdfiumError(
            "Failed to load document (PDFium: Incorrect password error)"
        )

    monkeypatch.setattr(convert_module.pdfium, "PdfDocument", locked)
    assert error_of("manual.pdf", tmp_path).code == "encrypted"


# ---------------------------------------------------------------------------- pictures
def test_the_collector_drops_tiny_repeated_and_unreadable_pictures(tmp_path: Path):
    big = png(tmp_path / "grande.png", (300, 200))
    tiny = png(tmp_path / "icono.png", (20, 20))
    collector = ImageCollector(tmp_path / "images")
    assert collector.add(big) == 0
    assert collector.add(big) == 0  # the same picture twice is one
    assert collector.add(tiny) is None
    assert collector.add(b"not a picture") is None
    assert (len(collector.images), collector.dropped) == (1, 2)


def test_other_picture_formats_are_re_encoded(tmp_path: Path):
    bitmap = tmp_path / "foto.bmp"
    Image.new("RGB", (200, 200), "red").save(bitmap, "BMP")
    collector = ImageCollector(tmp_path / "images")
    assert collector.add(bitmap.read_bytes()) == 0
    assert (collector.images[0].mime, collector.images[0].file) == ("image/png", "img-0.png")


def test_data_uris_become_references_and_remember_where_they_were(tmp_path: Path):
    import base64

    data = base64.b64encode(png(tmp_path / "a.png", (300, 200))).decode()
    markdown = (
        f"<!-- page: 3 -->\n\n![Gráfico](data:image/png;base64,{data})\n\n"
        f"<!-- Slide number: 2 -->\n\n![Otra](data:image/png;base64,{data})\n\n"
        "![Roto](data:image/png;base64,AAAAA)"
    )
    collector = ImageCollector(tmp_path / "images")
    out = extract_data_uris(markdown, collector)
    assert "base64" not in out
    assert out.count("![Gráfico](kimg:0)") == 1
    assert "![Otra](kimg:0)" in out  # same picture, same number
    assert "Roto" not in out
    assert [i.location for i in collector.images] == ["p. 3"]  # first place it was seen


# --------------------------------------------------------------------------- the worker
def test_the_inline_worker_answers_with_the_same_contract(tmp_path: Path):
    events = []
    answer = InlineWorker().request(
        {
            "id": "x",
            "op": "convert",
            "path": str(FIXTURES / "manual.pdf"),
            "ext": ".pdf",
            "workdir": str(tmp_path),
        },
        events.append,
    )
    assert answer["ok"] is True and answer["id"] == "x"
    assert "Básico 100 1 9 €" in answer["markdown"]
    assert events[-1] == {"id": "x", "event": "progress", "done": 5, "total": 5}
    failure = InlineWorker().request(
        {"op": "convert", "path": str(tmp_path / "no.md"), "ext": ".md", "workdir": str(tmp_path)}
    )
    assert (failure["ok"], failure["code"]) == (False, "not_found")
    assert InlineWorker().request({"op": "baila"})["code"] == "convert_error"


def test_the_worker_process_converts_at_low_priority_and_leaves_when_idle(tmp_path: Path):
    worker = ProcessWorker(idle_seconds=1.0)
    events = []
    try:
        answer = worker.request(
            {
                "op": "convert",
                "path": str(FIXTURES / "manual.pdf"),
                "ext": ".pdf",
                "workdir": str(tmp_path),
            },
            events.append,
        )
        assert answer["ok"] is True
        assert "Básico 100 1 9 €" in answer["markdown"]  # accents survive the pipe (UTF-8)
        assert [(e["done"], e["total"]) for e in events][-1] == (5, 5)
        pid = worker.pid
        assert pid is not None and pid != os.getpid()
        if sys.platform == "win32":
            import psutil

            assert psutil.Process(pid).nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS
        # A second request reuses the same process…
        worker.request({"op": "ping"})
        assert worker.pid == pid
        # …and when nobody asks anything it goes away, taking its memory with it.
        deadline = time.monotonic() + 15
        while worker.pid is not None and time.monotonic() < deadline:
            time.sleep(0.5)
        assert worker.pid is None
        assert worker.request({"op": "ping"})["ok"] is True  # and comes back when needed
    finally:
        worker.close()


def test_a_worker_that_dies_is_an_error_not_a_hang(tmp_path: Path):
    worker = ProcessWorker(command=lambda: [sys.executable, "-c", "pass"])
    try:
        with pytest.raises(KnowledgeError) as caught:
            worker.request({"op": "ping"})
        assert caught.value.code == "convert_error"
    finally:
        worker.close()


def test_the_work_folder_is_never_the_documents_folder(tmp_path: Path):
    # The converters write pictures only under the folder they are given.
    shutil.copy(FIXTURES / "informe.docx", tmp_path / "informe.docx")
    before = {p.name for p in tmp_path.iterdir()}
    convert_file(tmp_path / "informe.docx", ext=".docx", workdir=tmp_path / "work")
    assert {p.name for p in tmp_path.iterdir()} - before == {"work"}
