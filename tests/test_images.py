"""Illustrations: request shape, safety suffix, errors, and saving to media."""

import base64
import json
import re

import pytest

from fakes import FakeCard, FakeCollection, ug_note
from flag_mnemonics import images, pipeline
from flag_mnemonics.generator import mock_transport as claude_mock
from flag_mnemonics.pipeline import build_jobs, run_jobs, save_images
from flag_mnemonics.settings import Settings
from flag_mnemonics.storage import MnemonicStore
from flag_mnemonics.triggers import StrugglingCard

PNG = images.mock_transport("hf-inference", {}, "")[2]
ON = Settings.from_config({"images_enabled": True, "huggingface_api_key": "hf_test"})


def recording(responses):
    calls = []

    def transport(url, body, key):
        calls.append((url, body, key))
        return responses.pop(0)

    return transport, calls


def test_prompt_forbids_people_and_text():
    prompt = images.build_prompt("A white-over-red flag on a diner booth  next to a marble rye")
    assert prompt.startswith("A white-over-red flag on a diner booth next to a marble rye.")
    for phrase in ("no people", "no actors", "no likeness of any real person", "no text"):
        assert phrase in prompt


def test_nscale_request_matches_inference_client():
    ok = (200, "application/json", json.dumps({"data": [{"b64_json": base64.b64encode(PNG).decode()}]}).encode())
    transport, calls = recording([ok])
    assert images.generate_image("a flag", "hf_x", transport) == PNG
    url, body, key = calls[0]
    assert url == "https://router.huggingface.co/nscale/v1/images/generations"
    assert body["model"] == "black-forest-labs/FLUX.1-schnell"
    assert body["response_format"] == "b64_json"
    assert body["size"] == "512x512"
    assert key == "hf_x"


def test_falls_back_to_hf_inference():
    transport, calls = recording([(404, "application/json", b'{"error": "Model not supported"}'), (200, "image/png", PNG)])
    assert images.generate_image("a flag", "hf_x", transport) == PNG
    assert calls[1][0] == "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    assert calls[1][1]["inputs"].startswith("a flag.")


def test_bad_token_stops_without_trying_others():
    transport, calls = recording([(401, "application/json", b'{"error": "Invalid credentials"}')])
    with pytest.raises(images.ImageError, match="token was rejected"):
        images.generate_image("a flag", "hf_x", transport)
    assert len(calls) == 1


def test_missing_key():
    with pytest.raises(images.MissingHfKeyError, match="huggingface_api_key"):
        images.generate_image("a flag", "", images.mock_transport)


def test_not_an_image_is_an_error():
    transport, _ = recording([(200, "image/png", b"<html>"), (200, "image/png", b"<html>")])
    with pytest.raises(images.ImageError):
        images.generate_image("a flag", "hf_x", transport)


def test_media_filename_and_ownership():
    name = images.media_filename(42, PNG)
    assert re.fullmatch(r"flagmnem_42_[0-9a-f]{10}\.png", name)
    assert images.is_addon_file(name)
    assert not images.is_addon_file("ug-flag-poland.svg")
    assert not images.is_addon_file("flagmnem_../x.png")


def test_images_module_is_stdlib_only():
    source = (pipeline.os.path.dirname(images.__file__) + "/images.py")
    text = open(source, encoding="utf-8").read()
    imported = set(re.findall(r"^(?:from|import) (\w+)", text, re.MULTILINE))
    assert imported <= {"__future__", "base64", "hashlib", "json", "time", "urllib", "typing"}


# --- pipeline ------------------------------------------------------------


class Media:
    def __init__(self):
        self.files, self.trashed = {}, []

    def dir(self):
        return ""

    def write_data(self, name, data):
        self.files[name] = data
        return name

    def trash_files(self, names):
        self.trashed.extend(names)


def setup(tmp_path):
    poland = ug_note(10, "Poland")
    col = FakeCollection([FakeCard(1, poland, 4)])
    col.media = Media()
    store = MnemonicStore(str(tmp_path / "m.json"))
    cards = [StrugglingCard(1, 10, "Poland", 4, "Flag - Country")]
    return col, store, cards


def test_off_by_default(tmp_path):
    col, store, cards = setup(tmp_path)
    calls = []
    result = run_jobs(
        build_jobs(col, Settings(), cards, store), Settings(), store, "t",
        transport=claude_mock, image_transport=lambda *a: calls.append(a),
    )
    assert not result.images and not calls


def test_picture_is_saved_and_shown(tmp_path):
    col, store, cards = setup(tmp_path)
    result = run_jobs(build_jobs(col, ON, cards, store), ON, store, "t", transport=claude_mock, image_transport=images.mock_transport)
    [name] = save_images(col, store, result)
    assert col.media.files[name] == PNG
    assert store.get(10)["image"] == name
    assert MnemonicStore(store.path).get(10)["image"] == name  # saved to disk
    from flag_mnemonics import display

    assert f'<img src="{name}"' in display.field_html(store.get(10))


def test_image_failure_keeps_mnemonic(tmp_path, monkeypatch):
    col, store, cards = setup(tmp_path)
    bad = lambda url, body, key: (500, "text/plain", b"down")  # noqa: E731
    monkeypatch.setattr(images.time, "sleep", lambda s: None)
    result = run_jobs(build_jobs(col, ON, cards, store), ON, store, "t", transport=claude_mock, image_transport=bad)
    assert len(result.written) == 1 and 10 in store
    assert result.image_errors and "illustration" in result.summary()


def test_missing_hf_key_is_flagged_once(tmp_path):
    col, store, cards = setup(tmp_path)
    settings = Settings.from_config({"images_enabled": True})
    import os

    os.environ.pop("HF_TOKEN", None)
    result = run_jobs(build_jobs(col, settings, cards, store), settings, store, "t", transport=claude_mock)
    assert result.missing_hf_key and len(result.written) == 1


def test_regenerate_replaces_and_deletes_old_picture(tmp_path):
    col, store, cards = setup(tmp_path)
    first = run_jobs(build_jobs(col, ON, cards, store), ON, store, "t", transport=claude_mock, image_transport=images.mock_transport)
    [old] = save_images(col, store, first)

    other_png = PNG + b"\x00"  # different bytes -> different name
    again = run_jobs(
        build_jobs(col, ON, cards, store, force=True), ON, store, "t",
        transport=claude_mock, image_transport=lambda u, b, k: (404, "", b"") if "nscale" in u else (200, "image/png", other_png),
    )
    [new] = save_images(col, store, again)
    assert new != old
    assert col.media.trashed == [old]
    assert store.get(10)["image"] == new


def test_regenerate_with_pictures_off_deletes_old_picture(tmp_path):
    col, store, cards = setup(tmp_path)
    first = run_jobs(build_jobs(col, ON, cards, store), ON, store, "t", transport=claude_mock, image_transport=images.mock_transport)
    [old] = save_images(col, store, first)
    again = run_jobs(build_jobs(col, Settings(), cards, store, force=True), Settings(), store, "t", transport=claude_mock)
    save_images(col, store, again)
    assert col.media.trashed == [old]
    assert "image" not in store.get(10)


def test_mock_mode_draws_placeholder(tmp_path):
    col, store, cards = setup(tmp_path)
    settings = Settings.from_config({"images_enabled": True, "use_mock_api": True, "huggingface_api_key": "x"})
    result = run_jobs(build_jobs(col, settings, cards, store), settings, store, "t")
    assert result.images[0][1] == PNG
