# ruff: noqa: E501  (SVG markup and inline HTML are data)
"""S1: prototype of the layered owl set (base owl + accessories) and a preview page.

Writes one SVG per variant and `preview.html` (each owl at 16, 24, 48 and 128 px over a light
and a dark agent color) into the folder given as the first argument.
"""

import sys
from pathlib import Path

BODY, BELLY, EYE, PUPIL, BEAK, LINE = (
    "#8A5A3B",
    "#E9D3B4",
    "#FFFFFF",
    "#1B1B1F",
    "#F2A93B",
    "#3A2416",
)

BASE = f"""
  <path d="M30 34 L34 16 L44 30 Z M98 34 L94 16 L84 30 Z" fill="{BODY}" stroke="{LINE}" stroke-width="3" stroke-linejoin="round"/>
  <ellipse cx="64" cy="74" rx="40" ry="44" fill="{BODY}" stroke="{LINE}" stroke-width="3"/>
  <ellipse cx="64" cy="90" rx="25" ry="26" fill="{BELLY}"/>
  <path d="M52 86 q4 4 8 0 M68 86 q4 4 8 0 M58 98 q4 4 8 0" fill="none" stroke="{BODY}" stroke-width="2" stroke-linecap="round"/>
  <circle cx="48" cy="58" r="15" fill="{EYE}" stroke="{LINE}" stroke-width="3"/>
  <circle cx="80" cy="58" r="15" fill="{EYE}" stroke="{LINE}" stroke-width="3"/>
  <circle cx="50" cy="59" r="7" fill="{PUPIL}"/><circle cx="82" cy="59" r="7" fill="{PUPIL}"/>
  <circle cx="52" cy="56" r="2.2" fill="#fff"/><circle cx="84" cy="56" r="2.2" fill="#fff"/>
  <path d="M58 70 L70 70 L64 80 Z" fill="{BEAK}" stroke="{LINE}" stroke-width="2.5" stroke-linejoin="round"/>
"""

ACCESSORIES = {
    "plain": "",
    "top-hat": f"""<rect x="40" y="22" width="48" height="6" rx="3" fill="#24242B" stroke="{LINE}" stroke-width="2"/>
      <rect x="48" y="0" width="32" height="24" rx="3" fill="#24242B" stroke="{LINE}" stroke-width="2"/>
      <rect x="48" y="16" width="32" height="5" fill="#C0392B"/>""",
    "grad-cap": f"""<path d="M64 6 L104 20 L64 34 L24 20 Z" fill="#1F2A44" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>
      <path d="M100 21 L100 38" stroke="#F2C94C" stroke-width="3"/><circle cx="100" cy="40" r="3.5" fill="#F2C94C"/>""",
    "glasses": """<circle cx="48" cy="58" r="17" fill="none" stroke="#1B1B1F" stroke-width="4"/>
      <circle cx="80" cy="58" r="17" fill="none" stroke="#1B1B1F" stroke-width="4"/>
      <path d="M65 58 h-2" stroke="#1B1B1F" stroke-width="4"/>""",
    "sunglasses": """<path d="M30 50 h36 v8 q0 14 -18 14 q-18 0 -18 -14 Z M62 50 h36 v8 q0 14 -18 14 q-18 0 -18 -14 Z" fill="#14141A" stroke="#14141A" stroke-width="2"/>
      <path d="M36 54 l8 0" stroke="#5A6075" stroke-width="3" stroke-linecap="round"/>""",
    "headphones": f"""<path d="M24 64 q0 -50 40 -50 q40 0 40 50" fill="none" stroke="#2E5BD6" stroke-width="7" stroke-linecap="round"/>
      <rect x="16" y="56" width="16" height="26" rx="7" fill="#2E5BD6" stroke="{LINE}" stroke-width="2"/>
      <rect x="96" y="56" width="16" height="26" rx="7" fill="#2E5BD6" stroke="{LINE}" stroke-width="2"/>""",
    "bow-tie": f"""<path d="M64 114 L48 106 L48 122 Z M64 114 L80 106 L80 122 Z" fill="#C0392B" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>
      <circle cx="64" cy="114" r="4" fill="#8E2A20"/>""",
    "scarf": f"""<path d="M30 100 q34 14 68 0 l0 9 q-34 14 -68 0 Z" fill="#43A07A" stroke="{LINE}" stroke-width="2"/>
      <path d="M80 106 l6 20 l10 -4 l-6 -18" fill="#43A07A" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>""",
    "beanie": f"""<path d="M30 34 q0 -28 34 -28 q34 0 34 28 Z" fill="#E0663E" stroke="{LINE}" stroke-width="2"/>
      <rect x="28" y="28" width="72" height="10" rx="5" fill="#C24E2A" stroke="{LINE}" stroke-width="2"/>
      <circle cx="64" cy="6" r="6" fill="#F4E3D0" stroke="{LINE}" stroke-width="2"/>""",
    "crown": f"""<path d="M40 30 L40 10 L52 20 L64 6 L76 20 L88 10 L88 30 Z" fill="#F2C94C" stroke="{LINE}" stroke-width="2.5" stroke-linejoin="round"/>
      <circle cx="64" cy="20" r="3" fill="#C0392B"/>""",
    "book": f"""<path d="M36 104 l28 6 l28 -6 l0 20 l-28 4 l-28 -4 Z" fill="#2E5BD6" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>
      <path d="M64 110 v18" stroke="{LINE}" stroke-width="2"/>""",
    "monocle": """<circle cx="80" cy="58" r="17" fill="none" stroke="#B8902E" stroke-width="3.5"/>
      <path d="M96 64 q6 20 -2 40" fill="none" stroke="#B8902E" stroke-width="2"/>""",
    "wizard": f"""<path d="M34 32 L64 -6 L94 32 Z" fill="#5B3FA8" stroke="{LINE}" stroke-width="2.5" stroke-linejoin="round"/>
      <path d="M26 32 h76" stroke="{LINE}" stroke-width="6" stroke-linecap="round"/><path d="M26 32 h76" stroke="#5B3FA8" stroke-width="3" stroke-linecap="round"/>
      <circle cx="60" cy="16" r="3" fill="#F2C94C"/><circle cx="72" cy="22" r="2" fill="#F2C94C"/>""",
}
# The accessories that go behind the face (drawn before the base).
BEHIND = {"headphones"}


def svg(name: str) -> str:
    acc = ACCESSORIES[name]
    layers = (acc + BASE) if name in BEHIND else (BASE + acc)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="8 -6 112 136">{layers}</svg>'


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in ACCESSORIES:
        (out / f"owl-{name}.svg").write_text(svg(name), encoding="utf-8")
        cells = "".join(
            f'<span class="t" style="background:{bg};width:{s}px;height:{s}px;border-radius:{max(4, s // 5)}px">'
            f'<img src="owl-{name}.svg" width="{int(s * 0.96)}"></span>'
            for bg in ("#8FB4FF", "#13284D")
            for s in (16, 24, 48, 128)
        )
        rows.append(f"<div class='r'><b>{name}</b>{cells}</div>")
    (out / "preview.html").write_text(
        "<html><body style='font:13px sans-serif;background:#f4f6fa;margin:12px'>"
        "<style>.r{display:flex;align-items:center;gap:10px;margin:4px 0}.r b{width:90px}"
        ".t{display:grid;place-items:center;overflow:hidden}</style>"
        + "".join(rows)
        + "</body></html>",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
