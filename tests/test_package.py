"""scripts/package.py builds an installable .ankiaddon with no secrets or user data."""

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import package  # noqa: E402


@pytest.fixture
def addon_copy(tmp_path, addon_dir):
    copy = tmp_path / "flag_mnemonics"
    shutil.copytree(addon_dir, copy, ignore=shutil.ignore_patterns("__pycache__"))
    # Things a developer's working copy has that must never ship.
    (copy / "meta.json").write_text('{"config": {"claude_api_key": "sk-ant-secret"}}')
    (copy / "user_files" / "mnemonics.json").write_text("{}")
    (copy / "user_files" / "backups").mkdir()
    (copy / "user_files" / "backups" / "note_type.json").write_text("{}")
    (copy / "__pycache__").mkdir()
    (copy / "__pycache__" / "addon.cpython-313.pyc").write_bytes(b"x")
    return copy


def test_builds_ankiaddon_with_files_at_root(addon_copy, tmp_path):
    target = package.build(addon_copy, tmp_path / "dist")
    assert target.name == "flag_mnemonics-0.1.0.ankiaddon"
    with zipfile.ZipFile(target) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
    assert {"__init__.py", "manifest.json", "config.json", "config.md", "addon.py", "generator.py"} <= names
    assert "user_files/README.txt" in names
    assert manifest["package"] == "flag_mnemonics" and manifest["name"] == "Flag Mnemonics"


def test_leaves_out_secrets_user_data_and_caches(addon_copy, tmp_path):
    with zipfile.ZipFile(package.build(addon_copy, tmp_path / "dist")) as zf:
        names = zf.namelist()
        blob = b"".join(zf.read(n) for n in names)
    assert "meta.json" not in names
    assert not [n for n in names if n.startswith("user_files/") and n != "user_files/README.txt"]
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
    assert b"sk-ant-secret" not in blob


def test_every_source_file_is_packed(addon_dir, tmp_path):
    with zipfile.ZipFile(package.build(addon_dir, tmp_path / "dist")) as zf:
        names = set(zf.namelist())
    sources = {p.name for p in addon_dir.glob("*.py")}
    assert sources <= names


def test_refuses_a_key_in_config(addon_copy, tmp_path):
    config = json.loads((addon_copy / "config.json").read_text())
    config["claude_api_key"] = "sk-ant-oops"
    (addon_copy / "config.json").write_text(json.dumps(config))
    with pytest.raises(package.PackageError, match="Never ship a key"):
        package.build(addon_copy, tmp_path / "dist")


def test_refuses_mock_mode(addon_copy, tmp_path):
    config = json.loads((addon_copy / "config.json").read_text())
    config["use_mock_api"] = True
    (addon_copy / "config.json").write_text(json.dumps(config))
    with pytest.raises(package.PackageError, match="use_mock_api"):
        package.build(addon_copy, tmp_path / "dist")


def test_same_source_same_zip(addon_dir, tmp_path):
    a = package.build(addon_dir, tmp_path / "a").read_bytes()
    b = package.build(addon_dir, tmp_path / "b").read_bytes()
    assert a == b


def test_installed_copy_imports_cleanly_outside_anki(addon_dir, tmp_path):
    """Unzip as Anki would (addons21/<package>/) and import it in a clean Python."""
    target = package.build(addon_dir, tmp_path / "dist")
    addons21 = tmp_path / "addons21"
    with zipfile.ZipFile(target) as zf:
        zf.extractall(addons21 / "flag_mnemonics")
    code = (
        "import sys, compileall; sys.path.insert(0, sys.argv[1]);"
        "import flag_mnemonics, flag_mnemonics.generator, flag_mnemonics.images;"
        "assert compileall.compile_dir(sys.argv[1] + '/flag_mnemonics', quiet=1)"
    )
    subprocess.run([sys.executable, "-I", "-c", code, str(addons21)], check=True)


def test_cli(tmp_path, capsys):
    assert package.main(["--out", str(tmp_path)]) == 0
    assert "Built" in capsys.readouterr().out


# Anki 26.9's manifest schema (aqt/addons.py, AddonManager._manifest_schema).
MANIFEST_TYPES = {
    "package": str,
    "name": str,
    "mod": (int, float),
    "conflicts": list,
    "min_point_version": (int, float),
    "max_point_version": (int, float),
    "branch_index": (int, float),
    "human_version": str,
    "homepage": str,
}


def test_manifest_matches_ankis_schema(addon_dir):
    manifest = json.loads((addon_dir / "manifest.json").read_text())
    assert set(manifest) <= set(MANIFEST_TYPES)
    for key, value in manifest.items():
        assert isinstance(value, MANIFEST_TYPES[key]), key
    assert manifest["package"] == addon_dir.name
    assert manifest["package"].isidentifier()
