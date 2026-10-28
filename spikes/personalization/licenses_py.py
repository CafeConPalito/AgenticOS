"""S5: licenses of the backend's installed runtime distributions (no dev group)."""

import re
import sys
from collections import defaultdict
from importlib import metadata


def license_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr.strip()
    classifiers = [
        c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")
    ]
    if classifiers:
        return " / ".join(sorted(set(classifiers)))
    raw = (meta.get("License") or "").strip()
    return re.sub(r"\s+", " ", raw)[:60] or "UNKNOWN"


groups: dict[str, list[str]] = defaultdict(list)
for dist in metadata.distributions():
    groups[license_of(dist)].append(dist.metadata["Name"])
for lic, names in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f"{lic}\t{len(names)}\t{', '.join(sorted(names)) if len(names) <= 8 else ''}")
print("TOTAL", sum(len(v) for v in groups.values()), file=sys.stderr)
