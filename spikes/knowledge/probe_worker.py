"""S1/S8: a PyInstaller probe that relaunches itself as a low-priority worker process.

Modes:  probe.exe            -> parent: spawn `probe.exe --worker`, run the ops, print timings
        probe.exe --worker   -> worker: JSON lines on stdin, JSON lines on stdout
Variant (env PROBE_LIBS): "none" | "noocr" | "all" -- which heavy libraries the ops may use.
"""

import json
import os
import subprocess
import sys
import time

OPS_LIBS = os.environ.get("PROBE_LIBS", "all")


def worker():
    import psutil

    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    out = sys.stdout

    def send(o):
        out.write(json.dumps(o, ensure_ascii=False) + "\n")
        out.flush()

    send(
        {
            "op": "ready",
            "pid": os.getpid(),
            "nice": psutil.Process().nice(),
            "frozen": getattr(sys, "frozen", False),
        }
    )
    for line in sys.stdin:
        req = json.loads(line)
        t = time.perf_counter()
        op = req["op"]
        res = {}
        try:
            if op == "convert":
                from markitdown import MarkItDown

                res["chars"] = len(
                    MarkItDown(enable_plugins=False)
                    .convert(req["path"], keep_data_uris=True)
                    .text_content
                )
            elif op == "pdf":
                import pypdfium2 as pdfium

                pdf = pdfium.PdfDocument(req["path"])
                res["pages"] = len(pdf)
                res["chars"] = sum(len(p.get_textpage().get_text_range()) for p in pdf)
            elif op == "ocr":
                from rapidocr import RapidOCR

                r = RapidOCR()(req["path"])
                res["text"] = " ".join(r.txts)[:80]
            elif op == "embed":
                import numpy as np
                import onnxruntime as ort
                from tokenizers import Tokenizer

                s = ort.InferenceSession(req["model"], providers=["CPUExecutionProvider"])
                tk = Tokenizer.from_file(req["tok"])
                tk.enable_padding(pad_id=1, pad_token="<pad>")
                enc = tk.encode_batch(["passage: " + x for x in req["texts"]])
                ids = np.array([e.ids for e in enc], dtype=np.int64)
                o = s.run(
                    None,
                    {
                        "input_ids": ids,
                        "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
                        "token_type_ids": np.zeros_like(ids),
                    },
                )
                res["shape"] = list(o[0].shape)
            elif op == "quit":
                return
            res["ok"] = True
        except Exception as e:  # noqa: BLE001
            res["ok"] = False
            res["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        res.update(op=op, seconds=round(time.perf_counter() - t, 2))
        send(res)


def parent():
    import psutil

    flags = 0x00004000 | 0x08000000  # BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
    cmd = (
        [sys.executable, "--worker"]
        if getattr(sys, "frozen", False)
        else [sys.executable, __file__, "--worker"]
    )
    t = time.perf_counter()
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=flags,
    )
    print(
        "worker:",
        p.stdout.readline().strip(),
        f"(ready in {time.perf_counter() - t:.1f}s)",
        flush=True,
    )
    d = "D:/agentic_os/spikes/knowledge/"
    ops = [
        {"op": "convert", "path": d + "corpus/informe.docx"},
        {"op": "pdf", "path": d + "corpus/manual.pdf"},
    ]
    if OPS_LIBS == "all":
        ops.append({"op": "ocr", "path": d + "corpus/captura_error.png"})
    if OPS_LIBS in ("all", "noocr"):
        ops.append(
            {
                "op": "embed",
                "model": d + "models/e5-small/onnx/model_quantized.onnx",
                "tok": d + "models/e5-small/tokenizer.json",
                "texts": ["hola mundo"] * 8,
            }
        )
    for o in ops:
        p.stdin.write(json.dumps(o) + "\n")
        p.stdin.flush()
        print(p.stdout.readline().strip(), flush=True)
    print(
        "worker priority class (psutil nice):",
        psutil.Process(p.pid).nice(),
        "| parent:",
        psutil.Process().nice(),
    )
    p.stdin.write(json.dumps({"op": "quit"}) + "\n")
    p.stdin.flush()
    p.wait(10)


if __name__ == "__main__":
    worker() if "--worker" in sys.argv else parent()
