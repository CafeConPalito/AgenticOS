"""Test images for the vision spikes (S6/S7) and the keywords a good description must mention."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("corpus/images")
OUT.mkdir(parents=True, exist_ok=True)
F = lambda s: ImageFont.truetype("C:/Windows/Fonts/arial.ttf", s)
FB = lambda s: ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", s)


def bars():
    im = Image.new("RGB", (900, 560), "white")
    d = ImageDraw.Draw(im)
    d.text((40, 20), "Facturas emitidas por mes", font=FB(30), fill="black")
    data = [("Enero", 412, "#3b6fd4"), ("Febrero", 388, "#3b6fd4"), ("Marzo", 455, "#d4553b")]
    d.line((100, 480, 860, 480), fill="black", width=3)
    d.line((100, 100, 100, 480), fill="black", width=3)
    for i, (m, v, c) in enumerate(data):
        x = 170 + i * 230
        h = int(v / 500 * 360)
        d.rectangle((x, 480 - h, x + 140, 480), fill=c)
        d.text((x + 35, 480 - h - 36), str(v), font=FB(28), fill="black")
        d.text((x + 20, 495), m, font=F(26), fill="black")
    im.save(OUT / "grafico_barras.png")


def flow():
    im = Image.new("RGB", (1000, 360), "#f7f7fb")
    d = ImageDraw.Draw(im)
    names = ["Emitida", "Enviada", "Vencida", "Cobrada"]
    for i, n in enumerate(names):
        x = 40 + i * 245
        d.rounded_rectangle((x, 130, x + 180, 220), 14, fill="#dbe7ff", outline="#244a9a", width=3)
        d.text((x + 90, 175), n, font=FB(28), fill="#112244", anchor="mm")
        if i < 3:
            d.line((x + 182, 175, x + 243, 175), fill="#244a9a", width=4)
            d.polygon([(x + 243, 175), (x + 228, 165), (x + 228, 185)], fill="#244a9a")
    d.text((500, 60), "Estados de una factura", font=FB(32), fill="black", anchor="mm")
    d.text(
        (500, 300),
        "Un recordatorio automático se envía 3 días antes del vencimiento",
        font=F(24),
        fill="#444",
        anchor="mm",
    )
    im.save(OUT / "diagrama_flujo.png")


def table():
    im = Image.new("RGB", (900, 330), "white")
    d = ImageDraw.Draw(im)
    rows = [
        ["Plan", "Facturas/mes", "Usuarios", "Precio"],
        ["Básico", "100", "1", "9 €"],
        ["Profesional", "1 000", "5", "29 €"],
        ["Empresa", "Sin límite", "Sin límite", "79 €"],
    ]
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            x, y = 30 + c * 215, 20 + r * 75
            d.rectangle(
                (x, y, x + 215, y + 75),
                outline="black",
                width=2,
                fill="#e8e8e8" if r == 0 else "white",
            )
            d.text((x + 14, y + 20), cell, font=FB(28) if r == 0 else F(28), fill="black")
    im.save(OUT / "tabla_planes.png")


def org():
    im = Image.new("RGB", (900, 420), "white")
    d = ImageDraw.Draw(im)

    def box(x, y, t, c):
        d.rounded_rectangle((x, y, x + 220, y + 70), 10, fill=c, outline="black", width=2)
        d.text((x + 110, y + 35), t, font=FB(24), fill="black", anchor="mm")

    box(340, 30, "Dirección", "#ffe9b8")
    box(60, 220, "Ventas", "#cfe9d4")
    box(340, 220, "Soporte", "#cfe9d4")
    box(620, 220, "Finanzas", "#cfe9d4")
    for x in (170, 450, 730):
        d.line((450, 100, 450, 160), fill="black", width=3)
        d.line((170, 160, 730, 160), fill="black", width=3)
        d.line((x, 160, x, 220), fill="black", width=3)
    d.text((450, 370), "Organigrama de la empresa", font=F(26), fill="#333", anchor="mm")
    im.save(OUT / "organigrama.png")


bars()
flow()
table()
org()
import shutil

shutil.copy("corpus/captura_error.png", OUT / "captura_error.png")
print(sorted(p.name for p in OUT.iterdir()))
