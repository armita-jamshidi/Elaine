import json

import pytest

from flag_mnemonics.generator import Mnemonic
from flag_mnemonics.storage import MnemonicStore


def m(text, detail="d"):
    return Mnemonic(mnemonic=text, distinguishing_detail=detail, image_prompt="p", episode_title=None, theme="Seinfeld")


def test_put_get_persist(tmp_path):
    path = tmp_path / "user_files" / "mnemonics.json"
    store = MnemonicStore(str(path))
    store.put(123, "Poland", m("white over red"))
    assert 123 in store and len(store) == 1

    again = MnemonicStore(str(path))
    entry = again.get(123)
    assert entry["country"] == "Poland" and entry["mnemonic"] == "white over red"
    assert "warnings" not in entry
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 1 and "123" in raw["mnemonics"]


def test_remove(tmp_path):
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(1, "Chad", m("x"))
    assert store.remove(1) and not store.remove(1)
    assert MnemonicStore(str(tmp_path / "m.json")).get(1) is None


def test_prior_mnemonics_newest_first(tmp_path, monkeypatch):
    import flag_mnemonics.storage as storage

    clock = iter([100, 200])
    monkeypatch.setattr(storage.time, "time", lambda: next(clock))
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(1, "Chad", m("chad", "darker blue"))
    store.put(2, "Romania", m("romania"))
    prior = store.prior_mnemonics()
    assert [p.country for p in prior] == ["Romania", "Chad"]
    assert prior[1].distinguishing_detail == "darker blue"


def test_damaged_file_is_not_overwritten(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        MnemonicStore(str(path))
    assert path.read_text(encoding="utf-8") == "{not json"


def test_unicode_round_trip(tmp_path):
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(5, "Côte d'Ivoire", m("orange-white-green 🥨"))
    assert MnemonicStore(str(tmp_path / "m.json")).get(5)["mnemonic"] == "orange-white-green 🥨"
