#!/usr/bin/env python3
"""Fill pregenerated.json with Claude-written mnemonics for every demo flag.

Run this on your own computer, with your own key, before deploying:

    ANTHROPIC_API_KEY=sk-ant-... python pregenerate.py            # Seinfeld
    ANTHROPIC_API_KEY=sk-ant-... python pregenerate.py --theme "The Office"

The key is read from the environment and used only for these requests. It is
never written to any file. Flags that already have a Claude-written entry are
skipped unless you pass --redo. Each new mnemonic sees the earlier ones, so
look-alikes get different jokes, as in the add-on.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import demo_logic as logic
import generator

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme", default="Seinfeld")
    parser.add_argument("--model", default=generator.DEFAULT_MODEL)
    parser.add_argument("--redo", action="store_true", help="rewrite flags that already have one")
    args = parser.parse_args(argv)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("Set ANTHROPIC_API_KEY first (it's only read from the environment).", file=sys.stderr)
        return 1

    path = HERE / "pregenerated.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"mnemonics": []}
    by_country = {e["country"]: e for e in data["mnemonics"]}
    prior = [
        generator.PriorMnemonic(e["country"], e["mnemonic"], e.get("distinguishing_detail", ""))
        for e in by_country.values()
    ]
    for flag in logic.load_flags():
        existing = by_country.get(flag.country)
        if existing and existing.get("model") and not args.redo:
            continue
        m = generator.generate_mnemonic(logic.flag_input(flag), args.theme, key, prior=prior, model=args.model)
        by_country[flag.country] = {
            "country": flag.country,
            "theme": args.theme,
            "model": args.model,
            "mnemonic": m.mnemonic,
            "episode_title": m.episode_title,
            "distinguishing_detail": m.distinguishing_detail,
            "note": f"Pre-written by Claude ({args.model}), {args.theme} theme.",
        }
        prior.insert(0, generator.PriorMnemonic(flag.country, m.mnemonic, m.distinguishing_detail))
        print(f"{flag.country}: {m.mnemonic}")
        for warning in m.warnings:
            print(f"  warning: {warning}")
    data["mnemonics"] = list(by_country.values())
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(by_country)} mnemonic(s) to {path.name}. Read them before deploying.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
