import json
import re

from flag_mnemonics.settings import Settings


def test_manifest_is_valid(addon_dir):
    manifest = json.loads((addon_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["package"] == "flag_mnemonics"
    assert manifest["name"] == "Flag Mnemonics"


def test_config_defaults_match_spec(default_config):
    s = Settings.from_config(default_config)
    assert s.theme == "Seinfeld"
    assert s.lapse_threshold == 3
    assert s.deck_name == "Ultimate Geography"
    assert s.note_type == "Ultimate Geography"
    assert s.fields.flag == "Flag"
    assert s.fields.flag_similarity == "Flag similarity"
    assert s.fields.mnemonic == "Mnemonic"
    assert s.storage_mode == "field"
    assert s.images_enabled is False


def test_shipped_config_has_no_keys(default_config):
    assert default_config["claude_api_key"] == ""
    assert default_config["huggingface_api_key"] == ""


def test_config_md_documents_every_key(addon_dir, default_config):
    doc = (addon_dir / "config.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([a-z_]+)`", doc))
    keys = set(default_config) | set(default_config["fields"])
    assert keys <= documented, keys - documented


def test_missing_and_bad_values_fall_back_to_defaults():
    s = Settings.from_config(
        {"lapse_threshold": "lots", "storage_mode": "nonsense", "theme": "", "fields": {"flag": "Image"}}
    )
    assert s.lapse_threshold == 3
    assert s.storage_mode == "field"
    assert s.theme == "Seinfeld"
    assert s.fields.flag == "Image"
    assert s.fields.country == "Country"
    assert Settings.from_config(None) == Settings()


def test_env_var_key_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert Settings.from_config({}).resolved_claude_key() == "from-env"
    assert Settings.from_config({"claude_api_key": "from-config"}).resolved_claude_key() == "from-config"
    assert "Claude API key: set" in Settings.from_config({}).summary()
