# Flag Mnemonics

An Anki desktop add-on that writes themed mnemonics (Seinfeld by default) for the flag cards you keep forgetting. Each mnemonic encodes what the flag actually looks like and how it differs from its look-alikes, and it's written into the card itself so it syncs to AnkiMobile and AnkiDroid.

Status: early development (stage 3 of 10: finds struggling flag cards and writes mnemonics with Claude; they're saved but not on your cards yet).

## Repo layout

```
src/flag_mnemonics/   the add-on (symlink this into a dev Anki, see docs/DEVELOPMENT.md)
  __init__.py         entry point; does nothing outside Anki
  addon.py            Anki wiring: menus and hooks
  settings.py         typed config loading, no Anki imports
  config.json         default settings
  config.md           settings help shown in Anki's config dialog
  triggers.py         finds struggling flag cards (startup, after sync, Again)
  generator.py        prompt, Claude API call (urllib), JSON parsing; stdlib only
  media.py            reads the flag image; renders SVG flags to PNG with Qt
  pipeline.py         runs generation in the background
  storage.py          user_files/mnemonics.json, the source of truth
  display.py, images.py   later stages
tests/                pytest, with Anki mocked (plus one test file on a real Anki backend)
scripts/link_dev.py   symlinks the add-on into a dev Anki data folder
scripts/sample_mnemonics.py   generates sample mnemonics outside Anki
docs/DEVELOPMENT.md   dev setup, test profile, Python version
```

## Why no Anthropic SDK?

Anki add-ons can't `pip install` packages, so `generator.py` calls the Claude Messages API with Python's built-in `urllib`. It has no third-party or Anki imports, which also lets the Hugging Face Space demo reuse it unchanged.

## Developing

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Short version: back up your collection, run Anki with a separate data folder (`-b ~/AnkiDev`), `python scripts/link_dev.py ~/AnkiDev`, then `pytest`.
