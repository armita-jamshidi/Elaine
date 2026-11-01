from flag_mnemonics import display

BACK = "{{FrontSide}}\n<hr id=answer>\n{{Country}}\n"


def test_snippet_is_conditional_and_labeled():
    s = display.template_snippet("Mnemonic")
    assert s.startswith(display.SNIPPET_START) and s.endswith(display.SNIPPET_END)
    assert "{{#Mnemonic}}" in s and "{{/Mnemonic}}" in s and "{{Mnemonic}}" in s
    assert "🥨 Mnemonic" in s
    assert "<style" not in s and "class=" in s  # inline styles only


def test_add_snippet_appends_and_is_idempotent():
    once = display.add_snippet(BACK, "Mnemonic")
    assert once.startswith(BACK.rstrip())
    assert display.has_snippet(once, "Mnemonic")
    assert display.add_snippet(once, "Mnemonic") == once


def test_add_snippet_replaces_old_version():
    old = BACK + "\n" + display.SNIPPET_START + "\nold stuff\n" + display.SNIPPET_END + "\n"
    new = display.add_snippet(old, "Mnemonic")
    assert "old stuff" not in new and new.count(display.SNIPPET_START) == 1


def test_snippet_for_renamed_field():
    t = display.add_snippet(BACK, "Memory hook")
    assert "{{#Memory hook}}" in t
    assert not display.has_snippet(t, "Mnemonic")


def test_remove_snippet_restores_template():
    assert display.remove_snippet(display.add_snippet(BACK, "Mnemonic")) == BACK


def test_field_html_escapes_and_includes_episode_and_image():
    out = display.field_html(
        {"mnemonic": "White <over> red & proud", "episode_title": "The Opposite"},
        image_filename="flagmnem_poland.png",
    )
    assert out.startswith("White &lt;over&gt; red &amp; proud")
    assert "📺 Episode: “The Opposite”" in out
    assert 'src="flagmnem_poland.png"' in out


def test_field_html_minimal():
    assert display.field_html({"mnemonic": "Just this.", "episode_title": None}) == "Just this."
