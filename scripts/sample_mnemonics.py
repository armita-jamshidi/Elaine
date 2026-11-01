"""Generate sample mnemonics outside Anki, to judge quality.

Fetches each country's flag and "Flag similarity" text from the Ultimate
Geography repo on GitHub (nothing is saved or redistributed), then runs the
same generator the add-on uses.

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/sample_mnemonics.py
    python scripts/sample_mnemonics.py --theme "The Office" Poland Chad
    python scripts/sample_mnemonics.py --mock          # no API calls

Flags are SVGs. With PyQt6 installed (`pip install PyQt6`) they're rendered to
PNG and sent as images, like inside Anki; otherwise the SVG source is sent.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flag_mnemonics import media  # noqa: E402
from flag_mnemonics.generator import (  # noqa: E402
    DEFAULT_MODEL,
    FlagImage,
    FlagInput,
    GenerationError,
    PriorMnemonic,
    generate_mnemonic,
    mock_transport,
)

UG_RAW = "https://raw.githubusercontent.com/anki-geo/ultimate-geography/master/src"
DEFAULT_COUNTRIES = ["Poland", "Indonesia", "Monaco", "Chad", "Romania"]


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def load_similarity() -> dict[str, str]:
    text = fetch(f"{UG_RAW}/data/flag_similarity.csv").decode("utf-8")
    return {row["country"]: row["flag similarity"] for row in csv.DictReader(io.StringIO(text))}


def load_flag(country: str) -> FlagImage:
    slug = country.lower().replace(" ", "_")
    svg = fetch(f"{UG_RAW}/media/flags/ug-flag-{slug}.svg")
    if os.environ.get("QT_QPA_PLATFORM") is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        from PyQt6.QtGui import QGuiApplication

        _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
        png = media.render_svg_to_png(svg)
    except ImportError:
        png = None
    return FlagImage(png, "image/png") if png else FlagImage(svg, "image/svg+xml")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("countries", nargs="*", default=DEFAULT_COUNTRIES)
    parser.add_argument("--theme", default="Seinfeld")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--mock", action="store_true", help="use the offline mock instead of the API")
    parser.add_argument("--out", type=Path, help="also write the results to this Markdown file")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.mock:
        sys.exit("Set ANTHROPIC_API_KEY, or pass --mock.")

    similarity = load_similarity()
    prior: list[PriorMnemonic] = []
    lines = [f"# Sample mnemonics: {args.theme}", "", f"Model: `{args.model}`", ""]
    for country in args.countries:
        flag = FlagInput(country, load_flag(country), similarity.get(country, ""))
        try:
            m = generate_mnemonic(
                flag,
                args.theme,
                api_key,
                prior=prior,
                model=args.model,
                transport=mock_transport if args.mock else None,
            )
        except GenerationError as err:
            print(f"\n{country}: FAILED: {err}")
            lines += [f"## {country}", "", f"Failed: {err}", ""]
            continue
        prior.insert(0, PriorMnemonic(country, m.mnemonic, m.distinguishing_detail))
        sent_as = "PNG image" if flag.image.media_type == "image/png" else "SVG text"
        print(f"\n{country}  [{m.model}, flag sent as {sent_as}]")
        print(f"  Look-alikes: {flag.flag_similarity or '(none listed)'}")
        print(f"  Mnemonic: {m.mnemonic}")
        print(f"  Episode: {m.episode_title or '(none)'}")
        print(f"  Key detail: {m.distinguishing_detail}")
        print(f"  Image prompt: {m.image_prompt}")
        for w in m.warnings:
            print(f"  Warning: {w}")
        lines += [
            f"## {country}",
            "",
            f"**Mnemonic:** {m.mnemonic}",
            "",
            f"- Look-alikes (from the deck): {flag.flag_similarity or 'none listed'}",
            f"- Episode: {m.episode_title or 'none'}",
            f"- Key detail: {m.distinguishing_detail}",
            f"- Image prompt: {m.image_prompt}",
            "",
        ]
    if args.out:
        args.out.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
