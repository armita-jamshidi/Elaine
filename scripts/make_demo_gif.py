#!/usr/bin/env python3
"""Render docs/images/demo.gif: a flag card flipping to its answer, then the 🥨 box.

Uses the add-on's own display code for the box, so the GIF shows exactly what
the cards show. Needs Node with Playwright (for screenshots) and Pillow:

    pip install Pillow
    python scripts/make_demo_gif.py

The flag is drawn with CSS (two stripes), not taken from Ultimate Geography,
whose flag images have their own licenses.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from flag_mnemonics import display  # noqa: E402
from flag_mnemonics.generator import EXAMPLE_MNEMONIC  # noqa: E402

OUT = ROOT / "docs" / "images" / "demo.gif"
WIDTH, HEIGHT = 560, 560

ENTRY = {"mnemonic": EXAMPLE_MNEMONIC, "episode_title": "The Opposite"}

PAGE = """<!doctype html><meta charset="utf-8"><style>
body {{ margin:0; background:#e9e9ee; font-family: -apple-system, "Segoe UI", Arial, sans-serif; }}
.caption {{ background:#2b2b33; color:#fff; font-size:14px; padding:10px 16px; }}
.caption b {{ color:#f3c94b; }}
.card {{ background:#fff; color:#111; margin:16px; border-radius:10px; padding:22px 18px 26px;
        box-shadow:0 1px 4px rgba(0,0,0,.15); text-align:center; font-size:20px; }}
.flag {{ width:200px; height:125px; margin:0 auto 14px; border:1px solid #ccc;
        background:linear-gradient(#fff 50%, #dc143c 50%); }}
hr {{ border:none; border-top:1px solid #ddd; margin:16px 0; }}
.box {{ opacity:{opacity}; }}
</style>
<div class="caption">{caption}</div>
<div class="card">
  <div class="flag"></div>
  <div>Which country is this?</div>
  {answer}
</div>"""

ANSWER = '<hr><div style="font-size:24px;font-weight:bold">Poland</div>'

# (caption, show answer, box opacity, milliseconds)
FRAMES = [
    ("Reviewing a flag you've missed 3 times…", False, 0, 1600),
    ("Reviewing a flag you've missed 3 times…", True, 0, 1100),
    ("<b>Flag Mnemonics</b> added a Seinfeld mnemonic to the back", True, 0.25, 90),
    ("<b>Flag Mnemonics</b> added a Seinfeld mnemonic to the back", True, 0.5, 90),
    ("<b>Flag Mnemonics</b> added a Seinfeld mnemonic to the back", True, 0.75, 90),
    ("<b>Flag Mnemonics</b> added a Seinfeld mnemonic to the back", True, 1, 4500),
]

SHOOT = """
const { chromium } = require('playwright');
(async () => {
  const [pages, width, height] = JSON.parse(process.argv[1]);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  for (const [html, png] of pages) {
    await page.setContent(html);
    await page.screenshot({ path: png });
  }
  await browser.close();
})();
"""


def frame_html(caption: str, show_answer: bool, opacity: float) -> str:
    answer = ""
    if show_answer:
        answer = ANSWER
        if opacity:
            answer += f'<div class="box">{display.box_html(display.field_html(ENTRY))}</div>'
    return PAGE.format(caption=caption, answer=answer, opacity=opacity)


def main() -> int:
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        pages = []
        for i, (caption, show, opacity, _) in enumerate(FRAMES):
            pages.append([frame_html(caption, show, opacity), str(Path(tmp) / f"{i}.png")])
        subprocess.run(["node", "-e", SHOOT, json.dumps([pages, WIDTH, HEIGHT])], check=True)
        images = [Image.open(png).convert("RGB") for _, png in pages]
        palette = images[-1].quantize(colors=128)
        frames = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
        frames[0].save(
            OUT,
            save_all=True,
            append_images=frames[1:],
            duration=[ms for *_, ms in FRAMES],
            loop=0,
            optimize=True,
        )
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
