"""The installer's images (phase 20, amendment 1): the NSIS header and side panel in the main
theme's navy, with Café con Palito's negative logo.

Writes `desktop/src-tauri/windows/header.bmp` (150x57) and `sidebar.bmp` (164x314), 24-bit as
NSIS needs them. The colors come from `frontend/src/styles/tokens.css` (the sidebar navy), so
the installer follows the app; a backend test checks both.

    uv run --project backend python scripts/installer_art.py
"""

import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "frontend" / "src" / "styles" / "tokens.css"
LOGO = ROOT / "frontend" / "src" / "assets" / "brand" / "ccp-logo-negative.png"
OUT = ROOT / "desktop" / "src-tauri" / "windows"

HEADER_SIZE = (150, 57)
SIDEBAR_SIZE = (164, 314)


def token(name: str) -> str:
    """A hex color from the first `--name: #xxxxxx;` of tokens.css (the light block, where the
    sidebar navy is defined for both modes)."""
    match = re.search(rf"--{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})\s*;", TOKENS.read_text("utf-8"))
    if not match:
        raise SystemExit(f"token --{name} not found in {TOKENS}")
    return match.group(1)


def rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def paste_logo(canvas: Image.Image, box: tuple[int, int, int, int]) -> None:
    """The logo fitted inside `box` (left, top, right, bottom), centered."""
    logo = Image.open(LOGO).convert("RGBA")
    width, height = box[2] - box[0], box[3] - box[1]
    logo.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas.paste(
        logo,
        (box[0] + (width - logo.width) // 2, box[1] + (height - logo.height) // 2),
        logo,
    )


def main() -> None:
    navy = rgb(token("sidebar"))
    OUT.mkdir(parents=True, exist_ok=True)

    header = Image.new("RGB", HEADER_SIZE, navy)
    paste_logo(header, (47, 4, 143, 53))
    header.save(OUT / "header.bmp")

    side = Image.new("RGB", SIDEBAR_SIZE, navy)
    paste_logo(side, (22, 40, 142, 190))
    # A thin accent band at the bottom, the app's action blue.
    band = Image.new("RGB", (SIDEBAR_SIZE[0], 6), rgb(token("sidebar-primary")))
    side.paste(band, (0, SIDEBAR_SIZE[1] - 6))
    side.save(OUT / "sidebar.bmp")
    print(f"wrote {OUT / 'header.bmp'} and {OUT / 'sidebar.bmp'}")


if __name__ == "__main__":
    main()
