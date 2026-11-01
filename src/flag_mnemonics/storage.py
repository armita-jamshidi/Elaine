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
        # Small facts about this collection, e.g. whether field mode was ever set up.
        self.meta: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.entries, self.meta = {}, {}
            return
        except json.JSONDecodeError as err:
            # Never silently overwrite a damaged source of truth.
            raise ValueError(f"{self.path} is not valid JSON ({err}); fix or move it aside.") from err
        self.entries = dict(data.get("mnemonics", {}))
        self.meta = dict(data.get("meta", {}))

    def save(self) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {"version": FORMAT_VERSION, "meta": self.meta, "mnemonics": self.entries}
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".mnemonics-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def put(self, note_id: int, country: str, mnemonic: Mnemonic, guid: str = "") -> dict[str, Any]:
        entry = {"country": country, "created": int(time.time()), "guid": guid, **mnemonic.to_dict()}
        entry.pop("warnings", None)
        self.entries[str(note_id)] = entry
        self.save()
        return entry

    def get(self, note_id: int) -> Optional[dict[str, Any]]:
        return self.entries.get(str(note_id))

    def set_meta(self, key: str, value: Any) -> None:
        if self.meta.get(key) != value:
            self.meta[key] = value
            self.save()

    def rekey(self, old_id: int, new_id: int) -> None:
        self.entries[str(new_id)] = self.entries.pop(str(old_id))
        self.save()

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


def notes_needing_tag(
    col: Any,
    store: "MnemonicStore",
    note_ids: Optional[Iterable[int]] = None,
) -> list[Any]:
    """Notes with a stored mnemonic but no `mnemonic-added` tag, tagged in memory.

    Used in overlay mode, where the tag is the only change made to notes.
    Save the result with `col.update_notes(notes)`.
    """
    wanted = set(note_ids) if note_ids is not None else None
    notes = []
    for note_id, _entry in store:
        if wanted is not None and note_id not in wanted:
            continue
        try:
            note = col.get_note(note_id)
        except Exception:
            continue
        if not note.has_tag(MNEMONIC_TAG):
            note.add_tag(MNEMONIC_TAG)
            notes.append(note)
    return notes


def notes_to_clear(col: Any, settings: Settings, note_ids: Iterable[int]) -> list[Any]:
    """Empty the Mnemonic field and remove the tag, in memory. Other fields are untouched.

    Returns only the notes that changed; save them with `col.update_notes(notes)`.
    """
    field_name = settings.fields.mnemonic
    notes = []
    for note_id in note_ids:
        try:
            note = col.get_note(note_id)
        except Exception:
            continue
        changed = False
        if field_name in note and note[field_name]:
            note[field_name] = ""
            changed = True
        if note.has_tag(MNEMONIC_TAG):
            note.remove_tag(MNEMONIC_TAG)
            changed = True
        if changed:
            notes.append(note)
    return notes


def clear_mnemonic_from_note(col: Any, settings: Settings, note_id: int) -> bool:
    """Empty the Mnemonic field and remove the tag on one note, and save it."""
    notes = notes_to_clear(col, settings, [note_id])
    if notes:
        col.update_notes(notes)
    return bool(notes)


# --- upgrade repair --------------------------------------------------------
#
# Ultimate Geography upgrades go through CrowdAnki, which resets the note
# type's templates and can drop fields it doesn't know (and their content)
# and rewrite tags. Everything the add-on put on the cards can be rebuilt
# from mnemonics.json, so repair = re-add field and snippet, then rewrite.

FIELD_MODE_INSTALLED = "field_mode_installed"


@dataclass
class RepairReport:
    changes: list[str]
    restored: int = 0
    relinked: int = 0
    missing_notes: list[str] = None  # countries whose notes no longer exist
    declined: bool = False

    def __post_init__(self) -> None:
        if self.missing_notes is None:
            self.missing_notes = []

    @property
    def anything_done(self) -> bool:
        return bool(self.changes or self.restored or self.relinked)

    def summary(self, total: int) -> str:
        if self.declined:
            return (
                "Repair skipped: the Mnemonic field wasn't re-added. Your mnemonics are still saved "
                'and you can run Tools > "Repair mnemonics after deck upgrade" any time.'
            )
        lines = []
        if self.anything_done:
            lines.append("Flag Mnemonics repaired your cards:")
            lines.extend(f"- {c}" for c in self.changes)
            if self.relinked:
                lines.append(f"- Matched {self.relinked} mnemonic(s) to notes that had been re-created.")
            if self.restored:
                lines.append(f"- Restored {self.restored} mnemonic(s) from the add-on's saved copy.")
        else:
            lines.append(f"Everything is in place: {total} mnemonic(s) on your cards, nothing to repair.")
        if self.missing_notes:
            lines.append(
                f"- {len(self.missing_notes)} saved mnemonic(s) belong to notes that no longer exist "
                f"({', '.join(sorted(self.missing_notes))}). They're kept in mnemonics.json."
            )
        return "\n".join(lines)


def relink_by_guid(col: Any, store: MnemonicStore) -> tuple[int, list[str]]:
    """Re-key entries whose note ID is gone but whose note GUID still exists.

    Returns (relinked count, countries with no matching note).
    """
    relinked, missing = 0, []
    for note_id, entry in list(store):
        if col.db.scalar("select 1 from notes where id = ?", note_id):
            continue
        guid = entry.get("guid")
        new_id = col.db.scalar("select id from notes where guid = ?", guid) if guid else None
        if new_id:
            store.rekey(note_id, new_id)
            relinked += 1
        else:
            missing.append(entry.get("country") or str(note_id))
    return relinked, missing
