import hashlib
import json
import sys
from pathlib import Path

import httpx
from huggingface_hub import HfApi

sys.stdout.reconfigure(encoding="utf-8")
cat = json.load(open("out/catalog.json"))
for key in ("e5-small", "gemma2", "bge-m3"):
    e = cat[key]
    for f in e["files"]:
        if f["lfs_sha256"] is None:
            r = httpx.get(
                f"https://huggingface.co/{e['repo']}/resolve/{e['revision']}/{f['name']}",
                follow_redirects=True,
                timeout=60,
            )
            print(
                key,
                f["name"],
                "pinned == tested:",
                hashlib.sha256(r.content).hexdigest() == f["sha256"],
            )
models = Path(".venv/Lib/site-packages/rapidocr/models")
expect = {
    "PP-OCRv6_det_small.onnx": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    "latin_PP-OCRv5_rec_mobile.onnx": "b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a",
}
for name, sha in expect.items():
    data = (models / name).read_bytes()
    print("ocr", name, len(data), "sha ok:", hashlib.sha256(data).hexdigest() == sha)
api = HfApi()
for repo in ("RapidAI/RapidOCR",):
    try:
        files = api.list_repo_files(repo)
        print(
            repo,
            "files:",
            len(files),
            [
                f
                for f in files
                if "latin_PP-OCRv5_rec_mobile" in f
                or f.endswith("PP-OCRv6_det_small.onnx")
                or "cls_mobile" in f
            ][:6],
        )
    except Exception as e:
        print(repo, "ERR", type(e).__name__, str(e)[:100])
