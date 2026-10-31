**Flag Mnemonics settings**

Changes take effect after you restart Anki.

- `theme`: The show or topic the mnemonics riff on. Default `"Seinfeld"`. Try `"The Office"`, `"Star Wars"`, or anything else. Only new mnemonics use the new theme.
- `lapse_threshold`: How many times you must miss (press Again on) a flag card before it gets a mnemonic. Default `3`.
- `deck_name`: The deck to search for flag cards. Subdecks are included. Default `"Ultimate Geography"`.
- `note_type`: The note type of your flag notes. Default `"Ultimate Geography"`.
- `fields`: Which fields on that note type hold what.
    - `country`: the country name. Default `"Country"`.
    - `flag`: the flag image. Default `"Flag"`.
    - `flag_similarity`: notes about look-alike flags. Leave it as `""` if your deck has no such field. Default `"Flag similarity"`.
    - `mnemonic`: the field the add-on creates and fills. Default `"Mnemonic"`. The add-on never changes any other field.
- `flag_card_templates`: Names of the card templates that count as flag cards. Default `["Flag - Country", "Country - Flag"]` (the second only exists in the Extended version of Ultimate Geography).
- `storage_mode`: Where mnemonics are shown.
    - `"field"` (default): written into the `Mnemonic` field and shown by a small snippet on the back of flag cards. Syncs to AnkiMobile and AnkiDroid.
    - `"overlay"`: shown only on desktop at review time. Nothing on the cards changes. Use this if you never study on your phone.
- `images_enabled`: Generate an original illustration for each mnemonic with Hugging Face. Default `false`. Needs `huggingface_api_key`.
- `catch_up_on_startup`: Look for struggling flags when Anki starts. Default `true`.
- `catch_up_after_sync`: Look for struggling flags after each sync, so misses from your phone are picked up. Default `true`.
- `auto_sync_after_generation`: Sync automatically after new mnemonics are written, instead of reminding you to sync. Default `false`.
- `claude_api_key`: Your Anthropic API key, from https://console.anthropic.com. If empty, the add-on uses the `ANTHROPIC_API_KEY` environment variable.
- `claude_model`: The Claude model that writes mnemonics. Default `"claude-opus-5-5"`. Each mnemonic is one short request with a flag image.
- `use_mock_api`: For development. When `true`, no API calls are made and every mnemonic is a placeholder starting with `[mock]`. Default `false`.
- `huggingface_api_key`: Your Hugging Face access token, from https://huggingface.co/settings/tokens. Only needed when `images_enabled` is `true`. If empty, the add-on uses the `HF_TOKEN` environment variable.

Your keys are stored only in this add-on's settings on this computer. They are never written to your cards and never synced.
