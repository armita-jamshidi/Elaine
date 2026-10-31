import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "link_dev.py"
spec = importlib.util.spec_from_file_location("link_dev", SCRIPT)
link_dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link_dev)


def test_links_into_dev_folder(tmp_path):
    target = link_dev.link(tmp_path / "AnkiDev")
    assert target.is_symlink()
    assert (target / "manifest.json").exists()
    # Running twice is harmless.
    link_dev.link(tmp_path / "AnkiDev")


def test_refuses_real_anki_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(link_dev, "default_anki_base", lambda: tmp_path / "Anki2")
    with pytest.raises(SystemExit):
        link_dev.link(tmp_path / "Anki2")
