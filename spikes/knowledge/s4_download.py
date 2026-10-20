import sys

from huggingface_hub import hf_hub_download

sys.stdout.reconfigure(encoding="utf-8")
JOBS = {
    "e5-small": (
        "Xenova/multilingual-e5-small",
        ["onnx/model_quantized.onnx", "tokenizer.json", "config.json"],
    ),
    "gemma2": (
        "onnx-community/embeddinggemma-2-ONNX",
        [
            "onnx/model_quantized.onnx",
            "onnx/model_quantized.onnx_data",
            "onnx/model_q4.onnx",
            "onnx/model_q4.onnx_data",
            "tokenizer.json",
            "config.json",
        ],
    ),
    "bge-m3": ("Xenova/bge-m3", ["onnx/model_quantized.onnx", "tokenizer.json", "config.json"]),
}
for name, (repo, files) in JOBS.items():
    for f in files:
        p = hf_hub_download(repo, f, local_dir=f"models/{name}")
        print("ok", name, f, flush=True)
print("DONE")
