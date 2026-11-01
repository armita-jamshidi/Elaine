#!/usr/bin/env python3
"""Build dist/flag_mnemonics-<version>.ankiaddon from src/flag_mnemonics.

    python scripts/package.py            # build
    python scripts/package.py --out DIR  # build somewhere else

An .ankiaddon is a zip with the add-on's files at its root. Install it by
double-clicking it, or in Anki: Tools > Add-ons > Install from file.

Left out: __pycache__ and .pyc files, meta.json (Anki's copy of your config,
which can hold API keys), and everything in user_files/ except README.txt
(your mnemonics and backups). The build stops if config.json has a key in it.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDON_DIR = ROOT / "src" / "flag_mnemonics"
REQUIRED = ("__init__.py", "manifest.json", "config.json", "config.md")
SECRET_KEYS = ("claude_api_key", "huggingface_api_key")
# Fixed timestamp so the same source gives the same zip.
ZIP_DATE = (2024, 1, 1, 0, 0, 0)


class PackageError(Exception):
    pass


def included(rel: Path) -> bool:
    parts = rel.parts
    if "__pycache__" in parts or rel.suffix in (".pyc", ".pyo"):
        return False
    if any(p.startswith(".") for p in parts):  # .DS_Store, editor files
        return False
    if rel.name == "meta.json" and len(parts) == 1:
        return False
    if parts[0] == "user_files":
        return rel == Path("user_files/README.txt")
    return True


def check(addon_dir: Path) -> dict:
    for name in REQUIRED:
        if not (addon_dir / name).is_file():
            raise PackageError(f"Missing {name} in {addon_dir}")
    manifest = json.loads((addon_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in ("package", "name", "human_version"):
        if not manifest.get(key):
            raise PackageError(f'manifest.json needs "{key}"')
    config = json.loads((addon_dir / "config.json").read_text(encoding="utf-8"))
    for key in SECRET_KEYS:
        if config.get(key):
            raise PackageError(
                f"config.json has a value for {key}. Never ship a key: set it back to \"\" "
                "(your own key lives in meta.json, which isn't packaged)."
            )
    if config.get("use_mock_api"):
        raise PackageError("config.json has use_mock_api set to true. Set it back to false before packaging.")
    return manifest


def files_to_pack(addon_dir: Path) -> list[Path]:
    return sorted(
        p.relative_to(addon_dir) for p in addon_dir.rglob("*") if p.is_file() and included(p.relative_to(addon_dir))
    )


def build(addon_dir: Path = ADDON_DIR, out_dir: Path = ROOT / "dist") -> Path:
    manifest = check(addon_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{manifest['package']}-{manifest['human_version']}.ankiaddon"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files_to_pack(addon_dir):
            info = zipfile.ZipInfo(rel.as_posix(), ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, (addon_dir / rel).read_bytes())
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="output folder (default: dist/)")
    args = parser.parse_args(argv)
    try:
        target = build(out_dir=args.out)
    except PackageError as err:
        print(f"Not packaged: {err}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    print(f"Built {target} ({target.stat().st_size // 1024} KB, {len(names)} files)")
    print("Install: double-click it, or Anki > Tools > Add-ons > Install from file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
