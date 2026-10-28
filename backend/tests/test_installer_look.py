"""The installer's look (phase 20, amendment 1; CA16): images, colors and texts."""

import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "desktop" / "src-tauri" / "windows"
TOKENS = (ROOT / "frontend" / "src" / "styles" / "tokens.css").read_text("utf-8")
CONF = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text("utf-8"))
NSIS = CONF["bundle"]["windows"]["nsis"]
HOOKS = (WINDOWS / "hooks.nsh").read_text("utf-8-sig")


def token(name: str) -> str:
    match = re.search(rf"--{re.escape(name)}:\s*#([0-9a-fA-F]{{6}})\s*;", TOKENS)
    assert match, name
    return match.group(1).upper()


def test_the_images_have_the_sizes_nsis_needs():
    for key, size in (("headerImage", (150, 57)), ("sidebarImage", (164, 314))):
        path = ROOT / "desktop" / "src-tauri" / NSIS[key]
        assert path.suffix == ".bmp"
        image = Image.open(path)
        assert image.size == size
        assert image.mode == "RGB"


def test_the_images_use_the_navy_of_the_app():
    navy = token("sidebar")
    for key in ("headerImage", "sidebarImage"):
        pixel = Image.open(ROOT / "desktop" / "src-tauri" / NSIS[key]).getpixel((1, 1))
        assert "".join(f"{c:02X}" for c in pixel) == navy


def test_the_wizard_colors_are_the_navy_of_the_app():
    assert f'!define MUI_BGCOLOR "{token("sidebar")}"' in HOOKS
    assert f'!define MUI_TEXTCOLOR "{token("sidebar-foreground")}"' in HOOKS


def test_the_license_is_accepted_and_the_authorship_is_shown():
    assert CONF["bundle"]["licenseFile"].endswith("LICENSE")
    assert "!define MUI_LICENSEPAGE_CHECKBOX\n" in HOOKS.replace("\r\n", "\n")
    for page in ("MUI_WELCOMEPAGE_TEXT", "MUI_FINISHPAGE_TEXT"):
        line = next(x for x in HOOKS.splitlines() if x.startswith(f"!define {page} "))
        assert "Made By Café Con Palito with" in line
        assert "Albano Díez de Paulino" in line


def test_the_hooks_file_is_utf8_with_bom_for_nsis_unicode():
    assert (WINDOWS / "hooks.nsh").read_bytes().startswith(b"\xef\xbb\xbf")
