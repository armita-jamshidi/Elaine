"""Browser right-click menu: "Regenerate mnemonic" and "Remove mnemonic".

Both act on the selected notes of the Ultimate Geography note type; anything
else in the selection is ignored.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from . import storage
from .field_mode import FieldMode
from .pipeline import BatchResult, Pipeline
from .settings import Settings
from .triggers import StrugglingCard, get_logger, strip_html

TITLE = "Flag Mnemonics"
REGENERATE_LABEL = "Regenerate mnemonic"
REMOVE_LABEL = "Remove mnemonic"


def flag_note_ids(col: Any, settings: Settings, note_ids: Iterable[int]) -> list[int]:
    """The selected notes that belong to the configured note type."""
    result = []
    for note_id in note_ids:
        try:
            note = col.get_note(note_id)
        except Exception:
            continue
        if note.note_type()["name"] == settings.note_type:
            result.append(note_id)
    return result


def regenerate_inputs(col: Any, settings: Settings, note_ids: Iterable[int]) -> list[StrugglingCard]:
    """What the pipeline needs to (re)write a mnemonic for each note."""
    inputs = []
    for note_id in note_ids:
        note = col.get_note(note_id)
        field = settings.fields.country
        country = strip_html(note[field]) if field in note else ""
        inputs.append(StrugglingCard(card_id=0, note_id=note_id, country=country, lapses=0, template=""))
    return inputs


def remove_mnemonics(col: Any, settings: Settings, store: storage.MnemonicStore, note_ids: Iterable[int]) -> list[Any]:
    """Forget the stored mnemonics and return the notes to save (field cleared, tag removed)."""
    note_ids = list(note_ids)
    for note_id in note_ids:
        store.remove(note_id)
    return storage.notes_to_clear(col, settings, note_ids)


class BrowserActions:
    def __init__(
        self,
        mw: Any,
        get_settings: Callable[[], Settings],
        generation: Pipeline,
        field_mode: FieldMode,
        after_generation: Callable[[BatchResult], None],
    ) -> None:
        self.mw = mw
        self.get_settings = get_settings
        self.generation = generation
        self.field_mode = field_mode
        self.after_generation = after_generation

    def add_to_menu(self, browser: Any, menu: Any) -> None:
        menu.addSeparator()
        regenerate = menu.addAction(REGENERATE_LABEL)
        regenerate.triggered.connect(lambda *_: self.regenerate(browser))
        remove = menu.addAction(REMOVE_LABEL)
        remove.triggered.connect(lambda *_: self.remove(browser))

    def _selected(self, browser: Any) -> list[int]:
        from aqt.utils import tooltip

        settings = self.get_settings()
        note_ids = flag_note_ids(self.mw.col, settings, browser.selected_notes())
        if not note_ids:
            tooltip(f'{TITLE}: select one or more "{settings.note_type}" notes first.', parent=browser)
        return note_ids

    def regenerate(self, browser: Any) -> None:
        from aqt.utils import showInfo, tooltip

        note_ids = self._selected(browser)
        if not note_ids:
            return
        inputs = regenerate_inputs(self.mw.col, self.get_settings(), note_ids)

        def done(result: BatchResult) -> None:
            self.after_generation(result)
            if result.failed:
                showInfo(result.summary(), title=TITLE, parent=browser)
            elif result.written and len(result.written) == 1:
                _, country, mnemonic = result.written[0]
                showInfo(f"New mnemonic for {country}:\n\n{mnemonic.mnemonic}", title=TITLE, parent=browser)

        started = self.generation.generate(
            inputs, "Regenerated from the Browser", on_done=done, show_progress=True, force=True
        )
        if not started:
            tooltip(f"{TITLE}: mnemonics are already being written. Try again in a moment.", parent=browser)

    def remove(self, browser: Any) -> None:
        from aqt.operations import CollectionOp
        from aqt.utils import askUser, tooltip

        note_ids = self._selected(browser)
        if not note_ids:
            return
        stored = [n for n in note_ids if n in self.generation.store]
        message = (
            f"Remove the mnemonic from {len(note_ids)} note(s)? This deletes "
            f"{len(stored)} saved mnemonic(s), empties the Mnemonic field and removes the "
            f"{storage.MNEMONIC_TAG} tag. Other fields aren't touched.\n\n"
            "A flag you keep forgetting will get a new mnemonic the next time it's found."
        )
        if not askUser(message, parent=browser, title=TITLE, defaultno=True):
            return
        settings = self.get_settings()
        notes = remove_mnemonics(self.mw.col, settings, self.generation.store, note_ids)
        get_logger().info("Removed mnemonics from notes %s", note_ids)

        def done(_changes: Any) -> None:
            tooltip(f"{TITLE}: removed {len(stored)} mnemonic(s).", parent=browser)

        if notes:
            CollectionOp(parent=browser, op=lambda col: col.update_notes(notes)).success(done).run_in_background()
        else:
            done(None)


def register(actions: BrowserActions) -> None:
    from aqt import gui_hooks

    gui_hooks.browser_will_show_context_menu.append(actions.add_to_menu)
