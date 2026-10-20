import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

from huggingface_hub import hf_hub_download

sys.stdout.reconfigure(encoding="utf-8")
rel = json.load(
    urllib.request.urlopen("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1")
)[0]
asset = next(a for a in rel["assets"] if a["name"].endswith("bin-win-cpu-x64.zip"))
dest = Path("models/llama.cpp")
dest.mkdir(parents=True, exist_ok=True)
zpath = dest / asset["name"]
urllib.request.urlretrieve(asset["browser_download_url"], zpath)
sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
print(
    "llama.cpp",
    rel["tag_name"],
    asset["name"],
    "sha256",
    sha,
    "published digest:",
    asset.get("digest"),
    "MATCH" if asset.get("digest", "").endswith(sha) else "NO-DIGEST-MATCH",
    flush=True,
)
zipfile.ZipFile(zpath).extractall(dest / "bin")
print("extracted:", sorted(p.name for p in (dest / "bin").iterdir())[:40], flush=True)
JOBS = {
    "qwen3.5-2b": ("unsloth/Qwen3.5-2B-GGUF", ["Qwen3.5-2B-Q4_K_M.gguf", "mmproj-F16.gguf"]),
    "qwen3.5-4b": ("unsloth/Qwen3.5-4B-GGUF", ["Qwen3.5-4B-Q4_K_M.gguf", "mmproj-F16.gguf"]),
    "gemma4-e2b": (
        "unsloth/gemma-4-E2B-it-GGUF",
        ["gemma-4-E2B-it-Q4_K_M.gguf", "mmproj-F16.gguf"],
    ),
}
for name, (repo, files) in JOBS.items():
    for f in files:
        hf_hub_download(repo, f, local_dir=f"models/{name}")
        print("ok", name, f, flush=True)
print("DONE")
