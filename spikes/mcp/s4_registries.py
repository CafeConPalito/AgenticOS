"""Phase 18 · spike S4: what do the public MCP server registries offer? (read only, GET)"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import REPO  # noqa: E402

EVIDENCE = REPO / "docs" / "phases" / "18-conexiones-mcp" / "evidencias"
PROBES = {
    "official_list": "https://registry.modelcontextprotocol.io/v0.1/servers?limit=3",
    "official_search": "https://registry.modelcontextprotocol.io/v0.1/servers?search=github&limit=3",
    "official_v0_search": "https://registry.modelcontextprotocol.io/v0/servers?search=github&limit=3",
    "smithery_list": "https://registry.smithery.ai/servers?pageSize=3",
    "smithery_search": "https://registry.smithery.ai/servers?q=github&pageSize=3",
    "glama_list": "https://glama.ai/api/mcp/v1/servers?first=3",
    "glama_search": "https://glama.ai/api/mcp/v1/servers?query=github&first=3",
    "pulsemcp_list": "https://api.pulsemcp.com/v0beta/servers?count_per_page=3",
    "pulsemcp_search": "https://api.pulsemcp.com/v0beta/servers?query=github&count_per_page=3",
    "npm_search": "https://registry.npmjs.org/-/v1/search?text=%40modelcontextprotocol%2Fserver-github&size=1",
    "pypi_json": "https://pypi.org/pypi/mcp-server-fetch/json",
}


def main() -> None:
    out: dict = {}
    with httpx.Client(
        timeout=20, follow_redirects=True, headers={"User-Agent": "agentic-os-spike"}
    ) as c:
        for name, url in PROBES.items():
            started = time.monotonic()
            try:
                r = c.get(url)
            except httpx.HTTPError as error:
                out[name] = {"url": url, "error": f"{type(error).__name__}: {error}"[:200]}
                print(name, "ERROR", out[name]["error"])
                continue
            entry = {
                "url": url,
                "status": r.status_code,
                "seconds": round(time.monotonic() - started, 2),
                "content_type": r.headers.get("content-type"),
                "ratelimit": {
                    k: v
                    for k, v in r.headers.items()
                    if "ratelimit" in k.lower() or k.lower() == "retry-after"
                },
            }
            try:
                data = r.json()
                entry["keys"] = list(data)[:12] if isinstance(data, dict) else f"list[{len(data)}]"
                entry["sample"] = json.dumps(data, ensure_ascii=False)[:1800]
            except ValueError:
                entry["body"] = r.text[:300]
            out[name] = entry
            print(name, r.status_code, entry.get("keys"), entry["ratelimit"])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / f"s4-registries-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", path)


if __name__ == "__main__":
    main()
