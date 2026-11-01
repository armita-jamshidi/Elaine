# Sharing Flag Mnemonics on AnkiWeb (optional)

**Published:** <https://ankiweb.net/shared/info/1050900423> (code `1050900423`), version 0.1.0, supporting Anki 23.10 to 26.9. Uploads are done by you, under your own AnkiWeb account. The rest of this page is the checklist and listing used for that upload, kept for future updates.

## Before you upload

- [ ] PRs for stages 3 to 8 are merged, and the add-on has run for a while on your real profile (after a backup).
- [ ] Real mnemonics look good for the sample flags (Poland, Indonesia, Monaco, Chad, Romania).
- [ ] You've decided on a license and added a `LICENSE` file. AnkiWeb doesn't require one, but people reading the code on GitHub will look for it. If the code is meant to be reusable, MIT is the usual choice for add-ons.
- [ ] `human_version` in `src/flag_mnemonics/manifest.json` is the version you want to show.
- [ ] `python scripts/package.py` builds without complaint. It refuses to build if `config.json` contains an API key or has mock mode on, so a key can't end up in the upload. Your own key lives in `meta.json`, which is never packaged.
- [ ] You've taken two screenshots (see below).

## How the add-on behaves once it's on AnkiWeb

- AnkiWeb installs add-ons into a folder named after a number (the add-on's ID), not `flag_mnemonics`. The add-on finds its config through its own folder name, so this works without changes.
- Updates replace the add-on's files but keep `user_files/`, so everyone's saved mnemonics and note type backups survive updates.
- Users get the default `config.json` with empty keys, and Anki shows `config.md` next to the config editor. Without a key, the add-on shows one clear message explaining where to get one, and nothing else happens.

## Upload steps

1. Sign in at [ankiweb.net](https://ankiweb.net) with your account.
2. Open the add-ons page at <https://ankiweb.net/shared/addons> and choose to upload or share a new add-on. Signed in, AnkiWeb shows the upload form.
3. Fill in the form with the listing below, and attach `dist/flag_mnemonics-<version>.ankiaddon`. AnkiWeb accepts this zip as-is: files at the top level, no wrapping folder.
4. Pick the Anki versions it supports. The minimum is 23.10 (`min_point_version` 231000). It was tested on 26.9.
5. Submit, then open the public page it gives you and check the description and screenshots render properly.
6. Note the add-on's number (in the page URL). People install it with Tools > Add-ons > Get Add-ons and that number. Put the number in the README's Install section.
7. **For updates,** bump `human_version`, rebuild, and upload the new file on the same add-on's page (not as a new add-on), so existing users get it through Check for Updates.

I couldn't open the upload form from here (it needs your login), so field names may differ slightly from these steps. The form shows a preview of the description: check it before you submit.

## Listing

**Title:** Flag Mnemonics: Seinfeld (or any show) mnemonics for flags you keep forgetting

**Tags:** `geography flags mnemonics ultimate-geography ai claude`

**Branch 1 supports:** `23.10` to `26.9` (no `-` prefix, so newer versions can still download it).

**Support page:** https://github.com/armita-jamshidi/yada-yada-flags/issues

**Description.** AnkiWeb descriptions accept basic HTML (paragraphs, bold, links, lists, images); paste this and check the preview:

```html
<b>Keep forgetting the same flags in Ultimate Geography?</b> This add-on writes a short mnemonic for each flag you've missed 3 or more times, themed on a show you know well (Seinfeld by default), and puts it on the back of the card.

<img src="https://raw.githubusercontent.com/armita-jamshidi/yada-yada-flags/main/docs/images/demo.gif" alt="A Poland flag card showing its mnemonic">

<b>What makes it useful</b>
<ul>
<li>Each mnemonic encodes what the flag actually looks like, and what tells it apart from its look-alikes (Poland vs. Indonesia vs. Monaco, Chad vs. Romania). It uses the deck's own "Flag similarity" notes.</li>
<li>Mnemonics go into a "Mnemonic" field, so they sync to <b>AnkiMobile and AnkiDroid</b> with no add-on needed on your phone. Study on your phone as usual, and open desktop Anki now and then to catch up.</li>
<li>Works in the background: after a sync, on startup, and when you press Again on a flag for the 3rd time. Anki stays responsive while it writes.</li>
<li>Survives Ultimate Geography updates: if an update removes the field or the box, the add-on puts everything back from its own saved copy.</li>
<li>Browser right-click: Regenerate or Remove a mnemonic. Tools menu: write mnemonics for every struggling flag at once.</li>
<li>Optional: an original illustration for each mnemonic (objects and places only, never people), or desktop-only overlay mode that doesn't change your note type.</li>
</ul>

<b>You need</b>
<ul>
<li>The <a href="https://github.com/anki-geo/ultimate-geography">Ultimate Geography</a> deck. Note type and field names are configurable for other languages and editions.</li>
<li>Your own Claude API key from <a href="https://console.anthropic.com">console.anthropic.com</a>, pasted into the add-on's config. Each mnemonic is one small request, billed to your key. Only the flag, the country name and the look-alike notes are sent.</li>
<li>Optional, for illustrations: a Hugging Face token.</li>
</ul>

<b>First run.</b> Adding the Mnemonic field is a change to the note type, so your next sync is a one-way full sync. The add-on asks first and shows the exact steps: sync your phone, click Yes, upload from desktop, download on the phone. Please back up your collection before installing any add-on that edits a note type (File > Export > Collection Package).

Source, docs and issue tracker: <a href="https://github.com/armita-jamshidi/yada-yada-flags">github.com/armita-jamshidi/yada-yada-flags</a>

Credits: Ultimate Geography by the anki-geo contributors (this add-on doesn't include any of its images); mnemonics by Claude (Anthropic); illustrations by FLUX.1-schnell (Black Forest Labs, Apache 2.0) via Hugging Face. Not affiliated with Seinfeld or its makers.
```

The GIF link points at `main`, so it only works once the stage 8 PR is merged.

## Screenshots to take

AnkiWeb shows the description's images, so the GIF covers the main one. Two more help, both from your dev copy with real (not `[mock]`) mnemonics:

1. **The back of a flag card on your phone,** showing the 🥨 box (light or dark mode).
2. **The Browser right-click menu** with "Regenerate mnemonic" and "Remove mnemonic" visible.

Put them in `docs/images/` and add `<img>` lines for them to the description.
