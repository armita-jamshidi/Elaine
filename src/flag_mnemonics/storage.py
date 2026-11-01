"""Where mnemonics live.

- `MnemonicStore`: user_files/mnemonics.json, keyed by note ID. This is the
  source of truth; everything on the cards can be rebuilt from it.
- Field mode: the "Mnemonic" field on the note type plus a snippet on the
  flag cards' back template, so mnemonics sync to AnkiMobile and AnkiDroid.

No Anki imports: collection objects are passed in.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Optional

from . import display
from .generator import Mnemonic, PriorMnemonic
from .settings import Settings

MNEMONIC_TAG = "mnemonic-added"

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


# --- field mode -----------------------------------------------------------
#
# The functions below take an Anki collection but import nothing from Anki,
# so they can be tested against the `anki` package or simple fakes.


@dataclass
class FieldModeStatus:
    note_type_found: bool
    has_field: bool
    templates_missing_snippet: list[str]
    templates_not_found: list[str]

    @property
    def ready(self) -> bool:
        return self.note_type_found and self.has_field and not self.templates_missing_snippet


def _note_type(col: Any, settings: Settings) -> Optional[dict]:
    return col.models.by_name(settings.note_type)


def field_mode_status(col: Any, settings: Settings) -> FieldModeStatus:
    nt = _note_type(col, settings)
    if nt is None:
        return FieldModeStatus(False, False, [], list(settings.flag_card_templates))
    field_name = settings.fields.mnemonic
    names = {t["name"]: t for t in nt["tmpls"]}
    return FieldModeStatus(
        note_type_found=True,
        has_field=field_name in [f["name"] for f in nt["flds"]],
        templates_missing_snippet=[
            n for n in settings.flag_card_templates if n in names and not display.has_snippet(names[n]["afmt"], field_name)
        ],
        templates_not_found=[n for n in settings.flag_card_templates if n not in names],
    )


def backup_note_type(col: Any, settings: Settings, backup_dir: str) -> Optional[str]:
    """Save the note type (fields, templates, CSS) as JSON before changing it."""
    nt = _note_type(col, settings)
    if nt is None:
        return None
    os.makedirs(backup_dir, exist_ok=True)
    path = os.path.join(backup_dir, f"notetype-{int(time.time() * 1000)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nt, f, ensure_ascii=False, indent=2)
    return path


def needs_schema_change(col: Any, settings: Settings) -> bool:
    """Adding a field is a schema change: the next sync must be a one-way full sync."""
    status = field_mode_status(col, settings)
    return status.note_type_found and not status.has_field


def install_field_mode(col: Any, settings: Settings) -> list[str]:
    """Add the Mnemonic field and the back-template snippet where missing.

    Only appends: never renames, removes or reorders existing fields, and only
    adds the snippet block to the end of the flag cards' back templates.
    Returns a list of human-readable changes. Call `backup_note_type` first.
    """
    nt = _note_type(col, settings)
    if nt is None:
        raise ValueError(f'Note type "{settings.note_type}" not found.')
    field_name = settings.fields.mnemonic
    changes = []
    if field_name not in [f["name"] for f in nt["flds"]]:
        col.models.add_field(nt, col.models.new_field(field_name))
        changes.append(f'Added the "{field_name}" field to "{settings.note_type}".')
    for tmpl in nt["tmpls"]:
        if tmpl["name"] in settings.flag_card_templates and not display.has_snippet(tmpl["afmt"], field_name):
            tmpl["afmt"] = display.add_snippet(tmpl["afmt"], field_name)
            changes.append(f'Added the mnemonic box to the back of "{tmpl["name"]}".')
    if changes:
        col.models.update_dict(nt)
    return changes


def notes_needing_update(
    col: Any,
    settings: Settings,
    store: "MnemonicStore",
    note_ids: Optional[Iterable[int]] = None,
) -> list[Any]:
    """Notes whose Mnemonic field or tag doesn't match the store, already updated in memory.

    Changes only the Mnemonic field and the tag. Skips notes that are gone,
    belong to a note type without the field, or are already up to date.
    Save the result with `col.update_notes(notes)`.
    """
    field_name = settings.fields.mnemonic
    wanted = set(note_ids) if note_ids is not None else None
    notes = []
    for note_id, entry in store:
        if wanted is not None and note_id not in wanted:
            continue
        try:
            note = col.get_note(note_id)
        except Exception:  # deleted note: anki raises NotFoundError
            continue
        if field_name not in note:
            continue
        new_html = display.field_html(entry)
        has_tag = note.has_tag(MNEMONIC_TAG)
        if note[field_name] == new_html and has_tag:
            continue
        note[field_name] = new_html
        if not has_tag:
            note.add_tag(MNEMONIC_TAG)
        notes.append(note)
    return notes


def write_mnemonics_to_notes(
    col: Any,
    settings: Settings,
    store: "MnemonicStore",
    note_ids: Optional[Iterable[int]] = None,
) -> list[int]:
    """Copy stored mnemonics onto the notes and tag them. Returns changed note IDs."""
    notes = notes_needing_update(col, settings, store, note_ids)
    if notes:
        col.update_notes(notes)
    return [n.id for n in notes]


def clear_mnemonic_from_note(col: Any, settings: Settings, note_id: int) -> bool:
    """Empty the Mnemonic field and remove the tag. Other fields are untouched."""
    note = col.get_note(note_id)
    field_name = settings.fields.mnemonic
    if field_name in note:
        note[field_name] = ""
    note.remove_tag(MNEMONIC_TAG)
    col.update_note(note)
    return True
