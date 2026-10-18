"""Builds the sample corpus for the phase 14 spikes into ./corpus (run: uv run make_corpus.py)."""

from __future__ import annotations

import io
from pathlib import Path

from docx import Document
from docx.shared import Inches
from facts import FACTS
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Inches as PInches
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).parent / "corpus"
OUT.mkdir(exist_ok=True)
FONT = "C:/Windows/Fonts/arial.ttf"


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def text_image(
    lines: list[str], size: int = 28, width: int = 900, bg="white", fg="black"
) -> Image.Image:
    f = font(size)
    height = 30 + len(lines) * (size + 14)
    img = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((24, 20 + i * (size + 14)), line, font=f, fill=fg)
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def manual_pdf() -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT / "manual.pdf"), pagesize=A4, title="Manual de Aurora")
    story = [Paragraph("Manual de Aurora", styles["Title"]), Spacer(1, 12)]
    plans = Table(
        [
            ["Plan", "Facturas/mes", "Usuarios", "Precio"],
            ["Básico", "100", "1", "9 €"],
            ["Profesional", "1 000", "5", "29 €"],
            ["Empresa", "Sin límite", "Sin límite", "79 €"],
        ],
        hAlign="LEFT",
    )
    plans.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    story += [Paragraph("Planes", styles["Heading1"]), plans, Spacer(1, 12)]
    for i, fact in enumerate(FACTS):
        if i and i % 6 == 0:
            story.append(PageBreak())
        story += [
            Paragraph(fact["title"], styles["Heading2"]),
            Paragraph(fact["body"], styles["BodyText"]),
            Spacer(1, 8),
        ]
    doc.build(story)


def scanned_pdf() -> None:
    """Three facts rendered to images and put in a PDF with no text layer."""
    pdf = canvas.Canvas(str(OUT / "manual_escaneado.pdf"), pagesize=A4)
    for fact in (FACTS[15], FACTS[16], FACTS[28]):
        words = fact["body"].split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) > 52:
                lines.append(cur)
                cur = ""
            cur += w + " "
        lines.append(cur)
        img = text_image([fact["title"], ""] + lines, size=30, width=1000)
        pdf.drawImage(ImageReader(img), 30, 400, width=535, height=535 * img.height / img.width)
        pdf.showPage()
    pdf.save()


def informe_docx() -> None:
    doc = Document()
    doc.add_heading("Informe de facturación", 0)
    for fact in FACTS[:5]:
        doc.add_heading(fact["title"], 2)
        doc.add_paragraph(fact["body"])
    diagram = text_image(
        ["Flujo de cobro", "Emitida  ->  Enviada  ->  Vencida  ->  Cobrada"],
        34,
        900,
        bg="#EEF3FF",
        fg="#112244",
    )
    doc.add_paragraph("Figura 1. Estados de una factura.")
    doc.add_picture(io.BytesIO(png_bytes(diagram)), width=Inches(5.5))
    table = doc.add_table(rows=3, cols=3)
    for r, row in enumerate(
        [
            ["Mes", "Facturas", "Importe"],
            ["Enero", "412", "18 300 €"],
            ["Febrero", "388", "17 950 €"],
        ]
    ):
        for c, cell in enumerate(row):
            table.cell(r, c).text = cell
    doc.save(OUT / "informe.docx")


def ventas_xlsx() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ventas"
    ws.append(["Mes", "Facturas", "Importe"])
    for row in [("Enero", 412, 18300), ("Febrero", 388, 17950), ("Marzo", 455, 21200)]:
        ws.append(row)
    ws2 = wb.create_sheet("Clientes")
    ws2.append(["Cliente", "NIF", "País"])
    for row in [
        ("Talleres Norte SL", "B12345678", "España"),
        ("Studio Verde", "FR12345678901", "Francia"),
    ]:
        ws2.append(row)
    wb.save(OUT / "ventas.xlsx")


def presentacion_pptx() -> None:
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Aurora: hoja de ruta"
    s.placeholders[1].text = "Conciliación bancaria\nApp móvil\nFacturae 3.2.2"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Arquitectura"
    diagram = text_image(
        ["Cliente  ->  API v2  ->  Base de datos", "Webhook invoice.paid -> ERP"],
        34,
        900,
        bg="#FFF4E5",
        fg="#442200",
    )
    s2.shapes.add_picture(
        io.BytesIO(png_bytes(diagram)), PInches(0.5), PInches(2), width=PInches(9)
    )
    prs.save(OUT / "presentacion.pptx")


def captura_png() -> None:
    img = text_image(
        [
            "Aurora - Nueva factura",
            "",
            "ERR_4012: el NIF del cliente no es válido",
            "Revise el formato e inténtelo de nuevo.",
        ],
        30,
        900,
        bg="#FFEDED",
        fg="#7A0000",
    )
    img.save(OUT / "captura_error.png")


def small_files() -> None:
    (OUT / "notas.md").write_text(
        "# Notas de la reunión\n\n- Revisar el límite de 5 000 filas al importar.\n- Probar `aurora-cli sync`.\n",
        encoding="utf-8",
    )
    (OUT / "ejemplo.py").write_text(
        '"""Cliente mínimo de la API de Aurora."""\nimport httpx\n\n\ndef crear_factura(token: str, datos: dict) -> str:\n'
        '    r = httpx.post("https://api.aurora.example/v2/invoices", json=datos,\n'
        '                   headers={"Authorization": f"Bearer {token}"})\n    return r.json()["invoice_id"]\n',
        encoding="utf-8",
    )
    body = "".join(f"<h2>{f['title']}</h2><p>{f['body']}</p>" for f in FACTS[5:9])
    (OUT / "pagina.html").write_text(
        "<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Ayuda de Aurora</title></head><body>"
        "<nav>Inicio | Precios | Contacto</nav><main><h1>Centro de ayuda</h1>" + body + "</main>"
        "<footer>© Aurora</footer></body></html>",
        encoding="utf-8",
    )


if __name__ == "__main__":
    manual_pdf()
    scanned_pdf()
    informe_docx()
    ventas_xlsx()
    presentacion_pptx()
    captura_png()
    small_files()
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:28} {p.stat().st_size:>8} B")
