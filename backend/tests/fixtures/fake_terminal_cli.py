"""A CLI opened by hand (phase 23): writes how it was started to `terminal-seen.json` in its
folder, then waits like an interactive CLI until `exit` or the end of its input."""

import json
import os
import sys
from pathlib import Path

seen = {
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "config_dir": os.environ.get("CLAUDE_CONFIG_DIR"),
}
Path("terminal-seen.json").write_text(json.dumps(seen), encoding="utf-8")
print("listo", flush=True)
try:
    for line in sys.stdin:
        if line.strip() == "exit":
            break
        print(f"eco: {line.strip()}", flush=True)
except KeyboardInterrupt:
    pass
