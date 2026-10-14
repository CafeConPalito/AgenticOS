"""Status line command for the quota probe: appends stdin to the file given as argv[1]."""

import sys

data = sys.stdin.read().strip()
if data:
    with open(sys.argv[1], "a", encoding="utf-8") as f:
        f.write(data.replace("\n", " ") + "\n")
