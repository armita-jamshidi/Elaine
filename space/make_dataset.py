#!/usr/bin/env python3
"""Optional: turn pregenerated.json into a small Hugging Face dataset folder.

    python make_dataset.py            # writes dataset/ (data.jsonl, README.md)

Nothing is uploaded. To publish it (only if you want to), see DEPLOY.md.
Only Claude-written entries are included; the hand-written example isn't.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import demo_logic as logic

HERE = Path(__file__).resolve().parent
OUT = HERE / "dataset"

CARD = """---
language: en
pretty_name: Flag Mnemonics (Seinfeld)
size_categories: n<1K
tags: [mnemonics, flags, geography, education]
---

# Flag Mnemonics: Seinfeld

Short mnemonics for telling look-alike national flags apart, themed on Seinfeld. Written by Claude
(Anthropic) with the prompt from the [Flag Mnemonics Anki add-on](https://github.com/armita-jamshidi/Elaine),
which asks for the flag's real colors and layout, its distinguishing detail, and a real episode title (or none).

Columns: `country`, `theme`, `model`, `mnemonic`, `episode_title`, `distinguishing_detail`, `similarity`,
`image` (the stripe drawing used as input, in `images/`).

AI-written: check before relying on them. Episode titles were requested only when real, but verify them.
Not affiliated with Seinfeld or its makers. Flag drawings are simple stripe layouts of public-domain designs.
"""


def main() -> int:
    flags = {f.country: f for f in logic.load_flags()}
    rows = [e for e in logic.load_pregenerated().values() if e.get("model")]
    if not rows:
        print("No Claude-written mnemonics yet. Run pregenerate.py first.")
        return 1
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "images").mkdir(parents=True)
    with open(OUT / "data.jsonl", "w", encoding="utf-8") as f:
        for e in rows:
            flag = flags[e["country"]]
            shutil.copy(flag.path, OUT / "images" / flag.path.name)
            row = {k: e.get(k) for k in ("country", "theme", "model", "mnemonic", "episode_title", "distinguishing_detail")}
            row.update(similarity=flag.similarity, image=f"images/{flag.path.name}")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (OUT / "README.md").write_text(CARD, encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
