import sys

from huggingface_hub import HfApi

sys.stdout.reconfigure(encoding="utf-8")
api = HfApi()
for q in ("Qwen3.5 GGUF", "gemma-4 GGUF"):
    print("##", q)
    for m in api.list_models(search=q, sort="downloads", limit=16):
        print(f"  {m.id:60} downloads={m.downloads}")
