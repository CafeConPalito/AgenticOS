import sys
import time

import httpx
import trafilatura
from markitdown import MarkItDown

sys.stdout.reconfigure(encoding="utf-8")
md = MarkItDown(enable_plugins=False)
pages = {"local": open("corpus/pagina.html", encoding="utf-8").read()}
r = httpx.get("https://docs.python.org/3/library/sqlite3.html", timeout=30, follow_redirects=True)
pages["docs.python.org sqlite3"] = r.text
for name, html in pages.items():
    t = time.perf_counter()
    mk = md.convert_stream(
        __import__("io").BytesIO(html.encode()), file_extension=".html"
    ).text_content
    t1 = time.perf_counter() - t
    t = time.perf_counter()
    tr = (
        trafilatura.extract(
            html,
            output_format="markdown",
            include_tables=True,
            include_links=False,
            favor_recall=True,
        )
        or ""
    )
    t2 = time.perf_counter() - t
    print(
        f"## {name}: html={len(html)} chars | markitdown={len(mk)} chars {t1:.2f}s | trafilatura={len(tr)} chars {t2:.2f}s"
    )
    print("  markitdown start:", mk[:160].replace("\n", " ⏎ "))
    print("  trafilatura start:", tr[:160].replace("\n", " ⏎ "))
