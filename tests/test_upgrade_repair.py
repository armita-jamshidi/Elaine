"""Simulated Ultimate Geography upgrade, against a real Anki collection.

A CrowdAnki upgrade replaces the note type's templates and CSS with the
deck's versions, can drop fields the deck doesn't define (with their
content), and rewrites tags. These tests do that to a collection that has
mnemonics, then check that repair puts everything back from mnemonics.json.
"""

import sys
from unittest.mock import MagicMock

import pytest

anki_collection = pytest.importorskip("anki.collection")

from flag_mnemonics import display, field_mode, storage  # noqa: E402
from flag_mnemonics.generator import Mnemonic  # noqa: E402
from flag_mnemonics.settings import Settings  # noqa: E402
from flag_mnemonics.storage import MnemonicStore  # noqa: E402

FIELDS = ["Country", "Country info", "Capital", "Capital info", "Capital hint", "Flag", "Flag similarity", "Map"]
TEMPLATES = ["Country - Capital", "Capital - Country", "Flag - Country", "Map - Country"]
ORIGINAL_BACK = "{{FrontSide}}<hr id=answer>{{Country}}"
COUNTRIES = ["Poland", "Indonesia", "Monaco", "Chad", "Romania"]
S = Settings()


@pytest.fixture
def env(tmp_path, monkeypatch):
    col = anki_collection.Collection(str(tmp_path / "collection.anki2"))
    mm = col.models
    nt = mm.new("Ultimate Geography")
    for name in FIELDS:
        mm.add_field(nt, mm.new_field(name))
    for name in TEMPLATES:
        t = mm.new_template(name)
        t["qfmt"] = f"<div>{name}</div>{{{{Country}}}}{{{{Flag}}}}"
        t["afmt"] = ORIGINAL_BACK
        mm.add_template(nt, t)
    mm.add(nt)

    store = MnemonicStore(str(tmp_path / "user_files" / "mnemonics.json"))
    notes = {}
    for country in COUNTRIES:
        note = col.new_note(col.models.by_name("Ultimate Geography"))
        note["Country"] = country
        note["Flag"] = f'<img src="ug-flag-{country.lower()}.svg" />'
        note.tags = ["UG::Europe"]
        col.add_note(note, col.decks.id("Ultimate Geography"))
        notes[country] = note.id
        store.put(note.id, country, Mnemonic(f"{country} mnemonic", "detail", "p", "The Opposite"), guid=note.guid)

    monkeypatch.setattr(field_mode, "BACKUP_DIR", str(tmp_path / "backups"))
    utils = sys.modules["aqt.utils"]
    for name in ("askUser", "showInfo", "showWarning", "tooltip"):
        getattr(utils, name).reset_mock()
    utils.askUser.return_value = True
    mw = MagicMock()
    mw.col = col
    fm = field_mode.FieldMode(mw, lambda: S, store)
    fm.apply()  # first-time setup: asks once, writes all five
    utils.askUser.reset_mock()
    utils.showInfo.reset_mock()
    yield col, store, fm, utils, notes
    col.close()


def on_cards(col, notes):
    out = {}
    for country, nid in notes.items():
        note = col.get_note(nid)
        card = next(c for c in note.cards() if c.template()["name"] == "Flag - Country")
        out[country] = (
            note["Mnemonic"] if "Mnemonic" in note else None,
            note.has_tag("mnemonic-added"),
            f"{country} mnemonic" in card.answer(),
        )
    return out


def all_good(col, notes):
    return all(v[1] and v[2] and v[0].startswith(f"{c} mnemonic") for c, v in on_cards(col, notes).items())


def simulate_upgrade(col, *, drop_field=True, reset_tags=True):
    nt = col.models.by_name("Ultimate Geography")
    for t in nt["tmpls"]:
        t["afmt"] = ORIGINAL_BACK  # templates reset to the deck's version
    nt["css"] = ".card { color: navy; }"
    if drop_field:
        field = next(f for f in nt["flds"] if f["name"] == "Mnemonic")
        col.models.remove_field(nt, field)
    col.models.update_dict(nt)
    if reset_tags:
        for nid in col.find_notes(""):
            note = col.get_note(nid)
            note.tags = ["UG::Europe"]
            col.update_note(note)


def test_setup_worked(env):
    col, store, _, _, notes = env
    assert all_good(col, notes)
    assert store.meta[storage.FIELD_MODE_INSTALLED] is True


def test_full_upgrade_is_repaired_on_startup(env):
    col, store, fm, utils, notes = env
    simulate_upgrade(col)
    assert not any(v[2] for v in on_cards(col, notes).values())  # mnemonics gone from cards

    fm.repair()  # what runs on profile open

    assert utils.askUser.call_count == 1
    assert "probably because a deck upgrade removed it" in utils.askUser.call_args.args[0]
    assert "restore all 5 saved mnemonic(s)" in utils.askUser.call_args.args[0]
    assert all_good(col, notes)
    report = utils.showInfo.call_args.args[0]
    assert 'Added the "Mnemonic" field' in report
    assert 'Added the mnemonic box to the back of "Flag - Country"' in report
    assert "Restored 5 mnemonic(s)" in report
    # The upgrade's own changes are kept.
    nt = col.models.by_name("Ultimate Geography")
    assert nt["css"] == ".card { color: navy; }"
    assert [f["name"] for f in nt["flds"]] == FIELDS + ["Mnemonic"]


def test_template_only_reset_needs_no_question(env):
    col, _, fm, utils, notes = env
    simulate_upgrade(col, drop_field=False, reset_tags=False)
    assert not any(v[2] for v in on_cards(col, notes).values())  # box gone, field content kept

    fm.repair()

    utils.askUser.assert_not_called()  # no schema change, no full sync
    assert all_good(col, notes)
    report = utils.showInfo.call_args.args[0]
    assert "mnemonic box" in report and "Restored" not in report


def test_tags_only_reset(env):
    col, _, fm, utils, notes = env
    for nid in notes.values():
        note = col.get_note(nid)
        note.remove_tag("mnemonic-added")
        col.update_note(note)
    fm.repair()
    assert all_good(col, notes)
    assert "Restored 5 mnemonic(s)" in utils.showInfo.call_args.args[0]


def test_nothing_to_do_is_silent_on_startup_but_reported_manually(env):
    col, _, fm, utils, notes = env
    fm.repair()
    utils.showInfo.assert_not_called()
    fm.repair(manual=True)
    assert "Everything is in place: 5 mnemonic(s)" in utils.showInfo.call_args.args[0]
    assert all_good(col, notes)


def test_declining_changes_nothing_and_keeps_data(env):
    col, store, fm, utils, notes = env
    simulate_upgrade(col)
    utils.askUser.return_value = False
    fm.repair()
    assert "Repair skipped" in utils.showInfo.call_args.args[0]
    assert "Mnemonic" not in [f["name"] for f in col.models.by_name("Ultimate Geography")["flds"]]
    assert len(store) == 5
    fm.repair()  # not asked again this session on startup
    assert utils.askUser.call_count == 1
    utils.askUser.return_value = True
    fm.repair(manual=True)  # but the Tools action always asks
    assert all_good(col, notes)


def test_recreated_notes_are_matched_by_guid(env):
    col, store, fm, utils, notes = env
    old_id = notes["Chad"]
    guid = col.get_note(old_id).guid
    col.remove_notes([old_id])
    note = col.new_note(col.models.by_name("Ultimate Geography"))
    note["Country"] = "Chad"
    note.guid = guid  # same note re-imported under a new ID
    col.add_note(note, col.decks.id("Ultimate Geography"))
    notes["Chad"] = note.id

    fm.repair()

    assert store.get(note.id) is not None and store.get(old_id) is None
    assert all_good(col, notes)
    assert "Matched 1 mnemonic(s)" in utils.showInfo.call_args.args[0]


def test_deleted_notes_are_reported_not_lost(env):
    col, store, fm, utils, notes = env
    col.remove_notes([notes.pop("Romania")])
    fm.repair(manual=True)
    assert "1 saved mnemonic(s) belong to notes that no longer exist (Romania)" in utils.showInfo.call_args.args[0]
    assert len(store) == 5
