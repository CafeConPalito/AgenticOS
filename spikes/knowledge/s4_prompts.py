import json
import sys

from huggingface_hub import hf_hub_download, list_repo_files

sys.stdout.reconfigure(encoding="utf-8")
files = list_repo_files("google/embeddinggemma-2")
print([f for f in files if f.endswith(".json") or f.endswith(".md")])
for f in ("config_sentence_transformers.json",):
    if f in files:
        print(
            json.dumps(
                json.load(open(hf_hub_download("google/embeddinggemma-2", f))),
                ensure_ascii=False,
                indent=1,
            )[:1800]
        )
readme = open(hf_hub_download("google/embeddinggemma-2", "README.md"), encoding="utf-8").read()
import re

for m in re.finditer(r"(task:|title:|prompt_name|truncate|Matryoshka|MRL|dimension)", readme):
    s = max(0, m.start() - 100)
    print("…", readme[s : m.start() + 220].replace("\n", " "), "\n")
    break
i = readme.find("prompt")
print(readme[i - 300 : i + 900] if i > 0 else "no 'prompt' in README")
