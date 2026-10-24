"""Phase 17 · spike S3: what each public skills registry offers to a desktop app, without login.

Probes (anonymous GETs only) and stores a trimmed sample of each answer, with status and rate
limit headers, in docs/phases/17-skills/evidencias/s3-registries-<time>.json.

Usage: uv run python skills/s3_registries.py        (from spikes/)
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "17-skills" / "evidencias"
HEADERS = {"User-Agent": "agentic-os-spike"}
LIMIT_HEADERS = ("x-ratelimit", "retry-after")

PROBES = {
    # skills.sh: the documented /api/v1 needs a Vercel OIDC token; its own CLI (npm `skills`)
    # uses these public routes instead.
    "skills_sh_v1_search": "https://skills.sh/api/v1/skills/search?q=code%20review&limit=3",
    "skills_sh_search": "https://skills.sh/api/search?q=code%20review&limit=5",
    "skills_sh_download": "https://skills.sh/api/download/mattpocock/skills/code-review",
    "skills_sh_audit": "https://www.skills.sh/tele/audit?source=mattpocock/skills&skills=code-review",
    # Anthropic's official repository, through the GitHub API (60 requests/hour anonymous)
    "anthropic_list": "https://api.github.com/repos/anthropics/skills/contents/skills",
    "anthropic_tree": "https://api.github.com/repos/anthropics/skills/git/trees/main?recursive=1",
    "anthropic_commit": "https://api.github.com/repos/anthropics/skills/commits/main",
    # SkillsMP: anonymous search with daily and per-minute quotas
    "skillsmp_search": "https://skillsmp.com/api/v1/skills/search?q=code%20review&sort=stars&limit=3",
    # ClawHub: public search, listing by downloads, detail and zip download
    "clawhub_search": "https://clawhub.ai/api/v1/search?q=code%20review&limit=3",
    "clawhub_popular": "https://clawhub.ai/api/v1/skills?limit=3&sort=downloads",
    "clawhub_detail": "https://clawhub.ai/api/v1/skills/self-improving-agent?ownerHandle=pskoett",
    "clawhub_download": "https://clawhub.ai/api/v1/download?slug=self-improving-agent&ownerHandle=pskoett",
    # Open daily rankings aggregated from skills.sh, ClawHub and SkillHub (CC BY 4.0)
    "best_skills_top_installs": "https://raw.githubusercontent.com/LinklyAI/best-skills/main/data/latest/rankings/top-installs.csv",
}


def sample(name: str, response: httpx.Response) -> object:
    kind = response.headers.get("content-type", "")
    if "zip" in kind:
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        return [{"path": i.filename, "size": i.file_size} for i in archive.infolist()]
    if name.endswith("_tree") and response.is_success:
        tree = response.json()["tree"]
        return {
            "entries": len(tree),
            "skill_md": sum(1 for e in tree if e["path"].endswith("SKILL.md")),
            "truncated": response.json().get("truncated"),
        }
    if "csv" in kind or name.startswith("best_skills"):
        lines = response.text.splitlines()
        return {"rows": len(lines) - 1, "head": lines[:4]}
    text = response.text
    try:
        return json.loads(text) if len(text) < 4000 else text[:4000]
    except json.JSONDecodeError:
        return text[:1000]


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report = {}
    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for name, url in PROBES.items():
            started = time.monotonic()
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                report[name] = {"url": url, "error": repr(exc)}
                continue
            report[name] = {
                "url": url,
                "status": response.status_code,
                "ms": round((time.monotonic() - started) * 1000),
                "content_type": response.headers.get("content-type"),
                "limits": {
                    k: v for k, v in response.headers.items() if k.lower().startswith(LIMIT_HEADERS)
                },
                "sample": sample(name, response),
            }
            print(name, response.status_code, report[name]["ms"], "ms")
    out = EVIDENCE / f"s3-registries-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("evidence:", out)


if __name__ == "__main__":
    main()
