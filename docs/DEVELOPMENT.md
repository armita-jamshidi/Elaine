# Development setup

Develop against a throwaway copy of Anki's data, never your real collection.

## Python version

Anki desktop's official builds ship **Python 3.13** (Anki 26.05 through the current 26.08.1; the Anki repo pins 3.13 in `.python-version`). Anki's launcher can also run on Python 3.10+, so the add-on avoids anything newer than 3.10. Use Python 3.13 locally for tests to match what most users run.

Add-ons can't `pip install` anything, so the add-on itself uses only the standard library. `pytest` is the only dev dependency:

```bash
python3.13 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

## A separate dev copy of Anki

Anki keeps add-ons per data folder, shared by every profile in it, so a second *profile* alone isn't enough isolation: the add-on would load in your real profile too. Instead, give Anki a completely separate data folder with `-b`. It gets its own profiles, collection, and `addons21` folder.

**1. Back up your real collection first.** In your normal Anki: File > Export > "Anki Collection Package (.colpkg)", tick "Include media", and save it somewhere safe. Also check that AnkiWeb has your latest sync. Do this again before the first run on your real profile.

**2. Start Anki with a dev data folder** (Anki must be fully closed first):

| OS | Command |
| --- | --- |
| macOS | `open -n -a Anki --args -b ~/AnkiDev` |
| Windows | `"%LOCALAPPDATA%\Programs\Anki\anki.exe" -b "%USERPROFILE%\AnkiDev"` |
| Linux | `anki -b ~/AnkiDev` |

If your Anki ignores `-b`, set the `ANKI_BASE` environment variable to the same folder instead. You'll know it worked because Anki starts with an empty profile called "User 1" and none of your decks. Rename the profile to `FlagMnemonics-Test` (File > Switch Profile > Rename).

**3. Do not sign in to your real AnkiWeb account in the dev copy.** Syncing it would mix test data with your real collection. Stage 4 covers how to test phone sync safely.

**4. Import a copy of Ultimate Geography.** Download the English `.apkg` from the [Ultimate Geography releases](https://github.com/anki-geo/ultimate-geography/releases) (or from AnkiWeb) and import it with File > Import. To get flag cards past the lapse threshold quickly, use the Browser: select a few flag cards, then Cards > Set Due Date or just review them and press Again several times.

**5. Link the add-on.** Quit Anki, then from the repo root:

```bash
python scripts/link_dev.py ~/AnkiDev
```

This symlinks `src/flag_mnemonics` into `~/AnkiDev/addons21/flag_mnemonics`, so edits in the repo show up after an Anki restart. The script refuses to link into your real Anki data folder. On Windows, symlinks need Developer Mode turned on (Settings > For developers), or run the terminal as administrator.

**6. Check it loaded.** Start Anki with the dev folder again (step 2). Tools > "About Flag Mnemonics" should show the settings it loaded. Tools > Add-ons > Flag Mnemonics > Config opens `config.json` with `config.md` beside it.

## Making some flags "struggle" for testing

The add-on only acts on flag cards with 3 or more lapses. In the dev copy you can fake that from the debug console (Tools > Debug Console, or Ctrl/Cmd+Shift+;). Paste this and press Ctrl/Cmd+Enter:

```python
countries = ["Poland", "Indonesia", "Monaco", "Chad", "Romania"]
for country in countries:
    for cid in mw.col.find_cards(f'deck:"Ultimate Geography" card:"Flag - Country" "Country:{country}"'):
        card = mw.col.get_card(cid)
        card.type = card.queue = 2   # make it a review card
        card.lapses = 3
        mw.col.update_card(card)
print("done")
```

Then use Tools > "Generate mnemonics for struggling flags". It finds those five countries, writes a mnemonic for each in the background, and shows them in a dialog. Restarting Anki, syncing, or pressing Again on a flag card that reaches 3 lapses does the same thing automatically, with a short tooltip instead of a dialog.

## Generating mnemonics

- **Without an API key:** set `"use_mock_api": true` in the add-on config. Every mnemonic is a placeholder starting with `[mock]`, so you can test the whole flow for free.
- **With Claude:** set `claude_api_key` in the add-on config (Tools > Add-ons > Flag Mnemonics > Config) and `use_mock_api` back to `false`. The key stays in `meta.json`, which git ignores.
- Mnemonics are saved to `user_files/mnemonics.json`, keyed by note ID. A note that already has an entry isn't regenerated. To start over in the dev copy, delete that file.
- In field mode (the default), the first time it writes a mnemonic the add-on asks to add a "Mnemonic" field to the note type, and it adds a small box to the back of the flag templates. Before changing the note type it saves a copy to `user_files/backups/`. After that, mnemonics are copied into the field and the notes are tagged `mnemonic-added`. In the dev copy, check the result in the Browser (the Mnemonic field) and by reviewing or previewing a flag card.
- Adding a field means the next sync is a full sync. The dev copy isn't signed in, so that doesn't matter there; see [PHONE_CHECK.md](PHONE_CHECK.md) for doing it on your real profile.

To judge quality without Anki, generate the five sample flags from the command line:

```bash
pip install PyQt6   # optional: renders the SVG flags to PNG, as Anki does
ANTHROPIC_API_KEY=sk-ant-... python scripts/sample_mnemonics.py --out samples.md
python scripts/sample_mnemonics.py --theme "The Office" Poland Indonesia Monaco
```

## Trying the stage 6 actions

In the dev copy, with `"use_mock_api": true` (free) or a real key:

1. **Batch:** make a few flags struggle (see above), then Tools > "Generate mnemonics for struggling flags". A progress window counts through the flags ("Writing mnemonic 2 of 5: Chad"), then a summary lists what was written. Automatic runs (startup, after sync, after Again) don't show this window and stay in the background.
2. **Regenerate:** in the Browser, select one or more flag notes, right-click > "Regenerate mnemonic". The old mnemonic is replaced, and Claude is told it didn't stick so the new one uses a different scene.
3. **Remove:** select notes, right-click > "Remove mnemonic", confirm. The Mnemonic field is emptied, the `mnemonic-added` tag is removed, and the saved copy is deleted. Nothing else on the note changes.
4. **Overlay mode:** set `"storage_mode": "overlay"` in the config and restart. Review or preview a flag card that has a mnemonic: the 🥨 box shows on the answer side. The note type doesn't get a field (in a fresh dev copy), and the notes are only tagged. If a card already shows the box from field mode, overlay mode doesn't add a second one. Switch back to `"field"` afterwards.

Selections that include other note types are fine: those notes are skipped.

## Simulating an Ultimate Geography upgrade

Ultimate Geography upgrades go through CrowdAnki, which resets the note type's templates and styling, can drop fields the deck doesn't define (and their content), and can rewrite tags. The add-on keeps every mnemonic in `user_files/mnemonics.json`, so it can put everything back. To try it in the dev copy, once a few flags have mnemonics on their cards:

1. **Reset the template:** Tools > Manage Note Types > Ultimate Geography > Cards. Pick "Flag - Country", open the Back Template, and delete everything from `<!-- flag-mnemonics:start -->` to `<!-- flag-mnemonics:end -->`. Save.
2. **Drop the field:** in the same window, Fields > select "Mnemonic" > Delete. This also deletes its content from every note.
3. **Rewrite tags:** in the Browser, search `tag:mnemonic-added`, select all, then Notes > Remove Tags > `mnemonic-added`.
4. **Restart Anki.** The add-on asks to re-add the field (with the full-sync steps). Click Yes. A report then lists what it repaired: the field, the box on "Flag - Country", and how many mnemonics it restored.
5. **Check:** preview a flag card; the 🥨 box is back. The Browser search `tag:mnemonic-added` finds them all again.

Only the template step (1) needs no question, since it isn't a schema change. You can also run the same check any time with Tools > "Repair mnemonics after deck upgrade". On startup, the check stays silent when nothing is wrong.

If you use CrowdAnki for the real deck, you can test the real thing in the dev copy: import Ultimate Geography with CrowdAnki, generate a few mnemonics, then import it again from a newer release.

## Where things live

- The add-on's log is in the dev data folder under `logs/addons/flag_mnemonics/`.

- Your edited settings (including API keys) are saved by Anki to `addons21/flag_mnemonics/meta.json`. Through the symlink, that file sits in `src/flag_mnemonics/`, and `.gitignore` keeps it out of git.
- The add-on's own data goes in `src/flag_mnemonics/user_files/`, also ignored by git: `mnemonics.json` (every mnemonic, keyed by note ID, with the note's GUID as a fallback) and `backups/` (a copy of the note type from before each change). Anki preserves this folder across add-on updates.
- Errors from the add-on appear in Anki's error dialog. The debug console (Tools > Debug Console, or Ctrl/Cmd+Shift+;) is handy for poking at `mw.col`.
