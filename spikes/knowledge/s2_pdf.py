"""S2: pypdfium2 as the PDF converter: text per page, scanned detection, page render, embedded images."""

import time

import pypdfium2 as pdfium
import pypdfium2.raw as raw

for name in ("manual.pdf", "manual_escaneado.pdf"):
    t = time.perf_counter()
    pdf = pdfium.PdfDocument(f"corpus/{name}")
    print(f"## {name}: {len(pdf)} pages")
    for i in range(len(pdf)):
        page = pdf[i]
        text = page.get_textpage().get_text_range().strip()
        imgs = list(page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]))
        print(
            f"  p{i + 1}: text={len(text)} chars, image_objects={len(imgs)}, scanned={len(text) < 20 and bool(imgs)}"
        )
        if i == 0 and name == "manual.pdf":
            print(
                "  --- sample p1 text:\n" + "\n".join("   | " + l for l in text.splitlines()[:14])
            )
        if name == "manual_escaneado.pdf" and i == 0:
            bmp = page.render(scale=1.5).to_pil()
            bmp.save("out/escaneado_p1_render.png")
            print("  rendered p1 ->", bmp.size)
            for o in imgs:
                pil = o.get_bitmap().to_pil()
                print("  embedded image:", pil.size)
    print(f"  total {time.perf_counter() - t:.2f}s")
