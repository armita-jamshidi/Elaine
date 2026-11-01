"""Anki-side glue for field mode: set up the note type once, copy mnemonics
onto cards, and remind you to sync so they reach your phone."""

from __future__ import annotations

import os
from typing import Any, Callable, Iterable, Optional

from . import storage
from .settings import Settings
from .triggers import get_logger

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "user_files", "backups")

SCHEMA_CHANGE_MESSAGE = """Flag Mnemonics needs to add a "{field}" field to the "{note_type}" note type, so mnemonics can sync to your phone. It won't change any of your existing fields or their content.

Adding a field is a one-time change that makes your next sync a full sync. To avoid losing reviews:

1. Sync your phone first, so AnkiWeb has your latest reviews.
2. Click Yes here.
3. Sync desktop Anki and choose "Upload to AnkiWeb".
4. Sync your phone again and choose "Download from AnkiWeb".

Add the field now? If you choose No, mnemonics are still saved by the add-on and you'll be asked again next time."""


class FieldMode:
    def __init__(self, mw: Any, get_settings: Callable[[], Settings], store: storage.MnemonicStore) -> None:
        self.mw = mw
        self.get_settings = get_settings
        self.store = store
        self.declined_this_session = False

    def ensure_installed(self, settings: Settings, interactive: bool = True) -> bool:
        """Add the field and snippet if missing. Returns True when field mode is ready."""
        from aqt.utils import askUser, showWarning

        col = self.mw.col
        status = storage.field_mode_status(col, settings)
        if not status.note_type_found:
            showWarning(
                f'Flag Mnemonics couldn\'t find the note type "{settings.note_type}". '
                "Check note_type in the add-on config.",
                title="Flag Mnemonics",
            )
            return False
        if status.ready:
            return True
        if not status.has_field:
            if self.declined_this_session or not interactive:
                return False
            if not askUser(
                SCHEMA_CHANGE_MESSAGE.format(field=settings.fields.mnemonic, note_type=settings.note_type),
                title="Flag Mnemonics",
                defaultno=True,
            ):
                self.declined_this_session = True
                return False
        backup = storage.backup_note_type(col, settings, BACKUP_DIR)
        changes = storage.install_field_mode(col, settings)
        get_logger().info("Field mode set up (backup: %s): %s", backup, "; ".join(changes))
        return True

    def apply(self, note_ids: Optional[Iterable[int]] = None, interactive: bool = True) -> None:
        """Copy stored mnemonics onto the cards, then remind you to sync."""
        from aqt.operations import CollectionOp
        from aqt.utils import tooltip

        settings = self.get_settings()
        if settings.storage_mode != "field" or not len(self.store):
            return
        if not self.ensure_installed(settings, interactive):
            return
        notes = storage.notes_needing_update(self.mw.col, settings, self.store, note_ids)
        if not notes:
            return

        def done(_changes: Any) -> None:
            get_logger().info("Wrote %d mnemonic(s) to cards.", len(notes))
            if settings.auto_sync_after_generation:
                tooltip(f"Flag Mnemonics: added {len(notes)} mnemonic(s) to your cards. Syncing…")
                self.mw.on_sync_button_clicked()
            else:
                tooltip(
                    f"Flag Mnemonics: added {len(notes)} mnemonic(s) to your cards. "
                    "Sync to see them on your phone.",
                    period=6000,
                )

        CollectionOp(parent=self.mw, op=lambda col: col.update_notes(notes)).success(done).run_in_background()
