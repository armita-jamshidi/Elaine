"""Anki-side glue for field mode: set up the note type once, copy mnemonics
onto cards, repair them after a deck upgrade, and remind you to sync."""

from __future__ import annotations

import os
from typing import Any, Callable, Iterable, Optional

from . import storage
from .settings import Settings
from .triggers import get_logger

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "user_files", "backups")
TITLE = "Flag Mnemonics"

FULL_SYNC_STEPS = """Adding a field is a change that makes your next sync a one-way full sync. To avoid losing reviews:

1. Sync your phone first, so AnkiWeb has your latest reviews.
2. Click Yes here.
3. Sync desktop Anki and choose "Upload to AnkiWeb".
4. Sync your phone again and choose "Download from AnkiWeb"."""

FIRST_TIME_MESSAGE = (
    'Flag Mnemonics needs to add a "{field}" field to the "{note_type}" note type, so mnemonics '
    "can sync to your phone. It won't change any of your existing fields or their content.\n\n"
    + FULL_SYNC_STEPS
    + "\n\nAdd the field now? If you choose No, mnemonics are still saved by the add-on and "
    "you'll be asked again next time."
)

REPAIR_MESSAGE = (
    'The "{field}" field is missing from "{note_type}", probably because a deck upgrade removed it. '
    "Flag Mnemonics can add it back and restore all {count} saved mnemonic(s). Your other fields "
    "won't change.\n\n" + FULL_SYNC_STEPS + "\n\nRepair now?"
)

OVERLAY_REPAIR_MESSAGE = (
    'Storage mode is "overlay", so mnemonics are shown at review time and nothing on the cards '
    "needs repairing. Re-added the mnemonic-added tag to {count} note(s)."
)


class FieldMode:
    def __init__(self, mw: Any, get_settings: Callable[[], Settings], store: storage.MnemonicStore) -> None:
        self.mw = mw
        self.get_settings = get_settings
        self.store = store
        self.declined_this_session = False

    # --- shared steps ----------------------------------------------------

    def _note_type_missing(self, settings: Settings) -> bool:
        from aqt.utils import showWarning

        if storage.field_mode_status(self.mw.col, settings).note_type_found:
            return False
        showWarning(
            f'Flag Mnemonics couldn\'t find the note type "{settings.note_type}". '
            "Check note_type in the add-on config.",
            title=TITLE,
        )
        return True

    def _install(self, settings: Settings) -> list[str]:
        backup = storage.backup_note_type(self.mw.col, settings, BACKUP_DIR)
        changes = storage.install_field_mode(self.mw.col, settings)
        self.store.set_meta(storage.FIELD_MODE_INSTALLED, True)
        get_logger().info("Field mode set up (backup: %s): %s", backup, "; ".join(changes) or "no changes")
        return changes

    def _ask(self, message: str) -> bool:
        from aqt.utils import askUser

        return askUser(message, title=TITLE, defaultno=True)

    def _write(self, notes: list, on_done: Callable[[], None]) -> None:
        from aqt.operations import CollectionOp

        CollectionOp(parent=self.mw, op=lambda col: col.update_notes(notes)).success(
            lambda _changes: on_done()
        ).run_in_background()

    def _remind_to_sync(self, settings: Settings, message: str) -> None:
        from aqt.utils import tooltip

        if settings.auto_sync_after_generation:
            tooltip(f"{message} Syncing…")
            self.mw.on_sync_button_clicked()
        else:
            tooltip(f"{message} Sync to see them on your phone.", period=6000)

    # --- after generating ------------------------------------------------

    def ensure_installed(self, settings: Settings, interactive: bool = True) -> bool:
        """Add the field and snippet if missing. Returns True when field mode is ready."""
        if self._note_type_missing(settings):
            return False
        status = storage.field_mode_status(self.mw.col, settings)
        if status.ready:
            self.store.set_meta(storage.FIELD_MODE_INSTALLED, True)
            return True
        if not status.has_field:
            if self.declined_this_session or not interactive:
                return False
            message = FIRST_TIME_MESSAGE.format(field=settings.fields.mnemonic, note_type=settings.note_type)
            if not self._ask(message):
                self.declined_this_session = True
                return False
        self._install(settings)
        return True

    def tag(self, note_ids: Optional[Iterable[int]] = None, on_done: Optional[Callable[[int], None]] = None) -> None:
        """Overlay mode: add the `mnemonic-added` tag (the only change made to notes)."""
        notes = storage.notes_needing_tag(self.mw.col, self.store, note_ids)

        def done() -> None:
            if notes:
                get_logger().info("Tagged %d note(s) %s.", len(notes), storage.MNEMONIC_TAG)
            if on_done:
                on_done(len(notes))

        if notes:
            self._write(notes, done)
        else:
            done()

    def apply(self, note_ids: Optional[Iterable[int]] = None, interactive: bool = True) -> None:
        """Copy stored mnemonics onto the cards, then remind you to sync.

        In overlay mode only the tag is added; the mnemonic shows at review time.
        """
        settings = self.get_settings()
        if not len(self.store):
            return
        if settings.storage_mode == "overlay":
            self.tag(note_ids)
            return
        if not self.ensure_installed(settings, interactive):
            return
        notes = storage.notes_needing_update(self.mw.col, settings, self.store, note_ids)
        if not notes:
            return

        def done() -> None:
            get_logger().info("Wrote %d mnemonic(s) to cards.", len(notes))
            self._remind_to_sync(settings, f"Flag Mnemonics: added {len(notes)} mnemonic(s) to your cards.")

        self._write(notes, done)

    # --- upgrade repair --------------------------------------------------

    def repair(self, manual: bool = False) -> None:
        """Check the field, snippet and every stored mnemonic; fix what's missing.

        Runs on startup (quietly when all is well) and from the Tools menu.
        """
        from aqt.utils import showInfo

        settings = self.get_settings()
        if settings.storage_mode == "overlay":
            if len(self.store):

                def tagged(count: int) -> None:
                    if manual:
                        showInfo(OVERLAY_REPAIR_MESSAGE.format(count=count), title=TITLE)

                self.tag(on_done=tagged)
            elif manual:
                showInfo("No mnemonics have been saved yet, so there's nothing to repair.", title=TITLE)
            return
        if not len(self.store):
            if manual:
                showInfo("No mnemonics have been saved yet, so there's nothing to repair.", title=TITLE)
            return
        was_installed = bool(self.store.meta.get(storage.FIELD_MODE_INSTALLED))
        if not was_installed and not manual:
            # Never set up: the normal first-time question happens when mnemonics are written.
            self.apply()
            return
        if self._note_type_missing(settings):
            return

        col = self.mw.col
        relinked, missing = storage.relink_by_guid(col, self.store)
        report = storage.RepairReport(changes=[], relinked=relinked, missing_notes=missing)
        status = storage.field_mode_status(col, settings)

        if not status.has_field:
            if not manual and self.declined_this_session:
                return
            message = REPAIR_MESSAGE.format(
                field=settings.fields.mnemonic, note_type=settings.note_type, count=len(self.store)
            )
            if not self._ask(message):
                self.declined_this_session = True
                showInfo(storage.RepairReport(changes=[], declined=True).summary(len(self.store)), title=TITLE)
                return
        if not status.ready:
            report.changes = self._install(settings)

        notes = storage.notes_needing_update(col, settings, self.store)
        report.restored = len(notes)

        def done() -> None:
            text = report.summary(len(self.store))
            get_logger().info(text)
            if report.anything_done or manual or report.missing_notes:
                showInfo(text, title=TITLE)
            if report.restored:
                self._remind_to_sync(settings, f"Flag Mnemonics: restored {report.restored} mnemonic(s).")

        if notes:
            self._write(notes, done)
        else:
            done()
