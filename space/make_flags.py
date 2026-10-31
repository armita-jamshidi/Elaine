#!/usr/bin/env python3
"""Draw the demo's flags (flags/*.png) from flags.json. Needs Pillow.

Only flags made of plain stripes are used, so they can be drawn exactly from
their descriptions. No flag images from Ultimate Geography or elsewhere are
copied.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
HEIGHT = 300


def draw(spec: dict) -> Image.Image:
    w_ratio, h_ratio = spec["ratio"]
    width = round(HEIGHT * w_ratio / h_ratio)
    image = Image.new("RGB", (width, HEIGHT))
    pen = ImageDraw.Draw(image)
    colors = spec["colors"]
    n = len(colors)
    for i, color in enumerate(colors):
        if spec["layout"] == "horizontal":
            pen.rectangle([0, round(i * HEIGHT / n), width, round((i + 1) * HEIGHT / n)], fill=color)
        else:
            pen.rectangle([round(i * width / n), 0, round((i + 1) * width / n), HEIGHT], fill=color)
    # Thin grey outline, so white stripes don't vanish into a white page.
    pen.rectangle([0, 0, width - 1, HEIGHT - 1], outline="#BBBBBB")
    return image


def filename(country: str) -> str:
    return country.lower().replace(" ", "-") + ".png"


def main() -> None:
    specs = json.loads((HERE / "flags.json").read_text(encoding="utf-8"))["flags"]
    for spec in specs:
        draw(spec).save(HERE / "flags" / filename(spec["country"]), optimize=True)
    print(f"Drew {len(specs)} flags into {HERE / 'flags'}")


if __name__ == "__main__":
    main()
