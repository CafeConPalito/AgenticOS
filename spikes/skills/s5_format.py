"""Phase 17 · spike S5: what real SKILL.md files look like.

Downloads the 100 most installed skills (open rankings of LinklyAI/best-skills, skills.sh rows)
through skills.sh's public download route, caches them under spikes/out/skills-corpus/ and
reports: frontmatter quirks (extra fields, multi-line values, BOM, CRLF, colons, missing
name/description, name != folder), sizes (SKILL.md tokens, files, total) and kinds of support
files (executables included).

Usage: uv run python skills/s5_format.py [--offline]      (from spikes/)
"""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "17-skills" / "evidencias"
CORPUS = REPO / "spikes" / "out" / "skills-corpus"
RANKINGS = [
    "https://raw.githubusercontent.com/LinklyAI/best-skills/main/data/latest/rankings/" + name
    for name in ("top-installs.csv", "best-100.csv", "official-100.csv")
]
DOWNLOAD = "https://skills.sh/api/download/{source}/{slug}"
EXECUTABLE = {".py", ".sh", ".ps1", ".bat", ".cmd", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl"}
FRONT = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*(\r?\n|$)", re.S)


def fetch_corpus() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": "agentic-os-spike"}, timeout=20) as client:
        rows = [
            row for url in RANKINGS for row in csv.DictReader(io.StringIO(client.get(url).text))
        ]
        for row in rows:
            source = row.get("source_skillssh") or ""
            key = row.get("skill_key") or ""
            if row.get("platform") != "skills.sh" or not source:
                continue
            slug = key.rsplit("/", 1)[-1]
            target = CORPUS / f"{source.replace('/', '__')}__{slug}.json"
            if target.exists():
                continue
            response = client.get(DOWNLOAD.format(source=source, slug=slug))
            if response.is_success:
                data = response.json()
                keys = ("rank", "installs_skillssh", "category")
                data["_ranking"] = {k: row.get(k) for k in keys}
                target.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
            print(response.status_code, source, slug)
            time.sleep(0.2)


def analyse() -> dict:
    quirks: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    md_tokens, files_count, totals = [], [], []
    with_exec = 0
    examples: dict[str, list[str]] = {}
    skills = sorted(CORPUS.glob("*.json"))
    for path in skills:
        data = json.loads(path.read_text("utf-8"))
        files = {f["path"]: f["contents"] for f in data.get("files", [])}
        skill_md = next((v for k, v in files.items() if k.lower() == "skill.md"), None)
        name = path.stem.rsplit("__", 1)[-1]
        if skill_md is None:
            quirks["no SKILL.md at root"] += 1
            continue
        if skill_md.startswith("﻿"):
            quirks["BOM"] += 1
            skill_md = skill_md[1:]
        if "\r\n" in skill_md:
            quirks["CRLF"] += 1
        match = FRONT.match(skill_md)
        if not match:
            quirks["no frontmatter"] += 1
            continue
        raw = match.group(1)
        try:
            meta = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            quirks["YAML error"] += 1
            examples.setdefault("YAML error", []).append(f"{path.stem}: {str(exc)[:120]}")
            continue
        for key in meta:
            fields[str(key)] += 1
        if not meta.get("name"):
            quirks["missing name"] += 1
        elif str(meta["name"]) != name:
            quirks["name != folder/slug"] += 1
            examples.setdefault("name != folder/slug", []).append(f"{name} -> {meta['name']}")
        description = meta.get("description")
        if not description:
            quirks["missing description"] += 1
        else:
            if len(str(description)) > 1024:
                quirks["description > 1024 chars"] += 1
            if re.search(r"^description:\s*[|>]", raw, re.M):
                quirks["multi-line description"] += 1
        if re.search(r"^description:\s*[^\"'|>].*:\s", raw, re.M):
            quirks["unquoted colon in description"] += 1
        md_tokens.append(len(skill_md) // 4)
        files_count.append(len(files))
        totals.append(sum(len(v.encode("utf-8")) for v in files.values()))
        if len(skill_md.encode("utf-8")) > 24 * 1024:
            quirks["SKILL.md > 24 KB (agy limit)"] += 1
        has_exec = False
        for file in files:
            suffix = Path(file).suffix.lower() or "(none)"
            kinds[suffix] += 1
            if suffix in EXECUTABLE or files[file].startswith("#!"):
                has_exec = True
        with_exec += has_exec

    def spread(values: list[int]) -> dict:
        if not values:
            return {}
        values = sorted(values)
        return {
            "median": statistics.median(values),
            "p90": values[int(len(values) * 0.9) - 1],
            "max": values[-1],
        }

    return {
        "skills": len(skills),
        "quirks": dict(quirks.most_common()),
        "examples": {k: v[:5] for k, v in examples.items()},
        "frontmatter_fields": dict(fields.most_common()),
        "skill_md_tokens": spread(md_tokens),
        "files_per_skill": spread(files_count),
        "bytes_per_skill": spread(totals),
        "with_executables": with_exec,
        "file_kinds": dict(kinds.most_common(15)),
    }


def main() -> None:
    if "--offline" not in sys.argv:
        fetch_corpus()
    report = analyse()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"s5-format-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("evidence:", out)


if __name__ == "__main__":
    main()
