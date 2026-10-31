# Flag Mnemonics

An Anki desktop add-on that writes themed mnemonics (Seinfeld by default) for the flag cards you keep forgetting. Each mnemonic encodes what the flag actually looks like and how it differs from its look-alikes, and it's written into the card itself so it syncs to AnkiMobile and AnkiDroid.

Status: early development (stage 1 of 10, scaffold only).

## Repo layout

```
src/flag_mnemonics/   the add-on (symlink this into a dev Anki, see docs/DEVELOPMENT.md)
  __init__.py         Anki entry point: menus and hooks
  settings.py         typed config loading, no Anki imports
  config.json         default settings
  config.md           settings help shown in Anki's config dialog
  triggers.py, generator.py, display.py, storage.py, images.py   later stages
tests/                pytest, with Anki mocked
scripts/link_dev.py   symlinks the add-on into a dev Anki data folder
docs/DEVELOPMENT.md   dev setup, test profile, Python version
```

## Developing

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Short version: back up your collection, run Anki with a separate data folder (`-b ~/AnkiDev`), `python scripts/link_dev.py ~/AnkiDev`, then `pytest`.
