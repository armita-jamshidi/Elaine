---
title: Flag Mnemonics
emoji: 🥨
colorFrom: yellow
colorTo: red
sdk: gradio
sdk_version: 6.31.0
app_file: app.py
pinned: false
short_description: Themed mnemonics for look-alike flags (Seinfeld by default)
---

# 🥨 Flag Mnemonics

Pick a flag you keep mixing up (Poland, Indonesia or Monaco? Chad or Romania?) and get a one-to-three-sentence mnemonic, themed on a show you know, that encodes what the flag actually looks like and what sets it apart from its look-alikes.

This is a demo of the [Flag Mnemonics Anki add-on](https://github.com/armita-jamshidi/yada-yada-flags), which writes these automatically for the flags you keep forgetting in the Ultimate Geography deck and syncs them to AnkiMobile and AnkiDroid.

## Who writes the mnemonic

- **Free open model** (default): [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) through Hugging Face Inference Providers, paid for by this Space. Limited to a few per visitor per day, and a daily cap for the whole Space.
- **Your own Claude API key**: paste it to use Claude instead. It's sent to Anthropic for that one request only. It isn't stored or logged, and doesn't count against the free limit. This Space has no Claude key of its own.

Both use the same prompt as the add-on: encode the real colors and layout, name the detail that tells look-alikes apart, only cite real episodes, and keep it to three sentences.

## Credits

- Flags: simple stripe flags drawn for this demo from their layouts (national flag designs are in the public domain; colors approximate). No images from Ultimate Geography or elsewhere are used. Look-alike notes were written for this demo.
- Mnemonics: Claude (Anthropic) or Qwen2.5-VL (Alibaba Qwen team, Apache 2.0).
- Not affiliated with Seinfeld or its makers. Mnemonics are AI-written and can be wrong.
