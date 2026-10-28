# ruff: noqa: E501  (SVG markup is data)
"""The owl gallery for agent avatars (phase 20): one base owl plus an accessory per variant.

Writes `frontend/src/assets/owls/<id>.svg`. The set is the project's own drawing, under the
project's license (GPL-3.0-or-later). The ids are also listed in
`backend/src/agentic_os/services/avatars.py` (OWL_IDS), and a backend test keeps both in step.

    uv run --project backend python scripts/owls.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "src" / "assets" / "owls"

BODY, BELLY, EYE, PUPIL, BEAK, LINE = (
    "#8A5A3B",
    "#E9D3B4",
    "#FFFFFF",
    "#1B1B1F",
    "#F2A93B",
    "#3A2416",
)
# Dark accessories get a light rim so they still read on a dark agent color (spike S1).
RIM = 'stroke="#F4E3D0" stroke-opacity="0.85"'

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
    "top-hat": f"""<rect x="40" y="22" width="48" height="6" rx="3" fill="#2E3446" {RIM} stroke-width="2"/>
      <rect x="49" y="2" width="30" height="22" rx="3" fill="#2E3446" {RIM} stroke-width="2"/>
      <rect x="49" y="15" width="30" height="5" fill="#C0392B"/>""",
    "grad-cap": f"""<path d="M64 8 L102 21 L64 34 L26 21 Z" fill="#26324F" {RIM} stroke-width="2" stroke-linejoin="round"/>
      <path d="M98 22 L98 38" stroke="#F2C94C" stroke-width="3"/><circle cx="98" cy="40" r="3.5" fill="#F2C94C"/>""",
    "glasses": """<circle cx="48" cy="58" r="17" fill="none" stroke="#1B1B1F" stroke-width="4"/>
      <circle cx="80" cy="58" r="17" fill="none" stroke="#1B1B1F" stroke-width="4"/>
      <path d="M65 58 h-2" stroke="#1B1B1F" stroke-width="4"/>""",
    "sunglasses": """<path d="M30 50 h36 v8 q0 14 -18 14 q-18 0 -18 -14 Z M62 50 h36 v8 q0 14 -18 14 q-18 0 -18 -14 Z" fill="#14141A" stroke="#14141A" stroke-width="2"/>
      <path d="M36 54 l8 0 M68 54 l8 0" stroke="#5A6075" stroke-width="3" stroke-linecap="round"/>""",
    "headphones": f"""<path d="M24 64 q0 -50 40 -50 q40 0 40 50" fill="none" stroke="#2E5BD6" stroke-width="7" stroke-linecap="round"/>
      <rect x="16" y="56" width="16" height="26" rx="7" fill="#2E5BD6" stroke="{LINE}" stroke-width="2"/>
      <rect x="96" y="56" width="16" height="26" rx="7" fill="#2E5BD6" stroke="{LINE}" stroke-width="2"/>""",
    "bow-tie": f"""<path d="M64 104 L49 96 L49 112 Z M64 104 L79 96 L79 112 Z" fill="#C0392B" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>
      <circle cx="64" cy="104" r="4" fill="#8E2A20"/>""",
    "scarf": f"""<path d="M30 92 q34 14 68 0 l0 10 q-34 14 -68 0 Z" fill="#43A07A" stroke="{LINE}" stroke-width="2"/>
      <path d="M78 100 l6 18 l10 -4 l-6 -16" fill="#43A07A" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>""",
    "beanie": f"""<path d="M30 34 q0 -26 34 -26 q34 0 34 26 Z" fill="#E0663E" stroke="{LINE}" stroke-width="2"/>
      <rect x="28" y="28" width="72" height="10" rx="5" fill="#C24E2A" stroke="{LINE}" stroke-width="2"/>
      <circle cx="64" cy="8" r="6" fill="#F4E3D0" stroke="{LINE}" stroke-width="2"/>""",
    "crown": f"""<path d="M40 30 L40 10 L52 20 L64 6 L76 20 L88 10 L88 30 Z" fill="#F2C94C" stroke="{LINE}" stroke-width="2.5" stroke-linejoin="round"/>
      <circle cx="64" cy="20" r="3" fill="#C0392B"/>""",
    "book": f"""<path d="M38 96 l26 6 l26 -6 l0 20 l-26 4 l-26 -4 Z" fill="#2E5BD6" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>
      <path d="M64 102 v18" stroke="{LINE}" stroke-width="2"/>""",
    "monocle": """<circle cx="80" cy="58" r="17" fill="none" stroke="#B8902E" stroke-width="3.5"/>
      <path d="M96 64 q6 20 -2 40" fill="none" stroke="#B8902E" stroke-width="2"/>""",
    "wizard": f"""<path d="M36 32 L64 0 L92 32 Z" fill="#5B3FA8" {RIM} stroke-width="2" stroke-linejoin="round"/>
      <path d="M28 32 h72" stroke="#5B3FA8" stroke-width="6" stroke-linecap="round"/>
      <circle cx="60" cy="18" r="3" fill="#F2C94C"/><circle cx="72" cy="24" r="2" fill="#F2C94C"/>""",
}
# The accessories that go behind the face (drawn before the base).
BEHIND = {"headphones"}


def svg(name: str) -> str:
    accessory = ACCESSORIES[name]
    layers = (accessory + BASE) if name in BEHIND else (BASE + accessory)
    # Square, so the owl fills a square avatar without being cropped.
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -6 136 136">{layers}</svg>\n'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ACCESSORIES:
        (OUT / f"{name}.svg").write_text(svg(name), encoding="utf-8", newline="\n")
    print(f"{len(ACCESSORIES)} owls in {OUT}")


if __name__ == "__main__":
    main()
