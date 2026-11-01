"""Field mode against a real Anki collection (skipped if `anki` isn't installed)."""

import json

import pytest

anki_collection = pytest.importorskip("anki.collection")

from flag_mnemonics import display, storage  # noqa: E402
from flag_mnemonics.generator import Mnemonic  # noqa: E402
from flag_mnemonics.settings import Settings  # noqa: E402
from flag_mnemonics.storage import MnemonicStore  # noqa: E402

FIELDS = ["Country", "Country info", "Capital", "Capital info", "Capital hint", "Flag", "Flag similarity", "Map"]
TEMPLATES = ["Country - Capital", "Capital - Country", "Flag - Country", "Map - Country"]
CSS = ".card { font-family: arial; }"
S = Settings()


@pytest.fixture
def col(tmp_path):
    col = anki_collection.Collection(str(tmp_path / "collection.anki2"))
    mm = col.models
    nt = mm.new("Ultimate Geography")
    for name in FIELDS:
        mm.add_field(nt, mm.new_field(name))
    for name in TEMPLATES:
        t = mm.new_template(name)
        t["qfmt"] = f"<div>{name}</div>{{{{Country}}}}{{{{Flag}}}}"
        t["afmt"] = "{{FrontSide}}<hr id=answer>{{Country}}"
        mm.add_template(nt, t)
    nt["css"] = CSS
    mm.add(nt)
    yield col
    col.close()


def add_note(col, country, flag_similarity=""):
    note = col.new_note(col.models.by_name("Ultimate Geography"))
    note["Country"] = country
    note["Capital"] = "Warsaw"
    note["Flag"] = f'<img src="ug-flag-{country.lower()}.svg" />'
    note["Flag similarity"] = flag_similarity
    col.add_note(note, col.decks.id("Ultimate Geography"))
    return note


def flag_card(col, note):
    return next(c for c in note.cards() if c.template()["name"] == "Flag - Country")


def mnemonic(text="White over red, like George in 'The Opposite.'", episode="The Opposite"):
    return Mnemonic(text, "white on top", "prompt", episode, "Seinfeld")


def test_install_adds_field_and_snippet_only(col, tmp_path):
    before = col.models.by_name("Ultimate Geography")
    status = storage.field_mode_status(col, S)
    assert status.note_type_found and not status.has_field
    assert status.templates_missing_snippet == ["Flag - Country"]
    assert status.templates_not_found == ["Country - Flag"]  # Extended-only template

    backup = storage.backup_note_type(col, S, str(tmp_path / "backups"))
    assert json.load(open(backup, encoding="utf-8"))["name"] == "Ultimate Geography"

    changes = storage.install_field_mode(col, S)
    assert len(changes) == 2
    after = col.models.by_name("Ultimate Geography")
    assert [f["name"] for f in after["flds"]] == FIELDS + ["Mnemonic"]
    assert after["css"] == CSS
    for old, new in zip(before["tmpls"], after["tmpls"]):
        assert new["qfmt"] == old["qfmt"]
        if new["name"] == "Flag - Country":
            assert new["afmt"].startswith(old["afmt"]) and display.has_snippet(new["afmt"], "Mnemonic")
        else:
            assert new["afmt"] == old["afmt"]
    assert storage.field_mode_status(col, S).ready
    assert storage.install_field_mode(col, S) == []  # idempotent


def test_adding_field_is_a_schema_change_but_snippet_alone_is_not(col):
    col.db.execute("update col set ls = scm + 1")  # pretend we just synced
    assert storage.needs_schema_change(col, S)
    assert not col.schema_changed()

    nt = col.models.by_name("Ultimate Geography")
    col.models.add_field(nt, col.models.new_field("Mnemonic"))
    col.models.update_dict(nt)
    assert col.schema_changed()  # field added: next sync is a full sync

    col.db.execute("update col set ls = scm + 1")
    assert not storage.needs_schema_change(col, S)
    storage.install_field_mode(col, S)  # now only the template text changes
    assert not col.schema_changed()


def test_existing_note_content_unchanged(col):
    note = add_note(col, "Poland", "Indonesia (flipped)")
    before = dict(note.items())
    storage.install_field_mode(col, S)
    after = col.get_note(note.id)
    assert {k: after[k] for k in before} == before
    assert after["Mnemonic"] == ""


def test_write_and_render_on_answer_side_only(col, tmp_path):
    poland = add_note(col, "Poland")
    monaco = add_note(col, "Monaco")
    storage.install_field_mode(col, S)
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(poland.id, "Poland", mnemonic())

    assert storage.write_mnemonics_to_notes(col, S, store) == [poland.id]
    assert storage.write_mnemonics_to_notes(col, S, store) == []  # nothing new

    note = col.get_note(poland.id)
    assert note.has_tag("mnemonic-added")
    assert note["Mnemonic"].startswith("White over red")
    assert note["Country"] == "Poland"

    card = flag_card(col, note)
    assert "🥨 Mnemonic" not in card.question()
    answer = card.answer()
    assert "🥨 Mnemonic" in answer and "White over red" in answer and "The Opposite" in answer

    other = flag_card(col, col.get_note(monaco.id))
    assert "🥨 Mnemonic" not in other.answer()  # empty field: box hidden

    capital_card = next(c for c in note.cards() if c.template()["name"] == "Country - Capital")
    assert "🥨 Mnemonic" not in capital_card.answer()


def test_write_skips_deleted_notes_and_respects_filter(col, tmp_path):
    poland, chad = add_note(col, "Poland"), add_note(col, "Chad")
    storage.install_field_mode(col, S)
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(poland.id, "Poland", mnemonic())
    store.put(chad.id, "Chad", mnemonic("Chad is darker blue."))
    store.put(999, "Ghost", mnemonic())
    assert storage.write_mnemonics_to_notes(col, S, store, note_ids=[chad.id]) == [chad.id]
    assert sorted(storage.write_mnemonics_to_notes(col, S, store)) == [poland.id]


def test_clear_mnemonic(col, tmp_path):
    poland = add_note(col, "Poland")
    storage.install_field_mode(col, S)
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(poland.id, "Poland", mnemonic())
    storage.write_mnemonics_to_notes(col, S, store)
    storage.clear_mnemonic_from_note(col, S, poland.id)
    note = col.get_note(poland.id)
    assert note["Mnemonic"] == "" and not note.has_tag("mnemonic-added")
    assert "🥨 Mnemonic" not in flag_card(col, note).answer()


def test_custom_field_name_and_template(col, tmp_path):
    s = Settings.from_config({"fields": {"mnemonic": "Memory hook"}, "flag_card_templates": ["Map - Country"]})
    storage.install_field_mode(col, s)
    nt = col.models.by_name("Ultimate Geography")
    assert "Memory hook" in [f["name"] for f in nt["flds"]]
    assert [t["name"] for t in nt["tmpls"] if "flag-mnemonics" in t["afmt"]] == ["Map - Country"]


# --- the Anki-side flow (aqt mocked, real collection) ----------------------


@pytest.fixture
def flow(col, tmp_path, monkeypatch):
    import sys
    from unittest.mock import MagicMock

    from flag_mnemonics import field_mode

    monkeypatch.setattr(field_mode, "BACKUP_DIR", str(tmp_path / "backups"))
    utils = sys.modules["aqt.utils"]
    utils.askUser.reset_mock()
    utils.askUser.return_value = True
    utils.tooltip.reset_mock()
    mw = MagicMock()
    mw.col = col
    store = MnemonicStore(str(tmp_path / "m.json"))
    settings = {"value": Settings()}
    fm = field_mode.FieldMode(mw, lambda: settings["value"], store)
    return fm, store, utils, mw, settings, tmp_path


def test_flow_asks_before_adding_field_then_writes(flow, col):
    fm, store, utils, mw, _, tmp_path = flow
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic())
    fm.apply()
    assert utils.askUser.call_count == 1
    assert "Upload to AnkiWeb" in utils.askUser.call_args.args[0]
    assert col.get_note(poland.id)["Mnemonic"].startswith("White over red")
    assert list((tmp_path / "backups").iterdir())
    assert "Sync to see them on your phone" in utils.tooltip.call_args.args[0]
    mw.on_sync_button_clicked.assert_not_called()

    fm.apply()  # field exists now: no second question
    assert utils.askUser.call_count == 1


def test_flow_declined_keeps_cards_untouched(flow, col):
    fm, store, utils, _, _, _ = flow
    utils.askUser.return_value = False
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic())
    fm.apply()
    fm.apply()
    assert utils.askUser.call_count == 1  # asked once per session
    assert "Mnemonic" not in col.models.by_name("Ultimate Geography")["flds"][-1]["name"]
    assert len(store) == 1  # still saved


def test_flow_auto_sync(flow, col):
    fm, store, _, mw, settings, _ = flow
    settings["value"] = Settings.from_config({"auto_sync_after_generation": True})
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic())
    fm.apply()
    mw.on_sync_button_clicked.assert_called_once()


def test_flow_overlay_mode_leaves_note_type_alone(flow, col):
    fm, store, utils, _, settings, _ = flow
    settings["value"] = Settings.from_config({"storage_mode": "overlay"})
    poland = add_note(col, "Poland")
    store.put(poland.id, "Poland", mnemonic())
    fm.apply()
    utils.askUser.assert_not_called()
    assert storage.field_mode_status(col, settings["value"]).has_field is False
