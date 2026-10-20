import sys

from huggingface_hub import HfApi

sys.stdout.reconfigure(encoding="utf-8")
api = HfApi()
for q in ("embeddinggemma", "multilingual-e5-small", "bge-m3"):
    print(f"## search: {q}")
    for m in api.list_models(search=q, sort="downloads", limit=14):
        tags = [t for t in (m.tags or []) if t in ("onnx", "gguf")]
        print(f"  {m.id:55} gated={m.gated!s:6} downloads={m.downloads} {tags}")
