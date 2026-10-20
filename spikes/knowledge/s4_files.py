import sys

from huggingface_hub import HfApi

sys.stdout.reconfigure(encoding="utf-8")
api = HfApi()
for repo in (
    "onnx-community/embeddinggemma-2-ONNX",
    "onnx-community/embeddinggemma-300m-ONNX",
    "Xenova/multilingual-e5-small",
    "Xenova/bge-m3",
    "google/embeddinggemma-2",
):
    info = api.model_info(repo, files_metadata=True)
    lic = info.card_data.get("license") if info.card_data else None
    print(f"## {repo}  gated={info.gated}  license={lic}")
    for s in info.siblings:
        if (
            s.rfilename.endswith((".onnx", ".onnx_data", "tokenizer.json", "config.json"))
            or "dense" in s.rfilename.lower()
        ):
            print(f"   {(s.size or 0) / 1e6:8.1f} MB  {s.rfilename}")
