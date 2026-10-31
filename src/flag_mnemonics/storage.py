"""The add-on's own record of every mnemonic: user_files/mnemonics.json.

This file is the source of truth. Stage 4 copies entries into the
Mnemonic field; stage 5 restores them from here after a deck upgrade.
Pure Python with no Anki imports.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Any, Iterator, Optional

from .generator import Mnemonic, PriorMnemonic

FORMAT_VERSION = 1


class MnemonicStore:
    """Mnemonics keyed by note ID, saved atomically after every change."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.entries = {}
            return
        except json.JSONDecodeError as err:
            # Never silently overwrite a damaged source of truth.
            raise ValueError(f"{self.path} is not valid JSON ({err}); fix or move it aside.") from err
        self.entries = dict(data.get("mnemonics", {}))

    def save(self) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {"version": FORMAT_VERSION, "mnemonics": self.entries}
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".mnemonics-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def put(self, note_id: int, country: str, mnemonic: Mnemonic) -> dict[str, Any]:
        entry = {"country": country, "created": int(time.time()), **mnemonic.to_dict()}
        entry.pop("warnings", None)
        self.entries[str(note_id)] = entry
        self.save()
        return entry

    def get(self, note_id: int) -> Optional[dict[str, Any]]:
        return self.entries.get(str(note_id))

    def remove(self, note_id: int) -> bool:
        if self.entries.pop(str(note_id), None) is None:
            return False
        self.save()
        return True

    def __contains__(self, note_id: int) -> bool:
        return str(note_id) in self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[tuple[int, dict[str, Any]]]:
        for key, entry in self.entries.items():
            yield int(key), entry

    def prior_mnemonics(self) -> list[PriorMnemonic]:
        """Every stored mnemonic, newest first, as context for the generator."""
        ordered = sorted(self.entries.values(), key=lambda e: e.get("created", 0), reverse=True)
        return [
            PriorMnemonic(e.get("country", ""), e.get("mnemonic", ""), e.get("distinguishing_detail", ""))
            for e in ordered
            if e.get("mnemonic")
        ]
