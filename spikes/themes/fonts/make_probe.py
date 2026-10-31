"""Phase 22, spike S1: a page telling which families Chromium (Edge, WebView2) paints by name.

cargo run --release -q | tail -n +3 > families.txt
python make_probe.py families.txt > probe.html
msedge --headless=new --disable-gpu --dump-dom file:///.../probe.html
"""

import json
import sys
from pathlib import Path

PAGE = """<!doctype html><meta charset=utf-8><body><pre id=out></pre><script>
const fams = FAMILIES;
const c = document.createElement('canvas').getContext('2d');
const text = 'mmmmmmmmmmlli WQ@#0123 Agentic OS';
const w = f => { c.font = '32px ' + f; return c.measureText(text).width };
const missing = fams.filter(f => { const q = '"' + f + '"';
  return w(q + ', monospace') === w('monospace') && w(q + ', serif') === w('serif') });
document.getElementById('out').textContent =
  'TOTAL ' + fams.length + ' MISSING ' + missing.length + ': ' + missing.join(' | ');
</script>"""

families = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
print(PAGE.replace("FAMILIES", json.dumps(families)))
