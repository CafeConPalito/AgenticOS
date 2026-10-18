"""S6: describe images with llama-server (CPU) + a vision GGUF. Usage: uv run s6_vision.py qwen3.5-2b [threads]"""

import base64
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
from images_expected import EXPECTED

sys.stdout.reconfigure(encoding="utf-8")

name = sys.argv[1]
threads = sys.argv[2] if len(sys.argv) > 2 else "6"
d = Path("models") / name
model = next(p for p in d.glob("*.gguf") if "mmproj" not in p.name)
mmproj = next(d.glob("mmproj*.gguf"))
exe = Path("models/llama.cpp/bin/llama-server.exe")
port = 8089
t0 = time.perf_counter()
proc = subprocess.Popen(
    [
        str(exe),
        "-m",
        str(model),
        "--mmproj",
        str(mmproj),
        "-c",
        "4096",
        "-t",
        threads,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-webui",
        "-ngl",
        "0",
        "--jinja",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
)
base = f"http://127.0.0.1:{port}"
for _ in range(240):
    try:
        if httpx.get(base + "/health", timeout=2).status_code == 200:
            break
    except Exception:
        pass
    if proc.poll() is not None:
        print("server exited:", proc.stdout.read()[-1500:])
        sys.exit(1)
    time.sleep(1)
print(
    f"### {name} (model {model.stat().st_size / 1e9:.2f} GB + mmproj {mmproj.stat().st_size / 1e9:.2f} GB, {threads} threads) ready in {time.perf_counter() - t0:.0f}s"
)
PROMPT = "Describe esta imagen en español de forma breve y precisa (máximo 4 frases). Incluye todo el texto, los números y los datos que aparezcan."
ps = psutil.Process(proc.pid)
peak = 0
total_hits = total_kw = 0
times = []
for img, kws in EXPECTED.items():
    b64 = base64.b64encode(Path("corpus/images", img).read_bytes()).decode()
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                ],
            }
        ],
        "max_tokens": 300,
        "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t = time.perf_counter()
    r = httpx.post(base + "/v1/chat/completions", json=body, timeout=600).json()
    dt = time.perf_counter() - t
    times.append(dt)
    peak = max(peak, ps.memory_info().rss)
    text = (r.get("choices") or [{}])[0].get("message", {}).get("content", "") or str(r)[:300]
    hits = [k for k in kws if k in text.lower()]
    total_hits += len(hits)
    total_kw += len(kws)
    u = r.get("usage", {})
    print(
        f"- {img}: {dt:.1f}s tokens(in/out)={u.get('prompt_tokens')}/{u.get('completion_tokens')} hits={len(hits)}/{len(kws)}\n    {text.strip()[:420]}"
    )
print(
    f"=> mean {sum(times) / len(times):.1f}s/image, keyword recall {total_hits}/{total_kw}, server peak RSS {peak / 1e9:.2f} GB"
)
proc.terminate()
try:
    proc.wait(10)
except Exception:
    proc.kill()
