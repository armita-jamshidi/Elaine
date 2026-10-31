"""Symlink src/flag_mnemonics into a development Anki's add-ons folder.

Usage:
    python scripts/link_dev.py ~/AnkiDev

The argument is the separate Anki data folder you start Anki with
(`anki -b ~/AnkiDev`), never your real one. The script creates
<folder>/addons21/flag_mnemonics -> <repo>/src/flag_mnemonics.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADDON_SRC = REPO_ROOT / "src" / "flag_mnemonics"
ADDON_DIR_NAME = "flag_mnemonics"


def default_anki_base() -> Path:
    """Anki's normal data folder, which this script refuses to touch."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Anki2"
    if sys.platform.startswith("win"):
        return home / "AppData" / "Roaming" / "Anki2"
    return home / ".local" / "share" / "Anki2"


def link(base: Path, force_real_profile: bool = False) -> Path:
    base = base.expanduser().resolve()
    if base == default_anki_base().resolve() and not force_real_profile:
        raise SystemExit(
            f"{base} is your real Anki data folder. Use a separate dev folder "
            "(e.g. ~/AnkiDev) and start Anki with `-b ~/AnkiDev`."
        )
    addons = base / "addons21"
    addons.mkdir(parents=True, exist_ok=True)
    target = addons / ADDON_DIR_NAME
    if target.is_symlink():
        if target.resolve() == ADDON_SRC:
            print(f"Already linked: {target} -> {ADDON_SRC}")
            return target
        raise SystemExit(f"{target} is a symlink to somewhere else; remove it first.")
    if target.exists():
        raise SystemExit(f"{target} already exists and is not a symlink; remove it first.")
    target.symlink_to(ADDON_SRC, target_is_directory=True)
    print(f"Linked {target} -> {ADDON_SRC}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("anki_base", type=Path, help="dev Anki data folder, e.g. ~/AnkiDev")
    parser.add_argument(
        "--i-backed-up-my-real-collection",
        dest="force_real_profile",
        action="store_true",
        help="allow linking into your real Anki data folder",
    )
    args = parser.parse_args()
    link(args.anki_base, args.force_real_profile)


if __name__ == "__main__":
    main()
