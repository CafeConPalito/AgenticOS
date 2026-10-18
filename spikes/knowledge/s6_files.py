import sys

import httpx
from huggingface_hub import HfApi

sys.stdout.reconfigure(encoding="utf-8")
api = HfApi()
for repo in (
    "unsloth/Qwen3.5-2B-GGUF",
    "unsloth/Qwen3.5-4B-GGUF",
    "unsloth/gemma-4-E2B-it-GGUF",
    "unsloth/gemma-4-E4B-it-GGUF",
    "google/gemma-4-E4B-it-qat-q4_0-gguf",
):
    info = api.model_info(repo, files_metadata=True)
    lic = info.card_data.get("license") if info.card_data else None
    print(f"## {repo} gated={info.gated} license={lic}")
    for s in info.siblings:
        n = s.rfilename
        if n.endswith(".gguf") and (
            "Q4_K_M" in n or "mmproj" in n.lower() or "q4_0" in n.lower() or "Q4_K_XL" in n
        ):
            print(f"   {(s.size or 0) / 1e6:8.0f} MB  {n}")
r = httpx.get("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest", timeout=30).json()
print("llama.cpp", r.get("tag_name"))
for a in r.get("assets", []):
    if "win" in a["name"] and (
        "cpu" in a["name"] or "avx" in a["name"] or "vulkan" in a["name"] or "cuda" in a["name"]
    ):
        print(f"   {a['size'] / 1e6:7.0f} MB  {a['name']}")
