"""Phase 14 block 3: the data of the local-model catalog (revision, size and SHA-256 of each
file), computed from the files the spikes downloaded and checked against Hugging Face's own
LFS hashes of the pinned revision. Run: uv run s10_catalog_hashes.py > out/catalog.json"""

import hashlib
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi

sys.stdout.reconfigure(encoding="utf-8")
api = HfApi()
MODELS = Path("models")
ENTRIES = {
    "e5-small": ("Xenova/multilingual-e5-small", "e5-small",
                 ["onnx/model_quantized.onnx", "tokenizer.json", "config.json"]),
    "gemma2": ("onnx-community/embeddinggemma-2-ONNX", "gemma2",
               ["onnx/model_q4.onnx", "onnx/model_q4.onnx_data", "tokenizer.json", "config.json"]),
    "bge-m3": ("Xenova/bge-m3", "bge-m3", ["onnx/model_quantized.onnx", "tokenizer.json", "config.json"]),
    "qwen3.5-2b": ("unsloth/Qwen3.5-2B-GGUF", "qwen3.5-2b", ["Qwen3.5-2B-Q4_K_M.gguf", "mmproj-F16.gguf"]),
    "qwen3.5-4b": ("unsloth/Qwen3.5-4B-GGUF", "qwen3.5-4b", ["Qwen3.5-4B-Q4_K_M.gguf", "mmproj-F16.gguf"]),
    "gemma4-e2b": ("unsloth/gemma-4-E2B-it-GGUF", "gemma4-e2b",
                   ["gemma-4-E2B-it-Q4_K_M.gguf", "mmproj-F16.gguf"]),
}  # fmt: skip


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


out = {}
for key, (repo, folder, files) in ENTRIES.items():
    info = api.model_info(repo, files_metadata=True)
    remote = {s.rfilename: s for s in info.siblings}
    entry = {
        "repo": repo,
        "revision": info.sha,
        "license": (info.card_data or {}).get("license"),
        "files": [],
    }
    for name in files:
        local = MODELS / folder / name
        digest = sha256_of(local)
        lfs = getattr(remote[name], "lfs", None)
        remote_sha = lfs.sha256 if lfs else None
        entry["files"].append(
            {
                "name": name,
                "size": local.stat().st_size,
                "sha256": digest,
                "lfs_sha256": remote_sha,
                "matches_remote": (remote_sha == digest) if remote_sha else None,
            }
        )
        print(
            key,
            name,
            local.stat().st_size,
            digest[:12],
            "remote:",
            (remote_sha or "-")[:12],
            file=sys.stderr,
            flush=True,
        )
    out[key] = entry
print(json.dumps(out, indent=1))
