"""Browser right-click actions, overlay tagging, and regenerate, against a real
Anki collection (skipped if `anki` isn't installed)."""

import sys
from unittest.mock import MagicMock

import pytest

pytest.importorskip("anki.collection")

from test_field_mode import add_note, col, flag_card, mnemonic  # noqa: E402,F401

from flag_mnemonics import browser_actions, display, field_mode, overlay, storage  # noqa: E402
from flag_mnemonics.pipeline import Pipeline  # noqa: E402
from flag_mnemonics.settings import Settings  # noqa: E402

MOCK = Settings.from_config({"use_mock_api": True})
OVERLAY = Settings.from_config({"use_mock_api": True, "storage_mode": "overlay"})


@pytest.fixture
def env(col, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(field_mode, "BACKUP_DIR", str(tmp_path / "backups"))
    utils = sys.modules["aqt.utils"]
    for name in ("askUser", "tooltip", "showInfo"):
        getattr(utils, name).reset_mock()
    utils.askUser.return_value = True
    settings = {"value": MOCK}
    get = lambda: settings["value"]  # noqa: E731
    mw = MagicMock()
    mw.col = col
    mw.taskman.run_on_main.side_effect = lambda closure: closure()
    generation = Pipeline(mw, get, str(tmp_path / "m.json"))
    fm = field_mode.FieldMode(mw, get, generation.store)

    def after(result):
        if result.written:
            fm.apply([n for n, _, _ in result.written])

    actions = browser_actions.BrowserActions(mw, get, generation, fm, after)
    browser = MagicMock()
    browser.col = col
    return actions, browser, generation.store, utils, settings, mw


def test_menu_has_both_items(env):
    actions, browser, *_ = env
    menu = MagicMock()
    actions.add_to_menu(browser, menu)
    labels = [c.args[0] for c in menu.addAction.call_args_list]
    assert labels == ["Regenerate mnemonic", "Remove mnemonic"]


def test_other_note_types_are_ignored(env, col):  # noqa: F811
    actions, browser, store, utils, *_ = env
    basic = col.new_note(col.models.by_name("Basic"))
    basic["Front"] = "x"
    col.add_note(basic, 1)
    browser.selected_notes.return_value = [basic.id]
    actions.regenerate(browser)
    assert len(store) == 0
    assert "select one or more" in utils.tooltip.call_args.args[0]


def test_regenerate_writes_new_mnemonic_to_card(env, col):  # noqa: F811
    actions, browser, store, utils, *_ = env
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic("Old joke."))
    browser.selected_notes.return_value = [poland.id]
    actions.regenerate(browser)
    entry = store.get(poland.id)
    assert entry["mnemonic"].startswith("[mock] Poland")
    note = col.get_note(poland.id)
    assert note["Mnemonic"].startswith("[mock] Poland")
    assert note.has_tag(storage.MNEMONIC_TAG)
    assert "New mnemonic for Poland" in utils.showInfo.call_args.args[0]


def test_regenerate_tells_the_model_what_to_replace(env, col, monkeypatch):  # noqa: F811
    actions, browser, store, *_ = env
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic("Old joke about Kramer."))
    bodies = []
    from flag_mnemonics import pipeline
    from flag_mnemonics.generator import mock_transport

    real_run = pipeline.run_jobs

    def spy(jobs, settings, st, reason, transport=None, on_progress=None):
        def t(body, key):
            bodies.append(body)
            return mock_transport(body, key)

        return real_run(jobs, settings, st, reason, transport=t, on_progress=on_progress)

    monkeypatch.setattr(pipeline, "run_jobs", spy)
    browser.selected_notes.return_value = [poland.id]
    actions.regenerate(browser)
    text = bodies[0]["messages"][0]["content"][-1]["text"]
    assert "didn't stick: Old joke about Kramer." in text


def test_regenerate_several_shows_progress(env, col):  # noqa: F811
    actions, browser, store, _, _, mw = env
    ids = [add_note(col, c).id for c in ("Poland", "Chad", "Romania")]
    browser.selected_notes.return_value = ids
    actions.regenerate(browser)
    assert len(store) == 3
    labels = [c.kwargs["label"] for c in mw.progress.update.call_args_list]
    assert labels == [
        "Writing mnemonic 1 of 3: Poland",
        "Writing mnemonic 2 of 3: Chad",
        "Writing mnemonic 3 of 3: Romania",
    ]


def test_remove_clears_field_tag_and_saved_copy(env, col):  # noqa: F811
    actions, browser, store, utils, *_ = env
    poland = add_note(col, "Poland")
    chad = add_note(col, "Chad")
    for note in (poland, chad):
        store.put(note.id, note["Country"], mnemonic())
    actions.field_mode.apply()
    assert col.get_note(poland.id)["Mnemonic"]

    browser.selected_notes.return_value = [poland.id]
    actions.remove(browser)
    note = col.get_note(poland.id)
    assert note["Mnemonic"] == ""
    assert not note.has_tag(storage.MNEMONIC_TAG)
    assert poland.id not in store
    assert note["Country"] == "Poland" and note["Capital"] == "Warsaw"
    # Chad is untouched.
    assert chad.id in store and col.get_note(chad.id)["Mnemonic"]
    # The saved copy on disk is gone too.
    from flag_mnemonics.storage import MnemonicStore

    assert poland.id not in MnemonicStore(store.path)


def test_remove_asks_first(env, col):  # noqa: F811
    actions, browser, store, utils, *_ = env
    utils.askUser.return_value = False
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic())
    browser.selected_notes.return_value = [poland.id]
    actions.remove(browser)
    assert poland.id in store


def test_overlay_mode_tags_but_leaves_note_type_alone(env, col):  # noqa: F811
    actions, browser, store, utils, settings, _ = env
    settings["value"] = OVERLAY
    poland = add_note(col, "Poland")
    browser.selected_notes.return_value = [poland.id]
    actions.regenerate(browser)
    note = col.get_note(poland.id)
    assert note.has_tag(storage.MNEMONIC_TAG)
    assert "Mnemonic" not in note
    assert storage.field_mode_status(col, OVERLAY).has_field is False
    utils.askUser.assert_not_called()


def test_overlay_repair_puts_tags_back(env, col):  # noqa: F811
    actions, _, store, utils, settings, _ = env
    settings["value"] = OVERLAY
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic())
    actions.field_mode.repair(manual=True)
    assert col.get_note(poland.id).has_tag(storage.MNEMONIC_TAG)
    assert "1 note(s)" in utils.showInfo.call_args.args[0]


def test_overlay_on_a_real_card(env, col, tmp_path):  # noqa: F811
    _, _, store, *_ = env
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic())
    card = flag_card(col, poland)
    out = overlay.add_overlay(card.answer(), card, "reviewAnswer", OVERLAY, store)
    assert display.LABEL in out and "White over red" in out
    other = next(c for c in poland.cards() if c.template()["name"] == "Country - Capital")
    assert overlay.add_overlay("a", other, "reviewAnswer", OVERLAY, store) == "a"
