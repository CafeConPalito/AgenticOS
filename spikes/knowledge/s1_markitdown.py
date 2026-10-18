"""S1: what does MarkItDown give for each corpus file?"""

import re
import time
from pathlib import Path

from markitdown import MarkItDown

md = MarkItDown(enable_plugins=False)
for path in sorted(Path("corpus").iterdir()):
    t = time.perf_counter()
    try:
        r = md.convert(str(path), keep_data_uris=True)
        text = r.text_content
    except Exception as e:  # noqa: BLE001
        print(f"## {path.name}: ERROR {type(e).__name__}: {str(e)[:200]}")
        continue
    dt = time.perf_counter() - t
    (Path("out") / f"{path.name}.md").write_text(text, encoding="utf-8")
    uris = len(re.findall(r"!\[[^\]]*\]\(data:", text))
    heads = len(re.findall(r"^#{1,6} ", text, re.M))
    tables = len(re.findall(r"^\|", text, re.M))
    pages = len(re.findall(r"page", text, re.I))
    print(
        f"## {path.name}: {len(text)} chars, {dt:.2f}s, headings={heads}, table_rows={tables}, data_uris={uris}"
    )
