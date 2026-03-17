from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_NAME, CONF_SOURCES, DOMAIN

# ── Slot helpers (UI-only, not persisted) ─────────────────────────────────────

_NUM_SLOTS = 8
_SLOT_KEYS = [f"slot_{i}" for i in range(1, _NUM_SLOTS + 1)]
_NONE = ""


def _providers_to_slots(providers: list[str]) -> dict[str, str]:
    """Ordered source list → slot form fields."""
    return {
        key: (providers[i] if i < len(providers) else _NONE)
        for i, key in enumerate(_SLOT_KEYS)
    }


def _slots_to_providers(form_data: dict) -> list[str]:
    """Slot form fields → ordered source list (empties and duplicates dropped)."""
    seen: set[str] = set()
    result: list[str] = []
    for key in _SLOT_KEYS:
        val = form_data.get(key, _NONE)
        if val and val not in seen:
            seen.add(val)
            result.append(val)
    return result


# ── Config flow ───────────────────────────────────────────────────────────────


class CombinedMediaPlayerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input.get(CONF_NAME, "").strip()
            sources = user_input.get(CONF_SOURCES) or []

            if not name:
                errors[CONF_NAME] = "name_required"
            elif not sources:
                errors[CONF_SOURCES] = "sources_required"
            else:
                await self.async_set_unique_id(
                    f"combined_{name.lower().replace(' ', '_')}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_SOURCES: list(sources),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_SOURCES): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="media_player",
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "CombinedMediaPlayerOptionsFlow":
        return CombinedMediaPlayerOptionsFlow()


# ── Options flow ──────────────────────────────────────────────────────────────


class CombinedMediaPlayerOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            new_name = user_input.get(CONF_NAME, "").strip()
            if not new_name:
                errors[CONF_NAME] = "name_required"
            else:
                sources = _slots_to_providers(user_input)
                if not sources:
                    errors["base"] = "sources_required"
                else:
                    if new_name != self.config_entry.title:
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, title=new_name
                        )
                    return self.async_create_entry(
                        title="",
                        data={CONF_NAME: new_name, CONF_SOURCES: sources},
                    )

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_schema(user_input),
            errors=errors,
        )

    def _build_schema(self, prefill: dict | None = None) -> vol.Schema:
        current_name = (
            prefill.get(CONF_NAME)
            if prefill
            else (
                self.config_entry.options.get(CONF_NAME)
                or self.config_entry.data.get(CONF_NAME, "")
            )
        )
        current_sources = list(
            self.config_entry.options.get(CONF_SOURCES)
            or self.config_entry.data.get(CONF_SOURCES, [])
        )

        # Slot values: restore from prefill (after validation error) or from saved sources
        if prefill is not None:
            slots = {key: prefill.get(key, _NONE) for key in _SLOT_KEYS}
        else:
            slots = _providers_to_slots(current_sources)

        # Build dropdown options: "—" + all media_player entities (sorted by name)
        entity_options: list[selector.SelectOptionDict] = [
            selector.SelectOptionDict(value=_NONE, label="—")
        ] + [
            selector.SelectOptionDict(
                value=state.entity_id,
                label=state.attributes.get("friendly_name") or state.entity_id,
            )
            for state in sorted(
                self.hass.states.async_all("media_player"),
                key=lambda s: (s.attributes.get("friendly_name") or s.entity_id).lower(),
            )
        ]

        slot_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=entity_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        return vol.Schema(
            {
                vol.Required(CONF_NAME, default=current_name): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                **{
                    vol.Optional(key, default=slots[key]): slot_selector
                    for key in _SLOT_KEYS
                },
            }
        )
