"""Open a page in headless Edge and print the value of an expression once its promise resolves.

usage: cdp_eval.py <url> <expression>
Used by the S6 probe: the page sets `window.result` (a promise) and this prints what it gives.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9333


async def main(url: str, expression: str) -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = subprocess.Popen(
            [
                EDGE,
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-port={PORT}",
                f"--user-data-dir={profile}",
                url,
            ]
        )
        try:
            for _ in range(50):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
                        pages = [p for p in json.load(r) if p["type"] == "page"]
                    if pages:
                        break
                except OSError:
                    pass
                time.sleep(0.2)
            async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
                await asyncio.sleep(1)
                await ws.send(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": expression,
                                "awaitPromise": True,
                                "returnByValue": True,
                            },
                        }
                    )
                )
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == 1:
                        print(msg["result"]["result"].get("value", msg))
                        return
        finally:
            proc.terminate()
            proc.wait()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
