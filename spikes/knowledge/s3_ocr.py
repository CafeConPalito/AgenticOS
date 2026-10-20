"""S3: RapidOCR (ONNX) on Spanish screenshots and scanned pages."""

import sys
import time

import pypdfium2 as pdfium
from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

sys.stdout.reconfigure(encoding="utf-8")
variant = sys.argv[1] if len(sys.argv) > 1 else "latin"
if variant == "default":
    engine = RapidOCR()
else:
    engine = RapidOCR(
        params={
            "Rec.lang_type": LangRec.LATIN,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
        }
    )


def run(label, img):
    t = time.perf_counter()
    res = engine(img)
    dt = time.perf_counter() - t
    txt = " ".join(res.txts) if res.txts else ""
    print(f"[{variant}] {label}: {dt:.2f}s -> {txt}")


run("captura_error.png", "corpus/captura_error.png")
pdf = pdfium.PdfDocument("corpus/manual_escaneado.pdf")
for i in range(len(pdf)):
    img = pdf[i].render(scale=2).to_numpy()
    run(f"escaneado p{i + 1}", img)
