"""Typed access to the add-on config.

Pure Python with no Anki imports, so it can be tested and reused outside Anki.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

STORAGE_MODES = ("field", "overlay")


@dataclass(frozen=True)
class FieldNames:
    country: str = "Country"
    flag: str = "Flag"
    flag_similarity: str = "Flag similarity"
    mnemonic: str = "Mnemonic"


@dataclass(frozen=True)
class Settings:
    theme: str = "Seinfeld"
    lapse_threshold: int = 3
    deck_name: str = "Ultimate Geography"
    note_type: str = "Ultimate Geography"
    fields: FieldNames = field(default_factory=FieldNames)
    flag_card_templates: tuple[str, ...] = ("Flag - Country", "Country - Flag")
    storage_mode: str = "field"
    images_enabled: bool = False
    catch_up_on_startup: bool = True
    catch_up_after_sync: bool = True
    auto_sync_after_generation: bool = False
    claude_api_key: str = ""
    huggingface_api_key: str = ""

    @classmethod
    def from_config(cls, raw: Mapping[str, Any] | None) -> "Settings":
        """Build settings from Anki's config dict, falling back to defaults."""
        raw = dict(raw or {})
        defaults = cls()
        fields_raw = raw.get("fields") or {}
        default_fields = FieldNames()
        fields = FieldNames(
            **{
                name: str(fields_raw.get(name, getattr(default_fields, name)))
                for name in FieldNames.__dataclass_fields__
            }
        )

        storage_mode = str(raw.get("storage_mode", defaults.storage_mode))
        if storage_mode not in STORAGE_MODES:
            storage_mode = defaults.storage_mode

        try:
            threshold = max(1, int(raw.get("lapse_threshold", defaults.lapse_threshold)))
        except (TypeError, ValueError):
            threshold = defaults.lapse_threshold

        templates = raw.get("flag_card_templates", defaults.flag_card_templates)
        if isinstance(templates, str):
            templates = [templates]

        return cls(
            theme=str(raw.get("theme") or defaults.theme),
            lapse_threshold=threshold,
            deck_name=str(raw.get("deck_name", defaults.deck_name)),
            note_type=str(raw.get("note_type", defaults.note_type)),
            fields=fields,
            flag_card_templates=tuple(str(t) for t in templates),
            storage_mode=storage_mode,
            images_enabled=bool(raw.get("images_enabled", defaults.images_enabled)),
            catch_up_on_startup=bool(raw.get("catch_up_on_startup", defaults.catch_up_on_startup)),
            catch_up_after_sync=bool(raw.get("catch_up_after_sync", defaults.catch_up_after_sync)),
            auto_sync_after_generation=bool(
                raw.get("auto_sync_after_generation", defaults.auto_sync_after_generation)
            ),
            claude_api_key=str(raw.get("claude_api_key") or ""),
            huggingface_api_key=str(raw.get("huggingface_api_key") or ""),
        )

    def resolved_claude_key(self) -> str:
        return self.claude_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def resolved_hf_key(self) -> str:
        return self.huggingface_api_key or os.environ.get("HF_TOKEN", "")

    def summary(self) -> str:
        """Short human-readable summary, used by the Hello menu item."""
        claude = "set" if self.resolved_claude_key() else "missing"
        hf = "set" if self.resolved_hf_key() else "missing"
        return "\n".join(
            [
                f"Theme: {self.theme}",
                f"Lapse threshold: {self.lapse_threshold}",
                f"Deck: {self.deck_name}",
                f"Note type: {self.note_type}",
                f"Flag card templates: {', '.join(self.flag_card_templates)}",
                f"Storage mode: {self.storage_mode}",
                f"Images: {'on' if self.images_enabled else 'off'}",
                f"Claude API key: {claude}",
                f"Hugging Face key: {hf}",
            ]
        )
